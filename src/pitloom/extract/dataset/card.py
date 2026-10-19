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
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.enrich.readme import DATASET_CARD, find_card_file, read_card_frontmatter
from pitloom.extract.dataset.licence import (
    LICENSE_FIELD,
    LICENSE_LINK_FIELD,
    LICENSE_NAME_FIELD,
    apply_dataset_licence,
    dataset_licence,
)
from pitloom.extract.dataset.values import stated_text, stated_texts, stated_version
from pitloom.logging_config import LONE_SURROGATES_WARNING, loggable

log = logging.getLogger(__name__)

__all__ = ["card_tags", "read_dataset_card"]

_TEXT_KEYS = (LICENSE_FIELD, LICENSE_NAME_FIELD, LICENSE_LINK_FIELD, "pretty_name")


def card_tags(value: Any, source: str) -> list[str]:
    """A card's ``tags``: its texts, stripped and once each, in order (a
    single string is one tag); items of no text are left out, with one
    ``WARNING:`` naming *source*
    (:func:`~pitloom.extract.dataset.values.stated_texts`)."""
    return list(dict.fromkeys(stated_texts(value, source, "tags", split=False)))


def read_dataset_card(
    directory: Path, *, label: str | None = None
) -> DatasetMetadata | None:
    """The metadata the dataset card in *directory* states, or ``None``
    when it has no card or no frontmatter. Named by its ``pretty_name``,
    else by *directory*'s name; each field read is recorded in
    ``provenance`` (``Source: <label>/README.md | Field: <key>``, *label*
    by default *directory* as given)."""
    card = find_card_file(directory, DATASET_CARD)
    frontmatter = None if card is None else read_card_frontmatter(card, DATASET_CARD)
    if card is None or frontmatter is None:
        return None
    base: PurePath = directory if label is None else PurePosixPath(label)
    source = (base / card.name).as_posix()
    read = {key: frontmatter.get(key) for key in (*_TEXT_KEYS, "version")}
    tags = card_tags(frontmatter.get("tags"), source)

    provenance: dict[str, str] = {}
    pretty_name = stated_text(read["pretty_name"], source, "pretty_name")
    if pretty_name:
        provenance["name"] = f"Source: {source} | Field: pretty_name"
    licence = dataset_licence(
        read[LICENSE_FIELD],
        source=source,
        name=read[LICENSE_NAME_FIELD],
        link=read[LICENSE_LINK_FIELD],
        lister="dataset card",
    )
    if licence is not None:  # set again, in place, by apply_dataset_licence
        provenance["license"] = licence.provenance
    version = stated_version(read["version"], source, numbers=False)
    if version:
        provenance["version"] = f"Source: {source} | Field: version"
    if tags:
        provenance["keywords"] = f"Source: {source} | Field: tags"
    meta = DatasetMetadata(
        name=pretty_name or directory.name,
        version=version,
        keywords=tags,
        provenance=provenance,
    )
    apply_dataset_licence(meta, licence)
    # Only what was read is walked, never the rest of the frontmatter.
    if escape_lone_surrogates_in(meta)[1]:
        log.warning(LONE_SURROGATES_WARNING, "", loggable(source))
    return meta
