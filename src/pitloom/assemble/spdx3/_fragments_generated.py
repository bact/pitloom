# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A value Pitloom generated for a base model, which a fragment replaces.

A base ``ai_AIPackage`` (the project SBOM a project build, the Hatchling hook
or ``embed-wheel --project-dir`` merges into) may carry a value Pitloom made
from the model file's own format, not read from it: the description of a
CRFsuite model built from its labels, the domain of a fastText model derived
from its type. Its provenance says so (``Method: generated_from_labels``,
``Method: derived_from_format``). A fragment's different value for that
property replaces it, with one ``INFO:`` per property, and the property's
provenance is dropped. Any other conflict is the plain field merge: the base's
value is kept and the fragment's dropped with a ``Merge: conflicting``
warning.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` (the caller),
:mod:`pitloom.assemble.spdx3._fragments_model_names` (the same for a name) and
:mod:`pitloom.assemble.spdx3._fragments_props` (field merging).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_model_names import (
    drop_annotation_provenance,
    drop_comment_provenance,
)
from pitloom.assemble.spdx3._fragments_props import _differs, _is_empty
from pitloom.assemble.spdx3._fragments_refs import _endpoint_id
from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.assemble.spdx3.provenance import PROVENANCE_COMMENT_PREFIX
from pitloom.core.provenance import (
    GENERATED_METHODS,
    PROVENANCE_PROPERTY_FIELDS,
    parse_provenance_value,
)
from pitloom.export.spdx3_describe import describe_element, describe_value
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

log = logging.getLogger(__name__)

#: ``log.info()`` format for a generated value a fragment replaces. Arguments:
#: the property, the model (type and id), the fragment's value, the replaced one.
GENERATED_VALUE_REPLACED_INFO = (
    "Merge: %r on %s: keeping the fragment's %s, replacing the value generated "
    "from the model file, %s."
)


def _comment_methods(comment: str | None) -> dict[str, str | None]:
    """The ``Method`` of each field of the provenance lines in *comment*."""
    methods: dict[str, str | None] = {}
    for line in (comment or "").split("\n"):
        if not line.startswith(PROVENANCE_COMMENT_PREFIX):
            continue
        for part in line[len(PROVENANCE_COMMENT_PREFIX) :].split("; "):
            name, sep, source = part.partition(": ")
            if sep:
                methods[name] = parse_provenance_value(source).get("method")
    return methods


def _annotation_methods(annotation: spdx3.Annotation) -> dict[str, str | None]:
    """The ``Method`` of each field a Pitloom ``fields`` provenance
    statement of *annotation* names; empty for any other annotation."""
    try:
        statement = json.loads(annotation.statement or "")
    except ValueError:
        return {}
    fields = statement.get("fields") if isinstance(statement, dict) else None
    if not isinstance(fields, dict) or (
        statement.get("schema") != PitloomV1Encoder.schema_url
    ):
        return {}
    return {
        name: entry.get("method") if isinstance(entry, dict) else None
        for name, entry in fields.items()
    }


def _equivalent(old: object, new: object) -> bool:
    """Whether *new* says what *old* does: the same list in another order, or
    the same JSON text in another spelling."""
    if not _differs(old, new):
        return True
    if isinstance(old, (spdx3.ListProxy, list)) and isinstance(
        new, (spdx3.ListProxy, list)
    ):
        return set(old) == set(new)
    if isinstance(old, str) and isinstance(new, str):
        try:
            return bool(json.loads(old) == json.loads(new))
        except ValueError:
            return False
    return False


def generated_properties(methods: dict[str, str | None]) -> frozenset[str]:
    """The properties of a model whose provenance *methods* (field -> method)
    are all generated, from :data:`PROVENANCE_PROPERTY_FIELDS`."""
    generated: set[str] = set()
    for pyname, fields in PROVENANCE_PROPERTY_FIELDS.items():
        present = [methods[name] for name in fields if name in methods]
        if present and all(method in GENERATED_METHODS for method in present):
            generated.add(pyname)
    return frozenset(generated)


class GeneratedValues:
    """The base models of a merge and the properties Pitloom generated."""

    def __init__(
        self, exporter: Spdx3JsonExporter, base: Iterable[spdx3.SHACLObject]
    ) -> None:
        self._exporter = exporter
        #: The (model, field) provenance entries to drop once names are settled.
        self._dropped: list[tuple[spdx3.ai_AIPackage, str]] = []
        objects = list(base)
        annotations = [o for o in objects if isinstance(o, spdx3.Annotation)]
        self._generated: dict[int, set[str]] = {}
        for obj in objects:
            if not isinstance(obj, spdx3.ai_AIPackage) or not obj.spdxId:
                continue
            methods = _comment_methods(obj.comment)
            for annotation in annotations:
                if _endpoint_id(annotation.subject) == str(obj.spdxId):
                    methods.update(_annotation_methods(annotation))
            properties = generated_properties(methods)
            if properties:
                self._generated[id(obj)] = set(properties)

    def replace(
        self, canonical: spdx3.SHACLObject, duplicate: spdx3.SHACLObject
    ) -> None:
        """Give *canonical*, when it is a base model with generated values,
        the value *duplicate* has for each of them that differs."""
        properties = self._generated.get(id(canonical))
        if not properties or not isinstance(canonical, spdx3.ai_AIPackage):
            return
        for pyname in sorted(properties):
            new = getattr(duplicate, pyname, None)
            old = getattr(canonical, pyname, None)
            if _is_empty(new) or _equivalent(old, new):
                continue
            if isinstance(new, (spdx3.ListProxy, list, tuple)):
                new = list(new)
            setattr(canonical, pyname, new)
            properties.discard(pyname)
            if not _is_empty(old):  # nothing was generated for an empty value
                log.info(
                    GENERATED_VALUE_REPLACED_INFO,
                    pyname,
                    describe_element(
                        type(canonical).__name__, require_spdx_id(canonical), None
                    ),
                    describe_value(new),
                    describe_value(old),
                )
            for name in sorted(PROVENANCE_PROPERTY_FIELDS[pyname]):
                self._dropped.append((canonical, name))

    def finish(self) -> None:
        """Drop the provenance of every replaced value, after the names are
        settled (a rename rebuilds the comment of its model)."""
        for package, name in self._dropped:
            comment = drop_comment_provenance(package.comment, name)
            if comment is None:
                del package.comment  # the binding takes no None
            elif comment != package.comment:
                package.comment = comment
            drop_annotation_provenance(self._exporter, require_spdx_id(package), name)
        self._dropped.clear()
