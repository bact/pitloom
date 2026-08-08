# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Merging of pre-generated SPDX 3 fragment files into an SBOM document.

Each fragment (typically produced by :mod:`pitloom.loom`) is its own
standalone SPDX document.  Merging them into the main document is more than
concatenation: the same dataset or AI model may appear -- with a *different*
``spdxId`` -- in more than one fragment (e.g. a training run and an
evaluation run both refer to the same model), and every fragment carries its
own envelope (``SpdxDocument``, ``software_Sbom``) and its own copy of the
"Pitloom" creator ``Agent``/``Tool``.  This module unifies duplicates using a
strict, provable policy -- **never** by matching on ``type`` + ``name`` alone
-- so that two distinct things that merely share a label are never silently
collapsed into one.

Unification policy, in priority order:

1. **Same spdxId** as an element already known (main document or an earlier
   fragment) -- typically because both were minted from the same
   :class:`~pitloom.ids.IdRegistry` entry.
2. **SHA-256 content equality** (``verifiedUsing``) for ``software_File``,
   ``dataset_DatasetPackage``, and ``software_Package`` -- provably the same
   bytes, even without a registry.
3. **Deep-equal modulo (spdxId, creationInfo)** for ``Agent`` subclasses and
   ``Tool`` -- collapses the identical "Pitloom" agent/tool that every
   independently-generated fragment mints.
4. Otherwise: kept under its original id, added as-is.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import build_unification_annotation
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

log = logging.getLogger(__name__)

#: A recorded fragment-unification event: survivor id -> criterion ->
#: ``{"unified": set of dropped distinct ids, "fragments": set of origin paths}``.
#: Only *content-hash* (SHA-256) unifications are recorded -- those fold a
#: genuinely *distinct* id into the survivor ("these two different ids are the
#: same bytes"), which SPDX cannot express and which the merge would otherwise
#: discard. A same-id registry match (dropped id == survivor id) carries no such
#: fact -- its only content is the fragment origin, which belongs to the native
#: ``SpdxDocument.imports`` native anchor, not here. Agent/Tool structural dedup
#: (every fragment mints its own "Pitloom") is likewise excluded.
_UnificationEvents = dict[str, dict[str, dict[str, set[str]]]]

# A fragment's own SpdxDocument/Bom (software_Sbom is a Bom subclass) is
# always dropped -- the merged output has exactly one of each, owned by the
# main document being assembled.
_ENVELOPE_TYPES: tuple[type, ...] = (spdx3.SpdxDocument, spdx3.Bom)

# Element types eligible for SHA-256 content-equality unification.
_HASHABLE_TYPES: tuple[type, ...] = (
    spdx3.software_File,
    spdx3.dataset_DatasetPackage,
    spdx3.software_Package,
)

# Element types eligible for deep-equal-modulo-id unification -- collapses
# identical "Pitloom" Agent/Tool copies independently emitted per fragment.
_STRUCTURAL_TYPES: tuple[type, ...] = (spdx3.Agent, spdx3.Tool)

# Properties never considered by the property-merge or structural-equality
# comparisons: every element shares this shape but it is not "content".
# ``_id`` is the identity itself (``spdxId``/blank-node label -- it *is*
# declared in ``_OBJ_PY_PROPS``): unification exists precisely to collapse
# elements whose ids differ, so identity must never influence content
# comparison or be property-merged.
_SKIP_MERGE_PROPS = frozenset({"creationInfo", "_id"})

# Dictionary-typed properties merged by DictionaryEntry.key rather than by
# generic list-union (see _merge_dictionary_entries).
_KEYED_DICT_PROPS = frozenset({"ai_hyperparameter", "ai_metric"})


# ---------------------------------------------------------------------------
# spdx-python-model property enumeration -- single access point
# ---------------------------------------------------------------------------
#
# Every place in this module that needs to walk "all declared properties of
# an arbitrary element generically" (reference remapping, property merging,
# structural equality) goes through this one helper, so an upstream change
# to ``property_keys()``'s shape surfaces as a single, loud failure here
# rather than silent breakage scattered through the merge logic.
def _class_properties(obj: spdx3.SHACLObject) -> Iterable[str]:
    """Return the declared Python property names on *obj*'s class.

    ``property_keys()`` yields ``(python_name, iri, compact_name)`` triples;
    ``python_name`` is typed ``Optional[str]`` upstream for properties with
    no Python-attribute alias, though every property pitloom's model
    actually declares has one -- filter defensively rather than assume it.
    """
    return [k[0] for k in obj.property_keys() if k[0] is not None]


def _stable_key(obj: spdx3.SHACLObject) -> tuple[Any, ...]:
    """Deterministic sort key for iterating a ``SHACLObjectSet``.

    ``SHACLObjectSet.objects`` is a plain :class:`set`, so its iteration
    order varies between processes.  Every pass that makes a keep/drop or
    canonical-vs-duplicate decision must iterate in this order instead, or
    the merged SBOM would not be byte-reproducible.  ``_id`` (like
    ``_OBJ_PY_PROPS`` above) is spdx-python-model internal API: it is the
    ``spdxId`` for Elements and the blank-node label otherwise.
    """
    # pylint: disable=protected-access
    obj_id: str = getattr(obj, "_id", None) or ""
    return (type(obj).__name__, obj_id, _signature(obj))


def _as_element(obj: spdx3.SHACLObject) -> spdx3.Element:
    """Narrow *obj* to :class:`~spdx_python_model.bindings.v3_0_1.Element`.

    Every call site passes an object already known -- by an ``isinstance``
    check against an Element-only type tuple (``_HASHABLE_TYPES`` /
    ``_STRUCTURAL_TYPES``), or by construction (``find_by_id`` only ever
    resolves elements this module itself registered) -- to be an
    ``Element``, never a blank node. ``isinstance`` against a *variable*
    tuple of types doesn't let mypy narrow, so this cast documents and
    centralizes that invariant instead of scattering ``# pyrefly: ignore``.
    """
    return cast(spdx3.Element, obj)


# ---------------------------------------------------------------------------
# Helpers: hashing, structural equality, reference remapping
# ---------------------------------------------------------------------------


def _sha256_hash(obj: spdx3.Element) -> str | None:
    """Return the SHA-256 hex digest from *obj*'s ``verifiedUsing``, or
    ``None`` if it carries no SHA-256 ``Hash``."""
    for h in getattr(obj, "verifiedUsing", None) or []:
        if getattr(h, "algorithm", None) == spdx3.HashAlgorithm.sha256:
            value = getattr(h, "hashValue", None)
            if value:
                return str(value)
    return None


def _normalize_value(value: Any) -> Any:
    """Return a comparable, hashable-shaped representation of a property
    value for structural-equality comparison (see :func:`_signature`)."""
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
    """Return a comparable signature of *obj*'s content, excluding identity
    (``_id``, i.e. ``spdxId``) and the shared blank-node ``creationInfo``
    field (both via ``_SKIP_MERGE_PROPS``).

    Two elements with equal signatures are the same content in every
    user-visible respect -- used to detect the "Pitloom" Agent/Tool that
    every independently-generated fragment mints a fresh, otherwise-identical
    copy of.
    """
    parts: list[Any] = [type(obj).__name__]
    for pyname in sorted(_class_properties(obj)):
        if pyname in _SKIP_MERGE_PROPS:
            continue
        parts.append((pyname, _normalize_value(getattr(obj, pyname, None))))
    return tuple(parts)


def _remap_object_refs(
    obj: spdx3.SHACLObject, remap: dict[spdx3.SHACLObject, str]
) -> None:
    """Rewrite *obj*'s object-valued properties in place, replacing any
    reference to a dropped duplicate (a key in *remap*) with the id string
    of the element it was unified into.

    Walks every declared property generically (via :func:`_class_properties`)
    rather than naming each SPDX 3 field explicitly, so ``from``/``to``/
    ``rootElement``/``createdBy``/... are all covered uniformly -- including
    fields pitloom does not otherwise model.
    """
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


# ---------------------------------------------------------------------------
# Property-merge policy (applied when a duplicate is dropped in favour of a
# canonical element already present)
# ---------------------------------------------------------------------------


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, list, spdx3.ListProxy)):
        return len(value) == 0
    return False


def _paths_suffix_match(a: Any, b: Any) -> bool:
    """True when *a* and *b* are path strings naming the same file at
    different depths -- e.g. a wheel File's distribution path
    (``fragdemo/train.py``) vs. a loom fragment's project-relative script
    path (``src/fragdemo/train.py``)."""
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
            # Expected whenever a wheel File (named by distribution path)
            # unifies with a fragment's script File (named by project
            # path) -- same file, different vantage point; not a conflict.
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
    """Union two ``DictionaryEntry`` lists (``ai_hyperparameter``,
    ``ai_metric``) by key; canonical wins on a key collision."""
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
            continue  # canonical wins on key collision
        merged.append(entry)
        if key is not None:
            keys_seen.add(key)

    if len(merged) != len(canonical_entries):
        setattr(canonical, pyname, merged)


def _merge_properties(canonical: spdx3.Element, duplicate: spdx3.Element) -> None:
    """Fold *duplicate*'s fields into *canonical* in place; *duplicate* is
    then dropped by the caller.

    Policy: scalars keep canonical's value unless canonical's is unset (in
    which case duplicate's fills the gap); a genuine scalar conflict is
    logged and canonical wins. ``comment`` values are joined with ``"; "``.
    ``ai_hyperparameter``/``ai_metric`` are unioned by
    ``DictionaryEntry.key`` (canonical wins on a key collision). Every other
    list-valued property is unioned, preserving canonical's items first.
    """
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
    """Log a warning when *obj* shares a ``name`` with an already-known
    element of the same type but a different SHA-256 hash -- both are kept
    as separate elements (never guessed into one), but this is almost always
    worth a human's attention."""
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


# ---------------------------------------------------------------------------
# Cumulative de-duplication index across all fragments merged into one
# exporter
# ---------------------------------------------------------------------------


class _MergeIndex:
    """Cumulative unification state: the main document's own elements plus
    every fragment merged so far."""

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
    """Note that the distinct *dropped_id* (from *fragment_file*) was unified
    into *survivor_id* under *criterion* -- provenance the merge would otherwise
    discard (A1). Only called for a genuinely distinct id (see
    :func:`_merge_fragment_set`)."""
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
    """Unify and add every top-level element of *fragment_set* into *index*'s
    exporter, per the module-level unification policy. Records content-element
    unifications into *events* (see :func:`_record_unification`)."""
    # Iterate `.objects` (top-level graph entries only), not `.foreach()`
    # (which also yields inline blank-node children like DictionaryEntry --
    # those are never independently registered and are carried along
    # automatically as part of their parent element).
    remap: dict[spdx3.SHACLObject, str] = {}
    kept: list[spdx3.SHACLObject] = []

    for obj in sorted(fragment_set.objects, key=_stable_key):
        if isinstance(obj, _ENVELOPE_TYPES):
            continue  # envelopes are always dropped

        spdx_id = getattr(obj, "spdxId", None)
        by_id = index.find_by_id(spdx_id) if spdx_id else None
        if by_id is not None:
            # Same-id (registry) match: the fragment reused an existing id, so
            # nothing distinct is folded. Its only fact is the fragment origin,
            # which is SpdxDocument.imports territory -- not annotated
            # here (see _UnificationEvents). Properties are still merged.
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
            # Agent/Tool structural dedup (every fragment mints its own
            # "Pitloom" identity) is internal bookkeeping, not an artifact
            # identity fact -- unified silently, not annotated.
            structural_dup = index.find_structural_duplicate(obj)
            if structural_dup is not None:
                remap[obj] = require_spdx_id(_as_element(structural_dup))
                continue

        kept.append(obj)

    for obj in kept:
        _remap_object_refs(obj, remap)
    for obj in kept:
        index.register(obj)


# ---------------------------------------------------------------------------
# Post-merge passes: relationship dedup, profileConformance, second Sbom
# ---------------------------------------------------------------------------


def _endpoint_id(value: str | spdx3.Element | None) -> str | None:
    """Return a ``Relationship`` endpoint's id: itself when already a plain
    id string, or its ``spdxId`` when it is still an ``Element`` reference
    (not every reference is remapped to a string by :func:`_merge_fragment_set`
    -- e.g. an endpoint outside the merged fragments)."""
    if value is None or isinstance(value, str):
        return value
    return str(value.spdxId) if value.spdxId else None


def _dedupe_relationships(exporter: Spdx3JsonExporter) -> None:
    """Drop ``Relationship`` elements that are exact duplicates of one
    already kept, by ``(from, relationshipType, frozenset(to))``."""
    seen: set[tuple[Any, Any, frozenset[Any]]] = set()
    duplicates: list[spdx3.Relationship] = []

    for obj in sorted(exporter.object_set.objects, key=_stable_key):
        if not isinstance(obj, spdx3.Relationship):
            continue
        from_id = _endpoint_id(obj.from_)
        to_ids = frozenset(_endpoint_id(t) for t in obj.to)
        key = (from_id, obj.relationshipType, to_ids)
        if key in seen:
            duplicates.append(obj)
        else:
            seen.add(key)

    for dup in duplicates:
        exporter.object_set.objects.remove(dup)


def _find_main_document(object_set: spdx3.SHACLObjectSet) -> spdx3.SpdxDocument | None:
    for obj in object_set.objects:
        if isinstance(obj, spdx3.SpdxDocument):
            return obj
    return None


def _update_profile_conformance(
    main_doc: spdx3.SpdxDocument, exporter: Spdx3JsonExporter
) -> None:
    """Append ``ai``/``dataset`` to the main document's profileConformance
    when the merged graph now includes those element types (no duplicates)."""
    conformance = list(main_doc.profileConformance or [])
    has_ai = any(isinstance(o, spdx3.ai_AIPackage) for o in exporter.object_set.objects)
    has_dataset = any(
        isinstance(o, spdx3.dataset_DatasetPackage) for o in exporter.object_set.objects
    )
    if has_ai and spdx3.ProfileIdentifierType.ai not in conformance:
        conformance.append(spdx3.ProfileIdentifierType.ai)
    if has_dataset and spdx3.ProfileIdentifierType.dataset not in conformance:
        conformance.append(spdx3.ProfileIdentifierType.dataset)
    main_doc.profileConformance = conformance


def _mint_extra_id(namespace: str, prefix: str, existing_ids: set[str]) -> str:
    """Mint a fresh ``<namespace>#<prefix>-<n>`` id not already present in
    *existing_ids*."""
    n = 1
    while True:
        candidate = f"{namespace}#{prefix}-{n}"
        if candidate not in existing_ids:
            return candidate
        n += 1


def _find_fragment_document_id(fragment_set: spdx3.SHACLObjectSet) -> str | None:
    """Return the ``spdxId`` of the ``SpdxDocument`` envelope in *fragment_set*,
    if present."""
    for obj in fragment_set.objects:
        if isinstance(obj, spdx3.SpdxDocument):
            spdx_id = getattr(obj, "spdxId", None)
            if spdx_id:
                return str(spdx_id)
    return None


def _add_fragment_imports(
    main_doc: spdx3.SpdxDocument,
    fragment_imports: list[spdx3.ExternalMap],
) -> None:
    """Populate ``main_doc.import_`` with ``ExternalMap`` entries for merged
    fragment documents."""
    if not fragment_imports:
        return
    existing_imports = list(main_doc.import_ or [])
    existing_ids: set[str] = set()
    for item in existing_imports:
        if isinstance(item, spdx3.ExternalMap) and item.externalSpdxId:
            existing_ids.add(item.externalSpdxId)
        elif isinstance(item, str):
            existing_ids.add(item)

    for ext_map in fragment_imports:
        if ext_map.externalSpdxId and ext_map.externalSpdxId not in existing_ids:
            existing_imports.append(ext_map)
            existing_ids.add(ext_map.externalSpdxId)
    main_doc.import_ = existing_imports


def _emit_unification_annotations(
    events: _UnificationEvents,
    main_doc: spdx3.SpdxDocument,
    exporter: Spdx3JsonExporter,
) -> None:
    """Emit one ``unification`` Annotation per (survivor, criterion) recorded in
    *events* (A1). Ids are minted in the main document's namespace -- fragment
    merge runs after ``build`` and has no doc UUID of its own. Deterministic:
    survivors and criteria are iterated in sorted order and id/fragment lists
    are sorted inside :func:`build_unification_annotation`."""
    if not events:
        return
    namespace = main_doc.spdxId
    creation_info = main_doc.creationInfo
    if namespace is None or not isinstance(creation_info, spdx3.CreationInfo):
        return
    existing_ids = set(exporter.object_set.obj_by_id.keys())
    for survivor_id in sorted(events):
        for criterion in sorted(events[survivor_id]):
            rec = events[survivor_id][criterion]
            ann_id = _mint_extra_id(namespace, "Annotation-unification", existing_ids)
            existing_ids.add(ann_id)
            exporter.add_annotation(
                build_unification_annotation(
                    subject_spdx_id=survivor_id,
                    criterion=criterion,
                    unified_ids=list(rec["unified"]),
                    fragments=list(rec["fragments"]),
                    creation_info=creation_info,
                    annotation_spdx_id=ann_id,
                )
            )


def _add_model_sbom(main_doc: spdx3.SpdxDocument, exporter: Spdx3JsonExporter) -> None:
    """Add a second ``software_Sbom`` rooted at the merged ``ai_AIPackage``,
    when fragments contributed one -- "SBOM A describes the wheel, SBOM B
    describes the model", both inside the same SpdxDocument."""
    ai_packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.ai_AIPackage)
    ]
    if not ai_packages:
        return

    # Deterministic root choice when more than one AIPackage survives merge.
    root_pkg = min(ai_packages, key=require_spdx_id)

    namespace = main_doc.spdxId
    if namespace is None:
        return
    existing_ids = set(exporter.object_set.obj_by_id.keys())
    sbom_id = _mint_extra_id(namespace, "Sbom", existing_ids)

    model_sbom = spdx3.software_Sbom(
        spdxId=sbom_id,
        creationInfo=main_doc.creationInfo,
        rootElement=[require_spdx_id(root_pkg)],
    )
    model_sbom.software_sbomType = [spdx3.software_SbomType.build]
    exporter.add_sbom(model_sbom)

    root_elements = list(main_doc.rootElement or [])
    root_elements.append(require_spdx_id(model_sbom))
    main_doc.rootElement = root_elements


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def merge_fragments(
    project_dir: Path,
    fragment_files: list[str],
    exporter: Spdx3JsonExporter,
) -> None:
    """Load SPDX 3 JSON-LD fragment files and merge them into the exporter.

    Each fragment is a standalone SPDX document (e.g., produced by
    ``pitloom.loom.run``). Its elements are unified against the exporter's
    existing content and against every other fragment already merged (see
    the module docstring for the unification policy), then added to the
    exporter's object set.

    Missing or unreadable fragment files are logged as warnings; they do not
    raise exceptions so that the rest of the SBOM is still produced.

    When *exporter* holds a main ``SpdxDocument`` (i.e. this is a full
    project build, not a bare/standalone merge), two further passes run
    after all fragments are merged: ``profileConformance`` gains ``ai``/
    ``dataset`` when fragments contributed those element types, and -- when
    an ``ai_AIPackage`` survived the merge -- a second ``software_Sbom``
    rooted at it is added alongside the main one.

    Args:
        project_dir: Project root used to resolve relative fragment paths.
        fragment_files: List of paths to fragment files, relative to
            ``project_dir``.
        exporter: The exporter whose object set receives the merged elements.
    """
    index = _MergeIndex(exporter)
    events: _UnificationEvents = {}
    fragment_imports: list[spdx3.ExternalMap] = []
    seen_import_ids: set[str] = set()

    for fragment_file in fragment_files:
        fragment_path = project_dir / fragment_file
        if not fragment_path.exists():
            log.warning("Configured SBOM fragment %s not found.", fragment_path)
            continue
        try:
            with open(fragment_path, "rb") as f:
                fragment_set = spdx3.SHACLObjectSet()
                spdx3.JSONLDDeserializer().read(f, fragment_set)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning("Failed to ingest SBOM fragment %s: %s", fragment_path, exc)
            continue

        frag_doc_id = _find_fragment_document_id(fragment_set)
        if frag_doc_id and frag_doc_id not in seen_import_ids:
            seen_import_ids.add(frag_doc_id)
            fragment_imports.append(
                spdx3.ExternalMap(
                    externalSpdxId=frag_doc_id,
                    locationHint=fragment_file,
                )
            )

        _merge_fragment_set(fragment_set, index, fragment_file, events)

    _dedupe_relationships(exporter)

    main_doc = _find_main_document(exporter.object_set)
    if main_doc is not None:
        _update_profile_conformance(main_doc, exporter)
        _add_fragment_imports(main_doc, fragment_imports)
        _emit_unification_annotations(events, main_doc, exporter)
        _add_model_sbom(main_doc, exporter)
