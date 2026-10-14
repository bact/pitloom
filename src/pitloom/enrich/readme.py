# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Local README/model-card YAML frontmatter enrichment.

Deliberately narrow: parses only the leading ``---\\n...\\n---`` YAML
frontmatter block -- the de facto convention Hugging Face model cards
popularized, already handled for *remote* HF models by
:func:`pitloom.extract.remote.huggingface_fetch._load_model_card`. This module closes
the equivalent gap for a *local* model file sitting next to a local
``README.md``/``MODEL_CARD.md``, which no local-format extractor in
:mod:`pitloom.extract.ai_model` (``gguf``, ``safetensors``, ...) reads.

Not prose parsing -- no NLP, no regex-hunting through free text. Only
structured YAML frontmatter fields are read, which keeps this
deterministic and easy to unit test. A card is read up to
:data:`MODEL_CARD_MAX_BYTES`, not confined to the model's directory: a
Hugging Face cache ``snapshots/<rev>/README.md`` is a symlink into
``blobs/``. See
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
from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.enrich.base import EnrichedField, EnrichmentResult
from pitloom.logging_config import (
    LONE_SURROGATES_WARNING,
    Cap,
    field_loss_suffix,
    loggable,
    one_line,
    warn_over_cap,
)

log = logging.getLogger(__name__)

#: Candidate model-card filenames, in priority order. Matched
#: case-insensitively against what's actually on disk, same convention as
#: ``_license.py``'s ``_LICENSE_STEMS``.
_MODEL_CARD_STEMS = ("README.md", "MODEL_CARD.md")

#: The most bytes of a model card read. Only its leading YAML frontmatter
#: is used; a Hugging Face card is some KiB to a few hundred (a long
#: ``model-index`` of evaluation results included), so 1 MiB holds any
#: real frontmatter while a crafted multi-gigabyte card is never read whole.
MODEL_CARD_MAX_BYTES = 1024 * 1024
#: :data:`MODEL_CARD_MAX_BYTES` as :func:`~pitloom.logging_config.warn_over_cap`
#: names it, once per card and process (each model in a directory reads it).
MODEL_CARD_CAP = Cap(MODEL_CARD_MAX_BYTES, "byte", "model-card")
#: What a warning of this module says is lost.
_FIELDS_SKIPPED = field_loss_suffix("skipped", "license", "datasets")


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


def _frontmatter_block(text: str) -> str | None:
    """The text between *text*'s leading ``---`` and the next ``---``, or
    ``None`` when it does not start with one or it is not closed."""
    parts = text.split("---", 2) if text.startswith("---") else []
    return parts[1] if len(parts) == 3 else None


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Return the leading ``---\\n...\\n---`` YAML block as a dict, or
    ``None`` when absent, malformed, or not a mapping at the top level."""
    block = _frontmatter_block(text)
    if block is None:
        return None
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        msg = "Failed to parse model-card frontmatter: %s" + _FIELDS_SKIPPED
        log.warning(msg, one_line(exc))
        return None
    return data if isinstance(data, dict) else None


def _read_card(card_path: Path) -> str | None:
    """*card_path*'s text, its first :data:`MODEL_CARD_MAX_BYTES` (one byte
    past them read, never the rest); ``None``, with a ``WARNING:``, when it
    cannot be read or is over the cap with a frontmatter not closed within
    it. A frontmatter closed within the cap is the one the whole card holds,
    and a card not starting with one holds none, so neither warns."""
    try:
        with card_path.open("rb") as fh:
            raw = fh.read(MODEL_CARD_MAX_BYTES + 1)
    except OSError as exc:
        msg = "Failed to read model card %s: %s" + _FIELDS_SKIPPED
        log.warning(msg, loggable(str(card_path)), one_line(exc))
        return None
    text = raw[:MODEL_CARD_MAX_BYTES].decode("utf-8", errors="replace")
    over = len(raw) > MODEL_CARD_MAX_BYTES
    if over and text.startswith("---") and _frontmatter_block(text) is None:
        outcome = "frontmatter not closed within it; skipped" + _FIELDS_SKIPPED
        warn_over_cap(log, MODEL_CARD_CAP, str(card_path), outcome, once=True)
        return None
    return text


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

        text = _read_card(card_path)
        frontmatter = None if text is None else _parse_frontmatter(text)
        if frontmatter is None:
            return EnrichmentResult(source_name=self.name)
        # Only the two keys read below, and only their strings: YAML aliases
        # make the whole frontmatter an expanded tree of exponential size (or
        # a cycle). A "\ud800" in YAML is a lone surrogate no output can hold.
        license_value = frontmatter.get("license")
        datasets_value = frontmatter.get("datasets")
        read = {
            "license": license_value if isinstance(license_value, str) else None,
            "datasets": (
                [e for e in datasets_value if isinstance(e, str)]
                if isinstance(datasets_value, list)
                else None
            ),
        }
        read, lone = escape_lone_surrogates_in(read)
        if lone:
            log.warning(LONE_SURROGATES_WARNING, "", loggable(str(card_path)))
        license_value, datasets_value = read["license"], read["datasets"]

        source = f"Source: {card_path.name} | Method: yaml_frontmatter"
        changed: list[EnrichedField] = []

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
                    # The card is the model's own statement of its licence.
                    role="declared",
                    source=source,
                )
            )
            model.license = license_value.strip()
            model.provenance["license"] = source

        if isinstance(datasets_value, list):
            existing_names = {
                ref.metadata.name for ref in model.datasets if ref.metadata.name
            }
            for entry in datasets_value:
                if not entry.strip():  # non-strings were dropped above
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
