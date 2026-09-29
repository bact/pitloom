# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM-element harvest helpers for :class:`~pitloom.id_registry.IdRegistry`.

See also: :mod:`pitloom.id_registry._types` for the registry dataclasses,
:mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself (imports
from here -- see the ``TYPE_CHECKING``-only import below for how the
resulting cycle is avoided).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.id_registry._ambiguous import _ambiguous_entity_keys, _compact_type_of
from pitloom.id_registry._types import (
    PACKAGE_ENTITY_TYPE,
    EntityEntry,
    FileEntry,
    _entity_key,
    _sha256_from_verified_using,
)

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

__all__ = [
    "_SpdxIdIndex",
    "_harvest_elements",
    "_import_sbom_element",
    "_is_files_path_alias",
    "_release_stale_keys_for_id",
    "_sorted_by_spdx_id",
]


def _sorted_by_spdx_id(object_set: spdx3.SHACLObjectSet) -> list[Any]:
    """Return *object_set*'s objects sorted by ``spdxId`` for deterministic
    iteration (``SHACLObjectSet.objects`` is an unordered set).

    Not canonical for SBOM output: this order never feeds hashed or
    serialized SBOM content -- unlike
    :func:`pitloom.assemble.spdx3._fragments_unify._canonical_merge_key`,
    whose order does determine SBOM output content. It is still
    load-bearing for :class:`~pitloom.id_registry.IdRegistry` bookkeeping,
    though: when an imported SBOM carries more than one ``SpdxDocument``
    element, :meth:`~pitloom.id_registry.IdRegistry.import_sbom` takes the
    first one in this order as ``self.namespace`` (see its loop over
    ``sorted_objects``), and that namespace is itself persisted by
    :meth:`~pitloom.id_registry.IdRegistry.save`. Changing this key is
    safe for the common single-document case, but can change which
    namespace gets picked -- and persisted -- for a multi-document input.
    """
    return sorted(object_set.objects, key=lambda o: getattr(o, "spdxId", None) or "")


def _is_files_path_alias(path_a: str, path_b: str) -> bool:
    """True if *path_a*/*path_b* are the intentional physical-path/
    distribution-path dual-keying for a single src/-layout file: their
    :class:`~pathlib.PurePosixPath` parts tail-match, one a strict suffix
    of the other (e.g. ``src/pkg/x.py`` vs ``pkg/x.py``) -- not merely two
    unrelated paths that happen to end in the same filename (e.g.
    ``demo/a/__init__.py`` vs ``demo/c/__init__.py``, whose last two parts
    already differ)."""
    parts_a = PurePosixPath(path_a).parts
    parts_b = PurePosixPath(path_b).parts
    shorter, longer = (
        (parts_a, parts_b) if len(parts_a) <= len(parts_b) else (parts_b, parts_a)
    )
    return bool(shorter) and longer[-len(shorter) :] == shorter


@dataclass
class _SpdxIdIndex:
    """``spdx_id -> keys`` reverse index for a registry's ``files``/
    ``entities`` tables, scoped to one
    :meth:`~pitloom.id_registry.IdRegistry._harvest_sorted` pass and kept
    in sync as entries are added/removed during it.

    :func:`_release_stale_keys_for_id` uses this to find every OTHER key
    already sharing a given id in O(keys sharing that id), instead of
    scanning the whole ``files``/``entities`` table (and computing
    :func:`_is_files_path_alias` against every candidate, matching or
    not) on every harvested element -- O(harvested elements * registry
    size) over a full pass otherwise.
    """

    files: dict[str, set[str]] = field(default_factory=dict)
    entities: dict[str, set[tuple[str, str]]] = field(default_factory=dict)

    @classmethod
    def from_registry(cls, registry: IdRegistry) -> _SpdxIdIndex:
        """Build the index from *registry*'s current table contents."""
        files: dict[str, set[str]] = {}
        for path, file_entry in registry.files.items():
            files.setdefault(file_entry.spdx_id, set()).add(path)
        entities: dict[str, set[tuple[str, str]]] = {}
        for key, entity_entry in registry.entities.items():
            entities.setdefault(entity_entry.spdx_id, set()).add(key)
        return cls(files=files, entities=entities)

    def set_file(self, registry: IdRegistry, path: str, entry: FileEntry) -> None:
        """Write *entry* to ``registry.files[path]``, keeping this index
        in sync with both the old spdx_id (if *path* already had a
        different one) and the new one."""
        old = registry.files.get(path)
        if old is not None:
            self.files.get(old.spdx_id, set()).discard(path)
        registry.files[path] = entry
        self.files.setdefault(entry.spdx_id, set()).add(path)

    def drop_file(self, registry: IdRegistry, spdx_id: str, path: str) -> None:
        """Delete ``registry.files[path]``, keeping this index in sync."""
        del registry.files[path]
        self.files.get(spdx_id, set()).discard(path)

    def set_entity(
        self, registry: IdRegistry, key: tuple[str, str], entry: EntityEntry
    ) -> None:
        """Write *entry* to ``registry.entities[key]``, keeping this
        index in sync with both the old spdx_id (if *key* already had a
        different one) and the new one."""
        old = registry.entities.get(key)
        if old is not None:
            self.entities.get(old.spdx_id, set()).discard(key)
        registry.entities[key] = entry
        self.entities.setdefault(entry.spdx_id, set()).add(key)

    def drop_entity(
        self, registry: IdRegistry, spdx_id: str, key: tuple[str, str]
    ) -> None:
        """Delete ``registry.entities[key]``, keeping this index in sync."""
        del registry.entities[key]
        self.entities.get(spdx_id, set()).discard(key)


def _release_stale_keys_for_id(
    registry: IdRegistry,
    spdx_id: str,
    index: _SpdxIdIndex,
    *,
    files_key: str | None = None,
    files_sha256: str | None = None,
    entity_key: tuple[str, str] | None = None,
) -> None:
    """Enforce the one-key-per-id registry invariant before a harvested
    element claims *spdx_id*: drop any OTHER key, in either
    :attr:`IdRegistry.files` or :attr:`IdRegistry.entities`, that already
    holds this exact id but genuinely refers to something else.

    Two registry keys sharing one id is never legitimate for two
    *different* elements: a lookup by either key would hand back the same
    spdxId for what the caller treats as two distinct elements, so a
    later document that looks up both would emit one duplicate-id element
    instead of two. A stale key holding this id is itself evidence of an
    earlier harvest picking one arbitrary winner among several source
    elements that happened to share an id -- dropping it here stops that
    transient duplicate from calcifying into a permanent double-entry the
    next time this exact id is (re-)harvested.

    *index* is *registry*'s current ``spdx_id -> keys`` reverse index
    (:class:`_SpdxIdIndex`) -- every candidate this checks already shares
    *spdx_id*, so the more expensive sha256/alias check below only ever
    runs for genuine collision candidates, never the whole table.

    A *files* entry is only kept when BOTH its recorded ``sha256``
    matches *files_sha256* AND its path is a :func:`_is_files_path_alias`
    of *files_key* -- the intentional physical-path/distribution-path
    dual-keying for a single src/-layout file (see
    ``pitloom.core.project.project_relative_or_fallback``'s docstring and
    ``_add_package_files()``'s two-path lookup). Same content but
    unrelated paths (e.g. two different same-content empty
    ``__init__.py`` files) is NOT that alias and is dropped like any
    other stale key -- matching content alone is not sufficient evidence
    of the same file under two names. No alias case exists for entities,
    so any other entities key sharing the id is always dropped.
    *files_key*/*entity_key* is the key about to claim *spdx_id* and is
    excluded from its own removal either way.
    """
    for path in list(index.files.get(spdx_id, ())):
        if path == files_key:
            continue
        file_entry = registry.files[path]
        is_alias = (
            files_key is not None
            and file_entry.sha256 == files_sha256
            and _is_files_path_alias(path, files_key)
        )
        if not is_alias:
            index.drop_file(registry, spdx_id, path)
    for key in list(index.entities.get(spdx_id, ())):
        if key != entity_key:
            index.drop_entity(registry, spdx_id, key)


def _harvest_elements(
    registry: IdRegistry, sorted_objects: Iterable[Any]
) -> frozenset[tuple[str, str]]:
    """Harvest every element of *sorted_objects* into *registry*, leaving
    each :func:`_ambiguous_entity_keys` key untouched.

    Returns the skipped (ambiguous) keys; each is logged once at DEBUG.
    Run auto-harvest passes no element that never looked the registry up
    (see :func:`_ambiguous_entity_keys`).
    """
    objects = list(sorted_objects)
    ambiguous = _ambiguous_entity_keys(objects)
    for type_name, name in sorted(ambiguous):
        log.debug(
            "ID registry: not harvested (%s name held by several elements): %r",
            type_name,
            name,
        )
    index = _SpdxIdIndex.from_registry(registry)
    for obj in objects:
        _import_sbom_element(registry, obj, index, ambiguous_keys=ambiguous)
    return ambiguous


def _import_sbom_element(
    registry: IdRegistry,
    obj: Any,
    index: _SpdxIdIndex | None = None,
    *,
    ambiguous_keys: frozenset[tuple[str, str]] = frozenset(),
) -> None:
    """Harvest a single deserialized SBOM element into *registry*.

    The ``entities`` storage key goes through
    :func:`~pitloom.id_registry._types._entity_key`, same as every other
    reader/writer -- see its docstring for the
    :data:`~pitloom.id_registry._types.PACKAGE_ENTITY_TYPE` canonicalization
    this applies. The element's own ``.name`` field (what the SBOM
    actually displays) is untouched; only the registry's storage key is
    canonicalized.

    A key that already maps to a *different* id keeps its own entry, but
    :func:`_release_stale_keys_for_id` is called afterwards so a
    newly-assigned id first drops any other key that already held it --
    see that function's docstring for why one id can never legitimately
    back two registry keys.

    A key in *ambiguous_keys* (see :func:`_ambiguous_entity_keys`) is
    skipped outright: its existing entry, if any, stays and nothing is
    released for it.

    *index* is the ``spdx_id -> keys`` reverse index
    :func:`_release_stale_keys_for_id` needs --
    :func:`_harvest_elements` builds one and threads it through every
    element in its pass, so it's built once, not once per element. A
    direct caller (e.g. harvesting a single element outside a batch pass)
    can omit it and gets one freshly built from *registry*'s current
    contents, same result either way.
    """
    name = getattr(obj, "name", None)
    spdx_id = getattr(obj, "spdxId", None)
    if not name or not spdx_id:
        return
    if index is None:
        index = _SpdxIdIndex.from_registry(registry)

    compact_type = _compact_type_of(obj)

    if compact_type != PACKAGE_ENTITY_TYPE:
        sha256 = _sha256_from_verified_using(obj)
        if sha256 is not None:
            _release_stale_keys_for_id(
                registry, spdx_id, index, files_key=name, files_sha256=sha256
            )
            index.set_file(registry, name, FileEntry(spdx_id=spdx_id, sha256=sha256))
            return

    if compact_type == "object":
        log.debug("Import: skipping %r (no SPDX 3 compact type)", name)
        return
    key = _entity_key(name, compact_type)
    if key in ambiguous_keys:
        return
    _release_stale_keys_for_id(registry, spdx_id, index, entity_key=key)
    index.set_entity(registry, key, EntityEntry(spdx_id=spdx_id))
