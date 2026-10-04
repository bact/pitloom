# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unification logic and property merging for SPDX 3 fragment files.

See also: :mod:`pitloom.assemble.spdx3.fragments` (facade and merge orchestration)
and :mod:`pitloom.assemble.spdx3._fragments_licenses` (licence unification).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_licenses import (
    LICENSE_TYPES,
    find_license_survivor,
    register_license,
)
from pitloom.export.spdx3_describe import describe_value, property_names
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

log = logging.getLogger(__name__)

#: A recorded fragment-unification event: survivor id -> criterion ->
#: ``{"unified": set of dropped distinct ids, "fragments": set of origin paths}``.
_UnificationEvents = dict[str, dict[str, dict[str, set[str]]]]

_ENVELOPE_TYPES: tuple[type, ...] = (spdx3.SpdxDocument, spdx3.Bom)

_HASHABLE_TYPES: tuple[type, ...] = (
    spdx3.software_File,
    spdx3.dataset_DatasetPackage,
    spdx3.software_Package,
)

_STRUCTURAL_TYPES: tuple[type, ...] = (spdx3.Agent, spdx3.Tool)

_SKIP_MERGE_PROPS = frozenset({"creationInfo", "_id"})
_KEYED_DICT_PROPS = frozenset({"ai_hyperparameter", "ai_metric"})


def _class_properties(obj: spdx3.SHACLObject) -> Iterable[str]:
    """Return the declared Python property names on *obj*'s class."""
    return property_names(obj)


def _canonical_merge_key(obj: spdx3.SHACLObject) -> tuple[Any, ...]:
    """Deterministic sort key for iterating a ``SHACLObjectSet`` during
    fragment unification.

    Canonical: this order drives :class:`_MergeIndex` construction and
    :func:`_merge_fragment_set`'s iteration, which decides which
    duplicate element survives when
    :meth:`_MergeIndex.find_structural_duplicate` returns the first
    match -- i.e. it determines which object's properties become the
    merged, canonical ones in SBOM output, not just iteration order.
    Changing this key changes SBOM output content; re-verify
    ``test_graph_element_ordering`` and
    ``test_combined_output_is_deterministic`` after any change here.
    """
    # pylint: disable=protected-access
    obj_id: str = getattr(obj, "_id", None) or ""
    return (type(obj).__name__, obj_id, _signature(obj))


def _as_element(obj: spdx3.SHACLObject) -> spdx3.Element:
    """Narrow *obj* to :class:`~spdx_python_model.bindings.v3_0_1.Element`."""
    return cast(spdx3.Element, obj)


def _sha256_hash(obj: spdx3.Element) -> str | None:
    """Return the SHA-256 hex digest from *obj*'s ``verifiedUsing``."""
    for h in getattr(obj, "verifiedUsing", None) or []:
        if getattr(h, "algorithm", None) == spdx3.HashAlgorithm.sha256:
            value = getattr(h, "hashValue", None)
            if value:
                return str(value)
    return None


def _normalize_value(value: Any) -> Any:
    """Return a comparable, hashable-shaped representation of a property value.

    An element reference compares by id, whether it is the element object
    (a deserialised fragment links its own) or the id string (a build
    writes ids); an object with no id (a ``Hash``) by its content."""
    if value is None:
        return (0, None)
    if isinstance(value, spdx3.Element) and value.spdxId:
        return (3, "str", str(value.spdxId))
    if isinstance(value, spdx3.SHACLObject):
        return (1, _signature(value))
    if isinstance(value, spdx3.ListProxy):
        return (2, tuple(_normalize_value(v) for v in value))
    if isinstance(value, (list, tuple)):
        return (2, tuple(_normalize_value(v) for v in value))
    return (3, type(value).__name__, value)


def _signature(obj: spdx3.SHACLObject) -> tuple[Any, ...]:
    """Return a comparable signature of *obj*'s content."""
    parts: list[Any] = [type(obj).__name__]
    for pyname in sorted(_class_properties(obj)):
        if pyname in _SKIP_MERGE_PROPS:
            continue
        parts.append((pyname, _normalize_value(getattr(obj, pyname, None))))
    return tuple(parts)


def _as_id_ref(value: Any, id_map: dict[str, str], seen: set[int]) -> Any:
    """*value* with an element reference as the id string of the element
    that survives the merge; an object with no id is rewritten in place."""
    if isinstance(value, spdx3.Element) and value.spdxId:
        spdx_id = str(value.spdxId)
        return id_map.get(spdx_id, spdx_id)
    if isinstance(value, spdx3.SHACLObject):
        _to_id_refs(value, id_map, seen)
    elif isinstance(value, str):
        return id_map.get(value, value)
    return value


def _to_id_refs(obj: spdx3.SHACLObject, id_map: dict[str, str], seen: set[int]) -> None:
    """Rewrite *obj*'s element references in place as id strings through
    *id_map* (dropped id -> surviving id), nested objects with no id
    (``CreationInfo``, ``DictionaryEntry``) included: a reference to an
    element object of the fragment would otherwise be serialised as a second
    copy of it. A string equal to a dropped id (a ``customIdToUri`` value)
    is rewritten too."""
    if id(obj) in seen:
        return
    seen.add(id(obj))
    for pyname in _class_properties(obj):
        if pyname == "_id":
            continue
        value = getattr(obj, pyname, None)
        if isinstance(value, spdx3.ListProxy):
            items = cast(list[Any], value)
            for i, item in enumerate(items):
                new = _as_id_ref(item, id_map, seen)
                if new is not item:
                    items[i] = new
            continue
        new = _as_id_ref(value, id_map, seen)
        if new is not value:
            setattr(obj, pyname, new)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, list, spdx3.ListProxy)):
        return len(value) == 0
    return False


def _paths_suffix_match(a: Any, b: Any) -> bool:
    """True when *a* and *b* are path strings naming the same file at
    different depths."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return a.endswith("/" + b) or b.endswith("/" + a)


def _merge_scalar(
    canonical: spdx3.Element, pyname: str, canonical_val: Any, dup_val: Any
) -> None:
    if _is_empty(canonical_val):
        if not _is_empty(dup_val):
            setattr(canonical, pyname, dup_val)
        return
    if not _is_empty(dup_val) and _normalize_value(dup_val) != _normalize_value(
        canonical_val
    ):
        if pyname == "name" and _paths_suffix_match(canonical_val, dup_val):
            log.debug(
                "Merge: %s known as both %r and %r; keeping %r.",
                describe_value(canonical),
                canonical_val,
                dup_val,
                canonical_val,
            )
            return
        log.warning(
            "Merge: conflicting %r on %s: keeping %s, dropping %s.",
            pyname,
            describe_value(canonical),
            describe_value(canonical_val),
            describe_value(dup_val),
        )


def _merge_comment(canonical: spdx3.Element, canonical_val: Any, dup_val: Any) -> None:
    if _is_empty(canonical_val):
        if not _is_empty(dup_val):
            canonical.comment = dup_val
        return
    if not _is_empty(dup_val) and dup_val != canonical_val:
        canonical.comment = f"{canonical_val}; {dup_val}"


def _merge_list(
    canonical: spdx3.Element, pyname: str, canonical_val: Any, dup_val: Any
) -> None:
    canonical_items = list(canonical_val) if canonical_val else []
    dup_items = list(dup_val) if dup_val else []
    if not dup_items:
        return

    # One key per item: an element by id (object or string), an object with
    # no id by its content, anything else by value.
    present = {_normalize_value(existing) for existing in canonical_items}
    merged = list(canonical_items)
    for item in dup_items:
        key = _normalize_value(item)
        if key in present:
            continue
        present.add(key)
        merged.append(item)

    if len(merged) != len(canonical_items):
        setattr(canonical, pyname, merged)


def _merge_dictionary_entries(
    canonical: spdx3.Element, pyname: str, canonical_val: Any, dup_val: Any
) -> None:
    """Union two ``DictionaryEntry`` lists by key; canonical wins on a key collision."""
    canonical_entries = list(canonical_val) if canonical_val else []
    dup_entries = list(dup_val) if dup_val else []
    if not dup_entries:
        return

    keys_seen: set[str] = {
        entry.key for entry in canonical_entries if getattr(entry, "key", None)
    }
    merged = list(canonical_entries)
    for entry in dup_entries:
        key = getattr(entry, "key", None)
        if key is not None and key in keys_seen:
            continue
        merged.append(entry)
        if key is not None:
            keys_seen.add(key)

    if len(merged) != len(canonical_entries):
        setattr(canonical, pyname, merged)


def _merge_properties(canonical: spdx3.Element, duplicate: spdx3.Element) -> None:
    """Fold *duplicate*'s fields into *canonical* in place."""
    for pyname in _class_properties(canonical):
        if pyname in _SKIP_MERGE_PROPS:
            continue
        canonical_val = getattr(canonical, pyname, None)
        dup_val = getattr(duplicate, pyname, None)

        if pyname in _KEYED_DICT_PROPS:
            _merge_dictionary_entries(canonical, pyname, canonical_val, dup_val)
        elif pyname == "comment":
            _merge_comment(canonical, canonical_val, dup_val)
        elif isinstance(canonical_val, spdx3.ListProxy) or isinstance(
            dup_val, spdx3.ListProxy
        ):
            _merge_list(canonical, pyname, canonical_val, dup_val)
        else:
            _merge_scalar(canonical, pyname, canonical_val, dup_val)


def _warn_if_same_name_different_hash(
    obj: spdx3.Element, object_set: spdx3.SHACLObjectSet
) -> None:
    """Log a warning when *obj* shares a ``name`` with different SHA-256."""
    name = getattr(obj, "name", None)
    obj_hash = _sha256_hash(obj)
    if not name or obj_hash is None:
        return
    for existing in object_set.objects:
        if type(existing) is not type(obj) or existing is obj:
            continue
        if getattr(existing, "name", None) != name:
            continue
        existing_hash = _sha256_hash(_as_element(existing))
        if existing_hash is not None and existing_hash != obj_hash:
            log.warning(
                "Merge: %s %r appears with two different SHA-256 hashes "
                "(%s vs %s); keeping both as separate elements.",
                type(obj).__name__,
                name,
                existing_hash,
                obj_hash,
            )
            return


class _MergeIndex:
    """Cumulative unification state across fragments."""

    def __init__(self, exporter: Spdx3JsonExporter) -> None:
        self.exporter = exporter
        self.by_hash: dict[tuple[str, str], spdx3.Element] = {}
        self.structural: dict[type, list[spdx3.SHACLObject]] = {}
        for obj in sorted(exporter.object_set.objects, key=_canonical_merge_key):
            self._index(obj)

    def _index(self, obj: spdx3.SHACLObject) -> None:
        if isinstance(obj, _HASHABLE_TYPES):
            element = _as_element(obj)
            digest = _sha256_hash(element)
            if digest:
                self.by_hash.setdefault((type(obj).__name__, digest), element)
        if isinstance(obj, _STRUCTURAL_TYPES):
            self.structural.setdefault(type(obj), []).append(obj)

    def find_by_id(self, spdx_id: str) -> spdx3.SHACLObject | None:
        return self.exporter.object_set.find_by_id(spdx_id)

    def find_by_hash(self, obj: spdx3.Element) -> spdx3.Element | None:
        digest = _sha256_hash(obj)
        if digest is None:
            return None
        return self.by_hash.get((type(obj).__name__, digest))

    def find_structural_duplicate(
        self, obj: spdx3.SHACLObject
    ) -> spdx3.SHACLObject | None:
        signature = _signature(obj)
        for existing in self.structural.get(type(obj), []):
            if _signature(existing) == signature:
                return existing
        return None

    def register(self, obj: spdx3.SHACLObject) -> None:
        if isinstance(obj, LICENSE_TYPES):
            register_license(obj, self.exporter)
        else:
            self.exporter.object_set.add(obj)
        self._index(obj)


def _record_unification(
    events: _UnificationEvents,
    survivor_id: str,
    criterion: str,
    dropped_id: str,
    fragment_file: str,
) -> None:
    """Record unification event (A1)."""
    rec = events.setdefault(survivor_id, {}).setdefault(
        criterion, {"unified": set(), "fragments": set()}
    )
    rec["unified"].add(dropped_id)
    rec["fragments"].add(fragment_file)


def _envelope_roots(
    envelopes: list[spdx3.SHACLObject], id_map: dict[str, str]
) -> list[str]:
    """The ids the fragment's own ``SpdxDocument``/``Sbom`` envelopes root,
    through *id_map*, less the envelopes themselves (they are not merged)."""
    envelope_ids = {str(getattr(e, "spdxId", None)) for e in envelopes}
    roots: list[str] = []
    for envelope in envelopes:
        for root in getattr(envelope, "rootElement", None) or []:
            root_id = str(root.spdxId if isinstance(root, spdx3.Element) else root)
            if root_id not in envelope_ids:
                roots.append(id_map.get(root_id, root_id))
    return list(dict.fromkeys(roots))


def _find_survivor(
    obj: spdx3.SHACLObject,
    index: _MergeIndex,
    pending_licenses: dict[tuple[str, str], str],
) -> tuple[spdx3.SHACLObject | str | None, str]:
    """What *obj* unifies with, and by which criterion: by id, licence key,
    SHA-256, then structure. A ``(None, "")`` result keeps *obj*. A
    licence survivor is an id (its fields are not folded); any other is the
    object to fold *obj* into."""
    spdx_id = getattr(obj, "spdxId", None)
    by_id = index.find_by_id(spdx_id) if spdx_id else None
    if by_id is not None:
        return by_id, "id"
    if isinstance(obj, LICENSE_TYPES):
        survivor_id = find_license_survivor(obj, index.exporter, pending_licenses)
        return survivor_id, "license" if survivor_id else ""
    if isinstance(obj, _HASHABLE_TYPES):
        element = _as_element(obj)
        by_hash = index.find_by_hash(element)
        if by_hash is not None:
            return by_hash, "sha256"
        _warn_if_same_name_different_hash(element, index.exporter.object_set)
    if isinstance(obj, _STRUCTURAL_TYPES):
        structural_dup = index.find_structural_duplicate(obj)
        if structural_dup is not None:
            return structural_dup, "structural"
    return None, ""


def _merge_fragment_set(
    fragment_set: spdx3.SHACLObjectSet,
    index: _MergeIndex,
    fragment_file: str,
    events: _UnificationEvents,
) -> list[str]:
    """Unify and add every top-level element of *fragment_set* into
    *index*'s exporter; return the ids its envelopes root (see
    :func:`_envelope_roots`).

    Two passes: first a survivor for every element, then every element
    reference becomes the survivor's id string, on the elements folded into
    a survivor as on the kept ones, before any fields are folded -- a
    deserialised fragment links its references as objects, the document
    holds ids, and the two must compare equal."""
    id_map: dict[str, str] = {}
    folds: list[tuple[spdx3.SHACLObject, spdx3.SHACLObject]] = []
    kept: list[spdx3.SHACLObject] = []
    envelopes: list[spdx3.SHACLObject] = []
    pending_licenses: dict[tuple[str, str], str] = {}

    objects = sorted(fragment_set.objects, key=_canonical_merge_key)
    for obj in objects:
        if isinstance(obj, _ENVELOPE_TYPES):
            envelopes.append(obj)
            continue
        survivor, criterion = _find_survivor(obj, index, pending_licenses)
        if survivor is None:
            kept.append(obj)
            continue
        dropped_id = require_spdx_id(_as_element(obj))
        survivor_id = (
            survivor
            if isinstance(survivor, str)
            else require_spdx_id(_as_element(survivor))
        )
        id_map[dropped_id] = survivor_id
        if criterion in ("id", "sha256") and not isinstance(survivor, str):
            folds.append((survivor, obj))
        if criterion in ("license", "sha256"):
            _record_unification(
                events, survivor_id, criterion, dropped_id, fragment_file
            )

    seen: set[int] = set()
    for obj in objects:
        if not isinstance(obj, _ENVELOPE_TYPES):
            _to_id_refs(obj, id_map, seen)
    for survivor, obj in folds:
        _merge_properties(_as_element(survivor), _as_element(obj))
    for obj in kept:
        index.register(obj)
    return _envelope_roots(envelopes, id_map)
