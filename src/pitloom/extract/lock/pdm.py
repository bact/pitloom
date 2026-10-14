# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved dependencies from a PDM ``pdm.lock``.

See also: :mod:`pitloom.extract.lock.poetry` (the ``poetry.lock``
extractor this module mirrors in shape -- same ``groups``-based
main/default filtering, same source-stage-only scoping, same
``name==version`` output, same "no silent deviations" warning policy)
and :mod:`pitloom.extract.lock.cascade` (the cascade module that
calls this extractor and overlays its output onto
``ProjectMetadata.locked_dependencies``, in priority order against every
other lock format).

``pdm.lock`` is source-stage-only, the same class as every sibling lock
format: appropriate for ``loom project``/``loom generate``, never for
``loom wheel``/``embed-wheel`` (the real wheel's own metadata is ground
truth and never consults a lock) or ``loom env`` (live introspection of
what's actually installed is strictly more authoritative than a lock
that may be stale relative to it).

Unlike ``uv.lock``, a ``pdm.lock`` resolves one Python-compatibility
range per file (its own ``metadata.targets``), not a whole matrix of
marker branches in one flat table -- so it has nothing structurally
equivalent to ``uv.lock``'s "the same name pinned at two genuinely
different versions" case. The same package name *can* still appear more
than once, but only to record separate per-extra variants (e.g. a bare
``httpx`` entry alongside an ``httpx`` entry with ``extras = ["socks"]``)
that always agree on ``version`` -- collapsed here via
:func:`pitloom.extract.lock._common.group_versions_by_canonical_name`,
also shared with :mod:`pitloom.extract.lock.poetry` and
:mod:`pitloom.extract.lock.pylock`. Only a name whose entries actually
*disagree* on version (compared via
:func:`pitloom.extract.lock._common.is_same_version`'s PEP 440
equality, not raw string equality) is treated as ambiguous and skipped,
matching ``uv.lock``'s "don't guess" policy for that case.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.extract.lock._common import (
    default_group_included,
    find_first_present_key,
    has_required_top_level_table,
    is_usable_version,
    load_lock_toml,
    resolve_pinned_dependencies,
    shape_validated_package,
    warn_non_registry_source,
    warn_not_genuine_lock_file,
    warn_top_level_key_wrong_type,
)
from pitloom.extract.lock._extra_pins import packages_named

log = logging.getLogger(__name__)

__all__ = ["extract_pdm_lock_dependencies", "extract_pdm_lock_extra_pins"]

#: The default (main/runtime) group name in a ``pdm.lock``'s per-package
#: ``groups`` list -- PDM's equivalent of ``poetry.lock``'s ``"main"``.
_DEFAULT_GROUP = "default"

#: ``pdm.lock`` keys, present directly on a ``[[package]]`` table (no
#: nested ``source`` table, unlike ``uv.lock``), that mark a package as
#: not resolvable to a meaningful PyPI version pin. ``url`` records a
#: direct file-server/URL-sourced package (PDM's ``static_urls`` lock
#: strategy, or a plain ``pdm add <url>``) -- confirmed absent from
#: every ordinary registry-resolved entry in this repo's two real
#: pdm.lock fixtures, so including it here doesn't risk excluding a
#: normal package.
_NON_REGISTRY_KEYS = ("git", "hg", "svn", "bzr", "url", "path")


def _default_group_package_or_none(pkg: object) -> dict[str, Any] | None:
    """Return *pkg* itself when it's a well-formed, default-group,
    registry-sourced, versioned ``[[package]]`` entry -- ``None``
    otherwise (with a ``WARNING:`` for anything malformed or
    non-registry-sourced; silent for a package that's simply not in the
    default group, the same "expected filtering" as ``poetry.lock``'s
    non-``main`` group exclusion)."""
    validated = shape_validated_package(pkg, "pdm.lock")
    if validated is None:
        return None
    name = validated["name"]

    if not default_group_included(validated, "pdm.lock", _DEFAULT_GROUP, name):
        return None
    return _registry_package_or_none(validated)


def _registry_package_or_none(validated: dict[str, Any]) -> dict[str, Any] | None:
    """*validated*, or ``None`` with a ``WARNING:`` when it is not
    registry-sourced."""
    non_registry_key = find_first_present_key(validated, _NON_REGISTRY_KEYS)
    if non_registry_key is not None:
        warn_non_registry_source("pdm.lock", validated["name"], non_registry_key)
        return None
    return validated


def extract_pdm_lock_dependencies(project_dir: Path) -> list[str] | None:
    """Read ``pdm.lock`` next to ``pyproject.toml`` and return its
    resolved ``default``-group packages as exact-pin PEP 508 strings.

    Returns ``None`` when no ``pdm.lock`` is present, or when it can't be
    parsed -- this is optional enrichment, never a requirement. ``None``
    (as opposed to a valid-but-empty ``[]``) distinguishes an
    absent/unusable lock from a real one that simply resolves to zero
    ``default``-group packages.
    """
    lock_path = project_dir / "pdm.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None
    if not has_required_top_level_table(data, "metadata", "lock_version", str):
        warn_not_genuine_lock_file(lock_path, "metadata", "lock_version", "pdm.lock")
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        warn_top_level_key_wrong_type(
            lock_path, "package", packages, "a list", "pdm.lock"
        )
        return None

    default_group_packages = [
        pkg
        for pkg in (_default_group_package_or_none(raw) for raw in packages)
        if pkg is not None
    ]

    pairs = [(pkg["name"], pkg["version"]) for pkg in default_group_packages]
    return resolve_pinned_dependencies(pairs, "pdm.lock")


def _declared_extras(project_dir: Path) -> frozenset[str]:
    """PEP 503 names of the extras ``pyproject.toml`` declares statically
    (``[project.optional-dependencies]``); PDM records an extra and a
    development group alike as a lock group, so only this tells them
    apart."""
    data = load_lock_toml(project_dir / "pyproject.toml") or {}
    project = data.get("project")
    optional = (
        project.get("optional-dependencies") if isinstance(project, dict) else None
    )
    return frozenset(
        canonicalize_name(extra)
        for extra in (optional if isinstance(optional, dict) else {})
    )


def extract_pdm_lock_extra_pins(project_dir: Path, wanted: frozenset[str]) -> list[str]:
    """Exact pins for the packages ``pdm.lock`` resolved for one of the
    project's own extras (a lock group named as an extra in
    ``pyproject.toml``), limited to the PEP 503 names in *wanted*.

    A lock group holds an extra's whole closure, so *wanted* (the extras'
    direct requirement names) is what keeps this to direct entries. An
    extra PDM did not lock pins nothing.
    """
    # Read after the runtime pass accepted this same file.
    data = load_lock_toml(project_dir / "pdm.lock") or {}
    extras = _declared_extras(project_dir)
    pairs: list[tuple[str, str]] = []
    for raw in packages_named(data.get("package"), wanted):
        if (
            is_usable_version(raw.get("version"))
            and _in_groups(raw, extras)
            and _registry_package_or_none(raw) is not None
        ):
            pairs.append((raw["name"], raw["version"]))
    return resolve_pinned_dependencies(pairs, "pdm.lock") or []


def _in_groups(validated: dict[str, Any], groups: frozenset[str]) -> bool:
    """Whether *validated*'s ``groups`` list names one of *groups* (PEP 503
    names); a missing or malformed list names none."""
    listed = validated.get("groups")
    return isinstance(listed, list) and any(
        isinstance(group, str) and canonicalize_name(group) in groups
        for group in listed
    )
