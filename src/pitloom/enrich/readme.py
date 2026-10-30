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
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import yaml

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.dataset_names import (
    CARD_DATASETS_CAP,
    dataset_key,
    distinct_dataset_names,
)
from pitloom.core.frontmatter import opens_frontmatter, split_frontmatter
from pitloom.core.provenance import provenance_segment, provenance_source
from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.enrich.base import EnrichedField, EnrichmentResult
from pitloom.logging_config import (
    LONE_SURROGATES_WARNING,
    field_loss_suffix,
    loggable,
    one_line,
)
from pitloom.messages import Cap, warn_over_cap

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
#: :data:`MODEL_CARD_MAX_BYTES` as :func:`~pitloom.messages.warn_over_cap`
#: names it, once per card and process (each model in a directory reads it).
MODEL_CARD_CAP = Cap(MODEL_CARD_MAX_BYTES, "byte", "model-card")


@dataclass(frozen=True)
class CardKind:
    """A kind of card with YAML frontmatter, as its warnings name it."""

    #: Candidate filenames, in priority order, matched case-insensitively.
    stems: tuple[str, ...]
    #: The card's name in a warning (``"model card"``).
    label: str
    #: The read cap, named for this kind.
    cap: Cap
    #: What a warning says is lost (:func:`field_loss_suffix`).
    fields_skipped: str


#: A model card: ``license`` and ``datasets`` are read.
MODEL_CARD = CardKind(
    _MODEL_CARD_STEMS,
    "model card",
    MODEL_CARD_CAP,
    field_loss_suffix("skipped", "license", "datasets"),
)
#: A dataset card (Hugging Face convention: the dataset's ``README.md``),
#: read by :mod:`pitloom.extract.dataset.card`.
DATASET_CARD = CardKind(
    ("README.md",),
    "dataset card",
    Cap(MODEL_CARD_MAX_BYTES, "byte", "dataset-card"),
    field_loss_suffix(
        "skipped",
        "license",
        "license_name",
        "license_link",
        "version",
        "tags",
        "pretty_name",
    ),
)


def find_card_file(directory: Path, kind: CardKind = MODEL_CARD) -> Path | None:
    """The first existing *kind* card file in *directory*, or ``None``.
    Of several files spelling one stem in different case (``README.md``,
    ``readme.md``), the one spelt as the stem, else the first by name: the
    same on every file system, whatever order it lists them in."""
    wanted = {stem.lower() for stem in kind.stems}
    try:
        found = sorted(
            (p for p in directory.iterdir() if p.name.lower() in wanted),
            key=lambda p: p.name,
        )
    except OSError:
        return None
    files = [p for p in found if os.path.isfile(p)]
    for stem in kind.stems:
        matches = [p for p in files if p.name.lower() == stem.lower()]
        exact = [p for p in matches if p.name == stem]
        if exact or matches:
            return (exact or matches)[0]
    return None


def _frontmatter_block(text: str) -> str | None:
    """The text between *text*'s leading ``---`` line and the next one, or
    ``None`` when it does not start with one or it is not closed."""
    split = split_frontmatter(text)
    return None if split is None else split[0]


def _find_model_card_file(model_dir: Path) -> Path | None:
    """Return the first existing model-card file in *model_dir*, or ``None``."""
    return find_card_file(model_dir, MODEL_CARD)


def _parse_frontmatter(text: str, kind: CardKind = MODEL_CARD) -> dict[str, Any] | None:
    """Return the leading ``---\\n...\\n---`` YAML block as a dict, or
    ``None`` when absent, malformed, or not a mapping at the top level."""
    block = _frontmatter_block(text)
    if block is None:
        return None
    try:
        data = yaml.safe_load(block)
    # Any failure of the parser on a third party's text is a parse failure:
    # besides YAMLError, PyYAML raises a bare ValueError for an impossible
    # date (2024-02-30) or an integer over Python's digit limit, and deep
    # nesting exhausts the recursion limit.
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        label = kind.label.replace(" ", "-")
        msg = f"Failed to parse {label} frontmatter: %s" + kind.fields_skipped
        log.warning(msg, one_line(exc))
        return None
    return data if isinstance(data, dict) else None


def _read_card(card_path: Path, kind: CardKind, name: str | None) -> str | None:
    """*card_path*'s text, its first :data:`MODEL_CARD_MAX_BYTES` (one byte
    past them read, never the rest), a UTF-8 BOM dropped; ``None``, with a
    ``WARNING:``, when it cannot be read or is over the cap with a
    frontmatter not closed within it. A frontmatter closed within the cap is
    the one the whole card holds, and a card not starting with one holds
    none, so neither warns."""
    shown = str(card_path) if name is None else name
    try:
        with card_path.open("rb") as fh:
            raw = fh.read(MODEL_CARD_MAX_BYTES + 1)
    except OSError as exc:
        msg = f"Failed to read {kind.label} %s: %s" + kind.fields_skipped
        reason = exc if name is None else exc.strerror or type(exc).__name__
        log.warning(msg, loggable(shown), one_line(reason))
        return None
    text = raw[:MODEL_CARD_MAX_BYTES].decode("utf-8-sig", errors="replace")
    over = len(raw) > MODEL_CARD_MAX_BYTES
    if over and opens_frontmatter(text) and _frontmatter_block(text) is None:
        outcome = "frontmatter not closed within it; skipped" + kind.fields_skipped
        warn_over_cap(log, kind.cap, shown, outcome, once=True)
        return None
    return text


def read_card(
    card_path: Path, kind: CardKind = MODEL_CARD, *, name: str | None = None
) -> tuple[str, dict[str, Any] | None] | None:
    """The text of the *kind* card at *card_path*, within
    :data:`MODEL_CARD_MAX_BYTES`, and its frontmatter as
    :func:`read_card_frontmatter` gives it; ``None`` when the card cannot
    be read (one ``WARNING:``). A warning names the card by *name* when
    given (a downloaded card's local path is no name for it), else by
    *card_path*, and then gives the failure without a path in it."""
    text = _read_card(card_path, kind, name)
    return None if text is None else (text, _parse_frontmatter(text, kind))


def read_card_frontmatter(
    card_path: Path, kind: CardKind = MODEL_CARD
) -> dict[str, Any] | None:
    """The leading YAML frontmatter of the *kind* card at *card_path*, as a
    mapping; ``None`` when it has none (silently) or it cannot be read or
    parsed (one ``WARNING:``). Read within :data:`MODEL_CARD_MAX_BYTES`.
    A caller reads only the keys it uses, and only their plain values: YAML
    aliases can make the rest an expanded tree of exponential size."""
    read = read_card(card_path, kind)
    return None if read is None else read[1]


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

        frontmatter = read_card_frontmatter(card_path, MODEL_CARD)
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

        source = provenance_segment(
            provenance_source(card_path.name), "Method", "yaml_frontmatter"
        )
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
            existing = {dataset_key(ref.metadata.name) for ref in model.datasets}
            listed = distinct_dataset_names(
                datasets_value, CARD_DATASETS_CAP, str(card_path)
            )
            for dataset_name in listed:
                if dataset_key(dataset_name) in existing:
                    continue
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


__all__ = [
    "DATASET_CARD",
    "MODEL_CARD",
    "CardKind",
    "ReadmeEnricher",
    "find_card_file",
    "read_card",
    "read_card_frontmatter",
]
