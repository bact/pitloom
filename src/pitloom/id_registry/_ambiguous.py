# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which harvested elements a name-keyed registry cannot pin.

See also: :mod:`pitloom.id_registry._harvest` (its
``_import_sbom_element`` writes the keys this module predicts).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from pitloom.id_registry._types import (
    PACKAGE_ENTITY_TYPE,
    _entity_key,
    _sha256_from_verified_using,
)

__all__ = ["_ambiguous_entity_keys", "_compact_type_of"]


def _compact_type_of(obj: Any) -> str:
    """The SPDX 3 compact type name of *obj* (its class name as fallback)."""
    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    return compact_type or type(obj).__name__


def _entity_key_of(obj: Any) -> tuple[str, str] | None:
    """The ``entities`` key :func:`_import_sbom_element` would write *obj*
    under, or ``None`` when it writes none (unnamed, no id, a file entry,
    or no SPDX 3 compact type)."""
    name = getattr(obj, "name", None)
    if not name or not getattr(obj, "spdxId", None):
        return None
    compact_type = _compact_type_of(obj)
    if (
        compact_type != PACKAGE_ENTITY_TYPE
        and _sha256_from_verified_using(obj) is not None
    ):
        return None
    if compact_type == "object":
        return None
    return _entity_key(name, compact_type)


def _ambiguous_entity_keys(objects: Iterable[Any]) -> frozenset[tuple[str, str]]:
    """Every ``entities`` key more than one of *objects* would be written
    under.

    One document holding two elements of one type and one (canonical)
    name -- a self-referencing extra next to the main package, two
    pinned versions of one dependency, a bundled binary named like a
    package -- cannot be pinned by a name-keyed registry: writing either
    id would make the next run hand it to whichever element claims the
    name first, which is not the one harvested.
    """
    counts = Counter(key for key in map(_entity_key_of, objects) if key is not None)
    return frozenset(key for key, count in counts.items() if count > 1)
