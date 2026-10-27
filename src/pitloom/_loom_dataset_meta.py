# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a loom dataset's own sources state about it: a licence declared on
the call, a local Croissant file named by ``croissant=``, and the dataset
card (``README.md`` frontmatter) of a directory dataset, in that order,
field by field. Written onto the dataset's package when the run ends,
through the same writer a model's datasets use.

The loom call's own values win: the package keeps the declared name and
types, ``data_preprocessing=`` beats a source's, and a ``declared_license=``
on any declaration of the dataset beats every Croissant file and card (of
two declared licences, the first declaration's). A Croissant URL is not
read: loom has no network switch.

See also: :mod:`pitloom._loom_dataset` (the package),
:mod:`pitloom.extract.dataset` (the readers) and
:mod:`pitloom.assemble.spdx3.dataset` (the writer).
"""

from __future__ import annotations

import dataclasses
import logging
import os
import re
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._loom_caller import cwd_relative_label
from pitloom.assemble.spdx3._display_text import (
    DATASET,
    escape_element_display_text,
)
from pitloom.assemble.spdx3.dataset import (
    add_dataset_creator_agent,
    add_dataset_license,
    set_dataset_fields,
    written_provenance,
)
from pitloom.core.ai_metadata import MODEL_NAME_CAP, cap_model_name
from pitloom.core.dataset_metadata import FOLLOWER_FIELDS, DatasetMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich.readme import DATASET_CARD
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract.dataset import read_croissant, read_dataset_card
from pitloom.extract.dataset.licence import dataset_licence
from pitloom.logging_config import loggable, one_line, warn_over_cap

log = logging.getLogger("pitloom.loom")

__all__ = [
    "CARD_SKIPPED_WARNING",
    "CONTROL_CHARACTERS_WARNING",
    "CROISSANT_URL_ERROR",
    "DECLARED_LICENSE_TYPE_ERROR",
    "DatasetDoc",
    "DatasetSources",
    "escape_display_text",
    "merge_metadata",
    "read_sources",
    "write_metadata",
]

#: ``ValueError`` text for a ``croissant=`` URL. Argument: the URL.
CROISSANT_URL_ERROR = "loom: croissant=%r is a URL; only a local file is read"

#: ``TypeError`` text for a ``declared_license=`` that is not a string.
#: Argument: the value's type name.
DECLARED_LICENSE_TYPE_ERROR = "loom: declared_license must be a str, not %s"

#: ``log.warning()`` format for a dataset card that failed to be read.
#: Arguments: the dataset's name, the error's type name and text.
CARD_SKIPPED_WARNING = "loom: dataset %r: dataset card skipped: %s: %s"

#: ``log.warning()`` format for display text escaped in a dataset's
#: elements. Arguments: the dataset's name, the properties changed.
CONTROL_CHARACTERS_WARNING = (
    "loom: dataset %r: invisible or bidi control characters written as \\uXXXX in %s"
)

#: Fields the loom call itself sets: never taken from a source.
_DECLARED_FIELDS = frozenset({"name", "dataset_types", "provenance"})
#: Fields taken only with the one they follow.
_FOLLOWERS = frozenset(FOLLOWER_FIELDS.values())

#: An ``http``/``https`` URL in any case, also as ``Path`` collapses its
#: ``//`` (``https:/host``), or a Windows ``Path`` writes it.
_URL_RE = re.compile(r"https?:[/\\]", re.IGNORECASE)

#: The licence a caller declares by saying they make no assertion.
_NOASSERTION = "NOASSERTION"


@dataclasses.dataclass(frozen=True)
class DatasetDoc:
    """The document a loom dataset's metadata is written into."""

    exporter: Spdx3JsonExporter
    creation_info: spdx3.CreationInfo
    doc_uuid: str
    provenance_config: ProvenanceConfig


@dataclasses.dataclass
class DatasetSources:
    """What the declarations of one loom dataset state, each list in
    declaration order: what the caller declared (*declared*) and what the
    files read state (*read*). A merge takes every declared one first."""

    declared: list[DatasetMetadata] = dataclasses.field(default_factory=list)
    read: list[DatasetMetadata] = dataclasses.field(default_factory=list)

    def extend(self, later: DatasetSources) -> None:
        """Add what a *later* declaration of the dataset states, after
        what this one holds."""
        self.declared += later.declared
        self.read += later.read

    def merged(self, name: str) -> DatasetMetadata | None:
        """The merged metadata (:func:`merge_metadata`) named *name*."""
        return merge_metadata(name, [*self.declared, *self.read])


def _declared_licence(value: object) -> str | None:
    """The licence the caller's ``declared_license=`` *value* states: their
    own ``NOASSERTION`` (any case) as given; a placeholder (blank,
    ``unknown``, a bare ``other``) none, as from any source.

    Raises:
        TypeError: *value* is not a string.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(DECLARED_LICENSE_TYPE_ERROR % type(value).__name__)
    if value.strip().upper() == _NOASSERTION:
        return value.strip()
    licence = dataset_licence(value, source="declared_license")
    return None if licence is None else licence.text


def read_sources(
    name: str,
    *,
    croissant: str | os.PathLike[str] | None,
    declared_license: str | None,
    caller_info: str,
) -> DatasetSources:
    """What the sources of the loom dataset *name* state, unmerged. Each
    file is opened as given; its provenance names it from the current
    directory (:func:`~pitloom._loom_caller.cwd_relative_label`).

    Raises:
        TypeError: *declared_license* is not a string.
        ValueError: *croissant* is a URL, or cannot be read as Croissant.
    """
    sources = DatasetSources()
    licence = _declared_licence(declared_license)
    if licence is not None:
        provenance = {"license": f"{caller_info} | Field: declared_license"}
        sources.declared.append(
            DatasetMetadata(name, license=licence, provenance=provenance)
        )
    if croissant is not None:
        location = os.fspath(croissant)
        if _URL_RE.match(location):
            raise ValueError(CROISSANT_URL_ERROR % location)
        label = cwd_relative_label(location)
        sources.read.append(read_croissant(location, label=label))
    if os.path.isdir(name):
        card = _optional_card(name)
        if card is not None:
            sources.read.append(card)
    return sources


def _optional_card(name: str) -> DatasetMetadata | None:
    """What the card of the directory dataset *name* states. The caller did
    not name the card: any failure to read it skips it, with one
    ``WARNING:``, and never fails the declaration."""
    try:
        return read_dataset_card(Path(name), label=cwd_relative_label(name))
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        msg = CARD_SKIPPED_WARNING + DATASET_CARD.fields_skipped
        log.warning(
            msg,
            loggable(name),
            type(exc).__name__,
            one_line(exc),
        )
        return None


def _states(value: object) -> bool:
    """Whether a field's *value* states something. A reader leaves a field
    it did not read at its default (``None``, ``[]``), so an empty value
    is not told from an absent one: neither states anything."""
    return value is not None and value != [] and value != ""


def merge_metadata(name: str, sources: list[DatasetMetadata]) -> DatasetMetadata | None:
    """One :class:`DatasetMetadata` named *name*: each field from the first
    of *sources* stating it, with that source's provenance; ``None`` when
    none states any field."""
    merged = DatasetMetadata(name)
    stated = False
    for field in dataclasses.fields(DatasetMetadata):
        if field.name in _DECLARED_FIELDS or field.name in _FOLLOWERS:
            continue
        for source in sources:
            value = getattr(source, field.name)
            if _states(value):
                setattr(merged, field.name, value)
                follower = FOLLOWER_FIELDS.get(field.name)
                if follower:
                    setattr(merged, follower, getattr(source, follower))
                if field.name in source.provenance:
                    merged.provenance[field.name] = source.provenance[field.name]
                stated = True
                break
    return merged if stated else None


def write_metadata(
    package: spdx3.dataset_DatasetPackage,
    meta: DatasetMetadata,
    doc: DatasetDoc,
    *,
    preprocessing_declared: bool = False,
) -> tuple[dict[str, str], list[tuple[str, spdx3.Element]]]:
    """Write *meta* onto *package* (its fields, a ``publishedBy`` creator,
    a declared licence); return the provenance of what was written, for the
    package's one provenance record, and the elements holding the sources'
    text, labelled for :func:`escape_display_text`. With
    *preprocessing_declared* (``data_preprocessing=`` given on the call,
    even ``[]``), *package*'s own is kept. The creator's name is cut as a
    model's is (:func:`~pitloom.core.ai_metadata.cap_model_name`). Keywords
    are not written: an SPDX 3.0.1 dataset has no such property."""
    meta = dataclasses.replace(meta, provenance=written_provenance(meta))
    meta.name = str(package.name)
    if preprocessing_declared:
        meta.data_preprocessing = []
        meta.provenance.pop("data_preprocessing", None)
    set_dataset_fields(package, meta)
    elements: list[tuple[str, spdx3.Element]] = [(DATASET, package)]
    context = (doc.creation_info, "loom", doc.doc_uuid)
    given = str(meta.creator or "").strip()  # a blank creator names no one
    if given:
        creator = cap_model_name(given)
        if creator != given:
            # The name cap, naming the dataset whose creator name it cut.
            cap = dataclasses.replace(MODEL_NAME_CAP, subject="DATASET")
            warn_over_cap(log, cap, meta.name, "dataset creator name cut")
        elements += add_dataset_creator_agent(
            require_spdx_id(package), creator, *context, doc.exporter
        )
    elements += add_dataset_license(
        package, meta, context, doc.exporter, doc.provenance_config
    )
    return meta.provenance, elements


def escape_display_text(name: str, elements: list[tuple[str, spdx3.Element]]) -> None:
    """Escape the invisible and bidi controls in the display text of
    *elements*, written for the dataset *name*, and say once which
    properties had one; quiet when none had."""
    changed = sorted(
        {
            f"{label} {prop}"
            for label, element in elements
            for prop in escape_element_display_text(element)
        }
    )
    if changed:
        log.warning(CONTROL_CHARACTERS_WARNING, loggable(name), ", ".join(changed))
