# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved dependencies from a Pipenv ``Pipfile.lock``.

See also: :mod:`pitloom.extract._poetry_lock` (the sibling lock
extractor this module mirrors in shape -- same ``main``/``default``-group
filtering, same source-stage-only scoping, same ``name==version``
output, same "no silent deviations" warning policy) and
:mod:`pitloom.extract._locked_dependencies` (the cascade module that
calls this extractor and overlays its output onto
``ProjectMetadata.locked_dependencies``, in priority order against every
other lock format).

``Pipfile.lock`` is source-stage-only, the same class as every sibling
lock format: appropriate for ``loom project``/``loom generate``, never
for ``loom wheel``/``embed-wheel`` (the real wheel's own metadata is
ground truth and never consults a lock) or ``loom env`` (live
introspection of what's actually installed is strictly more
authoritative than a lock that may be stale relative to it).

Unlike every other lock format this repo parses, ``Pipfile.lock`` is
**JSON**, not TOML (:func:`pitloom.extract._lock_common.load_lock_json`,
not :func:`pitloom.extract._lock_common.load_lock_toml`). Its top level
has two package-name-keyed objects, ``"default"`` (main/runtime
dependencies) and ``"develop"`` (dev dependencies) -- only ``"default"``
is included here, mirroring ``poetry.lock``'s ``main``-group-only
policy. Each entry's own ``"version"`` field is already a PEP 440
specifier string (typically ``"==x.y.z"``, since ``pipenv lock``
resolves to an exact pin) rather than a bare version number the way
every other format's ``version`` field is -- this extractor validates
it's a single exact ``==`` specifier with no wildcard before using it,
not a range, a prefix-match specifier like ``"==x.y.*"``, or a
malformed string coerced into looking like one.
"""

from __future__ import annotations

import logging
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from pitloom.extract._lock_common import (
    find_first_present_key,
    load_lock_json,
    single_exact_pin,
    warn_missing_version,
    warn_non_registry_source,
    warn_top_level_key_wrong_type,
)

log = logging.getLogger(__name__)

__all__ = ["extract_pipfile_lock_dependencies"]

#: ``Pipfile.lock`` per-package keys that mark it as not resolvable to a
#: meaningful PyPI version pin -- a VCS (Git, Mercurial, Bazaar,
#: Subversion -- pip's/``requirementslib``'s full VCS backend list),
#: local-path, or archive/URL source, mirroring every sibling format's
#: own non-registry-source skip.
_NON_REGISTRY_KEYS = ("git", "hg", "bzr", "svn", "path", "file", "editable")


def extract_pipfile_lock_dependencies(project_dir: Path) -> list[str] | None:
    """Read ``Pipfile.lock`` next to ``Pipfile``/``setup.py`` and return
    its resolved ``"default"``-section packages as exact-pin PEP 508
    strings.

    Returns ``None`` when no ``Pipfile.lock`` is present, or when it
    can't be parsed -- this is optional enrichment, never a requirement.
    ``None`` (as opposed to a valid-but-empty ``[]``) distinguishes an
    absent/unusable lock from a real one that simply resolves to zero
    ``"default"``-section packages.
    """
    lock_path = project_dir / "Pipfile.lock"
    data = load_lock_json(lock_path)
    if data is None:
        return None

    default_section = data.get("default", {})
    if not isinstance(default_section, dict):
        warn_top_level_key_wrong_type(
            lock_path, "default", default_section, "a table", "Pipfile.lock"
        )
        return None

    dependencies: list[str] = []
    for name, entry in default_section.items():
        dep = _pinned_dep_for_package(name, entry)
        if dep is not None:
            dependencies.append(dep)
    return dependencies


def _pinned_dep_for_package(name: object, entry: object) -> str | None:
    """Return ``name==version`` for one ``"default"``-section entry, or
    ``None`` when it's malformed, non-registry-sourced, or its
    ``version`` isn't a single exact ``==`` specifier."""
    if not isinstance(name, str) or not name:
        log.warning(
            "Skipping malformed Pipfile.lock entry: non-string or empty "
            "package name (name=%r)",
            name,
        )
        return None
    if not isinstance(entry, dict):
        log.warning(
            "Skipping malformed Pipfile.lock entry %r: expected a table, got %s",
            name,
            type(entry).__name__,
        )
        return None
    non_registry_key = find_first_present_key(entry, _NON_REGISTRY_KEYS)
    if non_registry_key is not None and entry[non_registry_key] is not False:
        # Every non-registry key except 'editable' is presence-is-enough
        # (a git/hg/bzr/svn/path/file URL string). 'editable' is the
        # schema's one boolean-valued key -- an explicit
        # `"editable": false` (schema-legal, just uncommon) must not be
        # mistaken for a real editable/VCS source the same way a
        # present-but-falsy key would be for every other format's
        # presence-only check.
        warn_non_registry_source("Pipfile.lock", name, non_registry_key)
        return None
    pinned_version = _exact_pinned_version(name, entry.get("version"))
    if pinned_version is None:
        return None
    return f"{name}=={pinned_version}"


def _exact_pinned_version(name: str, version: object) -> str | None:
    """Return the bare version string when *version* is a single exact
    ``==`` PEP 440 specifier with no wildcard (e.g. ``"==2.31.0"`` ->
    ``"2.31.0"``), or ``None`` (with a ``WARNING:``) when it's missing,
    unparseable, or anything looser than one exact pin -- including a
    prefix-match specifier like ``"==2.31.*"``, which
    ``packaging.specifiers.Specifier`` also reports as operator ``"=="``
    but which pins a *range* of versions, not one exact release.
    """
    if not isinstance(version, str) or not version:
        # Unlike every sibling format, this field is already a PEP 440
        # *specifier* string (e.g. "==2.31.0"), not a plain version --
        # is_usable_version()'s stricter `packaging.version.Version`
        # check doesn't apply here (a specifier isn't a bare version and
        # would always fail it); SpecifierSet()/single_exact_pin() below
        # already validate it's a genuine, single, exact pin.
        warn_missing_version("Pipfile.lock", name)
        return None
    try:
        specifier_set = SpecifierSet(version)
    except InvalidSpecifier:
        log.warning(
            "Skipping Pipfile.lock entry %r: %r isn't a valid PEP 440 specifier",
            name,
            version,
        )
        return None
    pinned_version = single_exact_pin(specifier_set)
    if pinned_version is None:
        log.warning(
            "Skipping Pipfile.lock entry %r: 'version' %r isn't a single "
            "exact '==' pin",
            name,
            version,
        )
        return None
    return pinned_version
