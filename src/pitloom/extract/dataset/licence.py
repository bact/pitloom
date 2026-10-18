# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one mapping from a dataset source's licence to
:attr:`~pitloom.core.dataset_metadata.DatasetMetadata.license` and its
provenance, for every dataset reader (Croissant, a local dataset card, a Hub
dataset card), so the weak-value list and the wording cannot drift.

- An SPDX expression or any other text is kept as read (stripped).
- Absent, blank, ``unknown`` or ``NOASSERTION`` (any case): no licence; a
  placeholder is not a claim.
- ``other`` (any case): the source's ``license_name`` and ``license_link``,
  name first, as one text; neither: no licence.

See also: :mod:`pitloom.assemble.spdx3.dataset` (the writer) and
:func:`~pitloom.extract._license_classify.is_weak_licence` (the weak values).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pitloom.extract._license_classify import is_weak_licence
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

__all__ = [
    "LICENSE_FIELD",
    "LICENSE_LINK_FIELD",
    "LICENSE_NAME_FIELD",
    "NOT_TEXT_WARNING",
    "DatasetLicence",
    "dataset_licence",
    "stated_text",
]

#: The source fields a licence is read from (Croissant has only the first).
LICENSE_FIELD = "license"
LICENSE_NAME_FIELD = "license_name"
LICENSE_LINK_FIELD = "license_link"

#: The value that defers to :data:`LICENSE_NAME_FIELD` and
#: :data:`LICENSE_LINK_FIELD` (Hugging Face card convention).
_OTHER = "other"

#: ``log.warning()`` format for a dataset field holding no text.
#: Arguments: the source, the field, the value's type name.
NOT_TEXT_WARNING = "dataset metadata: %s field %s is of type %s, not text; skipped"


@dataclass(frozen=True)
class DatasetLicence:
    """A dataset licence as its source states it."""

    #: The licence text for ``DatasetMetadata.license``.
    text: str
    #: Its ``provenance["license"]`` entry.
    provenance: str


def stated_text(value: object, source: str, field: str) -> str | None:
    """*value*, a source's *field*, as stripped text: a string, the one
    string of a one-item list, or the ``@id`` of a JSON-LD node reference.
    ``None`` when absent or blank, silently; for any other shape (a number,
    a mapping, several items) also ``None``, with one ``WARNING:``."""
    found = value
    if isinstance(found, list) and len(found) == 1:
        found = found[0]
    if isinstance(found, dict) and isinstance(found.get("@id"), str):
        found = found["@id"]
    if value is None or value == []:
        return None
    if not isinstance(found, str):
        log.warning(NOT_TEXT_WARNING, loggable(source), field, type(value).__name__)
        return None
    return found.strip() or None


def _named_text(name: object, link: object, where: str) -> tuple[str, list[str]]:
    """The text of an ``other`` licence, its name then its link, and the
    fields it came from; ``("", [])`` when the source gives neither."""
    parts: list[tuple[str, str]] = []
    for field, value in ((LICENSE_NAME_FIELD, name), (LICENSE_LINK_FIELD, link)):
        text = stated_text(value, where, field)
        if text and not is_weak_licence(text):
            parts.append((field, text))
    if len(parts) == 2:
        return f"{parts[0][1]} ({parts[1][1]})", [f for f, _ in parts]
    return (parts[0][1], [parts[0][0]]) if parts else ("", [])


def dataset_licence(
    value: object,
    *,
    source: str,
    name: object = None,
    link: object = None,
    field_prefix: str = "",
    where: str | None = None,
) -> DatasetLicence | None:
    """The licence a dataset source states in its ``license`` *value*, with
    ``license_name`` *name* and ``license_link`` *link* where the source has
    them; *source* names it in the provenance (``Source: <source> | Field:
    <field_prefix>license``), *where* (default *source*) in a warning.
    ``None`` when it states none (see the module rules)."""
    shown = source if where is None else where
    text = stated_text(value, shown, LICENSE_FIELD)
    if text is None or is_weak_licence(text):
        return None
    fields = [LICENSE_FIELD]
    if text.lower() == _OTHER:
        text, named = _named_text(name, link, shown)
        if not text:
            return None
        fields += named
    return DatasetLicence(
        text, f"Source: {source} | Field: {field_prefix}{', '.join(fields)}"
    )
