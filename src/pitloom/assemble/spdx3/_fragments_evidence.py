# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``not_measured`` provenance entry that a merge made untrue.

A source that could not read a fact (a dataset over the hash ceiling) records
no value and a provenance entry ``Evidence: not_measured``. When a fragment
merge gives the element that value, the entry no longer holds: it goes from
every ``fields`` provenance Annotation of the element and from its comment,
with one ``INFO:`` per entry. An element still without the value keeps it.
The rule reads the merged graph only, so the order of the fold does not
matter.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` (the caller),
:mod:`pitloom.assemble.spdx3._fragments_model_names` (the drop helpers) and
:mod:`pitloom.core.evidence` (the levels).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Final

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_model_names import (
    drop_annotation_provenance,
    drop_comment_provenance,
)
from pitloom.assemble.spdx3._fragments_props import _is_empty
from pitloom.assemble.spdx3._fragments_refs import _endpoint_id
from pitloom.core.evidence import NOT_MEASURED
from pitloom.export.spdx3_describe import describe_element
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

#: Provenance field -> the property (binding name) holding its value.
MEASURED_PROPERTIES: Final[dict[str, str]] = {
    # The hash provenance field (``POINTER_PROVENANCE_FIELD``, the file
    # entries of ``_document_files``).
    "verified_using": "verifiedUsing",
    # ``DatasetMetadata.byte_size``, written by ``dataset.set_dataset_fields``.
    "byte_size": "dataset_datasetSize",
}

#: ``log.info()`` format for a dropped entry. Arguments: the property, the
#: element (type, id and name), the provenance field.
NOT_MEASURED_DROPPED_INFO = (
    "Merge: %r on %s: keeping the merged value, dropping the not_measured "
    "provenance of %r."
)


def _candidate_annotations(
    objects: Iterable[spdx3.SHACLObject],
) -> dict[str, list[spdx3.Annotation]]:
    """The Annotations that may hold a ``not_measured`` entry, by subject id
    (a cheap text probe; the drop helpers parse them)."""
    by_subject: dict[str, list[spdx3.Annotation]] = {}
    for obj in objects:
        if isinstance(obj, spdx3.Annotation) and NOT_MEASURED in (obj.statement or ""):
            by_subject.setdefault(str(_endpoint_id(obj.subject)), []).append(obj)
    return by_subject


def _drop_from_comment(element: spdx3.Element, field_name: str) -> bool:
    """Drop *field_name*'s ``not_measured`` entry from *element*'s comment;
    True when there was one."""
    comment = element.comment
    if NOT_MEASURED not in (comment or ""):
        return False
    kept = drop_comment_provenance(comment, field_name, evidence=NOT_MEASURED)
    if kept == comment:
        return False
    if kept is None:
        del element.comment  # the binding takes no None
    else:
        element.comment = kept
    return True


def drop_superseded_absences(exporter: Spdx3JsonExporter) -> None:
    """Drop each ``not_measured`` provenance entry whose element now holds
    the value (:data:`MEASURED_PROPERTIES`), after the last fragment."""
    objects = exporter.object_set.objects
    annotations = _candidate_annotations(objects)
    elements = [
        obj
        for obj in objects
        if isinstance(obj, spdx3.Element)
        and obj.spdxId
        and not isinstance(obj, spdx3.Annotation)
    ]
    for element in sorted(elements, key=lambda e: str(e.spdxId)):
        spdx_id = str(element.spdxId)
        for field_name, pyname in MEASURED_PROPERTIES.items():
            if _is_empty(getattr(element, pyname, None)):
                continue
            from_annotations = drop_annotation_provenance(
                exporter,
                annotations.get(spdx_id, ()),
                spdx_id,
                field_name,
                evidence=NOT_MEASURED,
            )
            if _drop_from_comment(element, field_name) or from_annotations:
                log.info(
                    NOT_MEASURED_DROPPED_INFO,
                    pyname,
                    describe_element(
                        type(element).__name__, loggable(spdx_id), element.name
                    ),
                    field_name,
                )
