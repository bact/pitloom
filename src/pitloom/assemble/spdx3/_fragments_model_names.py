# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The name of a base document's AI model that fragments re-declare.

A fragment ``ai_AIPackage`` that folds into one of the base document's
(the project SBOM a project build, the Hatchling hook or ``embed-wheel
--project-dir`` merges into) names the model as the user declared it
(``loom.set_model(name, path=...)``); the base names it from its file. When
every such fragment gives one name, that name is kept, with one ``INFO:``,
and the base's provenance for its own name is dropped. Fragments giving two
names keep the base's, with the usual ``Merge: conflicting`` warning per
other name. A fold into an element a fragment added (``loom merge`` has no
base model) and every other field are plain field merges.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` (the caller) and
:mod:`pitloom.assemble.spdx3._fragments_props` (field merging).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_props import (
    _differs,
    _finish_parameter_count_note,
    _is_empty,
    _merge_comment,
    _merge_scalar,
    _paths_suffix_match,
)
from pitloom.assemble.spdx3._fragments_refs import _endpoint_id
from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.assemble.spdx3.provenance import PROVENANCE_COMMENT_PREFIX
from pitloom.core.canonical_json import canonical_json
from pitloom.core.model_parameters import with_parameter_count_note
from pitloom.core.provenance import escape_provenance_comment_part
from pitloom.export.spdx3_describe import describe_element, describe_value
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

log = logging.getLogger(__name__)

#: ``log.info()`` format for a base model renamed by its fragments.
#: Arguments: the model (type and id), the kept name, the dropped name.
MODEL_NAME_KEPT_INFO = (
    "Merge: 'name' on %s: keeping the fragment's %s, dropping the project's %s."
)

_NAME = "name"
_SKIP_NAME = frozenset({_NAME})


@dataclass
class _BaseModel:
    """A base model and what the fragments folding into it said."""

    package: spdx3.ai_AIPackage
    #: The base's own name and comment (count note dropped), before any fold.
    name: str
    comment: str | None
    #: Every fragment name, in fold order, once each.
    names: dict[str, None] = field(default_factory=dict)
    #: Every fragment comment (count note dropped), in fold order.
    comments: list[str | None] = field(default_factory=list)
    #: Provenance fields of the base to drop (a fragment's value replaces
    #: what they say), in the order given.
    dropped: dict[str, None] = field(default_factory=dict)


def drop_comment_provenance(comment: str | None, field_name: str) -> str | None:
    """*comment* less *field_name*'s entry in each provenance line
    (:func:`~pitloom.assemble.spdx3.provenance.build_provenance_comment`'s
    escaping keeps ``"; "`` a separator); a line left empty goes."""
    entry = escape_provenance_comment_part(field_name, field=True) + ": "
    lines: list[str] = []
    for line in (comment or "").split("\n"):
        if line.startswith(PROVENANCE_COMMENT_PREFIX):
            body = line[len(PROVENANCE_COMMENT_PREFIX) :].split("; ")
            kept = [part for part in body if not part.startswith(entry)]
            if not kept:
                continue
            line = PROVENANCE_COMMENT_PREFIX + "; ".join(kept)
        lines.append(line)
    return "\n".join(lines) or None


def _drop_annotation_field(
    annotation: spdx3.Annotation, field_name: str
) -> spdx3.Annotation | None:
    """*annotation* less *field_name* when it is a ``fields`` provenance
    statement naming it; ``None`` when nothing is left of it."""
    try:
        statement = json.loads(annotation.statement or "")
    except ValueError:
        return annotation
    fields = statement.get("fields") if isinstance(statement, dict) else None
    if (
        not isinstance(fields, dict)
        or field_name not in fields
        or statement.get("schema") != PitloomV1Encoder.schema_url
    ):
        return annotation
    del fields[field_name]
    if not fields:
        return None
    annotation.statement = canonical_json(statement)
    return annotation


def drop_annotation_provenance(
    exporter: Spdx3JsonExporter,
    annotations: Iterable[spdx3.Annotation],
    spdx_id: str,
    field_name: str,
) -> None:
    """Drop *field_name*'s provenance from those of *annotations* that are
    ``fields`` provenance Annotations of *spdx_id*; an Annotation left with
    no field goes."""
    emptied = [
        annotation
        for annotation in annotations
        if _endpoint_id(annotation.subject) == spdx_id
        and _drop_annotation_field(annotation, field_name) is None
    ]
    if emptied:
        object_set = exporter.object_set
        object_set.objects.difference_update(emptied)
        object_set.create_index()


class ModelNames:
    """The base models of a merge and the names fragments give them."""

    def __init__(
        self, exporter: Spdx3JsonExporter, base: Iterable[spdx3.SHACLObject]
    ) -> None:
        self._exporter = exporter
        self._models: dict[int, _BaseModel] = {}
        self._annotations: list[spdx3.Annotation] = []
        for obj in base:
            if isinstance(obj, spdx3.Annotation):
                self._annotations.append(obj)
            elif isinstance(obj, spdx3.ai_AIPackage) and not _is_empty(obj.name):
                self._models[id(obj)] = _BaseModel(
                    obj, str(obj.name), with_parameter_count_note(obj.comment, False)
                )

    def record(
        self, canonical: spdx3.SHACLObject, duplicate: spdx3.SHACLObject
    ) -> frozenset[str]:
        """Note *duplicate*'s name and comment when *canonical* is a base
        model; return the fields the fold must leave to :meth:`finish`."""
        model = self._models.get(id(canonical))
        if model is None or not isinstance(duplicate, spdx3.ai_AIPackage):
            return frozenset()
        if not _is_empty(duplicate.name):
            model.names.setdefault(str(duplicate.name))
        model.comments.append(with_parameter_count_note(duplicate.comment, False))
        return _SKIP_NAME

    def drop_provenance(self, package: spdx3.SHACLObject, field_name: str) -> None:
        """Have :meth:`finish` drop the base's provenance of *field_name* from
        *package* when it is a base model; a fragment's own comment and
        Annotations are never touched."""
        model = self._models.get(id(package))
        if model is not None:
            model.dropped.setdefault(field_name)

    def finish(self) -> None:
        """Settle every base model's name and provenance, after the last
        fragment."""
        models = (m for m in self._models.values() if m.names or m.dropped)
        for model in sorted(models, key=lambda m: require_spdx_id(m.package)):
            fields = list(model.dropped)
            names = list(model.names)
            if len(names) == 1 and _renames(model.name, names[0]):
                self._rename(model, names[0])
                fields.append(_NAME)
            else:
                for name in sorted(names):  # today's field merge, in a fixed order
                    _merge_scalar(model.package, _NAME, model.package.name, name)
            if fields:
                self._drop_provenance(model, fields)

    def _rename(self, model: _BaseModel, name: str) -> None:
        package = model.package
        log.info(
            MODEL_NAME_KEPT_INFO,
            describe_element(type(package).__name__, require_spdx_id(package), None),
            describe_value(name),
            describe_value(model.name),
        )
        package.name = name

    def _drop_provenance(self, model: _BaseModel, fields: list[str]) -> None:
        """Rebuild the comment of *model* from the base comment without the
        provenance of *fields* and from the fragments' comments in fold order,
        and drop *fields* from the base's Annotations."""
        package = model.package
        comment = model.comment
        for field_name in fields:
            comment = drop_comment_provenance(comment, field_name)
        if comment is None:
            del package.comment  # the binding takes no None
        else:
            package.comment = comment
        for fragment_comment in model.comments:
            _merge_comment(package, package.comment, fragment_comment)
        _finish_parameter_count_note(package)
        for field_name in fields:
            drop_annotation_provenance(
                self._exporter,
                self._annotations,
                require_spdx_id(package),
                field_name,
            )


def _renames(base_name: str, fragment_name: str) -> bool:
    """True when *fragment_name* replaces *base_name*: a different name,
    not the same path at another depth."""
    return _differs(base_name, fragment_name) and not _paths_suffix_match(
        base_name, fragment_name
    )
