# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved dependencies from a ``uv.lock``.

See also: :mod:`pitloom.extract.lock.poetry` and
:mod:`pitloom.extract.lock.pylock` (the sibling lock extractors this module
mirrors in shape -- same source-stage-only scoping, same
``name==version`` output, same "no silent deviations" warning policy)
and :mod:`pitloom.extract.lock.cascade` (the cascade module that
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
(main/runtime only -- the project's *own* ``optional-dependencies``/
``dev-dependencies`` groups are extras and dev groups a user would have
to opt into, excluded the same way ``poetry.lock``'s non-``main`` groups
are), then resolves each referenced name against the flat table *only*
when exactly one candidate exists for that name. An ambiguous
(multiple-version) or marker-conditional (inline ``version`` on the
dependency reference itself) name is skipped with a ``WARNING:``, not
guessed. A dependency reference that names a specific extra on the
package it points at (e.g. ``uvicorn[standard]``) still walks *that
package's own* ``optional-dependencies[extra]`` list, since an extra a
real dependency requests is part of what actually gets installed -- see
:func:`pitloom.extract.lock._uv_graph._enqueue_requested_extras`. The
project's own extras are pinned separately, direct references only:
:func:`extract_uv_lock_extra_pins`.

See also: :mod:`pitloom.extract.lock._uv_graph` for the package-table
walk.
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
    """Read the bare ``[project].name`` from *project_dir*'s
    ``pyproject.toml``, or ``None`` if it's absent/unreadable -- used
    only to disambiguate a shared uv workspace lock's multiple local
    package entries, not as a metadata-resolution path in its own right
    (that's :func:`pitloom.extract.project.pyproject.read_pyproject`'s job)."""
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
    # uv.lock's own format marker is a flat top-level `version` (int),
    # not nested in a sub-table like poetry.lock's `metadata.lock-version`
    # or pdm.lock's `metadata.lock_version` -- same genuineness check as
    # those two siblings, adapted to this format's actual shape, so an
    # unrelated/hand-edited TOML file can't silently win the cascade via
    # a spurious authoritative-empty `[[package]]` list.
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
        # `ProjectMetadata.name` is typed `str`, never `None` -- a
        # cascade caller whose own name resolution failed (e.g. a
        # `setup.py`-only project with a dynamic, AST-unresolvable
        # `name=`) passes `""`, not `None`. Falling back here on any
        # falsy value (not just `None`) keeps that case from silently
        # skipping the same re-read `_expected_project_name()` would
        # have done for an explicit `None` -- an empty name could never
        # usefully match a real workspace member's name anyway.
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
    """Read ``uv.lock`` next to ``pyproject.toml`` and return the
    project's own transitive main/runtime dependencies (the root
    package's own ``dependencies``, plus everything *they* in turn
    depend on) as exact-pin PEP 508 strings.

    *expected_name* disambiguates a shared uv workspace lock's multiple
    local package entries (see :func:`find_root_package`) -- pass the
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
    loaded = _read_root_package(project_dir, expected_name)
    if loaded is None:
        return None
    root, by_name = loaded

    root_dependencies = root.get("dependencies", [])
    if not isinstance(root_dependencies, list):
        log.warning(
            "%s: project package's 'dependencies' key is %s, expected a "
            "list -- ignoring uv.lock",
            project_dir / "uv.lock",
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
