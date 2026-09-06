# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved dependencies from a ``uv.lock``.

See also: :mod:`pitloom.extract._poetry_lock` and
:mod:`pitloom.extract._pylock` (the sibling lock extractors this module
mirrors in shape -- same source-stage-only scoping, same
``name==version`` output, same "no silent deviations" warning policy)
and :mod:`pitloom.extract._locked_dependencies` (the cascade module that
calls this extractor and overlays its output onto
``ProjectMetadata.locked_dependencies``, in priority order against every
other lock format).

``uv.lock`` is source-stage-only, the same class as ``poetry.lock`` and
``pylock.toml``: appropriate for ``loom project``/``loom generate``,
never for ``loom wheel``/``embed-wheel`` (the real wheel's own metadata
is ground truth and never consults a lock) or ``loom env`` (live
introspection of what's actually installed is strictly more
authoritative than a lock that may be stale relative to it).

Unlike ``poetry.lock`` and ``pylock.toml``, a ``uv.lock`` resolves
*every* Python version/platform combination its ``resolution-markers``
cover in one file: the top-level ``[[package]]`` table is a flat union
across all of them, so the same package name can legitimately appear
more than once at different versions (e.g. one entry pinned for
``python_full_version < '3.10'``, another for ``>= '3.10'``). Picking
one of those without evaluating markers against a real environment
would misrepresent the resolved set, so this extractor doesn't guess:
it reads the *project's own* ``[[package]]`` entry (identified by
``source.editable``/``source.virtual``, uv's markers for "this is a
local project, not a PyPI download") and only its ``dependencies`` list
(main/runtime only -- ``optional-dependencies``/``dev-dependencies`` are
extras and dev groups, excluded the same way ``poetry.lock``'s
non-``main`` groups are), then resolves each referenced name against
the flat table *only* when exactly one candidate exists for that name.
An ambiguous (multiple-version) or marker-conditional (inline
``version`` on the dependency reference itself) name is skipped with a
``WARNING:``, not guessed.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.extract._lock_common import (
    find_first_present_key,
    is_usable_version,
    load_lock_toml,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
    warn_top_level_key_wrong_type,
)

log = logging.getLogger(__name__)

__all__ = ["extract_uv_lock_dependencies"]

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


def _scan_packages(
    packages: Iterable[object],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Single pass over the top-level ``[[package]]`` list, returning
    the canonical-name index :func:`_collect_transitive_dependencies`
    needs and the local/workspace-root candidates :func:`_find_root_package`
    needs -- folded into one scan instead of three independent ones,
    since building the index and finding root candidates only need to
    look at each entry once.

    Warns (the same way every sibling lock format's own package-list
    loop does) on a non-table entry or a table with a
    missing/non-string/empty ``name``, then excludes it from both
    results -- it can never be the target of a real dependency reference
    by name, nor a real root-package candidate.
    """
    by_name: dict[str, list[dict[str, Any]]] = {}
    root_candidates: list[dict[str, Any]] = []
    for pkg in packages:
        if not isinstance(pkg, dict):
            warn_malformed_entry_not_table("uv.lock", "[[package]]", pkg)
            continue
        name = pkg.get("name")
        if not isinstance(name, str) or not name:
            warn_missing_name("Skipping malformed uv.lock [[package]] entry", name)
            continue
        # uv itself normalizes every ``name`` field it writes, but a
        # dependency *reference* and the package's own top-level entry
        # are two separately literal strings in the file -- grouping by
        # canonical name (as ``_collect_transitive_dependencies``'s
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


def _find_root_package(
    candidates: list[dict[str, Any]], expected_name: str | None
) -> dict[str, Any] | None:
    """Return the entry in *candidates* (every ``editable``/``virtual``-
    sourced ``[[package]]`` entry, from :func:`_scan_packages`) that is
    the project's own, or ``None`` if none is found.

    A shared ``uv.lock`` (a uv workspace) can list more than one such
    entry -- one per local workspace member. When *expected_name* (the
    calling project's own declared name, from its ``pyproject.toml``) is
    given, it's used to pick the matching entry among candidates rather
    than blindly taking the first one, which would silently attribute a
    *different* workspace member's dependencies to this project. Falls
    back to the sole candidate when there's exactly one and none named
    *expected_name* matched (e.g. the name is unreadable, or differs
    only in normalization); with more than one candidate and no match,
    returns ``None`` rather than guess.
    """
    if not candidates:
        return None

    if expected_name is not None:
        expected = canonicalize_name(expected_name)
        for pkg in candidates:
            name = pkg.get("name")
            if isinstance(name, str) and canonicalize_name(name) == expected:
                return pkg

    if len(candidates) > 1:
        log.warning(
            "%d candidate local/workspace package entries found in "
            "uv.lock but none named %r -- can't determine which is this "
            "project's own; ignoring uv.lock",
            len(candidates),
            expected_name,
        )
        return None
    return candidates[0]


def _resolved_package_for_dependency(
    dep_ref: object, by_name: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    """Return the single, unambiguous ``[[package]]`` entry that one
    ``dependencies``-list reference resolves to -- the root package's
    own, or one already-visited package's own nested reference during
    the transitive walk in :func:`_collect_transitive_dependencies` --
    or ``None`` when it can't be resolved that way."""
    if not isinstance(dep_ref, dict):
        warn_malformed_entry_not_table("uv.lock", "dependency reference", dep_ref)
        return None
    name = dep_ref.get("name")
    if not isinstance(name, str) or not name:
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
        log.warning(
            "Skipping uv.lock dependency %r: %d resolved versions present "
            "(marker-conditional) -- no marker evaluation",
            name,
            len(candidates),
        )
        return None

    return candidates[0]


def _collect_transitive_dependencies(
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
    :func:`_resolved_package_for_dependency`) is skipped and not walked
    into further, the same "don't guess" policy the root-level case
    already applied.
    """
    dependencies: dict[str, str] = {}
    visited: set[str] = set()
    visited_extras: set[tuple[str, str]] = set()
    queue: deque[object] = deque(root_dependencies)
    while queue:
        dep_ref = queue.popleft()
        pkg = _resolved_package_for_dependency(dep_ref, by_name)
        if pkg is None:
            continue
        canonical_name = canonicalize_name(pkg["name"])
        if canonical_name not in visited:
            visited.add(canonical_name)

            pin = _pinned_dep_for_package(pkg)
            if pin is not None:
                dependencies[canonical_name] = pin

            nested = pkg.get("dependencies", [])
            if isinstance(nested, list):
                queue.extend(nested)
            elif nested:
                log.warning(
                    "Skipping uv.lock entry %r nested 'dependencies': "
                    "expected a list, got %s",
                    pkg["name"],
                    type(nested).__name__,
                )

        if isinstance(dep_ref, dict):
            _enqueue_requested_extras(
                dep_ref, pkg, canonical_name, visited_extras, queue
            )
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
    requested_extras = (
        [extra_val]
        if isinstance(extra_val, str)
        else [e for e in extra_val if isinstance(e, str)]
    )
    opt_deps_map = pkg.get("optional-dependencies", {})
    if not isinstance(opt_deps_map, dict):
        return
    for extra_name in requested_extras:
        extra_key = (canonical_name, extra_name)
        if extra_key in visited_extras:
            continue
        visited_extras.add(extra_key)
        extra_deps = opt_deps_map.get(extra_name, [])
        if isinstance(extra_deps, list):
            queue.extend(extra_deps)


def _pinned_dep_for_package(pkg: dict[str, Any]) -> str | None:
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


def _expected_project_name(project_dir: Path) -> str | None:
    """Read the bare ``[project].name`` from *project_dir*'s
    ``pyproject.toml``, or ``None`` if it's absent/unreadable -- used
    only to disambiguate a shared uv workspace lock's multiple local
    package entries, not as a metadata-resolution path in its own right
    (that's :func:`pitloom.extract._pyproject.read_pyproject`'s job)."""
    data = load_lock_toml(project_dir / "pyproject.toml")
    if data is None:
        return None
    project_table = data.get("project", {})
    if not isinstance(project_table, dict):
        return None
    name = project_table.get("name")
    return name if isinstance(name, str) and name else None


def extract_uv_lock_dependencies(
    project_dir: Path, expected_name: str | None = None
) -> list[str] | None:
    """Read ``uv.lock`` next to ``pyproject.toml`` and return the
    project's own transitive main/runtime dependencies (the root
    package's own ``dependencies``, plus everything *they* in turn
    depend on) as exact-pin PEP 508 strings.

    *expected_name* disambiguates a shared uv workspace lock's multiple
    local package entries (see :func:`_find_root_package`) -- pass the
    caller's already-resolved :attr:`~pitloom.core.project.ProjectMetadata.name`
    (``apply_locked_dependencies()`` always does) to avoid re-parsing
    ``pyproject.toml`` a second time just for this. When omitted (e.g. a
    caller invoking this extractor directly, outside the cascade), falls
    back to reading it via :func:`_expected_project_name`.

    Returns ``None`` when no ``uv.lock`` is present, it can't be parsed,
    or the project's own package entry can't be identified -- this is
    optional enrichment, never a requirement. ``None`` (as opposed to a
    valid-but-empty ``[]``) distinguishes an absent/unusable lock from a
    real one whose root package simply has zero runtime dependencies.
    """
    lock_path = project_dir / "uv.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        warn_top_level_key_wrong_type(
            lock_path, "package", packages, "a list", "uv.lock"
        )
        return None
    by_name, root_candidates = _scan_packages(packages)

    if not expected_name:
        # `ProjectMetadata.name` is typed `str`, never `None` -- a
        # cascade caller whose own name resolution failed (e.g. a
        # `setup.py`-only project with a dynamic, AST-unresolvable
        # `name=`) passes `""`, not `None`. Falling back here on any
        # falsy value (not just `None`) keeps that case from silently
        # skipping the same re-read `_expected_project_name()` would
        # have done for an explicit `None` -- an empty name could never
        # usefully match a real workspace member's name anyway.
        expected_name = _expected_project_name(project_dir)
    root = _find_root_package(root_candidates, expected_name)
    if root is None:
        log.warning(
            "%s: no project package found (no 'editable'/'virtual' "
            "source entry) -- ignoring uv.lock",
            lock_path,
        )
        return None

    root_dependencies = root.get("dependencies", [])
    if not isinstance(root_dependencies, list):
        log.warning(
            "%s: project package's 'dependencies' key is %s, expected a "
            "list -- ignoring uv.lock",
            lock_path,
            type(root_dependencies).__name__,
        )
        return None

    return _collect_transitive_dependencies(root_dependencies, by_name)
