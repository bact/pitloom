# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unification logic and property merging for SPDX 3 fragment files.

See also: :mod:`pitloom.assemble.spdx3.fragments` (facade and merge orchestration).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast

from spdx_python_model.bindings import v3_0_1 as spdx3

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
    return [k[0] for k in obj.property_keys() if k[0] is not None]


def _stable_key(obj: spdx3.SHACLObject) -> tuple[Any, ...]:
    """Deterministic sort key for iterating a ``SHACLObjectSet``."""
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
    """Return a comparable, hashable-shaped representation of a property value."""
    if value is None:
        return (0, None)
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


def _remap_object_refs(
    obj: spdx3.SHACLObject, remap: dict[spdx3.SHACLObject, str]
) -> None:
    """Rewrite *obj*'s object-valued properties in place."""
    for pyname in _class_properties(obj):
        value = getattr(obj, pyname, None)
        if isinstance(value, spdx3.SHACLObject):
            replacement = remap.get(value)
            if replacement is not None:
                setattr(obj, pyname, replacement)
        elif isinstance(value, spdx3.ListProxy):
            for i, item in enumerate(value):
                if isinstance(item, spdx3.SHACLObject):
                    replacement = remap.get(item)
                    if replacement is not None:
                        cast(list[Any], value)[i] = replacement


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
    if not _is_empty(dup_val) and dup_val != canonical_val:
        if pyname == "name" and _paths_suffix_match(canonical_val, dup_val):
            log.debug(
                "Merge: %s %s known as both %r and %r; keeping %r.",
                type(canonical).__name__,
                getattr(canonical, "spdxId", "?"),
                canonical_val,
                dup_val,
                canonical_val,
            )
            return
        log.warning(
            "Merge: conflicting %r on %s %s: keeping %r, dropping %r.",
            pyname,
            type(canonical).__name__,
            getattr(canonical, "spdxId", "?"),
            canonical_val,
            dup_val,
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

    merged = list(canonical_items)
    for item in dup_items:
        if isinstance(item, spdx3.SHACLObject):
            already = any(
                isinstance(existing, spdx3.SHACLObject)
                and type(existing) is type(item)
                and getattr(existing, "spdxId", object())
                == getattr(item, "spdxId", None)
                for existing in canonical_items
            )
            if already:
                continue
        elif item in canonical_items:
            continue
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
        for obj in sorted(exporter.object_set.objects, key=_stable_key):
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


def _merge_fragment_set(
    fragment_set: spdx3.SHACLObjectSet,
    index: _MergeIndex,
    fragment_file: str,
    events: _UnificationEvents,
) -> None:
    """Unify and add every top-level element of *fragment_set* into
    *index*'s exporter."""
    remap: dict[spdx3.SHACLObject, str] = {}
    kept: list[spdx3.SHACLObject] = []

    for obj in sorted(fragment_set.objects, key=_stable_key):
        if isinstance(obj, _ENVELOPE_TYPES):
            continue

        spdx_id = getattr(obj, "spdxId", None)
        by_id = index.find_by_id(spdx_id) if spdx_id else None
        if by_id is not None:
            _merge_properties(_as_element(by_id), _as_element(obj))
            remap[obj] = require_spdx_id(_as_element(by_id))
            continue

        if isinstance(obj, _HASHABLE_TYPES):
            element = _as_element(obj)
            by_hash = index.find_by_hash(element)
            if by_hash is not None:
                survivor = require_spdx_id(by_hash)
                _merge_properties(by_hash, element)
                remap[obj] = survivor
                _record_unification(
                    events, survivor, "sha256", require_spdx_id(element), fragment_file
                )
                continue
            _warn_if_same_name_different_hash(element, index.exporter.object_set)

        if isinstance(obj, _STRUCTURAL_TYPES):
            structural_dup = index.find_structural_duplicate(obj)
            if structural_dup is not None:
                remap[obj] = require_spdx_id(_as_element(structural_dup))
                continue

        kept.append(obj)

    for obj in kept:
        _remap_object_refs(obj, remap)
    for obj in kept:
        index.register(obj)
