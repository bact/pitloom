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
types, and ``data_preprocessing=`` beats a source's. A Croissant URL is not
read: loom has no network switch.

See also: :mod:`pitloom._loom_dataset` (the package),
:mod:`pitloom.extract.dataset` (the readers) and
:mod:`pitloom.assemble.spdx3.dataset` (the writer).
"""

from __future__ import annotations

import dataclasses
import logging
import os
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._display_text import (
    DATASET,
    DATASET_CREATOR,
    escape_element_display_text,
)
from pitloom.assemble.spdx3.dataset import (
    add_dataset_creator_agent,
    add_dataset_license,
    set_dataset_fields,
    written_provenance,
)
from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract.dataset import read_croissant, read_dataset_card
from pitloom.logging_config import loggable

log = logging.getLogger("pitloom.loom")

__all__ = [
    "CONTROL_CHARACTERS_WARNING",
    "CROISSANT_URL_ERROR",
    "DatasetDoc",
    "escape_display_text",
    "merge_metadata",
    "read_sources",
    "write_metadata",
]

#: ``ValueError`` text for a ``croissant=`` URL. Argument: the URL.
CROISSANT_URL_ERROR = "loom: croissant=%r is a URL; only a local file is read"

#: ``log.warning()`` format for display text escaped in a dataset's
#: elements. Arguments: the dataset's name, the properties changed.
CONTROL_CHARACTERS_WARNING = (
    "loom: dataset %r: invisible or bidi control characters written as \\uXXXX in %s"
)

#: Fields the loom call itself sets: never taken from a source.
_DECLARED_FIELDS = frozenset({"name", "dataset_types", "provenance"})


@dataclasses.dataclass(frozen=True)
class DatasetDoc:
    """The document a loom dataset's metadata is written into."""

    exporter: Spdx3JsonExporter
    creation_info: spdx3.CreationInfo
    doc_uuid: str
    provenance_config: ProvenanceConfig


def _cwd_relative(location: str) -> str:
    """*location* as a POSIX path from the current directory when it is
    below it (the provenance a source records then does not depend on where
    the project lies), else as given."""
    absolute = Path(os.path.normpath(os.path.abspath(location)))
    try:
        return absolute.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return Path(location).as_posix()


def read_sources(
    name: str,
    *,
    croissant: str | os.PathLike[str] | None,
    declared_license: str | None,
    caller_info: str,
) -> DatasetMetadata | None:
    """The metadata the sources of the loom dataset *name* state, merged
    (:func:`merge_metadata`); ``None`` when none states anything.

    Raises:
        ValueError: *croissant* is a URL, or cannot be read as Croissant.
    """
    sources: list[DatasetMetadata] = []
    if declared_license and declared_license.strip():
        provenance = {"license": f"{caller_info} | Field: declared_license"}
        sources.append(
            DatasetMetadata(name, license=declared_license, provenance=provenance)
        )
    if croissant is not None:
        location = os.fspath(croissant)
        if location.startswith(("http://", "https://")):
            raise ValueError(CROISSANT_URL_ERROR % location)
        sources.append(read_croissant(_cwd_relative(location)))
    if os.path.isdir(name):
        card = read_dataset_card(Path(_cwd_relative(name)))
        if card is not None:
            sources.append(card)
    return merge_metadata(name, sources)


def _states(value: object) -> bool:
    """Whether a field's *value* states something (not absent or empty)."""
    return value is not None and value != [] and value != ""


def merge_metadata(name: str, sources: list[DatasetMetadata]) -> DatasetMetadata | None:
    """One :class:`DatasetMetadata` named *name*: each field from the first
    of *sources* stating it, with that source's provenance; ``None`` when
    none states any field."""
    merged = DatasetMetadata(name)
    stated = False
    for field in dataclasses.fields(DatasetMetadata):
        if field.name in _DECLARED_FIELDS:
            continue
        for source in sources:
            value = getattr(source, field.name)
            if _states(value):
                setattr(merged, field.name, value)
                if field.name in source.provenance:
                    merged.provenance[field.name] = source.provenance[field.name]
                stated = True
                break
    return merged if stated else None


def write_metadata(
    package: spdx3.dataset_DatasetPackage,
    meta: DatasetMetadata,
    doc: DatasetDoc,
) -> tuple[dict[str, str], list[tuple[str, spdx3.Element]]]:
    """Write *meta* onto *package* (its fields, a ``publishedBy`` creator,
    a declared licence); return the provenance of what was written, for the
    package's one provenance record, and the elements holding the sources'
    text, labelled for :func:`escape_display_text`. A
    ``data_preprocessing`` already on *package* (declared on the call) is
    kept. Keywords are not written: an SPDX 3.0.1 dataset has no such
    property."""
    meta = dataclasses.replace(meta, provenance=written_provenance(meta))
    meta.name = str(package.name)
    if package.dataset_dataPreprocessing:
        meta.data_preprocessing = []
        meta.provenance.pop("data_preprocessing", None)
    set_dataset_fields(package, meta)
    elements: list[tuple[str, spdx3.Element]] = [(DATASET, package)]
    context = (doc.creation_info, "loom", doc.doc_uuid)
    if meta.creator:
        agent = add_dataset_creator_agent(
            require_spdx_id(package), meta.creator, *context, doc.exporter
        )
        elements.append((DATASET_CREATOR, agent))
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
