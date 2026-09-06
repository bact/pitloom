# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved transitive dependencies from ``poetry.lock``.

See also: :mod:`pitloom.extract._poetry` (direct ``[tool.poetry.dependencies]``
extraction, which this module's output complements, never replaces).

``poetry.lock`` is produced and consumed entirely by the separate ``poetry``
CLI application (``poetry lock``/``add``/``update`` write it, ``poetry
install`` reads it) -- poetry-core's build backend (``poetry build``, ``pip
install .``, ``python -m build``) never touches it. That makes it a
source-stage-only artifact: appropriate for ``loom project``/``loom
generate`` (a static file sitting next to ``pyproject.toml``), never for
``loom wheel``/``embed-wheel`` (the real wheel's own metadata is ground
truth and never consulted the lock) or ``loom env`` (live introspection of
what's actually installed is strictly more authoritative than a lock that
may be stale relative to it). Callers must only invoke this from the
source-stage path -- see ``working-docs/implementation/sbom-lifecycle-stages.md``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.extract._lock_common import (
    default_group_included,
    group_versions_by_canonical_name,
    has_required_top_level_table,
    load_lock_toml,
    shape_validated_package,
    warn_conflicting_versions,
    warn_non_registry_source,
    warn_not_genuine_lock_file,
    warn_top_level_key_wrong_type,
)

log = logging.getLogger(__name__)

__all__ = ["extract_poetry_lock_dependencies"]

_DEFAULT_GROUP = "main"


def extract_poetry_lock_dependencies(project_dir: Path) -> list[str] | None:
    """Read ``poetry.lock`` next to ``pyproject.toml`` and return its
    resolved ``main``-group packages as exact-pin PEP 508 strings.

    Returns ``None`` when no ``poetry.lock`` is present, or when it
    can't be parsed -- this is optional enrichment on top of
    ``[tool.poetry.dependencies]``, never a requirement. ``None`` (as
    opposed to a valid-but-empty ``[]``) distinguishes an absent/unusable
    lock from a real one that simply resolves to zero ``main``-group
    packages.

    Packages belonging only to a non-``main`` group (``[tool.poetry.group.dev]``
    and similar) or marked ``optional = true`` (optional/extras dependencies)
    are excluded from the base runtime dependency set. A package listed under
    both ``main`` and another group still counts.
    """
    lock_path = project_dir / "poetry.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None
    if not has_required_top_level_table(data, "metadata", "lock-version", str):
        warn_not_genuine_lock_file(lock_path, "metadata", "lock-version", "poetry.lock")
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        warn_top_level_key_wrong_type(
            lock_path, "package", packages, "a list", "poetry.lock"
        )
        return None

    main_group_packages = [
        pkg
        for pkg in (_main_group_package_or_none(raw) for raw in packages)
        if pkg is not None
    ]

    pairs = [(pkg["name"], pkg["version"]) for pkg in main_group_packages]

    dependencies: list[str] = []
    for group in group_versions_by_canonical_name(pairs).values():
        name, version = group[0]
        conflicting_versions = {v for _, v in group}
        if len(conflicting_versions) > 1:
            warn_conflicting_versions("poetry.lock", name, conflicting_versions)
            continue
        dependencies.append(f"{name}=={version}")
    return dependencies


_NON_PEP508_SOURCE_TYPES = frozenset({"directory", "file", "git", "url"})


def _main_group_package_or_none(pkg: object) -> dict[str, Any] | None:
    """Return *pkg* when it's a well-formed, non-optional, main-group,
    registry-sourced entry -- ``None`` otherwise.

    Mirrors the skip policy :func:`pitloom.extract._poetry._poetry_dep_to_pep508`
    already applies to direct ``[tool.poetry.dependencies]`` entries: a
    package resolved from a local path or VCS has no meaningful PyPI
    version pin, so including it here would misrepresent it as an
    ordinary published release (wrong PURL, bogus PyPI enrichment lookup).
    """
    validated = shape_validated_package(pkg, "poetry.lock")
    if validated is None:
        return None
    name = validated["name"]

    if validated.get("optional") is True:
        return None
    if not default_group_included(validated, "poetry.lock", _DEFAULT_GROUP, name):
        return None
    source = validated.get("source")
    source_type = source.get("type") if isinstance(source, dict) else None
    if isinstance(source_type, str) and source_type in _NON_PEP508_SOURCE_TYPES:
        warn_non_registry_source("poetry.lock", name, source_type)
        return None
    return validated
