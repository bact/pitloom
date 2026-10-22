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

#: uv.lock ``source`` keys that mark a package as not resolvable to a
#: meaningful PyPI version pin -- mirrors ``poetry.lock``'s
#: ``directory``/``file``/``git``/``url`` skip and ``pylock.toml``'s
#: ``vcs``/``directory``/``archive`` skip. ``url`` is uv's direct
#: remote-wheel/sdist source (per uv's docs: source types are
#: Index/Git/URL/Path/Directory/Editable/Virtual) -- without it, a
#: url-sourced package would be emitted as an ordinary registry pin.
_NON_REGISTRY_SOURCE_KEYS = ("git", "url", "path", "directory", "editable", "virtual")

#: ``source`` keys identifying the project's own package entry (a local
#: root/workspace member, not a PyPI download).
_ROOT_SOURCE_KEYS = ("editable", "virtual")


def scan_packages(
    packages: Iterable[object], *, warn: bool = True
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Single pass over the top-level ``[[package]]`` list, returning
    the canonical-name index :func:`collect_transitive_dependencies`
    needs and the local/workspace-root candidates :func:`find_root_package`
    needs -- folded into one scan instead of three independent ones,
    since building the index and finding root candidates only need to
    look at each entry once.

    Warns (the same way every sibling lock format's own package-list
    loop does, unless *warn* is false) on a non-table entry or a table
    with a missing or invalid ``name``, then excludes it from both
    results -- it can never be the target of a real dependency reference
    by name, nor a real root-package candidate.
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
        # uv itself normalizes every ``name`` field it writes, but a
        # dependency *reference* and the package's own top-level entry
        # are two separately literal strings in the file -- grouping by
        # canonical name (as ``collect_transitive_dependencies``'s
        # ``visited`` set already does) keeps lookup consistent with a
        # name that differs only in case/``-``/``_``/``.`` folding,
        # instead of a literal-string mismatch silently causing a
        # resolvable dependency to be reported as "not found".
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
    """Return the entry in *candidates* (every ``editable``/``virtual``-
    sourced ``[[package]]`` entry, from :func:`scan_packages`) that is
    the project's own, or ``None`` if none is found.

    A shared ``uv.lock`` (a uv workspace) can list more than one such
    entry -- one per local workspace member. When *expected_name* (the
    calling project's own declared name, from its ``pyproject.toml``) is
    given, it's used to pick the matching entry among candidates rather
    than blindly taking the first one, which would silently attribute a
    *different* workspace member's dependencies to this project. The sole
    candidate is taken as it is only when *expected_name* is unknown; one
    named otherwise is another project's, so with a known name and no
    match, or with more than one candidate and none known, returns
    ``None`` (after a ``WARNING:``) rather than guess.
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
    """Return the single, unambiguous ``[[package]]`` entry that one
    ``dependencies``-list reference resolves to -- the root package's
    own, or one already-visited package's own nested reference during
    the transitive walk in :func:`collect_transitive_dependencies` --
    or ``None`` when it can't be resolved that way."""
    name = dep_ref.get("name")
    if not is_usable_name(name):
        warn_missing_name("Skipping malformed uv.lock dependency reference", name)
        return None
    if "version" in dep_ref:
        # An inline version on the reference itself means this
        # dependency resolves to a different version per environment
        # marker -- ambiguous without evaluating markers against a real
        # environment, which this extractor deliberately doesn't do.
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
        # Every candidate agrees on version (PEP 440) -- the marker
        # branches they come from don't change the resolved output, so
        # there's nothing ambiguous to guess about; same "agreeing
        # duplicates collapse" rule every sibling lock format already
        # applies (see e.g. `poetry.py`'s `is_same_version` check).

    return candidates[0]


def collect_transitive_dependencies(
    root_dependencies: list[object], by_name: dict[str, list[dict[str, Any]]]
) -> list[str]:
    """Breadth-first walk of the resolved dependency graph starting from
    the project root package's own ``dependencies`` list, returning
    every reachable package (not just the root's immediate dependencies)
    as exact-pin PEP 508 strings.

    A ``uv.lock``'s flat ``[[package]]`` table records each package's
    *own* ``dependencies`` list once, keyed by name -- the actual
    installed set is the closure of that graph, not just its first
    layer (e.g. a CLI tool's own root dependency on a framework that
    itself pulls in several more packages). PEP 503-canonicalized names
    guard against revisiting the same package twice (a diamond
    dependency shared by two branches) or looping on a cycle; a name
    that fails to resolve unambiguously (see
    :func:`resolved_package_for_dependency`) is skipped and not walked
    into further, the same "don't guess" policy the root-level case
    already applied.
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
            # Requested but not declared by the package's own
            # `optional-dependencies` table (stale/hand-edited lock, or
            # an extra renamed/removed since resolution) -- a deviation
            # worth a WARNING, same as every other unresolvable
            # reference in this module, not a silent no-op.
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
    """Return ``name==version`` for one top-level ``[[package]]`` entry,
    or ``None`` when it's non-registry-sourced or missing a version."""
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
