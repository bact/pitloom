# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which harvested elements a ``(type, name)``-keyed registry cannot pin.

See also: :mod:`pitloom.id_registry._harvest` (its
``_import_sbom_element`` writes the keys this module predicts).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from pitloom.id_registry._types import _element_key

__all__ = [
    "_ambiguous_keys",
    "_compact_type_of",
    "_element_key_of",
    "ambiguous_keys_message",
]


def _compact_type_of(obj: Any) -> str:
    """The SPDX 3 compact type name of *obj* (its class name as fallback)."""
    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    return compact_type or type(obj).__name__


def _element_key_of(obj: Any) -> tuple[str, str] | None:
    """The key :func:`~pitloom.id_registry._harvest._import_sbom_element`
    writes *obj* under, or ``None`` when it writes none (unnamed, no id, or
    no SPDX 3 compact type)."""
    name = getattr(obj, "name", None)
    if not name or not getattr(obj, "spdxId", None):
        return None
    compact_type = _compact_type_of(obj)
    if compact_type == "object":
        return None
    return _element_key(type_name=compact_type, name=name)


def _ambiguous_keys(objects: Iterable[Any]) -> frozenset[tuple[str, str]]:
    """Every key more than one of *objects* would be written under, file
    paths included.

    One document holding two elements of one type and one (canonical)
    name -- two pinned versions of one dependency, two bundled binaries
    of one name, two wheel members normalised to one path -- cannot be
    pinned by a name-keyed registry: writing either id would make the
    next run hand it to whichever element claims the name first, which
    is not the one harvested.

    A run's auto-harvest
    (:func:`pitloom.assemble._generators_shared._sync_registry`) first
    leaves out the elements that never look the registry up (a non-PEP 508
    dependency string named like the project, a phantom named like the
    project or a dependency), so they neither count nor get written, and
    the one element that looks the name up is written. ``id import`` has
    no such record and passes every element.
    """
    counts = Counter(key for key in map(_element_key_of, objects) if key is not None)
    return frozenset(key for key, count in counts.items() if count > 1)


def ambiguous_keys_message(outcome: str, keys: Iterable[tuple[str, str]]) -> str:
    """The one line naming the :func:`_ambiguous_keys` *keys* left out:
    ``ID registry: <outcome> (name held by several elements): <type>
    '<name>', ...``, sorted, each name ``repr()``'d so a control character
    in it cannot forge the line. Shared by ``id import``'s ``INFO:`` and
    run auto-harvest's DEBUG record."""
    listed = ", ".join(f"{type_name} {name!r}" for type_name, name in sorted(keys))
    return f"ID registry: {outcome} (name held by several elements): {listed}"
