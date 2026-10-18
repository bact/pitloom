# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A local dataset card: the YAML frontmatter of a dataset directory's
``README.md`` (the Hugging Face dataset-card convention).

Read: ``license`` (with ``license_name`` and ``license_link`` for
``other``), ``pretty_name``, ``version`` and ``tags``; nothing is inferred
from the card's prose.

See also: :mod:`pitloom.enrich.readme` (the frontmatter reader, shared with
model cards) and :mod:`pitloom.extract.dataset.licence` (the licence rules).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.enrich.readme import DATASET_CARD, find_card_file, read_card_frontmatter
from pitloom.extract.dataset.licence import (
    LICENSE_FIELD,
    LICENSE_LINK_FIELD,
    LICENSE_NAME_FIELD,
    NOT_TEXT_WARNING,
    dataset_licence,
    stated_text,
)
from pitloom.logging_config import LONE_SURROGATES_WARNING, loggable

log = logging.getLogger(__name__)

__all__ = ["read_dataset_card"]

_TEXT_KEYS = (LICENSE_FIELD, LICENSE_NAME_FIELD, LICENSE_LINK_FIELD, "pretty_name")


def _escape_strings(read: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """*read* with lone surrogates escaped in each value that is a string
    or a list of strings, and whether any was; other values are kept as
    they are and never walked (YAML aliases can make a tree of exponential
    size)."""
    plain = {
        k: v
        for k, v in read.items()
        if isinstance(v, str)
        or (isinstance(v, list) and all(isinstance(i, str) for i in v))
    }
    escaped, lone = escape_lone_surrogates_in(plain)
    return {**read, **escaped}, lone


def _version(value: Any, source: str) -> str | None:
    """A card's ``version``: text, or a whole number as written; a
    float (``1.10`` reads as ``1.1``) or anything else is no version, with
    one ``WARNING:``."""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if value is None or isinstance(value, str):
        return stated_text(value, source, "version")
    log.warning(NOT_TEXT_WARNING, loggable(source), "version", type(value).__name__)
    return None


def _tags(value: Any) -> list[str]:
    """A card's ``tags``: its strings, stripped and once each, in order; a
    single string is one tag."""
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list):
        return []
    tags = (t.strip() for t in items if isinstance(t, str))
    return list(dict.fromkeys(t for t in tags if t))


def read_dataset_card(directory: Path) -> DatasetMetadata | None:
    """The metadata the dataset card in *directory* states, or ``None``
    when it has no card or no frontmatter. Named by its ``pretty_name``,
    else by *directory*'s name; each field read is recorded in
    ``provenance`` (``Source: <directory>/README.md | Field: <key>``)."""
    card = find_card_file(directory, DATASET_CARD)
    frontmatter = None if card is None else read_card_frontmatter(card, DATASET_CARD)
    if card is None or frontmatter is None:
        return None
    source = (directory / card.name).as_posix()
    read = {key: frontmatter.get(key) for key in (*_TEXT_KEYS, "version")}
    read["tags"] = _tags(frontmatter.get("tags"))
    read, lone = _escape_strings(read)
    if lone:
        log.warning(LONE_SURROGATES_WARNING, "", loggable(source))

    provenance: dict[str, str] = {}
    pretty_name = stated_text(read["pretty_name"], source, "pretty_name")
    if pretty_name:
        provenance["name"] = f"Source: {source} | Field: pretty_name"
    licence = dataset_licence(
        read[LICENSE_FIELD],
        source=source,
        name=read[LICENSE_NAME_FIELD],
        link=read[LICENSE_LINK_FIELD],
    )
    if licence is not None:
        provenance["license"] = licence.provenance
    version = _version(read["version"], source)
    if version:
        provenance["version"] = f"Source: {source} | Field: version"
    if read["tags"]:
        provenance["keywords"] = f"Source: {source} | Field: tags"
    return DatasetMetadata(
        name=pretty_name or directory.name,
        version=version,
        license=None if licence is None else licence.text,
        keywords=read["tags"],
        provenance=provenance,
    )
