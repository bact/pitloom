# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM-element harvest helpers for :class:`~pitloom.id_registry.IdRegistry`.

See also: :mod:`pitloom.id_registry._types` for the registry dataclasses,
:mod:`pitloom.id_registry._ambiguous` for the keys left out,
:mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself (it imports
this module, so the reverse import is ``TYPE_CHECKING``-only).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeGuard

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.hashes import sha256_of
from pitloom.id_registry._ambiguous import (
    MODEL_NOT_RECORDED_INFO,
    DerivedKeys,
    KeptPairs,
    RecordedKeys,
    WrittenKey,
    _ambiguous_keys,
    _written_key,
    ambiguous_keys_message,
    unique_file_keys,
)
from pitloom.id_registry._types import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    RegistryEntry,
    is_utf8_text,
    unencodable_message,
)
from pitloom.logging_config import loggable

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

#: The types a lookup always gates on content: the only ones a run's harvest
#: records a SHA-256 for. Any other type's hash is ignored (a package's
#: Merkle root differs between a project and its wheel, and would flip the
#: entry).
_GATED_TYPES = frozenset({AI_PACKAGE_TYPE, FILE_TYPE})
#: The types whose recorded SHA-256 an unhashed element of the same id
#: keeps: the gated ones, and a dataset package (its hash is recorded by
#: ``id import`` and ``id generate -e`` only, never by a run's harvest).
_HASH_KEPT_TYPES = _GATED_TYPES | {DATASET_PACKAGE_TYPE}

__all__ = [
    "_SpdxIdIndex",
    "_harvest_elements",
    "_import_sbom_element",
    "_release_stale_keys_for_id",
    "_sorted_by_spdx_id",
    "content_gate_message",
]


def _sorted_by_spdx_id(object_set: spdx3.SHACLObjectSet) -> list[Any]:
    """Return *object_set*'s objects sorted by ``spdxId`` for deterministic
    iteration (``SHACLObjectSet.objects`` is an unordered set).

    Never feeds SBOM output, but it is load-bearing for the registry: an
    imported SBOM with several ``SpdxDocument`` elements has the first in
    this order adopted as the namespace
    (:meth:`~pitloom.id_registry.IdRegistry.import_sbom`), which is then
    persisted. Changing the key can change that namespace.
    """
    return sorted(object_set.objects, key=lambda o: getattr(o, "spdxId", None) or "")


@dataclass
class _SpdxIdIndex:
    """``spdx_id -> keys`` reverse index for a registry's ``elements``
    table, built per :func:`_harvest_elements` pass and kept in sync as
    entries are added or removed during it.

    :func:`_release_stale_keys_for_id` uses it to find every OTHER key
    sharing an id without scanning the whole table per harvested element.
    """

    keys: dict[str, set[tuple[str, str]]] = field(default_factory=dict)

    @classmethod
    def from_registry(cls, registry: IdRegistry) -> _SpdxIdIndex:
        """Build the index from *registry*'s current table contents."""
        keys: dict[str, set[tuple[str, str]]] = {}
        for key, entry in registry.elements.items():
            keys.setdefault(entry.spdx_id, set()).add(key)
        return cls(keys=keys)

    def set_entry(
        self, registry: IdRegistry, key: tuple[str, str], entry: RegistryEntry
    ) -> None:
        """Write *entry* to ``registry.elements[key]``, keeping this index
        in sync with both the old spdx_id (if *key* had another) and the
        new one."""
        old = registry.elements.get(key)
        if old is not None:
            self.keys.get(old.spdx_id, set()).discard(key)
        registry.elements[key] = entry
        self.keys.setdefault(entry.spdx_id, set()).add(key)

    def drop(self, registry: IdRegistry, spdx_id: str, key: tuple[str, str]) -> None:
        """Delete ``registry.elements[key]``, keeping this index in sync."""
        del registry.elements[key]
        self.keys.get(spdx_id, set()).discard(key)


def _release_stale_keys_for_id(
    registry: IdRegistry,
    spdx_id: str,
    index: _SpdxIdIndex,
    *,
    key: tuple[str, str],
) -> None:
    """Enforce one key per id before *key* claims *spdx_id*: drop every
    OTHER key that already holds this exact id, a layout alias included
    (the run's lookup key replacing it is a promotion).

    Two keys sharing one id would make a later document emit one
    duplicate-id element for what are two elements; a stale holder is the
    leftover of an earlier harvest that picked one winner, and dropping it
    stops that from becoming permanent. *index* is *registry*'s current
    reverse index.
    """
    for other in list(index.keys.get(spdx_id, ())):
        if other != key:
            index.drop(registry, spdx_id, other)


def _held_under(
    index: _SpdxIdIndex, spdx_id: str, written: WrittenKey
) -> list[tuple[str, str]]:
    """The other keys of *written*'s type holding *spdx_id*, sorted; none
    for a recorded key (R-keep applies to a name only)."""
    if written.recorded:
        return []
    key = written.key
    return sorted(
        other
        for other in index.keys.get(spdx_id, ())
        if other[0] == key[0] and other != key
    )


#: R-keep's skipped (spdxId, written key) pairs -> the first key, sorted,
#: holding that id that no written element moves (:func:`_r_kept`).
_KeptBy = dict[tuple[str, tuple[str, str]], tuple[str, str]]


def _log_r_kept(written: WrittenKey, held: tuple[str, str], *, imported: bool) -> None:
    """The one line for an element R-keep skips, its id held under *held*:
    an ``INFO:`` for ``id import`` (*imported*), DEBUG for a run's merged
    fragment."""
    log.log(
        logging.INFO if imported else logging.DEBUG,
        "ID registry: %s %r not %s: its id is held under %r",
        written.key[0],
        written.key[1],
        "imported" if imported else "harvested",
        held[1],
    )


def _r_kept(
    index: _SpdxIdIndex, objects: list[Any], keys: RecordedKeys | None
) -> _KeptBy:
    """The (spdxId, written key) pairs of *objects* R-keep skips, decided
    once before the pass so the spdxId order never changes them: the
    element's id is its own in *objects* and is held (*index*, before the
    pass) under a key of its type no element is written under, so no write
    moves or drops it. A skipped element writes nothing, so its key frees
    no id either: repeated until no pair is added."""
    found = [
        (str(obj.spdxId), key)
        for obj in objects
        if (key := _written_key(obj, keys)) is not None
    ]
    ids = Counter(spdx_id for spdx_id, _ in found)
    held = {
        (spdx_id, key.key): others
        for spdx_id, key in found
        if ids[spdx_id] == 1 and (others := _held_under(index, spdx_id, key))
    }
    kept: _KeptBy = {}
    while True:
        targets = {key.key for spdx_id, key in found if (spdx_id, key.key) not in kept}
        now = {
            pair: free[0]
            for pair, others in held.items()
            if (free := [other for other in others if other not in targets])
        }
        if now.keys() == kept.keys():
            return kept
        kept = now


@dataclass(frozen=True)
class _Pass:
    """What a harvest pass decides before any write: the registry's reverse
    *index*, R-keep's *kept* (:func:`_r_kept`) and the *ambiguous* keys
    (:func:`~pitloom.id_registry._ambiguous._ambiguous_keys`)."""

    index: _SpdxIdIndex
    kept: _KeptBy
    ambiguous: frozenset[tuple[str, str]]

    @classmethod
    def of(
        cls,
        registry: IdRegistry,
        objects: list[Any],
        keys: RecordedKeys | None,
        stale: KeptPairs = frozenset(),
    ) -> _Pass:
        """The pass over *objects*, *stale* pairs never written."""
        index = _SpdxIdIndex.from_registry(registry)
        kept = _r_kept(index, objects, keys)
        ambiguous = _ambiguous_keys(objects, keys, kept=kept.keys() | stale)
        return cls(index, kept, ambiguous)


def _model_file_keys(
    registry: IdRegistry, objects: list[Any], keys: RecordedKeys | None
) -> tuple[list[Any], RecordedKeys | None]:
    """A run's *objects* and *keys*, each hashed ``ai_AIPackage`` with no
    recorded key (a merged fragment's model) keyed by the one file of
    *objects* holding its SHA-256
    (:func:`~pitloom.id_registry._ambiguous.unique_file_keys`), a derived
    key; with none, it is left out: its id reserved, one
    :data:`~pitloom.id_registry._ambiguous.MODEL_NOT_RECORDED_INFO`. Never
    its name: a pathful model's name entry would outlive a retrain."""
    files = unique_file_keys(objects, keys)
    derived: dict[str, tuple[str, str]] = {}
    passed = []
    for obj in objects:
        written = _written_key(obj, keys)
        sha = sha256_of(obj)
        if written is None or written.recorded or written.key[0] != AI_PACKAGE_TYPE:
            passed.append(obj)
        elif sha is None:
            passed.append(obj)  # ungated: its name, as any unhashed element
        elif (file_key := files.get(sha)) is not None:
            derived[str(obj.spdxId)] = (AI_PACKAGE_TYPE, file_key)
            passed.append(obj)
        else:
            registry.reserve_id(str(obj.spdxId))
            log.info(MODEL_NOT_RECORDED_INFO, loggable(str(obj.name)))
    if not derived:
        return passed, keys
    recorded = [spdx_id for spdx_id in keys or {} if spdx_id not in derived]
    return passed, DerivedKeys({**(keys or {}), **derived}, recorded=recorded)


def _stale(
    objects: list[Any], keys: RecordedKeys | None
) -> dict[str, tuple[tuple[str, str], str]]:
    """spdxId -> (written key, the other element's id) of each hashed
    :data:`_GATED_TYPES` element with no recorded key whose key an element
    with a recorded key and another SHA-256 is written under: the run's
    own lookup is the current content, so the other is never written and
    blocks nothing."""
    current: dict[tuple[str, str], tuple[str | None, str]] = {}
    unrecorded = []
    for obj in objects:
        written = _written_key(obj, keys)
        if written is None or written.key[0] not in _GATED_TYPES:
            continue
        sha = sha256_of(obj)
        if written.recorded:
            current.setdefault(written.key, (sha, str(obj.spdxId)))
        elif sha is not None:
            unrecorded.append((str(obj.spdxId), written.key, sha))
    return {
        spdx_id: (key, current[key][1])
        for spdx_id, key, sha in unrecorded
        if key in current and current[key][0] != sha
    }


def _harvest_elements(
    registry: IdRegistry,
    sorted_objects: Iterable[Any],
    *,
    imported: bool,
    keys: RecordedKeys | None = None,
) -> frozenset[tuple[str, str]]:
    """Harvest every element of *sorted_objects* into *registry*, leaving
    each :func:`~pitloom.id_registry._ambiguous._ambiguous_keys` key
    untouched; an element R-keep skips (:func:`_r_kept`) or a stale one
    (:func:`_stale`) neither counts toward nor blocks one. *imported*: ``id
    import`` (see :func:`_import_sbom_element`), else a run's auto-harvest,
    which first keys its fragment models (:func:`_model_file_keys`).
    *keys*: the keys the run's lookups recorded, or (``id import``) the
    ones :func:`~pitloom.id_registry.import_keys.import_keys` derived.

    Returns the skipped (ambiguous) keys, logged in one DEBUG record. A
    run's auto-harvest passes no element that never looked the registry up
    (see :func:`~pitloom.id_registry._ambiguous._ambiguous_keys`).
    """
    objects = list(sorted_objects)
    if not imported:
        objects, keys = _model_file_keys(registry, objects, keys)
    stale = _stale(objects, keys)
    state = _Pass.of(registry, objects, keys, {(i, k) for i, (k, _) in stale.items()})
    if state.ambiguous:
        log.debug("%s", ambiguous_keys_message("not harvested", state.ambiguous))
    for obj in objects:
        spdx_id = str(getattr(obj, "spdxId", None))
        if spdx_id in stale:
            registry.reserve_id(spdx_id)
            key, current = stale[spdx_id]
            log.info("%s", content_gate_message(key, spdx_id, current, older=True))
            continue
        _import_sbom_element(registry, obj, state, imported=imported, keys=keys)
    return state.ambiguous


def content_gate_message(
    key: tuple[str, str],
    spdx_id: str,
    held: str,
    *,
    imported: bool = False,
    older: bool = False,
) -> str:
    """The one line for an element *spdx_id* a content-gated *key* (held by
    *held*) decides: unhashed, with another id than the hashed entry,
    ``id import`` replaced the entry (*imported*) or a run's harvest left
    it as is; with no recorded key and a SHA-256 other than the entry's
    (*older*: a merged fragment's), a run's harvest left it as is."""
    subject = f"{key[0]} {key[1]!r}"
    if imported:
        return (
            f"ID registry: content gate dropped for {subject}: "
            f"imported id {spdx_id} replaces {held}"
        )
    element = (
        f"element id {spdx_id} with an older SHA-256"
        if older
        else f"harvested id {spdx_id}"
    )
    return (
        f"ID registry: content gate kept for {subject}: "
        f"{element} not recorded over {held}"
    )


def _stale_over(
    existing: RegistryEntry | None,
    sha256: str | None,
    written: WrittenKey,
    *,
    imported: bool,
) -> TypeGuard[RegistryEntry]:
    """Whether a run's harvest leaves *existing* as is for an element with
    no recorded key (a merged fragment's) whose *sha256* is not the one
    *existing* records: the fragment's content is older than the entry's,
    which ``id generate`` or a run's own lookup wrote. ``id import`` and a
    recorded key (a retrain) replace it."""
    return (
        not imported
        and not written.recorded
        and sha256 is not None
        and existing is not None
        and existing.sha256 is not None
        and existing.sha256 != sha256
    )


def _own_sha256(obj: Any, type_name: str, *, imported: bool) -> str | None:
    """The SHA-256 of *obj* harvest records: for a :data:`_GATED_TYPES`
    element, and on ``id import`` for a dataset package too; else none."""
    types = _HASH_KEPT_TYPES if imported else _GATED_TYPES
    return sha256_of(obj) if type_name in types else None


def _import_sbom_element(
    registry: IdRegistry,
    obj: Any,
    state: _Pass | None = None,
    *,
    imported: bool = False,
    keys: RecordedKeys | None = None,
) -> None:
    """Harvest a single deserialized SBOM element into *registry*.

    Records, never classifies: an element with an id, a name and a compact
    type other than ``"object"`` is written under the key *keys* holds for
    it (its run's lookup recorded it, or ``id import`` derived it), else
    its type and name (:func:`~pitloom.id_registry._ambiguous._written_key`).
    A :data:`_GATED_TYPES` entry gets the element's SHA-256
    (:func:`~pitloom.export.hashes.sha256_of`), or none, and so does an
    imported dataset package; any other type never gets one of its own.
    The element's own ``.name`` is untouched; only the key is
    canonicalised.

    In order: its id is reserved
    (:meth:`~pitloom.id_registry.IdRegistry.reserve_id`) -- an id seen in
    the registry's namespace is never minted for another key, the element
    skipped or not; an unencodable key or id, and an ambiguous key
    (*state*), is skipped outright (its existing entry, if any,
    stays); an element with no recorded key whose id another key of its
    type holds, one no element of the pass moves, is skipped (*state*'s
    R-keep: that key stays, a merged fragment's or an imported element's name never
    re-keys a pinned path); the content gate;
    every other key holding the id is dropped
    (:func:`_release_stale_keys_for_id`); the entry is written.

    The harvested id wins: an entry already under the key is replaced. A
    hashed element replaces a gated entry's SHA-256; an unhashed one (in a
    run's harvest, a dataset package always is) with the entry's id keeps it
    (:data:`_HASH_KEPT_TYPES`). An unhashed one with another id over a
    hashed entry of those types: ``id import`` (*imported*) writes it with
    no SHA-256 and logs one ``INFO:``; a run's harvest never erases a
    recorded SHA-256, so it leaves the entry as is, also with one ``INFO:``
    (:func:`content_gate_message`).

    *state* is the pass :func:`_harvest_elements` decided; a direct
    caller may omit it and gets one for *obj* alone, from *registry*'s
    current contents.
    """
    written = _written_key(obj, keys)
    if written is None:
        if getattr(obj, "name", None) and getattr(obj, "spdxId", None):
            log.debug("Import: skipping %r (no SPDX 3 compact type)", obj.name)
        return
    key = written.key
    spdx_id = str(obj.spdxId)
    # Reserved even when the element is skipped: its id is never minted.
    registry.reserve_id(spdx_id)
    label = "key" if written.recorded else "name"
    for what, text in ((label, key[1]), ("spdxId", spdx_id)):
        if not is_utf8_text(text):
            log.warning("%s; skipped", unencodable_message(what, text))
            return
    if state is None:
        state = _Pass.of(registry, [obj], keys)
    if key in state.ambiguous:
        return
    if (held := state.kept.get((spdx_id, key))) is not None:
        _log_r_kept(written, held, imported=imported)
        return
    sha256 = _own_sha256(obj, key[0], imported=imported)
    existing = registry.elements.get(key)
    if _stale_over(existing, sha256, written, imported=imported):
        log.info("%s", content_gate_message(key, spdx_id, existing.spdx_id, older=True))
        return
    if (
        key[0] in _HASH_KEPT_TYPES
        and sha256 is None
        and existing is not None
        and existing.sha256
    ):
        if existing.spdx_id == spdx_id:
            sha256 = existing.sha256
        else:
            log.info(
                "%s",
                content_gate_message(key, spdx_id, existing.spdx_id, imported=imported),
            )
            if not imported:
                return
    _release_stale_keys_for_id(registry, spdx_id, state.index, key=key)
    state.index.set_entry(registry, key, RegistryEntry(spdx_id=spdx_id, sha256=sha256))
