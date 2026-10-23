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

from pitloom.assemble.spdx3._fragments_model_names import ModelNames
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
from pitloom.export.spdx3_json import require_spdx_id

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
        name: entry.get("method")
        for name, entry in fields.items()
        if isinstance(entry, dict)  # anything else says nothing
    }


class _Float(str):
    """A JSON number with a fraction or an exponent, kept as its text: two
    spellings of it are two values (a float would equate ``1e400`` with
    ``2e999``, or ``0.1`` with ``0.10000000000000000001``)."""


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key")
    return dict(pairs)


def _same(old: object, new: object) -> bool:
    """Whether two parsed JSON values are the same, a number and a boolean
    never (``1`` and ``true``) and a float only as the same text."""
    if type(old) is not type(new):
        return False
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(_same(old[k], new[k]) for k in old)
    if isinstance(old, list) and isinstance(new, list):
        return len(old) == len(new) and all(
            _same(o, n) for o, n in zip(old, new, strict=True)
        )
    return bool(old == new)


#: The deepest nesting of fragment JSON text that is compared. Reading deeper
#: text fails at a depth that depends on the Python version and the call stack
#: (about 1000 on 3.10 and 3.11, more later), so the line is drawn here.
MAX_JSON_DEPTH = 64


def _nests_over(text: str, limit: int) -> bool:
    """Whether the brackets of the JSON *text* nest deeper than *limit*;
    brackets inside a string do not count."""
    if text.count("[") + text.count("{") <= limit:
        return False
    depth = 0
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > limit:
                return True
        elif char in "]}":
            depth -= 1
    return False


def _same_json(old: str, new: str) -> bool:
    """Whether the JSON texts *old* and *new* say the same, in any spelling of
    the whitespace and the order of an object's keys. Text that is no JSON, has
    a repeated key or nests too deeply to read (a fragment is untrusted) is not
    the same as anything but itself."""
    if _nests_over(old, MAX_JSON_DEPTH) or _nests_over(new, MAX_JSON_DEPTH):
        return False
    try:
        return _same(
            *(
                json.loads(
                    text,
                    parse_float=_Float,
                    object_pairs_hook=_no_duplicate_keys,
                )
                for text in (old, new)
            )
        )
    except (ValueError, RecursionError):
        return False


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
        return _same_json(old, new)
    return False


def _align(
    canonical: spdx3.SHACLObject, duplicate: spdx3.SHACLObject, pyname: str
) -> None:
    """Give *duplicate* the value of *pyname* that *canonical* has, so the
    plain field merge that follows finds nothing to union or to warn about."""
    current = getattr(canonical, pyname)
    if isinstance(current, (spdx3.ListProxy, list)):
        current = list(current)
    setattr(duplicate, pyname, current)


def _agreed(sources: list[dict[str, str | None]]) -> dict[str, str | None]:
    """The method of each field when every source that names it agrees that
    it is generated, else ``None`` for it: the sources come from a set, and a
    field they disagree on is read as not generated, in any order."""
    methods: dict[str, str | None] = {}
    for source in sources:
        for name, method in source.items():
            if name not in methods:
                methods[name] = method
            elif method not in GENERATED_METHODS or methods[name] not in (
                GENERATED_METHODS
            ):
                methods[name] = None
    return methods


def generated_properties(methods: dict[str, str | None]) -> frozenset[str]:
    """The properties of a model whose provenance *methods* (field -> method)
    are all generated, from :data:`PROVENANCE_PROPERTY_FIELDS`."""
    generated: set[str] = set()
    for pyname, fields in PROVENANCE_PROPERTY_FIELDS.items():
        present = [methods[name] for name in fields if name in methods]
        if present and all(method in GENERATED_METHODS for method in present):
            generated.add(pyname)
    return frozenset(generated)


# pylint: disable-next=too-few-public-methods
class GeneratedValues:
    """The base models of a merge and the properties Pitloom generated."""

    def __init__(
        self, model_names: ModelNames, base: Iterable[spdx3.SHACLObject]
    ) -> None:
        self._model_names = model_names
        objects = list(base)
        annotations = [o for o in objects if isinstance(o, spdx3.Annotation)]
        self._generated: dict[int, set[str]] = {}
        #: The generated value each replaced property had, by model: a later
        #: fragment that says the same is no new value.
        self._replaced: dict[int, dict[str, object]] = {}
        for obj in objects:
            if not isinstance(obj, spdx3.ai_AIPackage) or not obj.spdxId:
                continue
            sources = [_comment_methods(obj.comment)]
            sources += [
                _annotation_methods(annotation)
                for annotation in annotations
                if _endpoint_id(annotation.subject) == str(obj.spdxId)
            ]
            properties = generated_properties(_agreed(sources))
            if properties:
                self._generated[id(obj)] = set(properties)

    def replace(
        self, canonical: spdx3.SHACLObject, duplicate: spdx3.SHACLObject
    ) -> None:
        """Give *canonical*, when it is a base model with generated values,
        the value *duplicate* has for each of them that differs."""
        if not isinstance(canonical, spdx3.ai_AIPackage):
            return
        self._restate(canonical, duplicate)
        properties = self._generated.get(id(canonical))
        if not properties:
            return
        for pyname in sorted(properties):
            new = getattr(duplicate, pyname, None)
            old = getattr(canonical, pyname, None)
            if _is_empty(new):
                continue
            if _equivalent(old, new):  # a respelling: the plain merge sees none
                _align(canonical, duplicate, pyname)
                continue
            if isinstance(new, (spdx3.ListProxy, list, tuple)):
                new = list(new)
            self._replaced.setdefault(id(canonical), {})[pyname] = (
                list(old) if isinstance(old, (spdx3.ListProxy, list)) else old
            )
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
                self._model_names.drop_provenance(canonical, name)

    def _restate(
        self, canonical: spdx3.ai_AIPackage, duplicate: spdx3.SHACLObject
    ) -> None:
        """Give *duplicate* the value *canonical* now has for a property it
        replaced, where *duplicate* says what was replaced: the plain merge
        that follows then finds nothing to union or to warn about, in any
        order of fragments."""
        for pyname, old in self._replaced.get(id(canonical), {}).items():
            new = getattr(duplicate, pyname, None)
            if _is_empty(new) or not _equivalent(old, new):
                continue
            _align(canonical, duplicate, pyname)
