# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Digest comparison for SPDX 3 fragment unification.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` (the merge) and
:mod:`pitloom.assemble.spdx3._fragments_ids` (the rename a conflict causes).
"""

from __future__ import annotations

import logging

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.hashes import sha256_of

log = logging.getLogger(__name__)


def _hash_values(obj: spdx3.SHACLObject) -> dict[str, set[str]]:
    """*obj*'s ``verifiedUsing`` digests: algorithm -> lowercase values."""
    found: dict[str, set[str]] = {}
    for h in getattr(obj, "verifiedUsing", None) or []:
        value = getattr(h, "hashValue", None)
        algorithm = getattr(h, "algorithm", None)
        if value and algorithm:
            name = str(algorithm).rpartition("/")[2]
            found.setdefault(name, set()).add(str(value).lower())
    return found


def hash_conflict(a: spdx3.SHACLObject, b: spdx3.SHACLObject) -> str | None:
    """The first algorithm (by name) for which *a* and *b* both carry
    digests and share none, else ``None``: the same id and algorithm with
    different content is two artefacts. Case and other algorithms do not
    conflict; an element with no digest never does."""
    ours, theirs = _hash_values(a), _hash_values(b)
    for algorithm in sorted(ours.keys() & theirs.keys()):
        if ours[algorithm].isdisjoint(theirs[algorithm]):
            return algorithm
    return None


def warn_if_same_name_different_hash(
    obj: spdx3.Element, object_set: spdx3.SHACLObjectSet
) -> None:
    """Log a warning when *obj* shares a ``name`` with different SHA-256."""
    name = getattr(obj, "name", None)
    obj_hash = sha256_of(obj)
    if not name or obj_hash is None:
        return
    for existing in object_set.objects:
        if type(existing) is not type(obj) or existing is obj:
            continue
        if getattr(existing, "name", None) != name:
            continue
        existing_hash = sha256_of(existing)
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
