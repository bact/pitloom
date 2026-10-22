# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved dependencies from a ``uv.lock``.

Source-stage only, like ``poetry.lock`` and ``pylock.toml``: used by
``loom project``/``loom generate``, never by ``loom wheel``/``embed-wheel``
or ``loom env``.

The project's own entry (``source.editable`` or ``source.virtual``)
supplies the main ``dependencies``, each resolved only when exactly one
candidate exists; an ambiguous or marker-conditional name is skipped with a
``WARNING:``. The project's own extras and dev groups are excluded, but an
extra a dependency itself requests (``uvicorn[standard]``) is walked. The
project's own extras are pinned separately, direct references only:
:func:`extract_uv_lock_extra_pins`.

See also: :mod:`pitloom.extract.lock._uv_graph` (the package-table walk),
:mod:`pitloom.extract.lock.poetry` and :mod:`pitloom.extract.lock.pylock`
(siblings of the same shape) and :mod:`pitloom.extract.lock.cascade`
(which calls this and ranks it against the other formats).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.extract._extract_utils import quote_source
from pitloom.extract.lock._uv_graph import (
    collect_transitive_dependencies,
    find_root_package,
    pinned_dep_for_package,
    resolved_package_for_dependency,
    scan_packages,
)
from pitloom.extract.lock.common import (
    is_format_version_number,
    load_lock_toml,
    warn_top_level_key_wrong_type,
)

log = logging.getLogger(__name__)

__all__ = ["extract_uv_lock_dependencies", "extract_uv_lock_extra_pins"]


def _expected_project_name(project_dir: Path) -> str | None:
    """The bare ``[project].name`` from *project_dir*'s ``pyproject.toml``,
    else ``None``; only disambiguates a workspace lock's local entries."""
    data = load_lock_toml(project_dir / "pyproject.toml")
    if data is None:
        return None
    project_table = data.get("project", {})
    if not isinstance(project_table, dict):
        return None
    name = project_table.get("name")
    return name if isinstance(name, str) and name else None


def _read_root_package(
    project_dir: Path, expected_name: str | None, *, warn_entries: bool = True
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]] | None:
    """Return the project's own ``[[package]]`` entry in *project_dir*'s
    ``uv.lock`` and the lock's canonical-name package index, or ``None``
    (after a ``WARNING:`` for anything but an absent file) when the lock or
    its root entry is unusable -- see :func:`extract_uv_lock_dependencies`.
    *warn_entries* false: a malformed package entry is skipped silently
    (a second read of a lock whose first read warned of it)."""
    lock_path = project_dir / "uv.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None
    # The format marker is a flat top-level int ``version``.
    if not is_format_version_number(data.get("version")):
        log.warning(
            "%s: no top-level 'version' key (int) -- doesn't look like a "
            "genuine uv.lock, ignoring",
            quote_source(lock_path),
        )
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        warn_top_level_key_wrong_type(
            lock_path, "package", packages, "a list", "uv.lock"
        )
        return None
    by_name, root_candidates = scan_packages(packages, warn=warn_entries)

    if not expected_name:
        # An unresolved name arrives as ``""``, not ``None``: both fall back.
        expected_name = _expected_project_name(project_dir)
    if not root_candidates:
        log.warning(
            "%s: no project package found (no 'editable'/'virtual' "
            "source entry) -- ignoring uv.lock",
            quote_source(lock_path),
        )
        return None
    # No match among candidates: find_root_package has warned.
    root = find_root_package(root_candidates, expected_name, lock_path=lock_path)
    return None if root is None else (root, by_name)


def extract_uv_lock_dependencies(
    project_dir: Path, expected_name: str | None = None
) -> list[str] | None:
    """The project's transitive main/runtime dependencies from the
    ``uv.lock`` beside ``pyproject.toml``, as exact-pin strings.

    *expected_name* disambiguates a workspace lock's local entries (see
    :func:`~pitloom.extract.lock._uv_graph.find_root_package`); omitted, it
    is read from ``pyproject.toml``. ``None`` means no usable lock or root
    entry; ``[]`` is a real lock whose root has no runtime dependencies.
    """
    loaded = _read_root_package(project_dir, expected_name)
    if loaded is None:
        return None
    root, by_name = loaded

    root_dependencies = root.get("dependencies", [])
    if not isinstance(root_dependencies, list):
        log.warning(
            "%s: project package's 'dependencies' key is %s, expected a "
            "list -- ignoring uv.lock",
            quote_source(project_dir / "uv.lock"),
            type(root_dependencies).__name__,
        )
        return None

    return collect_transitive_dependencies(root_dependencies, by_name)


def extract_uv_lock_extra_pins(
    project_dir: Path, expected_name: str | None, wanted: frozenset[str]
) -> list[str]:
    """Exact pins for the requirements the project's own extras list
    directly (the root entry's ``optional-dependencies`` table), limited
    to the PEP 503 names in *wanted*; no transitive walk.

    A reference resolves as in the runtime walk: an ambiguous or
    non-registry one is skipped with its ``WARNING:``.
    """
    if not wanted:
        return []
    # Read after the runtime pass accepted this same file and warned of its
    # malformed entries.
    root, by_name = _read_root_package(
        project_dir, expected_name, warn_entries=False
    ) or ({}, {})
    optional = root.get("optional-dependencies")
    if not isinstance(optional, dict):
        return []
    pins: list[str] = []
    for ref in _wanted_refs(optional, wanted):
        pkg = resolved_package_for_dependency(ref, by_name)
        pin = pinned_dep_for_package(pkg) if pkg is not None else None
        if pin is not None:
            pins.append(pin)
    return pins


def _wanted_refs(
    optional: dict[str, Any], wanted: frozenset[str]
) -> Iterator[dict[str, Any]]:
    """The first reference to each name in *wanted* among *optional*'s
    lists (extra -> references), extras in sorted order; anything else is
    skipped silently."""
    seen: set[str] = set()
    for extra in sorted(optional):
        refs = optional[extra]
        for ref in refs if isinstance(refs, list) else []:
            name = ref.get("name") if isinstance(ref, dict) else None
            canonical = canonicalize_name(name) if isinstance(name, str) else ""
            if canonical in wanted and canonical not in seen:
                seen.add(canonical)
                yield ref
