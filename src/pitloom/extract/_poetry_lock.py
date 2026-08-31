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

from pitloom.extract._toml_io import TOMLDecodeError, load_toml_file

log = logging.getLogger(__name__)

__all__ = ["extract_poetry_lock_dependencies"]


def extract_poetry_lock_dependencies(project_dir: Path) -> list[str]:
    """Read ``poetry.lock`` next to ``pyproject.toml`` and return its
    resolved ``main``-group packages as exact-pin PEP 508 strings.

    Returns an empty list when no ``poetry.lock`` is present, or when it
    can't be parsed -- this is optional enrichment on top of
    ``[tool.poetry.dependencies]``, never a requirement.

    Packages belonging only to a non-``main`` group (``[tool.poetry.group.dev]``
    and similar) are excluded, matching the same "not a runtime dependency
    of the package" policy already applied to direct dependencies -- see
    "Dependency groups" in ``working-docs/implementation/poetry-support.md``.
    A package listed under both ``main`` and another group still counts.
    """
    lock_path = project_dir / "poetry.lock"
    try:
        data = load_toml_file(lock_path)
    except FileNotFoundError:
        return []
    except (OSError, TOMLDecodeError) as exc:
        log.warning("Failed to parse %s: %s", lock_path, exc)
        return []

    packages = data.get("package", [])
    if not isinstance(packages, list):
        return []

    dependencies: list[str] = []
    for pkg in packages:
        dep = _pinned_dep_for_package(pkg)
        if dep is not None:
            dependencies.append(dep)
    return dependencies


def _pinned_dep_for_package(pkg: Any) -> str | None:
    """Return ``name==version`` for one ``[[package]]`` table entry, or
    ``None`` when it's malformed or not in the ``main`` group."""
    if not isinstance(pkg, dict):
        return None
    name = pkg.get("name")
    version = pkg.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str):
        return None
    groups = pkg.get("groups", ["main"])
    if not isinstance(groups, list) or "main" not in groups:
        return None
    return f"{name}=={version}"
