# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``IdRegistrySession``: one document's registry lookups, first-claimant-wins.

See also: :mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

__all__ = ["IdRegistrySession"]


class IdRegistrySession:
    """One document's registry lookups, first-claimant-wins.

    Every element that would otherwise look ``registry.lookup_file``/
    ``lookup_entity`` up directly, across an entire document build (files,
    directories, AI models, deployed packages, loom fragments), instead
    goes through one shared session so a registry hit reused by two
    different elements is claimed by only the first -- see
    :meth:`file_id`/:meth:`entity_id`.
    """

    def __init__(self, registry: IdRegistry | None) -> None:
        self._registry = registry
        #: spdxId -> the claimant key that first claimed it.
        self._claimed: dict[str, str] = {}

    @property
    def registry(self) -> IdRegistry | None:
        """The underlying :class:`IdRegistry`, or ``None`` when none applies."""
        return self._registry

    def _claim(self, claimant: str, spdx_id: str) -> str | None:
        """Return *spdx_id* if nothing has claimed it yet in this session,
        recording the claim; otherwise log one collision ``WARNING:`` and
        return ``None`` (treated as a lookup miss by the caller, so it
        mints its own id instead).

        Two distinct elements both hitting the same registry-supplied id
        happens when a stale registry entry outlives the element it
        originally named -- reusing it for both would itself create the
        exact duplicate-spdxId bug this whole mechanism exists to
        prevent, so only the first claimant (in whatever order the
        caller iterates, which must itself be deterministic) gets to
        reuse it; every later one falls back to a fresh mint.
        """
        first_claimant = self._claimed.get(spdx_id)
        if first_claimant is not None:
            log.warning(
                "ID registry: %s is registered for both %s and %s; %s gets a new id",
                spdx_id,
                first_claimant,
                claimant,
                claimant,
            )
            return None
        self._claimed[spdx_id] = claimant
        return spdx_id

    def file_id(
        self,
        claimant: str,
        paths: Sequence[str],
        sha256: str,
        *,
        on_miss: Callable[[], None] | None = None,
    ) -> str | None:
        """Look up a registered file id for the first of *paths* that
        matches *sha256*, claim it, and return it -- or ``None``.

        *paths* are tried in order (e.g. a src/-layout file's physical
        path, then its distribution path); the first raw hit is used.
        *on_miss* is called only when every path in *paths* is a raw miss
        (not found, or found with a different hash) -- never when a hit
        exists but this session's claim is rejected (see :meth:`_claim`).
        Returns ``None`` immediately, without calling *on_miss*, when no
        registry is loaded in this session.
        """
        if self._registry is None:
            return None
        for path in paths:
            spdx_id = self._registry.lookup_file(path, sha256)
            if spdx_id is not None:
                return self._claim(claimant, spdx_id)
        if on_miss is not None:
            on_miss()
        return None

    def entity_id(
        self,
        claimant: str,
        names: Sequence[str],
        type_name: str,
        *,
        on_miss: Callable[[], None] | None = None,
    ) -> str | None:
        """Look up a registered entity id for the first of *names* that
        matches under *type_name*, claim it, and return it -- or ``None``.

        *names* are tried in order (e.g. an AI model's declared name,
        then its file stem); the first raw hit is used. *on_miss* is
        called only when every name in *names* is a raw miss -- never
        when a hit exists but this session's claim is rejected. Returns
        ``None`` immediately, without calling *on_miss*, when no registry
        is loaded in this session.
        """
        if self._registry is None:
            return None
        for name in names:
            spdx_id = self._registry.lookup_entity(name, type_name)
            if spdx_id is not None:
                return self._claim(claimant, spdx_id)
        if on_miss is not None:
            on_miss()
        return None

    def claimed_ids(self) -> list[str]:
        """Return every id claimed so far in this session, in claim order."""
        return list(self._claimed)
