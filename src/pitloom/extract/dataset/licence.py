# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one mapping from a dataset source's licence to
:attr:`~pitloom.core.dataset_metadata.DatasetMetadata.license` and its
provenance, for every dataset reader (Croissant, a local dataset card, a Hub
dataset card), so the weak-value list and the wording cannot drift.

- An SPDX expression or any other text is kept as read (stripped).
- Absent, blank, ``unknown``, ``NOASSERTION`` or ``N/A`` (any case): no
  licence; a placeholder is not a claim.
- ``other`` (any case): the source's ``license_name`` and ``license_link``,
  name first, as one text, each left out when it is a placeholder (a name
  of ``other`` too); none left: no licence.
- A list of several: each text by the rules above, in order, once each
  (letter case ignored); an ``other`` among them states nothing of its own
  and is left out. Two or more kept are the first licence and
  :class:`~pitloom.core.dataset_metadata.FurtherLicences`.

See also: :mod:`pitloom.assemble.spdx3.dataset` (the writer) and
:func:`~pitloom.extract._license_classify.is_weak_licence` (the weak values).
"""

from __future__ import annotations

from dataclasses import dataclass

from pitloom.core.dataset_metadata import DatasetMetadata, FurtherLicences
from pitloom.extract._license_classify import is_weak_licence
from pitloom.extract.dataset.values import (
    NOT_TEXT_WARNING,
    is_placeholder,
    stated_text,
    stated_texts,
)

__all__ = [
    "LICENSE_FIELD",
    "LICENSE_LINK_FIELD",
    "LICENSE_NAME_FIELD",
    "NOT_TEXT_WARNING",
    "DatasetLicence",
    "apply_dataset_licence",
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


@dataclass(frozen=True)
class DatasetLicence:
    """A dataset licence as its source states it."""

    #: The licence text for ``DatasetMetadata.license``.
    text: str
    #: Its ``provenance["license"]`` entry.
    provenance: str
    #: The licences the source lists after :attr:`text`, if any.
    further: FurtherLicences | None = None


def _is_weak(text: str) -> bool:
    """Whether *text* is a placeholder, not a licence claim."""
    return is_weak_licence(text) or is_placeholder(text)


def apply_dataset_licence(
    meta: DatasetMetadata, licence: DatasetLicence | None
) -> None:
    """Set on *meta* the licence, further licences and provenance
    *licence* states; nothing when ``None``."""
    if licence is None:
        return
    meta.license = licence.text
    meta.further_licenses = licence.further
    meta.provenance[LICENSE_FIELD] = licence.provenance


def _named_text(name: object, link: object, where: str) -> tuple[str, list[str]]:
    """The text of an ``other`` licence, its name then its link, and the
    fields it came from; ``("", [])`` when the source gives neither."""
    parts: list[tuple[str, str]] = []
    for field, value in ((LICENSE_NAME_FIELD, name), (LICENSE_LINK_FIELD, link)):
        text = stated_text(value, where, field)
        if text and not _is_weak(text) and text.lower() != _OTHER:
            parts.append((field, text))
    if len(parts) == 2:
        return f"{parts[0][1]} ({parts[1][1]})", [f for f, _ in parts]
    return (parts[0][1], [parts[0][0]]) if parts else ("", [])


def _listed_licences(
    value: list[object], where: str, lister: str, provenance: str
) -> DatasetLicence | None:
    """The licences a list of several *value* states (see the module
    rules); *lister* names the source in the several-licences comment."""
    unique: dict[str, str] = {}
    for text in stated_texts(value, where, LICENSE_FIELD, split=False):
        if not _is_weak(text) and text.lower() != _OTHER:
            unique.setdefault(text.lower(), text)
    texts = list(unique.values())
    if not texts:
        return None
    further = FurtherLicences(tuple(texts[1:]), lister) if len(texts) > 1 else None
    return DatasetLicence(texts[0], f"{provenance}{LICENSE_FIELD}", further)


# pylint: disable-next=too-many-arguments
def dataset_licence(
    value: object,
    *,
    source: str,
    name: object = None,
    link: object = None,
    field_prefix: str = "",
    where: str | None = None,
    lister: str = "source",
) -> DatasetLicence | None:
    """The licence a dataset source states in its ``license`` *value*, with
    ``license_name`` *name* and ``license_link`` *link* where the source has
    them; *source* names it in the provenance (``Source: <source> | Field:
    <field_prefix>license``), *where* (default *source*) in a warning,
    *lister* in the comment on several licences (``The <lister> lists
    several licences...``). ``None`` when it states none (see the module
    rules)."""
    shown = source if where is None else where
    if isinstance(value, list) and len(value) > 1:
        return _listed_licences(
            value, shown, lister, f"Source: {source} | Field: {field_prefix}"
        )
    text = stated_text(value, shown, LICENSE_FIELD)
    if text is None or _is_weak(text):
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
