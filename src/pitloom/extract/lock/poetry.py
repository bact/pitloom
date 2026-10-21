# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved transitive dependencies from ``poetry.lock``.

See also: :mod:`pitloom.extract.project.poetry` (direct ``[tool.poetry.dependencies]``
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

from pitloom.extract.lock._extra_pins import packages_named, requirement_names
from pitloom.extract.lock.common import (
    default_group_included,
    has_required_top_level_table,
    is_usable_version,
    load_lock_toml,
    resolve_pinned_dependencies,
    shape_validated_package,
    warn_non_registry_source,
    warn_not_genuine_lock_file,
    warn_top_level_key_wrong_type,
)

log = logging.getLogger(__name__)

__all__ = ["extract_poetry_lock_dependencies", "extract_poetry_lock_extra_pins"]

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
    return resolve_pinned_dependencies(pairs, "poetry.lock")


_NON_PEP508_SOURCE_TYPES = frozenset({"directory", "file", "git", "url"})


def _is_main_group(validated: dict[str, Any], name: str) -> bool:
    """Return True if package belongs to the main/default group.

    Modern Poetry (1.2+) locks use ``groups``; legacy pre-1.5 locks use
    ``category`` instead -- the two are schema-version-exclusive and
    never coexist in a genuine lock file, so ``groups`` taking precedence
    when both happen to be present (e.g. a hand-merged/corrupted file) is
    an arbitrary but harmless tie-break.
    """
    if "groups" in validated:
        return (
            default_group_included(validated, "poetry.lock", _DEFAULT_GROUP, name)
            is True
        )
    if "category" in validated:
        category = validated.get("category")
        if not isinstance(category, str):
            log.warning(
                "Skipping malformed poetry.lock entry %r: 'category' is %s, "
                "expected a string",
                name,
                type(category).__name__,
            )
            return False
        return category == _DEFAULT_GROUP
    return (
        default_group_included(validated, "poetry.lock", _DEFAULT_GROUP, name) is True
    )


def _main_group_package_or_none(
    pkg: object, *, allow_optional: bool = False
) -> dict[str, Any] | None:
    """Return *pkg* when it's a well-formed, main-group, registry-sourced
    entry, non-optional unless *allow_optional* -- ``None`` otherwise.

    A package resolved from a local path, a URL or VCS has no meaningful
    PyPI version pin, so including it here would misrepresent it as an
    ordinary published release (wrong PURL, bogus PyPI enrichment lookup);
    a direct ``[tool.poetry.dependencies]`` entry on such a source is a
    ``name @ URL`` direct reference
    (:mod:`pitloom.extract.project._poetry_requirements`), never a pin.
    """
    validated = shape_validated_package(pkg, "poetry.lock")
    if validated is None:
        return None
    name = validated["name"]

    optional = validated.get("optional") is True and not allow_optional
    if optional or not _is_main_group(validated, name):
        return None
    source = validated.get("source")
    source_type = source.get("type") if isinstance(source, dict) else None
    if isinstance(source_type, str) and source_type in _NON_PEP508_SOURCE_TYPES:
        warn_non_registry_source("poetry.lock", name, source_type)
        return None
    return validated


def _extras_table_names(extras: object) -> set[str]:
    """PEP 503 names listed by a ``poetry.lock`` ``[extras]`` table (extra
    -> requirement strings, e.g. ``["tomli ; python_version < '3.11'"]``);
    an entry that is not a string or not PEP 508 is ignored."""
    names: set[str] = set()
    for requirements in extras.values() if isinstance(extras, dict) else []:
        names |= requirement_names(
            requirements if isinstance(requirements, list) else []
        )
    return names


def extract_poetry_lock_extra_pins(
    project_dir: Path, wanted: frozenset[str]
) -> list[str]:
    """Exact pins for the requirements the project's own extras list
    directly (the lock's top-level ``[extras]`` table), limited to the PEP
    503 names in *wanted*; no transitive walk.

    Such a package is a ``main``-group entry marked ``optional = true``
    (or not, when another group also needs it); one non-registry-sourced
    or resolved to conflicting versions is skipped with a ``WARNING:``.
    """
    # Read after the runtime pass accepted this same file.
    data = load_lock_toml(project_dir / "poetry.lock") or {}
    targets = _extras_table_names(data.get("extras")) & wanted
    pairs: list[tuple[str, str]] = []
    for raw in packages_named(data.get("package"), targets):
        # A malformed entry was already warned about by the runtime pass.
        if not is_usable_version(raw.get("version")):
            continue
        pkg = _main_group_package_or_none(raw, allow_optional=True)
        if pkg is not None:
            pairs.append((pkg["name"], pkg["version"]))
    return resolve_pinned_dependencies(pairs, "poetry.lock") or []
