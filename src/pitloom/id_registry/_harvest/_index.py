# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``spdx_id -> keys`` reverse index of a harvest pass.

See also: :mod:`pitloom.id_registry._harvest` (its user) and
:mod:`pitloom.id_registry._harvest._skip` (the elements a pass leaves out).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pitloom.id_registry._types import RegistryEntry

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry


@dataclass
class SpdxIdIndex:
    """``spdx_id -> keys`` reverse index for a registry's ``elements``
    table, built per
    :func:`~pitloom.id_registry._harvest._harvest_elements` pass and kept in sync as
    entries are added or removed during it.

    :func:`~pitloom.id_registry._harvest._release_stale_keys_for_id` uses
    it to find every OTHER key sharing an id without scanning the whole
    table per harvested element.
    """

    keys: dict[str, set[tuple[str, str]]] = field(default_factory=dict)

    @classmethod
    def from_registry(cls, registry: IdRegistry) -> SpdxIdIndex:
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
