# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved dependencies from a PEP 751 ``pylock.toml``.

See also: :mod:`pitloom.extract._poetry_lock` (the ``poetry.lock``
extractor this module mirrors in shape -- same source-stage-only scoping,
same ``name==version`` output, same "no silent deviations" warning
policy) and :mod:`pitloom.extract._locked_dependencies` (the cascade
module that calls this extractor and overlays its output onto
``ProjectMetadata.locked_dependencies``, in priority order against every
other lock format).

``pylock.toml`` (PEP 751) is the build-backend-agnostic Python
interoperability standard for recording a fully resolved dependency set --
produced by tools like ``uv``, ``pdm``, and ``poetry`` (via ``export``),
consumed only by installers, never by a PEP 517 build backend. That makes
it a **source-stage-only** artifact, the same class as ``poetry.lock``:
appropriate for ``loom project``/``loom generate`` (a static file sitting
next to ``pyproject.toml``), never for ``loom wheel``/``embed-wheel`` (the
real wheel's own metadata is ground truth and never consults a lock) or
``loom env`` (live introspection of what's actually installed is strictly
more authoritative than a lock that may be stale relative to it).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.extract._lock_common import find_first_present_key, load_lock_toml

log = logging.getLogger(__name__)

__all__ = ["extract_pylock_dependencies"]

_NON_REGISTRY_SOURCE_KEYS = ("vcs", "directory", "archive")


def extract_pylock_dependencies(project_dir: Path) -> list[str]:
    """Read ``pylock.toml`` next to ``pyproject.toml`` and return its
    resolved packages as exact-pin PEP 508 strings.

    Returns an empty list when no ``pylock.toml`` is present, or when it
    can't be parsed -- this is optional enrichment, never a requirement.

    Unlike ``poetry.lock``, PEP 751 has no ``groups``-style per-package
    membership to filter on: a ``pylock.toml`` is already the flattened,
    fully resolved package set for whichever extras/dependency-groups the
    tool that generated it was asked to include, so every ``[[packages]]``
    entry is taken as-is.
    """
    lock_path = project_dir / "pylock.toml"
    data = load_lock_toml(lock_path)
    if data is None:
        return []

    if not isinstance(data.get("lock-version"), str):
        log.warning(
            "%s: missing or non-string top-level 'lock-version' key -- "
            "ignoring pylock.toml",
            lock_path,
        )
        return []

    packages = data.get("packages", [])
    if not isinstance(packages, list):
        log.warning(
            "%s: top-level 'packages' key is %s, expected a list -- "
            "ignoring pylock.toml",
            lock_path,
            type(packages).__name__,
        )
        return []

    dependencies: list[str] = []
    for pkg in packages:
        dep = _pinned_dep_for_package(pkg)
        if dep is not None:
            dependencies.append(dep)
    return dependencies


def _pinned_dep_for_package(pkg: Any) -> str | None:
    """Return ``name==version`` for one ``[[packages]]`` table entry, or
    ``None`` when it's malformed or sourced from a location that
    ``name==version`` can't represent.

    A package pinned via ``vcs``, ``directory``, or ``archive`` (PEP 751's
    non-registry source tables) has no meaningful PyPI version pin, so
    including it here would misrepresent it as an ordinary published
    release (wrong PURL, bogus PyPI enrichment lookup) -- mirrors
    ``poetry.lock``'s equivalent ``directory``/``file``/``git``/``url``
    skip in :func:`pitloom.extract._poetry_lock._pinned_dep_for_package`.
    A registry-resolved package sourced via ``sdist``/``wheels`` (or with
    no source table at all) is always included when it has a version.
    """
    if not isinstance(pkg, dict):
        log.warning(
            "Skipping malformed pylock.toml [[packages]] entry: expected a "
            "table, got %s",
            type(pkg).__name__,
        )
        return None
    name = pkg.get("name")
    if not isinstance(name, str) or not name:
        log.warning(
            "Skipping malformed pylock.toml [[packages]] entry: missing or "
            "non-string 'name' (name=%r)",
            name,
        )
        return None
    non_registry_source = find_first_present_key(pkg, _NON_REGISTRY_SOURCE_KEYS)
    if non_registry_source is not None:
        log.warning(
            "Skipping pylock.toml entry %r: %s-sourced dependencies cannot "
            "be represented as a PEP 508 specifier",
            name,
            non_registry_source,
        )
        return None
    version = pkg.get("version")
    if not isinstance(version, str) or not version:
        log.warning(
            "Skipping pylock.toml entry %r: missing or non-string 'version'",
            name,
        )
        return None
    return f"{name}=={version}"
