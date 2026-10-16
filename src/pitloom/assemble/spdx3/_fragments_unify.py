# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unification of the elements of SPDX 3 fragment files.

See also: :mod:`pitloom.assemble.spdx3.fragments` (facade and merge
orchestration), :mod:`pitloom.assemble.spdx3._fragments_props` (property
merging), :mod:`pitloom.assemble.spdx3._fragments_hashes` (digest conflicts),
:mod:`pitloom.assemble.spdx3._fragments_licenses` (licence unification) and
:mod:`pitloom.assemble.spdx3._fragments_ids` (ids minted during a merge).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_hashes import (
    hash_conflict,
    warn_if_same_name_different_hash,
)
from pitloom.assemble.spdx3._fragments_ids import rename_id_clash
from pitloom.assemble.spdx3._fragments_licenses import (
    LICENSE_TYPES,
    find_license_survivor,
    register_license,
)
from pitloom.assemble.spdx3._fragments_props import (
    _class_properties,
    _merge_properties,
    _signature,
)
from pitloom.export.hashes import sha256_of
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


class _MergeIndex:
    """Cumulative unification state across fragments.

    *namespace* (the main document's id) is where a fragment element that
    must be kept apart from a holder of its id gets its new id; without
    one, the id's own namespace."""

    def __init__(
        self, exporter: Spdx3JsonExporter, namespace: str | None = None
    ) -> None:
        self.exporter = exporter
        self.namespace = namespace
        self.by_hash: dict[tuple[str, str], spdx3.Element] = {}
        self.sources: dict[str, set[str]] = {}
        self.note_source("", exporter.object_set.objects)
        self.structural: dict[type, list[spdx3.SHACLObject]] = {}
        for obj in sorted(exporter.object_set.objects, key=_canonical_merge_key):
            self._index(obj)

    def _index(self, obj: spdx3.SHACLObject) -> None:
        if isinstance(obj, _HASHABLE_TYPES):
            element = _as_element(obj)
            digest = sha256_of(element)
            if digest:
                self.by_hash.setdefault((type(obj).__name__, digest), element)
        if isinstance(obj, _STRUCTURAL_TYPES):
            self.structural.setdefault(type(obj), []).append(obj)

    def note_source(self, source: str, objects: Iterable[spdx3.SHACLObject]) -> None:
        """Record that *source* (the base document, ``""``, or a fragment
        path) holds an id in each of *objects*' namespaces."""
        for obj in objects:
            spdx_id = getattr(obj, "spdxId", None)
            if spdx_id:
                namespace = str(spdx_id).partition("#")[0]
                self.sources.setdefault(namespace, set()).add(source)

    def outranks(self, candidate: spdx3.SHACLObject, holder: spdx3.SHACLObject) -> bool:
        """True when *candidate*'s id is more likely registry-pinned than
        *holder*'s: its id is free in the document and its namespace is held
        by more sources. A minted id's namespace belongs to its one
        fragment; a pinned id's is shared by every fragment and the base
        that use the registry. A tie keeps *holder*, the earlier."""

        def held_by(obj: spdx3.SHACLObject) -> int:
            spdx_id = str(getattr(obj, "spdxId", "")).partition("#")[0]
            return len(self.sources.get(spdx_id, ()))

        candidate_id = str(getattr(candidate, "spdxId", ""))
        return self.find_by_id(candidate_id) is None and held_by(candidate) > held_by(
            holder
        )

    def promote(
        self, survivor: spdx3.Element, new_id: str, events: _UnificationEvents
    ) -> str:
        """Give the kept *survivor* the id *new_id* (held by no element) and
        point every reference, recorded event and registry record at it;
        return the old id. The old id's recorded registry key moves to
        *new_id* unless *new_id* has one of its own."""
        old_id = require_spdx_id(survivor)
        survivor.spdxId = new_id
        self.exporter.object_set.create_index()
        seen: set[int] = set()
        for obj in self.exporter.object_set.objects:
            _to_id_refs(obj, {old_id: new_id}, seen)
        if old_id in events:
            events[new_id] = events.pop(old_id)
        non_readers = self.exporter.registry_non_readers
        if old_id in non_readers:
            non_readers.discard(old_id)
            non_readers.add(new_id)
        keys = self.exporter.registry_keys
        if old_id in keys:
            keys.setdefault(new_id, keys.pop(old_id))
        return old_id

    def find_by_id(self, spdx_id: str) -> spdx3.SHACLObject | None:
        """The element holding *spdx_id*, whatever its type."""
        return self.exporter.object_set.find_by_id(spdx_id)

    def keep_apart(self, obj: spdx3.SHACLObject, fragment_ids: set[str]) -> None:
        """Rename *obj*, about to be kept, when an element already holds its
        id (of another type, or of its type with a conflicting digest, see
        :func:`hash_conflict`): never two elements with one id. The new
        id is none of the document's or *fragment_ids*, and joins the
        latter."""
        spdx_id = getattr(obj, "spdxId", None)
        holder = self.find_by_id(spdx_id) if spdx_id else None
        if holder is None:
            return
        namespace = self.namespace or str(spdx_id).partition("#")[0]
        taken = (self.exporter.object_set.obj_by_id, fragment_ids)
        fragment_ids.add(rename_id_clash(_as_element(obj), holder, namespace, *taken))

    def find_by_hash(self, obj: spdx3.Element) -> spdx3.Element | None:
        digest = sha256_of(obj)
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
    """Record one unification event under its survivor and criterion."""
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
    """What *obj* unifies with, and by which criterion: by id (same type
    only, and no conflicting digest), licence key, SHA-256, then structure.
    A ``(None, "")`` result keeps *obj*. A licence survivor is an id (its
    fields are not folded); any other is the object to fold *obj* into.

    An id held with a conflicting digest skips only the id criterion:
    the same bytes elsewhere still unify, else :meth:`_MergeIndex.keep_apart`
    renames *obj* (and warns, so the name check below stays quiet)."""
    spdx_id = getattr(obj, "spdxId", None)
    by_id = index.find_by_id(spdx_id) if spdx_id else None
    id_conflict = False
    if by_id is not None and type(by_id) is type(obj):
        if hash_conflict(by_id, obj) is None:
            return by_id, "id"
        id_conflict = True
    if isinstance(obj, LICENSE_TYPES):
        survivor_id = find_license_survivor(obj, index.exporter, pending_licenses)
        return survivor_id, "license" if survivor_id else ""
    if isinstance(obj, _HASHABLE_TYPES):
        element = _as_element(obj)
        by_hash = index.find_by_hash(element)
        if by_hash is not None:
            return by_hash, "sha256"
        if not id_conflict:
            warn_if_same_name_different_hash(element, index.exporter.object_set)
    if isinstance(obj, _STRUCTURAL_TYPES):
        structural_dup = index.find_structural_duplicate(obj)
        if structural_dup is not None:
            return structural_dup, "structural"
    return None, ""


def _resolve_ids(
    obj: spdx3.SHACLObject,
    survivor: spdx3.SHACLObject | str,
    criterion: str,
    index: _MergeIndex,
    events: _UnificationEvents,
) -> tuple[str, str]:
    """Return ``(survivor_id, dropped_id)`` for *obj* folded into *survivor*;
    a ``sha256`` match swaps the two when *obj* outranks the survivor."""
    dropped_id = require_spdx_id(_as_element(obj))
    if isinstance(survivor, str):
        return survivor, dropped_id
    survivor_id = require_spdx_id(_as_element(survivor))
    if criterion == "sha256" and index.outranks(obj, survivor):
        return dropped_id, index.promote(_as_element(survivor), dropped_id, events)
    return survivor_id, dropped_id


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
    holds ids, and the two must compare equal. A kept element is renamed
    in the first pass (:meth:`_MergeIndex.keep_apart`), so the references
    to it follow; its old id stays the other element's."""
    id_map: dict[str, str] = {}
    folds: list[tuple[spdx3.SHACLObject, spdx3.SHACLObject]] = []
    kept: list[spdx3.SHACLObject] = []
    envelopes: list[spdx3.SHACLObject] = []
    pending_licenses: dict[tuple[str, str], str] = {}

    objects = sorted(fragment_set.objects, key=_canonical_merge_key)
    fragment_ids = {
        str(o.spdxId) for o in objects if isinstance(o, spdx3.Element) and o.spdxId
    }
    for obj in objects:
        if isinstance(obj, _ENVELOPE_TYPES):
            envelopes.append(obj)
            continue
        survivor, criterion = _find_survivor(obj, index, pending_licenses)
        if survivor is None:
            index.keep_apart(obj, fragment_ids)
            kept.append(obj)
            continue
        survivor_id, dropped_id = _resolve_ids(obj, survivor, criterion, index, events)
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
