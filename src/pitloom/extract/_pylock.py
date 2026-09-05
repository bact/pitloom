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

from pitloom.extract._lock_common import (
    find_first_present_key,
    is_usable_version,
    load_lock_toml,
    warn_non_registry_source,
)

log = logging.getLogger(__name__)

__all__ = ["extract_pylock_dependencies"]

_NON_REGISTRY_SOURCE_KEYS = ("vcs", "directory", "archive")

#: The highest ``lock-version`` this extractor understands, as
#: ``(major, minor)``. PEP 751 defines only ``"1.0"`` to date. A
#: consumer must reject a different *major* version outright (a future
#: 2.x could change the schema incompatibly) but may still read a newer
#: *minor* version within the same major (additive, backward-compatible
#: fields only, per PEP 751) -- with a warning that some of its content
#: may go unrecognized.
_SUPPORTED_LOCK_FILE_VERSION = (1, 0)


def _parse_lock_version(lock_version: str) -> tuple[int, int] | None:
    """Parse a ``lock-version`` string as ``(major, minor)``, or
    ``None`` if it isn't a plain ``major.minor`` pair of non-negative
    integers -- PEP 751's own grammar for this field, rejecting a value
    like ``"2"``, ``"1.0.0"``, or ``"garbage"`` that isn't shaped like a
    version at all."""
    parts = lock_version.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1])


def extract_pylock_dependencies(project_dir: Path) -> list[str] | None:
    """Read ``pylock.toml`` next to ``pyproject.toml`` and return its
    resolved packages as exact-pin PEP 508 strings.

    Returns ``None`` when no ``pylock.toml`` is present, it can't be
    parsed, or its declared ``lock-version`` is unsupported -- this is
    optional enrichment, never a requirement, and ``None`` (as opposed
    to a valid-but-empty ``[]``) tells :mod:`pitloom.extract._locked_dependencies`'s
    cascade this source doesn't apply here, so a lower-priority source
    can still be tried, rather than a genuinely dependency-free lock
    file being confused with an absent/unusable one.

    Unlike ``poetry.lock``, PEP 751 has no ``groups``-style per-package
    membership to filter on: a ``pylock.toml`` is already the flattened,
    fully resolved package set for whichever extras/dependency-groups the
    tool that generated it was asked to include, so every ``[[packages]]``
    entry is taken as-is.
    """
    lock_path = project_dir / "pylock.toml"
    data = load_lock_toml(lock_path)
    if data is None:
        return None

    raw_lock_version = data.get("lock-version")
    parsed_version = (
        _parse_lock_version(raw_lock_version)
        if isinstance(raw_lock_version, str)
        else None
    )
    if parsed_version is None:
        log.warning(
            "%s: missing or malformed top-level 'lock-version' key "
            "(%r, expected a 'major.minor' string) -- ignoring pylock.toml",
            lock_path,
            raw_lock_version,
        )
        return None
    major, minor = parsed_version
    supported_major, supported_minor = _SUPPORTED_LOCK_FILE_VERSION
    if major != supported_major:
        log.warning(
            "%s: 'lock-version' %r is major version %d, but this Pitloom "
            "release only understands major version %d -- ignoring "
            "pylock.toml",
            lock_path,
            raw_lock_version,
            major,
            supported_major,
        )
        return None
    if minor > supported_minor:
        log.warning(
            "%s: 'lock-version' %r is newer than the %d.%d schema this "
            "Pitloom release knows -- reading it anyway (PEP 751 minor "
            "versions are additive), but newer fields may be ignored",
            lock_path,
            raw_lock_version,
            supported_major,
            supported_minor,
        )

    packages = data.get("packages", [])
    if not isinstance(packages, list):
        log.warning(
            "%s: top-level 'packages' key is %s, expected a list -- "
            "ignoring pylock.toml",
            lock_path,
            type(packages).__name__,
        )
        return None

    dependencies: list[str] = []
    for pkg in packages:
        dep = _pinned_dep_for_package(pkg)
        if dep is not None:
            dependencies.append(dep)
    return dependencies


def _pinned_dep_for_package(pkg: object) -> str | None:
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
        warn_non_registry_source("pylock.toml", name, non_registry_source)
        return None
    version = pkg.get("version")
    if not is_usable_version(version):
        log.warning(
            "Skipping pylock.toml entry %r: missing or non-string 'version'",
            name,
        )
        return None
    return f"{name}=={version}"
