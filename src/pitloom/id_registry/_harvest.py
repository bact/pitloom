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

from pitloom.export.spdx3_json import sha256_of
from pitloom.id_registry._ambiguous import (
    _ambiguous_keys,
    _element_key_of,
    ambiguous_keys_message,
)
from pitloom.id_registry._types import AI_PACKAGE_TYPE, FILE_TYPE, RegistryEntry

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

#: The types a lookup gates on content: the only ones harvest records a
#: SHA-256 for. Any other type's hash is ignored (a package's Merkle root
#: differs between a project and its wheel, and would flip the entry).
_GATED_TYPES = frozenset({AI_PACKAGE_TYPE, FILE_TYPE})

__all__ = [
    "_SpdxIdIndex",
    "_harvest_elements",
    "_import_sbom_element",
    "_is_alias",
    "_is_files_path_alias",
    "_release_stale_keys_for_id",
    "_sorted_by_spdx_id",
    "content_gate_message",
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
    """``spdx_id -> keys`` reverse index for a registry's ``elements``
    table, scoped to one
    :meth:`~pitloom.id_registry.IdRegistry._harvest_sorted` pass and kept
    in sync as entries are added/removed during it.

    :func:`_release_stale_keys_for_id` uses this to find every OTHER key
    already sharing a given id in O(keys sharing that id), instead of
    scanning the whole table (and computing :func:`_is_files_path_alias`
    against every candidate) on every harvested element.
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


def _is_alias(
    kept: tuple[str, str],
    kept_sha256: str | None,
    claiming: tuple[str, str],
    sha256: str | None,
) -> bool:
    """Whether *kept* is the src-layout alias of *claiming*: the same type,
    the same non-empty SHA-256, and names that are path suffixes of each
    other (:func:`_is_files_path_alias`)."""
    return (
        kept[0] == claiming[0]
        and bool(sha256)
        and kept_sha256 == sha256
        and _is_files_path_alias(kept[1], claiming[1])
    )


def _release_stale_keys_for_id(
    registry: IdRegistry,
    spdx_id: str,
    index: _SpdxIdIndex,
    *,
    key: tuple[str, str],
    sha256: str | None,
) -> None:
    """Enforce one key per id before *key* claims *spdx_id*: drop every
    OTHER key that already holds this exact id.

    Two keys sharing one id is never legitimate for two *different*
    elements: a lookup by either would hand back the same spdxId for what
    the caller treats as two elements, so a later document that looks up
    both would emit one duplicate-id element instead of two. A stale key
    holding this id is evidence of an earlier harvest picking one winner
    among several elements that shared an id; dropping it here stops that
    duplicate from becoming permanent.

    The one exception is the src-layout alias (:func:`_is_alias`): the
    physical and the distribution path of one file, same type and same
    content (see ``pitloom.core.project.project_relative_or_fallback``).
    Same content under unrelated paths (two empty ``__init__.py`` files)
    is not that alias and is dropped. *index* is *registry*'s current
    reverse index (:class:`_SpdxIdIndex`), so only keys already sharing
    *spdx_id* are checked.
    """
    for other in list(index.keys.get(spdx_id, ())):
        if other == key:
            continue
        if not _is_alias(other, registry.elements[other].sha256, key, sha256):
            index.drop(registry, spdx_id, other)


def _harvest_elements(
    registry: IdRegistry, sorted_objects: Iterable[Any], *, imported: bool
) -> frozenset[tuple[str, str]]:
    """Harvest every element of *sorted_objects* into *registry*, leaving
    each :func:`~pitloom.id_registry._ambiguous._ambiguous_keys` key
    untouched. *imported*: ``id import`` (see :func:`_import_sbom_element`),
    else a run's auto-harvest.

    Returns the skipped (ambiguous) keys, logged in one DEBUG record.
    Run auto-harvest passes no element that never looked the registry up
    (see :func:`~pitloom.id_registry._ambiguous._ambiguous_keys`).
    """
    objects = list(sorted_objects)
    ambiguous = _ambiguous_keys(objects)
    if ambiguous:
        log.debug("%s", ambiguous_keys_message("not harvested", ambiguous))
    index = _SpdxIdIndex.from_registry(registry)
    for obj in objects:
        _import_sbom_element(
            registry, obj, index, ambiguous_keys=ambiguous, imported=imported
        )
    return ambiguous


def content_gate_message(
    key: tuple[str, str], spdx_id: str, held: str, *, imported: bool
) -> str:
    """The one line for an unhashed element whose id *spdx_id* differs from
    the hashed entry *held* under the content-gated *key*: ``id import``
    replaced the entry (*imported*), or a run's harvest left it as is."""
    subject = f"{key[0]} {key[1]!r}"
    if imported:
        return (
            f"ID registry: content gate dropped for {subject}: "
            f"imported id {spdx_id} replaces {held}"
        )
    return (
        f"ID registry: content gate kept for {subject}: "
        f"harvested id {spdx_id} not recorded over {held}"
    )


def _import_sbom_element(
    registry: IdRegistry,
    obj: Any,
    index: _SpdxIdIndex | None = None,
    *,
    ambiguous_keys: frozenset[tuple[str, str]] = frozenset(),
    imported: bool = False,
) -> None:
    """Harvest a single deserialized SBOM element into *registry*.

    Records, never classifies: a named element with an id and a compact
    type other than ``"object"`` is written under its own key
    (:func:`~pitloom.id_registry._ambiguous._element_key_of`). A
    :data:`_GATED_TYPES` entry gets the element's SHA-256
    (:func:`~pitloom.export.spdx3_json.sha256_of`), or none; any other type
    never gets one. The element's own ``.name`` is untouched; only the key
    is canonicalised.

    The harvested id wins: an entry already under the key is replaced,
    and :func:`_release_stale_keys_for_id` first drops any other key that
    held the new id. A hashed element replaces a gated entry's SHA-256; an
    unhashed one with the entry's id keeps it. An unhashed one with
    another id over a hashed entry: ``id import`` (*imported*) writes it
    with no SHA-256 and logs one ``INFO:``; a run's harvest never erases a
    recorded SHA-256, so it leaves the entry as is, also with one ``INFO:``
    (:func:`content_gate_message`).

    A key in *ambiguous_keys* is skipped outright: its existing entry, if
    any, stays and nothing is released for it. Its id, as every id read
    here, is still reserved (:meth:`~pitloom.id_registry.IdRegistry.reserve_id`):
    an id seen in the registry's namespace is never minted for another key.

    *index* is the reverse index :func:`_release_stale_keys_for_id`
    needs; :func:`_harvest_elements` builds one per pass. A direct caller
    may omit it and gets one built from *registry*'s current contents.
    """
    key = _element_key_of(obj)
    if key is None:
        if getattr(obj, "name", None) and getattr(obj, "spdxId", None):
            log.debug("Import: skipping %r (no SPDX 3 compact type)", obj.name)
        return
    spdx_id = str(obj.spdxId)
    registry.reserve_id(spdx_id)
    if key in ambiguous_keys:
        return
    gated = key[0] in _GATED_TYPES
    sha256 = sha256_of(obj) if gated else None
    existing = registry.elements.get(key)
    if gated and sha256 is None and existing is not None and existing.sha256:
        if existing.spdx_id == spdx_id:
            sha256 = existing.sha256
        else:
            log.info(
                "%s",
                content_gate_message(key, spdx_id, existing.spdx_id, imported=imported),
            )
            if not imported:
                return
    if index is None:
        index = _SpdxIdIndex.from_registry(registry)
    _release_stale_keys_for_id(registry, spdx_id, index, key=key, sha256=sha256)
    index.set_entry(registry, key, RegistryEntry(spdx_id=spdx_id, sha256=sha256))
