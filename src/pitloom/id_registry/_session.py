# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``IdRegistrySession``: one document's registry lookups, first-claimant-wins.

See also: :mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself.
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType

from pitloom.core.untrusted_text import escape_display_controls
from pitloom.id_registry._registry import IdRegistry
from pitloom.id_registry._types import _require_names
from pitloom.id_registry.keys import (
    LAYOUT_ALIAS_HITS_INFO,
    Alias,
    LookupKey,
    alias_candidates,
    alias_tail,
)
from pitloom.logging_config import loggable

log = logging.getLogger("pitloom.id_registry")

__all__ = ["IdRegistrySession", "info_identity_unknown", "warn_claim_collision"]


def info_identity_unknown() -> None:
    """Log the one ``INFO:`` for a package whose identity is unknown: it is
    neither looked up in nor recorded into the declared registry."""
    log.info("ID registry: package identity unknown; not looked up or recorded")


def warn_claim_collision(spdx_id: str, first: str, second: str) -> None:
    """Log the one ``WARNING:`` for *spdx_id* wanted by *second* after *first*
    already took it; *second* mints its own id."""
    log.warning(
        "ID registry: %s is registered for both %s and %s; %s gets a new id",
        spdx_id,
        first,
        second,
        second,
    )


def _info_alias_tie(key: str, held: Sequence[str]) -> None:
    """Log the one ``INFO:`` for *key* matching more than one *held* layout
    alias with its content: none is reused."""
    log.info(
        "ID registry: %s matches more than one layout alias (%s); none reused",
        loggable(key),
        ", ".join(loggable(name) for name in held),
    )


def _spellings(names: Sequence[str]) -> list[str]:
    """Each of *names* as given, then display-escaped when that differs: a
    registry imported from an SBOM holds a name as the SBOM shows it."""
    spellings: list[str] = []
    for name in names:
        shown = escape_display_controls(name)
        spellings.extend((name, shown) if shown != name else (name,))
    return spellings


def _aliased(lookup: LookupKey, key: str, held: str) -> bool:
    """Whether *held* is a layout alias of *key* (a spelling of *lookup*'s)
    in ``lookup.alias``'s direction, below ``lookup.base``: ``CANONICAL``,
    *held* is *key*'s :func:`~pitloom.id_registry.keys.alias_tail`;
    ``LAYOUT``, the reverse."""
    if lookup.alias is Alias.CANONICAL:
        return alias_tail(key, lookup.base) == held
    return alias_tail(held, lookup.base) == key


def _held_aliases(
    registry: IdRegistry, type_name: str, lookup: LookupKey, sha256: str
) -> list[str]:
    """The held keys of *type_name* recording *sha256* that are
    :func:`_aliased` to either spelling of *lookup*'s key, sorted."""
    held: set[str] = set()
    for spelling in _spellings((lookup.key,)):
        key = unicodedata.normalize("NFC", spelling)
        held.update(
            name
            for name in alias_candidates(
                registry, type_name, key, sha256, base=lookup.base
            )
            if _aliased(lookup, key, name)
        )
    return sorted(held)


class IdRegistrySession:
    """One document's registry lookups, first-claimant-wins.

    Every element that would otherwise call ``registry.lookup`` directly,
    across an entire document build (files, directories, AI models, the
    project's own, dependency and phantom packages, deployed packages,
    loom fragments), instead goes through one shared session so a
    registry hit reused by two different elements is claimed by only the
    first -- see :meth:`lookup_key` and :meth:`lookup_id`.
    """

    def __init__(self, registry: IdRegistry | None) -> None:
        self._registry = registry
        #: spdxId -> the claimant key that first claimed it.
        self._claimed: dict[str, str] = {}
        #: spdxId -> (type name, raw key) it is harvested under.
        self._keys: dict[str, tuple[str, str]] = {}
        #: (type name, key) whose layout-alias tie was logged.
        self._ties: set[tuple[str, str]] = set()
        #: Claimed hits found through a layout alias.
        self._alias_hits = 0

    @property
    def registry(self) -> IdRegistry | None:
        """The underlying :class:`IdRegistry`, or ``None`` when none applies."""
        return self._registry

    def _claim(self, claimant: str, spdx_id: str) -> str | None:
        """Return *spdx_id* if nothing has claimed it yet in this session,
        recording the claim; otherwise log one collision ``WARNING:`` and
        return ``None`` (treated as a lookup miss by the caller, so it
        mints its own id instead).

        Two elements hitting one registry id happens when a stale entry
        outlives the element it named; reusing it for both would emit a
        duplicate spdxId. Only the first claimant (in the caller's
        iteration order, which must be deterministic) reuses it; each
        later one mints afresh.
        """
        first_claimant = self._claimed.get(spdx_id)
        if first_claimant is not None:
            warn_claim_collision(spdx_id, first_claimant, claimant)
            return None
        self._claimed[spdx_id] = claimant
        return spdx_id

    def lookup_id(
        self,
        claimant: str,
        type_name: str,
        names: Sequence[str],
        *,
        sha256: str | None = None,
        on_miss: Callable[[], None] | None = None,
    ) -> str | None:
        """Look up the id registered under *type_name* for the first of
        *names* that hits, claim it, and return it -- or ``None``.

        *names* (a package's or a directory's name) are tried in order,
        each as given, then display-escaped
        (:func:`~pitloom.core.untrusted_text.escape_display_controls`): a
        registry imported from an SBOM holds a name as the SBOM shows it,
        escaped. With *sha256*, only an entry recording that hash is a hit
        (see :meth:`~pitloom.id_registry.IdRegistry.lookup`). *on_miss* is
        called only when every name is a raw miss -- never when a hit
        exists but this session's claim is rejected (see :meth:`_claim`).
        Returns ``None`` immediately, without calling *on_miss*, when no
        registry is loaded in this session.
        """
        _require_names(names)
        if self._registry is None:
            return None
        spdx_id = self._registry.lookup(type_name, _spellings(names), sha256=sha256)
        if spdx_id is not None:
            return self._claim(claimant, spdx_id)
        if on_miss is not None:
            on_miss()
        return None

    def lookup_key(
        self,
        claimant: str,
        type_name: str,
        lookup: LookupKey,
        *,
        sha256: str | None = None,
        pin_without_hash: bool = False,
        miss_hashed: bool = False,
        on_miss: Callable[[], None] | None = None,
    ) -> str | None:
        """Look up the id registered under *type_name* for *lookup*, claim
        it, record the key it is harvested under, and return it -- or
        ``None``.

        In order: (1) ``lookup.key`` as given; (2) display-escaped
        (:func:`~pitloom.core.untrusted_text.escape_display_controls`), as
        :meth:`lookup_id` does; (3) only when both miss, ``lookup.alias`` is
        not ``NONE`` and *sha256* is given: the one held layout alias in
        ``lookup.alias``'s direction (either spelling, below
        ``lookup.base``) recording *sha256*
        (:func:`~pitloom.id_registry.keys.alias_candidates`); more than one
        is a miss with one ``INFO:`` per type and key in this session; (4)
        a hit is claimed (see :meth:`_claim`); (5) a claimed id records
        ``lookup.key`` (raw), or under ``LAYOUT`` the held key it matched
        (see :meth:`recorded_keys`). With *sha256*, only an entry recording
        that hash is a hit, or in (1) and (2) one recording none with
        *pin_without_hash* (see :meth:`IdRegistry.lookup`); without it, no
        alias is tried, and with *miss_hashed* an entry recording a hash
        misses. A claimed alias hit is counted
        (:meth:`info_layout_alias_hits`). *on_miss* is called on a miss,
        never on a rejected claim. Returns ``None`` without calling
        *on_miss* or recording when no registry is loaded.
        """
        registry = self._registry
        if registry is None:
            return None
        key = lookup.key
        spdx_id = registry.lookup(
            type_name,
            _spellings((key,)),
            sha256=sha256,
            pin_without_hash=pin_without_hash,
            miss_hashed=miss_hashed,
        )
        aliased = False
        if spdx_id is None and lookup.alias is not Alias.NONE and sha256 is not None:
            held = self._held_alias(registry, type_name, lookup, sha256)
            if held is not None:
                spdx_id = registry.lookup(type_name, (held,), sha256=sha256)
                key = held if lookup.alias is Alias.LAYOUT else key
                aliased = True
        if spdx_id is None:
            if on_miss is not None:
                on_miss()
            return None
        claimed = self._claim(claimant, spdx_id)
        if claimed is not None:
            self._keys[claimed] = (type_name, key)
            self._alias_hits += aliased
        return claimed

    def _held_alias(
        self, registry: IdRegistry, type_name: str, lookup: LookupKey, sha256: str
    ) -> str | None:
        """The one :func:`_held_aliases` key of *lookup*; ``None`` for none,
        and for more than one, with one ``INFO:`` per type and key in this
        session."""
        found = _held_aliases(registry, type_name, lookup, sha256)
        if len(found) <= 1:
            return found[0] if found else None
        tie = (type_name, lookup.key)
        if tie not in self._ties:
            self._ties.add(tie)
            _info_alias_tie(lookup.key, found)
        return None

    def info_layout_alias_hits(self) -> None:
        """Log the one ``INFO:`` counting this session's claimed hits found
        through a layout alias, if any
        (:data:`~pitloom.id_registry.keys.LAYOUT_ALIAS_HITS_INFO`)."""
        if self._alias_hits:
            log.info(LAYOUT_ALIAS_HITS_INFO, self._alias_hits)

    def record_key(self, spdx_id: str, type_name: str, key: str) -> None:
        """Record the raw (never display-escaped) *key* under *type_name*
        that *spdx_id*, minted after a miss, is harvested under. A key
        recorded by a hit (:meth:`lookup_key`) wins. No-op when no registry
        is loaded."""
        if self._registry is not None:
            self._keys.setdefault(spdx_id, (type_name, key))

    def recorded_keys(self) -> Mapping[str, tuple[str, str]]:
        """A read-only view of spdxId -> (type name, raw key) recorded by
        :meth:`lookup_key` and :meth:`record_key`; an id with no recorded
        key is absent."""
        return MappingProxyType(self._keys)

    def register_id(
        self, claimant: str, type_name: str, name: str, *, sha256: str
    ) -> str | None:
        """Register *name* under *type_name* with *sha256*
        (:meth:`~pitloom.id_registry.IdRegistry.register`) and claim the id
        for *claimant*, as a hit would be (see :meth:`_claim`): a later
        lookup hitting it in this session mints its own id.

        Raises:
            ValueError: no registry is loaded in this session.
        """
        if self._registry is None:
            raise ValueError("no ID registry loaded in this session")
        spdx_id = self._registry.register(type_name, name, sha256=sha256)
        return self._claim(claimant, spdx_id)

    def claimed_ids(self) -> list[str]:
        """Return every id claimed so far in this session, in claim order."""
        return list(self._claimed)
