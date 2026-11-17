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

from pitloom.extract.lock.common import (
    find_first_present_key,
    is_same_version,
    is_usable_name,
    is_usable_version,
    warn_conflicting_versions,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
)
from pitloom.messages.lock_files import (
    DEPENDENCIES_LIST_LINE,
    EXTRA_LIST_LINE,
    KEY_ITEMS_LINE,
    KEY_TABLE_LINE,
    KEY_TEXT_OR_LIST_LINE,
    NO_EXTRA_LINE,
    NO_MATCH_LINE,
    NO_NAME_LINE,
    NOT_IN_TABLE_LINE,
    REFERENCE_VERSION_LINE,
    Said,
    say_lock_entry,
    say_lock_file,
)

log = logging.getLogger(__name__)

#: How a line names this lock.
_LOCK_NAME = "uv.lock"

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
                warn_malformed_entry_not_table(_LOCK_NAME, "package", pkg)
            continue
        name = pkg.get("name")
        if not is_usable_name(name):
            if warn:
                warn_missing_name(_LOCK_NAME, "package", name)
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

    *expected_name* picks the match among a workspace's members. Without a
    name only a sole candidate is taken; with no match, or several
    candidates and no name, ``None`` after a ``WARNING:``.
    """
    # Never take the first of several: it could be another member's entry,
    # attributing its dependencies to this project.
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

    file = _LOCK_NAME if lock_path is None else lock_path
    if expected_name:
        say_lock_file(
            log,
            NO_MATCH_LINE,
            file=file,
            number=len(candidates),
            package=expected_name,
        )
    else:
        say_lock_file(log, NO_NAME_LINE, file=file, number=len(candidates))
    return None


def resolved_package_for_dependency(
    dep_ref: dict[str, Any],
    by_name: dict[str, list[dict[str, Any]]],
    *,
    said: Said | None = None,
) -> dict[str, Any] | None:
    """The one ``[[package]]`` entry a dependency reference resolves to, else
    ``None`` after a ``WARNING:``: malformed, carrying an inline
    (marker-conditional) ``version``, not in the table, or present at
    several versions. Markers are never evaluated. *said*: the memo of the
    walk, so a package missing from the table or at several versions is said
    once however many references name it."""
    name = dep_ref.get("name")
    if not is_usable_name(name):
        warn_missing_name(_LOCK_NAME, "dependencies", name)
        return None
    if "version" in dep_ref:
        # An inline version means a different version per marker.
        say_lock_entry(
            log, REFERENCE_VERSION_LINE, file=_LOCK_NAME, package=name, said=said
        )
        return None

    candidates = by_name.get(canonicalize_name(name), [])
    if not candidates:
        say_lock_entry(log, NOT_IN_TABLE_LINE, file=_LOCK_NAME, package=name, said=said)
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
            warn_conflicting_versions(
                _LOCK_NAME,
                name,
                {"no version" if v is None else str(v) for v in versions},
                said=said,
            )
            return None
        # All candidates agree (PEP 440): duplicates collapse, as in the
        # sibling formats.

    return candidates[0]


def collect_transitive_dependencies(
    root_dependencies: list[object],
    by_name: dict[str, list[dict[str, Any]]],
    said: Said | None = None,
) -> list[str]:
    """Every package reachable from the root's ``dependencies``, as exact
    pins (breadth-first).

    A reference that does not resolve
    (:func:`resolved_package_for_dependency`) is skipped and not walked into.
    """
    # The installed set is the closure of the graph, not its first layer;
    # canonical names guard against diamonds and cycles.
    dependencies: dict[str, str] = {}
    visited: set[str] = set()
    visited_extras: set[tuple[str, str]] = set()
    if said is None:
        said = set()
    queue: deque[object] = deque(root_dependencies)
    while queue:
        dep_ref = queue.popleft()
        if not isinstance(dep_ref, dict):
            warn_malformed_entry_not_table(_LOCK_NAME, "dependencies", dep_ref)
            continue
        pkg = resolved_package_for_dependency(dep_ref, by_name, said=said)
        if pkg is None:
            continue
        canonical_name = canonicalize_name(pkg["name"])
        if canonical_name not in visited:
            visited.add(canonical_name)

            pin = pinned_dep_for_package(pkg, said)
            if pin is not None:
                dependencies[canonical_name] = pin

            nested = pkg.get("dependencies")
            if isinstance(nested, list):
                queue.extend(nested)
            elif nested is not None:
                say_lock_entry(
                    log,
                    DEPENDENCIES_LIST_LINE,
                    file=_LOCK_NAME,
                    package=pkg["name"],
                    lock_key="dependencies",
                    value_type=nested,
                )

        _enqueue_requested_extras(
            dep_ref, pkg, canonical_name, visited_extras, queue, said
        )
    return list(dependencies.values())


def _enqueue_requested_extras(
    dep_ref: dict[str, Any],
    pkg: dict[str, Any],
    canonical_name: str,
    visited_extras: set[tuple[str, str]],
    queue: deque[object],
    said: Said,
) -> None:
    """Enqueue dependencies from *pkg*'s ``optional-dependencies`` table
    for any extra requested by *dep_ref*, skipping already-visited extras
    to guard against cycles."""
    request_key = "extra" if dep_ref.get("extra") else "extras"
    extra_val = dep_ref.get(request_key)
    if not extra_val:
        return
    package = pkg["name"]
    if isinstance(extra_val, str):
        requested_extras = [extra_val]
    elif isinstance(extra_val, list):
        requested_extras = [e for e in extra_val if isinstance(e, str)]
        if len(requested_extras) != len(extra_val):
            say_lock_entry(
                log,
                KEY_ITEMS_LINE,
                file=_LOCK_NAME,
                package=package,
                lock_key=request_key,
                said=said,
            )
    else:
        say_lock_entry(
            log,
            KEY_TEXT_OR_LIST_LINE,
            file=_LOCK_NAME,
            package=package,
            lock_key=request_key,
            value_type=extra_val,
            said=said,
        )
        return
    opt_deps_map = pkg.get("optional-dependencies", {})
    if not isinstance(opt_deps_map, dict):
        say_lock_entry(
            log,
            KEY_TABLE_LINE,
            file=_LOCK_NAME,
            package=package,
            lock_key="optional-dependencies",
            value_type=opt_deps_map,
            said=said,
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
            say_lock_entry(
                log,
                NO_EXTRA_LINE,
                file=_LOCK_NAME,
                package=package,
                extra_name=extra_name,
                lock_key="optional-dependencies",
            )
            continue
        if isinstance(extra_deps, list):
            queue.extend(extra_deps)
        else:
            say_lock_entry(
                log,
                EXTRA_LIST_LINE,
                file=_LOCK_NAME,
                package=package,
                lock_key="optional-dependencies",
                extra_name=extra_name,
                value_type=extra_deps,
            )


def pinned_dep_for_package(pkg: dict[str, Any], said: Said | None = None) -> str | None:
    """``name==version`` for one ``[[package]]`` entry; ``None`` when it is
    non-registry-sourced or lacks a usable version (each with a
    ``WARNING:``, said once when *said* is shared)."""
    name = pkg["name"]
    source = pkg.get("source")
    if isinstance(source, dict):
        non_registry_source = find_first_present_key(source, _NON_REGISTRY_SOURCE_KEYS)
        if non_registry_source is not None:
            warn_non_registry_source(_LOCK_NAME, name, non_registry_source, said)
            return None
    version = pkg.get("version")
    if not is_usable_version(version):
        warn_missing_version(_LOCK_NAME, name, said)
        return None
    return f"{name}=={version}"
