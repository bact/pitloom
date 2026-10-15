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

from pitloom.core.untrusted_text import escape_display_controls
from pitloom.id_registry._registry import IdRegistry
from pitloom.id_registry._types import _require_names

log = logging.getLogger("pitloom.id_registry")

__all__ = ["IdRegistrySession", "warn_claim_collision"]


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


class IdRegistrySession:
    """One document's registry lookups, first-claimant-wins.

    Every element that would otherwise call ``registry.lookup`` directly,
    across an entire document build (files, directories, AI models, the
    project's own, dependency and phantom packages, deployed packages,
    loom fragments), instead goes through one shared session so a
    registry hit reused by two different elements is claimed by only the
    first -- see :meth:`lookup_id`.
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

        *names* are tried in order (e.g. a src/-layout file's physical
        path, then its distribution path), each as given, then
        display-escaped
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
        spellings: list[str] = []
        for name in names:
            shown = escape_display_controls(name)
            spellings.extend((name, shown) if shown != name else (name,))
        spdx_id = self._registry.lookup(type_name, spellings, sha256=sha256)
        if spdx_id is not None:
            return self._claim(claimant, spdx_id)
        if on_miss is not None:
            on_miss()
        return None

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
