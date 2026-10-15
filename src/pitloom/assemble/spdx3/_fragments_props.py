# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Property comparison and merging for SPDX 3 fragment unification.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` (the merge that
calls these) and :mod:`pitloom.assemble.spdx3.fragments` (facade).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.spdx3_describe import describe_value, property_names

log = logging.getLogger(__name__)

_SKIP_MERGE_PROPS = frozenset({"creationInfo", "_id"})
_KEYED_DICT_PROPS = frozenset({"ai_hyperparameter", "ai_metric"})


def _class_properties(obj: spdx3.SHACLObject) -> Iterable[str]:
    """Return the declared Python property names on *obj*'s class."""
    return property_names(obj)


def _normalize_value(value: Any) -> Any:
    """Return a comparable, hashable-shaped representation of a property value.

    An element reference compares by id, whether it is the element object
    (a deserialised fragment links its own) or the id string (a build
    writes ids); an object with no id (a ``Hash``) by its content."""
    if value is None:
        return (0, None)
    if isinstance(value, spdx3.Element) and value.spdxId:
        return (3, "str", str(value.spdxId))
    if isinstance(value, spdx3.SHACLObject):
        return (1, _signature(value))
    if isinstance(value, spdx3.ListProxy):
        return (2, tuple(_normalize_value(v) for v in value))
    if isinstance(value, (list, tuple)):
        return (2, tuple(_normalize_value(v) for v in value))
    return (3, type(value).__name__, value)


def _signature(obj: spdx3.SHACLObject) -> tuple[Any, ...]:
    """Return a comparable signature of *obj*'s content."""
    parts: list[Any] = [type(obj).__name__]
    for pyname in sorted(_class_properties(obj)):
        if pyname in _SKIP_MERGE_PROPS:
            continue
        parts.append((pyname, _normalize_value(getattr(obj, pyname, None))))
    return tuple(parts)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, list, spdx3.ListProxy)):
        return len(value) == 0
    return False


def _paths_suffix_match(a: Any, b: Any) -> bool:
    """True when *a* and *b* are path strings naming the same file at
    different depths."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return a.endswith("/" + b) or b.endswith("/" + a)


def _merge_scalar(
    canonical: spdx3.Element, pyname: str, canonical_val: Any, dup_val: Any
) -> None:
    if _is_empty(canonical_val):
        if not _is_empty(dup_val):
            setattr(canonical, pyname, dup_val)
        return
    if not _is_empty(dup_val) and _normalize_value(dup_val) != _normalize_value(
        canonical_val
    ):
        if pyname == "name" and _paths_suffix_match(canonical_val, dup_val):
            log.debug(
                "Merge: %s known as both %r and %r; keeping %r.",
                describe_value(canonical),
                canonical_val,
                dup_val,
                canonical_val,
            )
            return
        log.warning(
            "Merge: conflicting %r on %s: keeping %s, dropping %s.",
            pyname,
            describe_value(canonical),
            describe_value(canonical_val),
            describe_value(dup_val),
        )


def _merge_comment(canonical: spdx3.Element, canonical_val: Any, dup_val: Any) -> None:
    if _is_empty(canonical_val):
        if not _is_empty(dup_val):
            canonical.comment = dup_val
        return
    if not _is_empty(dup_val) and dup_val != canonical_val:
        canonical.comment = f"{canonical_val}; {dup_val}"


def _merge_list(
    canonical: spdx3.Element, pyname: str, canonical_val: Any, dup_val: Any
) -> None:
    canonical_items = list(canonical_val) if canonical_val else []
    dup_items = list(dup_val) if dup_val else []
    if not dup_items:
        return

    # One key per item: an element by id (object or string), an object with
    # no id by its content, anything else by value.
    present = {_normalize_value(existing) for existing in canonical_items}
    merged = list(canonical_items)
    for item in dup_items:
        key = _normalize_value(item)
        if key in present:
            continue
        present.add(key)
        merged.append(item)

    if len(merged) != len(canonical_items):
        setattr(canonical, pyname, merged)


def _merge_dictionary_entries(
    canonical: spdx3.Element, pyname: str, canonical_val: Any, dup_val: Any
) -> None:
    """Union two ``DictionaryEntry`` lists by key; canonical wins on a key collision."""
    canonical_entries = list(canonical_val) if canonical_val else []
    dup_entries = list(dup_val) if dup_val else []
    if not dup_entries:
        return

    keys_seen: set[str] = {
        entry.key for entry in canonical_entries if getattr(entry, "key", None)
    }
    merged = list(canonical_entries)
    for entry in dup_entries:
        key = getattr(entry, "key", None)
        if key is not None and key in keys_seen:
            continue
        merged.append(entry)
        if key is not None:
            keys_seen.add(key)

    if len(merged) != len(canonical_entries):
        setattr(canonical, pyname, merged)


def _merge_properties(canonical: spdx3.Element, duplicate: spdx3.Element) -> None:
    """Fold *duplicate*'s fields into *canonical* in place."""
    for pyname in _class_properties(canonical):
        if pyname in _SKIP_MERGE_PROPS:
            continue
        canonical_val = getattr(canonical, pyname, None)
        dup_val = getattr(duplicate, pyname, None)

        if pyname in _KEYED_DICT_PROPS:
            _merge_dictionary_entries(canonical, pyname, canonical_val, dup_val)
        elif pyname == "comment":
            _merge_comment(canonical, canonical_val, dup_val)
        elif isinstance(canonical_val, spdx3.ListProxy) or isinstance(
            dup_val, spdx3.ListProxy
        ):
            _merge_list(canonical, pyname, canonical_val, dup_val)
        else:
            _merge_scalar(canonical, pyname, canonical_val, dup_val)
