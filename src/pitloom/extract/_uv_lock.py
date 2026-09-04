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
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.extract._lock_common import (
    find_first_present_key,
    index_packages_by_name,
    is_usable_version,
    load_lock_toml,
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


def _find_root_package(
    packages: list[Any], expected_name: str | None
) -> dict[str, Any] | None:
    """Return the ``[[package]]`` entry that is the project's own
    (identified by an ``editable``/``virtual`` ``source``), or ``None``
    if none is found.

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
    candidates = [
        pkg
        for pkg in packages
        if isinstance(pkg, dict)
        and isinstance(pkg.get("source"), dict)
        and find_first_present_key(pkg["source"], _ROOT_SOURCE_KEYS) is not None
    ]
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


def _pinned_dep_for_root_dependency(
    dep_ref: Any, by_name: dict[str, list[dict[str, Any]]]
) -> str | None:
    """Return ``name==version`` for one entry of the root package's own
    ``dependencies`` list, or ``None`` when it can't be resolved to a
    single, unambiguous, registry-sourced pin."""
    if not isinstance(dep_ref, dict):
        log.warning(
            "Skipping malformed uv.lock dependency reference: expected a table, got %s",
            type(dep_ref).__name__,
        )
        return None
    name = dep_ref.get("name")
    if not isinstance(name, str) or not name:
        log.warning(
            "Skipping malformed uv.lock dependency reference: missing or "
            "non-string 'name' (name=%r)",
            name,
        )
        return None
    if "version" in dep_ref:
        # An inline version on the reference itself means this
        # dependency resolves to a different version per environment
        # marker -- ambiguous without evaluating markers against a real
        # environment, which this extractor deliberately doesn't do.
        log.warning(
            "Skipping uv.lock dependency %r: marker-conditional version "
            "on the root package's own dependency reference (no marker "
            "evaluation)",
            name,
        )
        return None

    candidates = by_name.get(name, [])
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

    return _pinned_dep_for_package(candidates[0])


def _pinned_dep_for_package(pkg: dict[str, Any]) -> str | None:
    """Return ``name==version`` for one top-level ``[[package]]`` entry,
    or ``None`` when it's non-registry-sourced or missing a version."""
    name = pkg["name"]
    source = pkg.get("source")
    if isinstance(source, dict):
        non_registry_source = find_first_present_key(source, _NON_REGISTRY_SOURCE_KEYS)
        if non_registry_source is not None:
            log.warning(
                "Skipping uv.lock entry %r: %s-sourced dependencies cannot "
                "be represented as a PEP 508 specifier",
                name,
                non_registry_source,
            )
            return None
    version = pkg.get("version")
    if not is_usable_version(version):
        log.warning(
            "Skipping uv.lock entry %r: missing or non-string 'version'",
            name,
        )
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
) -> list[str]:
    """Read ``uv.lock`` next to ``pyproject.toml`` and return the
    project's own main/runtime dependencies as exact-pin PEP 508
    strings.

    *expected_name* disambiguates a shared uv workspace lock's multiple
    local package entries (see :func:`_find_root_package`) -- pass the
    caller's already-resolved :attr:`~pitloom.core.project.ProjectMetadata.name`
    (``apply_locked_dependencies()`` always does) to avoid re-parsing
    ``pyproject.toml`` a second time just for this. When omitted (e.g. a
    caller invoking this extractor directly, outside the cascade), falls
    back to reading it via :func:`_expected_project_name`.

    Returns an empty list when no ``uv.lock`` is present, it can't be
    parsed, or the project's own package entry can't be identified --
    this is optional enrichment, never a requirement.
    """
    lock_path = project_dir / "uv.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return []

    packages = data.get("package", [])
    if not isinstance(packages, list):
        log.warning(
            "%s: top-level 'package' key is %s, expected a list -- ignoring uv.lock",
            lock_path,
            type(packages).__name__,
        )
        return []

    if expected_name is None:
        expected_name = _expected_project_name(project_dir)
    root = _find_root_package(packages, expected_name)
    if root is None:
        log.warning(
            "%s: no project package found (no 'editable'/'virtual' "
            "source entry) -- ignoring uv.lock",
            lock_path,
        )
        return []

    root_dependencies = root.get("dependencies", [])
    if not isinstance(root_dependencies, list):
        log.warning(
            "%s: project package's 'dependencies' key is %s, expected a "
            "list -- ignoring uv.lock",
            lock_path,
            type(root_dependencies).__name__,
        )
        return []

    by_name = index_packages_by_name(packages)
    dependencies: list[str] = []
    for dep_ref in root_dependencies:
        dep = _pinned_dep_for_root_dependency(dep_ref, by_name)
        if dep is not None:
            dependencies.append(dep)
    return dependencies
