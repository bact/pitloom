# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Local README/model-card YAML frontmatter enrichment.

Deliberately narrow: parses only the leading ``---\\n...\\n---`` YAML
frontmatter block -- the de facto convention Hugging Face model cards
popularized, already handled for *remote* HF models by
:func:`pitloom.extract._huggingface_fetch._load_model_card`. This module closes
the equivalent gap for a *local* model file sitting next to a local
``README.md``/``MODEL_CARD.md``, which no local-format extractor
(``_gguf.py``, ``_safetensors.py``, ...) ever reads.

Not prose parsing -- no NLP, no regex-hunting through free text. Only
structured YAML frontmatter fields are read, which keeps this
deterministic and easy to unit test. See
``working-docs/design/sbom-enrichment.md`` for the broader enrichment
design this is one piece of.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

import yaml

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.enrich.base import EnrichedField, EnrichmentResult

log = logging.getLogger(__name__)

#: Candidate model-card filenames, in priority order. Matched
#: case-insensitively against what's actually on disk, same convention as
#: ``_license.py``'s ``_LICENSE_STEMS``.
_MODEL_CARD_STEMS = ("README.md", "MODEL_CARD.md")


def _find_model_card_file(model_dir: Path) -> Path | None:
    """Return the first existing model-card file in *model_dir*, or ``None``."""
    try:
        actual: dict[str, Path] = {
            p.name.lower(): p for p in model_dir.iterdir() if p.is_file()
        }
    except OSError:
        return None
    for stem in _MODEL_CARD_STEMS:
        found = actual.get(stem.lower())
        if found is not None:
            return found
    return None


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Return the leading ``---\\n...\\n---`` YAML block as a dict, or
    ``None`` when absent, malformed, or not a mapping at the top level."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        log.debug("Failed to parse model-card frontmatter: %s", exc)
        return None
    return data if isinstance(data, dict) else None


# pylint: disable=too-few-public-methods
class ReadmeEnricher:
    """Fills license/dataset gaps from a local model card's YAML frontmatter.

    Gap-filling only: never overwrites a value the model's own extractor
    already populated, same "primary wins" discipline as
    :func:`pitloom.core.project.merge_project_metadata`.
    """

    name: ClassVar[str] = "readme"

    def enrich(self, model: AiModelMetadata, *, model_dir: Path) -> EnrichmentResult:
        card_path = _find_model_card_file(model_dir)
        if card_path is None:
            return EnrichmentResult(source_name=self.name)

        try:
            text = card_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.debug("Failed to read model card %s: %s", card_path, exc)
            return EnrichmentResult(source_name=self.name)

        frontmatter = _parse_frontmatter(text)
        if frontmatter is None:
            return EnrichmentResult(source_name=self.name)

        source = f"Source: {card_path.name} | Method: yaml_frontmatter"
        changed: list[EnrichedField] = []

        license_value = frontmatter.get("license")
        if (
            not model.license
            and isinstance(license_value, str)
            and license_value.strip()
        ):
            changed.append(
                EnrichedField(
                    field="license",
                    before=None,
                    after=license_value.strip(),
                    role="detected",
                    source=source,
                )
            )
            model.license = license_value.strip()
            model.provenance["license"] = source

        datasets_value = frontmatter.get("datasets")
        if isinstance(datasets_value, list):
            existing_names = {
                ref.metadata.name for ref in model.datasets if ref.metadata.name
            }
            for entry in datasets_value:
                if not isinstance(entry, str) or not entry.strip():
                    continue
                dataset_name = entry.strip()
                if dataset_name in existing_names:
                    continue
                existing_names.add(dataset_name)
                changed.append(
                    EnrichedField(
                        field=f"datasets:{dataset_name}",
                        before=None,
                        after=dataset_name,
                        role="detected",
                        source=source,
                    )
                )
                model.datasets.append(
                    DatasetReference(
                        role="trainedOn",
                        metadata=DatasetMetadata(
                            name=dataset_name,
                            provenance={"name": source},
                        ),
                    )
                )

        return EnrichmentResult(source_name=self.name, fields=changed)


__all__ = ["ReadmeEnricher"]
