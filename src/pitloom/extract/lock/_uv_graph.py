# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``uv.lock`` package table as a graph: scanning ``[[package]]`` entries,
finding the project's own entry, resolving a dependency reference to exactly
one entry and walking the transitive set (including the extras a dependency
requests).

See also: :mod:`pitloom.extract.lock.uv`, the extractor that reads the lock
file and calls these functions.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.extract._extract_utils import quote_source
from pitloom.extract.lock.common import (
    find_first_present_key,
    is_same_version,
    is_usable_name,
    is_usable_version,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
)
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

#: ``source`` keys of a package with no registry version to pin (``url`` is a
#: direct wheel/sdist source).
_NON_REGISTRY_SOURCE_KEYS = ("git", "url", "path", "directory", "editable", "virtual")

#: ``source`` keys of the project's own entry (a local or workspace member).
_ROOT_SOURCE_KEYS = ("editable", "virtual")


def scan_packages(
    packages: Iterable[object], *, warn: bool = True
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """One pass over the ``[[package]]`` list: the canonical-name index for
    :func:`collect_transitive_dependencies` and the root candidates for
    :func:`find_root_package`.

    A non-table entry or one with a missing or invalid ``name`` is skipped,
    with a ``WARNING:`` unless *warn* is false.
    """
    by_name: dict[str, list[dict[str, Any]]] = {}
    root_candidates: list[dict[str, Any]] = []
    for pkg in packages:
        if not isinstance(pkg, dict):
            if warn:
                warn_malformed_entry_not_table("uv.lock", "[[package]]", pkg)
            continue
        name = pkg.get("name")
        if not is_usable_name(name):
            if warn:
                warn_missing_name("Skipping malformed uv.lock [[package]] entry", name)
            continue
        # Canonical names: a reference and an entry may differ in
        # case/separators only.
        by_name.setdefault(canonicalize_name(name), []).append(pkg)
        source = pkg.get("source")
        if (
            isinstance(source, dict)
            and find_first_present_key(source, _ROOT_SOURCE_KEYS) is not None
        ):
            root_candidates.append(pkg)
    return by_name, root_candidates


def find_root_package(
    candidates: list[dict[str, Any]],
    expected_name: str | None,
    lock_path: Path | None = None,
) -> dict[str, Any] | None:
    """The project's own entry among *candidates* (the ``editable``/
    ``virtual`` entries from :func:`scan_packages`), else ``None``.

    A uv workspace lists one per member, so *expected_name* picks the match
    rather than the first (which would attribute another member's
    dependencies to this project). Without a name only a sole candidate is
    taken; with no match, or several candidates and no name, ``None`` after
    a ``WARNING:``.
    """
    if not candidates:
        return None

    if expected_name:
        expected = canonicalize_name(expected_name)
        for pkg in candidates:
            name = pkg.get("name")
            if isinstance(name, str) and canonicalize_name(name) == expected:
                return pkg
    elif len(candidates) == 1:
        return candidates[0]

    prefix = f"{quote_source(lock_path)}: " if lock_path is not None else ""
    log.warning(
        "%s%d candidate local/workspace package entries found in "
        "uv.lock but none named %s -- can't determine which is this "
        "project's own; ignoring uv.lock",
        prefix,
        len(candidates),
        loggable(repr(expected_name)),
    )
    return None


def resolved_package_for_dependency(
    dep_ref: dict[str, Any], by_name: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    """The one ``[[package]]`` entry a dependency reference resolves to, else
    ``None`` after a ``WARNING:``: malformed, carrying an inline
    (marker-conditional) ``version``, not in the table, or present at
    several versions. Markers are never evaluated."""
    name = dep_ref.get("name")
    if not is_usable_name(name):
        warn_missing_name("Skipping malformed uv.lock dependency reference", name)
        return None
    if "version" in dep_ref:
        # An inline version means a different version per marker.
        log.warning(
            "Skipping uv.lock dependency %r: marker-conditional version "
            "on its own dependency reference (no marker evaluation)",
            name,
        )
        return None

    candidates = by_name.get(canonicalize_name(name), [])
    if not candidates:
        log.warning(
            "Skipping uv.lock dependency %r: referenced but not found in "
            "the lock file's package table",
            name,
        )
        return None
    if len(candidates) > 1:
        versions = [c.get("version") for c in candidates]
        first_version = versions[0]
        if not all(
            isinstance(v, str)
            and isinstance(first_version, str)
            and is_same_version(v, first_version)
            for v in versions
        ):
            log.warning(
                "Skipping uv.lock dependency %r: %d resolved versions present "
                "(marker-conditional) -- no marker evaluation",
                name,
                len(candidates),
            )
            return None
        # All candidates agree (PEP 440): duplicates collapse, as in the
        # sibling formats.

    return candidates[0]


def collect_transitive_dependencies(
    root_dependencies: list[object], by_name: dict[str, list[dict[str, Any]]]
) -> list[str]:
    """Every package reachable from the root's ``dependencies``, as exact
    pins (breadth-first).

    The installed set is the closure of the graph, not its first layer.
    Canonical names guard against diamonds and cycles; a reference that does
    not resolve (:func:`resolved_package_for_dependency`) is skipped and not
    walked into.
    """
    dependencies: dict[str, str] = {}
    visited: set[str] = set()
    visited_extras: set[tuple[str, str]] = set()
    queue: deque[object] = deque(root_dependencies)
    while queue:
        dep_ref = queue.popleft()
        if not isinstance(dep_ref, dict):
            warn_malformed_entry_not_table("uv.lock", "dependency reference", dep_ref)
            continue
        pkg = resolved_package_for_dependency(dep_ref, by_name)
        if pkg is None:
            continue
        canonical_name = canonicalize_name(pkg["name"])
        if canonical_name not in visited:
            visited.add(canonical_name)

            pin = pinned_dep_for_package(pkg)
            if pin is not None:
                dependencies[canonical_name] = pin

            nested = pkg.get("dependencies")
            if isinstance(nested, list):
                queue.extend(nested)
            elif nested is not None:
                log.warning(
                    "Skipping uv.lock entry %r nested 'dependencies': "
                    "expected a list, got %s",
                    pkg["name"],
                    type(nested).__name__,
                )

        _enqueue_requested_extras(dep_ref, pkg, canonical_name, visited_extras, queue)
    return list(dependencies.values())


def _enqueue_requested_extras(
    dep_ref: dict[str, Any],
    pkg: dict[str, Any],
    canonical_name: str,
    visited_extras: set[tuple[str, str]],
    queue: deque[object],
) -> None:
    """Enqueue dependencies from *pkg*'s ``optional-dependencies`` table
    for any extra requested by *dep_ref*, skipping already-visited extras
    to guard against cycles."""
    extra_val = dep_ref.get("extra") or dep_ref.get("extras")
    if not extra_val:
        return
    if isinstance(extra_val, str):
        requested_extras = [extra_val]
    elif isinstance(extra_val, list):
        requested_extras = [e for e in extra_val if isinstance(e, str)]
        if len(requested_extras) != len(extra_val):
            log.warning(
                "Skipping uv.lock entry %r requested 'extra'/'extras' "
                "entries that are not strings",
                pkg.get("name", canonical_name),
            )
    else:
        log.warning(
            "Skipping uv.lock entry %r requested 'extra'/'extras': "
            "expected a string or list, got %s",
            pkg.get("name", canonical_name),
            type(extra_val).__name__,
        )
        return
    opt_deps_map = pkg.get("optional-dependencies", {})
    if not isinstance(opt_deps_map, dict):
        log.warning(
            "Skipping uv.lock entry %r 'optional-dependencies': "
            "expected a table, got %s",
            pkg.get("name", canonical_name),
            type(opt_deps_map).__name__,
        )
        return

    for extra_name in requested_extras:
        extra_canon = canonicalize_name(extra_name)
        extra_key = (canonical_name, extra_canon)
        if extra_key in visited_extras:
            continue
        visited_extras.add(extra_key)
        extra_deps = opt_deps_map.get(extra_name)
        if extra_deps is None:
            extra_deps = next(
                (
                    v
                    for k, v in opt_deps_map.items()
                    if canonicalize_name(k) == extra_canon
                ),
                None,
            )
        if extra_deps is None:
            # Stale or hand-edited lock: warn, do not skip silently.
            log.warning(
                "uv.lock: %r requested extra %r not found in %r's "
                "optional-dependencies -- skipping",
                dep_ref.get("name", canonical_name),
                extra_name,
                pkg.get("name", canonical_name),
            )
            continue
        if isinstance(extra_deps, list):
            queue.extend(extra_deps)
        else:
            log.warning(
                "Skipping uv.lock entry %r optional-dependencies %r: "
                "expected a list, got %s",
                pkg.get("name", canonical_name),
                extra_name,
                type(extra_deps).__name__,
            )


def pinned_dep_for_package(pkg: dict[str, Any]) -> str | None:
    """``name==version`` for one ``[[package]]`` entry; ``None`` when it is
    non-registry-sourced or lacks a usable version (each with a
    ``WARNING:``)."""
    name = pkg["name"]
    source = pkg.get("source")
    if isinstance(source, dict):
        non_registry_source = find_first_present_key(source, _NON_REGISTRY_SOURCE_KEYS)
        if non_registry_source is not None:
            warn_non_registry_source("uv.lock", name, non_registry_source)
            return None
    version = pkg.get("version")
    if not is_usable_version(version):
        warn_missing_version("uv.lock", name)
        return None
    return f"{name}=={version}"
