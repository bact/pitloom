# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by two or more lock/pin extractors (poetry, pylock, uv, pdm,
pipfile, requirements; see :mod:`pitloom.extract.lock.cascade`): entry
validation and the names re-exported from the modules below. Anything
specific to one format stays in that format's module.

See also: :mod:`pitloom.extract.lock._common_warnings` (``WARNING:``
helpers), :mod:`pitloom.extract.lock._lock_io` (reading a lock file) and
:mod:`pitloom.extract.lock._pins` (exact pins).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any, TypeGuard

from packaging.utils import InvalidName, canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom.extract.lock._common_warnings import (
    warn_conflicting_versions,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
    warn_not_genuine_lock_file,
    warn_top_level_key_wrong_type,
)
from pitloom.extract.lock._lock_io import (
    LockFileRefusedError,
    load_lock_json,
    load_lock_toml,
    read_lock_bytes,
    warn_unreadable_lock_file,
)
from pitloom.extract.lock._pins import (
    canonical_name_and_pinned_version,
    group_by_canonical_name,
    is_same_version,
    parse_exact_pin_requirement,
    resolve_pinned_dependencies,
    single_exact_pin,
)
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

__all__ = [
    "LockFileRefusedError",
    "POETRY_LOCK_SOURCE_NAME",
    "canonical_name_and_pinned_version",
    "default_group_included",
    "find_first_present_key",
    "group_by_canonical_name",
    "has_required_top_level_table",
    "is_format_version_number",
    "is_same_version",
    "is_usable_name",
    "is_usable_version",
    "load_lock_json",
    "load_lock_toml",
    "parse_exact_pin_requirement",
    "read_lock_bytes",
    "resolve_pinned_dependencies",
    "shape_validated_package",
    "single_exact_pin",
    "version_key",
    "warn_conflicting_versions",
    "warn_malformed_entry_not_table",
    "warn_missing_name",
    "warn_missing_version",
    "warn_non_registry_source",
    "warn_not_genuine_lock_file",
    "warn_top_level_key_wrong_type",
    "warn_unreadable_lock_file",
]

#: The ``Source:`` name recorded in ``provenance["locked_dependencies"]`` for
#: ``poetry.lock``; the cascade reads it back to find that source's rank, so
#: producer and consumer share this constant.
POETRY_LOCK_SOURCE_NAME = "poetry.lock"


def is_format_version_number(value: object) -> bool:
    """Whether *value* is an ``int`` format version, not a ``bool``
    (``version = true``)."""
    return isinstance(value, int) and not isinstance(value, bool)


def has_required_top_level_table(
    data: dict[str, Any],
    table_key: str,
    required_key: str,
    value_type: type | tuple[type, ...] = object,
) -> bool:
    """Whether *data* has a top-level table *table_key* with *required_key*
    holding a *value_type* value: the "is this a file of this format" check.
    A wrong-typed marker counts as absent.
    """
    # Callers use it before an empty package list may count as an
    # authoritative "no dependencies": otherwise a valid but unrelated or
    # truncated document would win the cascade over a usable lower-priority
    # lock.
    table = data.get(table_key)
    if not isinstance(table, dict):
        return False
    value = table.get(required_key)
    # A boolean is never a format marker, whatever *value_type*.
    return isinstance(value, value_type) and not isinstance(value, bool)


def version_key(version: str) -> Version | str:
    """A hashable key equal under PEP 440 (``"1.0"`` == ``"1.0.0"``); the
    raw string when *version* does not parse."""
    try:
        return Version(version)
    except (InvalidVersion, TypeError):
        return version


def is_usable_name(name: object) -> TypeGuard[str]:
    """Whether *name* is a valid PEP 508 distribution name; rejects
    ``a @ url``, ``a[x]``, ``a; marker`` and control characters. The call
    site logs the ``WARNING:`` (:func:`warn_missing_name`)."""
    if not isinstance(name, str):
        return False
    try:
        canonicalize_name(name, validate=True)
    except InvalidName:
        return False
    return True


def is_usable_version(version: object) -> TypeGuard[str]:
    """Whether *version* is a non-empty string that parses as PEP 440 and
    is not padded with white space (``"*"`` and ``"not a version"`` fail).
    The call site logs its own ``WARNING:``. A ``TypeGuard`` for ``str``.
    """
    if not isinstance(version, str) or not version or version != version.strip():
        return False
    try:
        Version(version)
    except InvalidVersion:
        return False
    return True


def find_first_present_key(
    mapping: Mapping[str, object], keys: Iterable[str]
) -> str | None:
    """The first of *keys* that is a key of *mapping*, else ``None``: the
    shared "which non-registry marker is present" lookup (``pylock.toml``,
    ``uv.lock``, ``pdm.lock``). ``poetry.lock`` checks a *value*
    (``source.type``) and does not use it.
    """
    return next((key for key in keys if key in mapping), None)


def shape_validated_package(
    pkg: object, lock_file: str, entry_label: str = "[[package]]"
) -> dict[str, Any] | None:
    """*pkg* when it is a table with a usable ``name`` and ``version``, else
    ``None`` after a ``WARNING:``. Shared by the flat ``name``/``version``
    formats (``poetry.lock``, ``pdm.lock``)."""
    if not isinstance(pkg, dict):
        warn_malformed_entry_not_table(lock_file, entry_label, pkg)
        return None
    name = pkg.get("name")
    if not is_usable_name(name):
        warn_missing_name(f"Skipping malformed {lock_file} {entry_label} entry", name)
        return None
    version = pkg.get("version")
    if not is_usable_version(version):
        warn_missing_version(lock_file, name)
        return None
    return pkg


def default_group_included(
    validated: Mapping[str, object], lock_file: str, default_group: str, name: str
) -> bool | None:
    """Whether *validated* (see :func:`shape_validated_package`) is in
    *default_group* per its ``groups`` list (default: just that group);
    ``None`` after a ``WARNING:`` when ``groups`` is not a list. Shared by
    ``poetry.lock`` (``"main"``) and ``pdm.lock`` (``"default"``)."""
    groups = validated.get("groups", [default_group])
    if not isinstance(groups, list):
        log.warning(
            "Skipping malformed %s entry %r: 'groups' is %s, expected a list",
            loggable(lock_file),
            name,
            type(groups).__name__,
        )
        return None
    return default_group in groups
