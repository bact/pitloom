# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PEP 621 ``dynamic`` field resolution for ``pyproject.toml``.

Split out of :mod:`pitloom.extract._pyproject` (which calls
:func:`prepare_dynamic_version`) to keep that module from growing into a
dumping ground -- this is a cohesive sub-concern (resolving
``dynamic = [...]`` fields via whichever mechanism the declared build
backend uses) with its own clear boundary.

Tries each backend's own resolution logic first
(:mod:`pitloom.extract._flit` for ``version``/``description``,
:mod:`pitloom.extract._pdm` for ``version`` via ``[tool.pdm.version]``,
:func:`_extract_setuptools_dynamic_version` for
``[tool.setuptools.dynamic]``), falling back to a generic
``__about__.py``/``__version__.py``-file heuristic
(:func:`_extract_dynamic_version`) for ``version`` when the backend
isn't recognized or its own resolution comes up empty.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.extract._flit import resolve_flit_dynamic_metadata
from pitloom.extract._pdm import resolve_pdm_dynamic_version
from pitloom.extract._setuptools import detect_build_backend


def _resolve_field(
    data: dict[str, Any],
    project_data: dict[str, Any],
    dynamic_fields: list[str],
    field: str,
    value: str | None,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Fold a resolved dynamic *field*'s *value* into *data*/*project_data*,
    dropping it from *dynamic_fields*. No-op (returned unchanged) when
    *value* is falsy."""
    if not value:
        return data, project_data, dynamic_fields
    dynamic_fields = [f for f in dynamic_fields if f != field]
    project_data = {**project_data, field: value, "dynamic": dynamic_fields}
    data = {**data, "project": project_data}
    return data, project_data, dynamic_fields


def prepare_dynamic_version(
    data: dict[str, Any],
    project_data: dict[str, Any],
    pyproject_path: Path,
) -> tuple[dict[str, Any], list[str], str | None, str | None]:
    """Resolve dynamic ``version``/``description`` in project metadata, if
    declared.

    Tries the declared build backend's own resolution logic first
    (:mod:`pitloom.extract._flit` for ``version``/``description``,
    :mod:`pitloom.extract._pdm` for ``version`` via
    ``[tool.pdm.version]``) -- each knows a convention (Flit: a
    module-level ``__version__``/docstring; PDM: an explicit ``source``
    directive) the generic ``__about__.py``/``__version__.py``-file
    heuristic below can't see. Falls back to that generic heuristic for
    ``version`` when the backend isn't recognized or its own resolution
    comes up empty.
    """
    dynamic_fields = list(project_data.get("dynamic", []))
    version_source: str | None = None
    description_source: str | None = None
    if not dynamic_fields:
        return data, dynamic_fields, version_source, description_source

    backend = detect_build_backend(pyproject_path.parent, pyproject_data=data)

    if backend == "flit":
        resolved = resolve_flit_dynamic_metadata(pyproject_path, dynamic_fields)
        for field, value in resolved.items():
            data, project_data, dynamic_fields = _resolve_field(
                data, project_data, dynamic_fields, field, value
            )
            if not value:
                continue
            if field == "version":
                version_source = (
                    "Source: pyproject.toml | Method: flit_dynamic_metadata"
                )
            elif field == "description":
                description_source = (
                    "Source: pyproject.toml | Method: flit_dynamic_metadata"
                )

    if backend == "pdm" and "version" in dynamic_fields:
        version, source = resolve_pdm_dynamic_version(
            pyproject_path.parent, data, dynamic_fields
        )
        data, project_data, dynamic_fields = _resolve_field(
            data, project_data, dynamic_fields, "version", version
        )
        if version:
            version_source = source

    if "version" in dynamic_fields:
        version, generic_source = _extract_dynamic_version(pyproject_path.parent, data)
        data, project_data, dynamic_fields = _resolve_field(
            data, project_data, dynamic_fields, "version", version
        )
        if version:
            version_source = generic_source

    return data, dynamic_fields, version_source, description_source


def _extract_setuptools_dynamic_version(
    project_dir: Path,
    pyproject_data: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Resolve ``[tool.setuptools.dynamic] version = {attr = "..."}`` or
    ``{file = "..."}`` -- setuptools' own dynamic-version directive,
    reachable even when a ``[project]`` table is present (unlike
    :mod:`pitloom.extract._setuptools`'s ``read_setuptools()``, which
    only runs when there's no usable ``[project]`` table at all).
    ``pyproject-metadata``'s backend-agnostic ``StandardMetadata`` has no
    concept of this setuptools-specific table, so nothing else resolves
    it on this path.

    Delegates to :mod:`pitloom.extract._setuptools_cfg`'s
    ``attr:``/``file:`` resolvers -- the exact same AST-scan/file-read
    logic ``read_setuptools()`` already uses for ``setup.cfg``'s
    ``version = attr: ...``/``version = file: ...`` directives, not a
    second, drifting implementation of the same resolution.
    """
    version_directive = (
        pyproject_data.get("tool", {})
        .get("setuptools", {})
        .get("dynamic", {})
        .get("version")
    )
    if not isinstance(version_directive, dict):
        return None, None

    # pylint: disable-next=import-outside-toplevel
    from pitloom.extract._setuptools_cfg import (
        _resolve_cfg_attr_directive,
        _resolve_cfg_version_file_directive,
    )

    attr = version_directive.get("attr")
    if attr:
        return _resolve_cfg_attr_directive(attr, project_dir)

    file_list = version_directive.get("file")
    if file_list:
        # setuptools accepts either a single path or a list here; only
        # the first is used, matching setuptools' own behavior.
        path = file_list[0] if isinstance(file_list, list) else file_list
        return _resolve_cfg_version_file_directive(path, project_dir)

    return None, None


def _extract_dynamic_version(
    project_dir: Path,
    pyproject_data: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Resolve a dynamic version from setuptools'/Hatchling's own dynamic-
    version config, or common file-path conventions.

    Returns ``(version, provenance_source)`` or ``(None, None)`` if not found.
    """
    version, source = _extract_setuptools_dynamic_version(project_dir, pyproject_data)
    if version:
        return version, source

    hatch_version_path = (
        pyproject_data.get("tool", {}).get("hatch", {}).get("version", {}).get("path")
    )
    if hatch_version_path:
        p = project_dir / hatch_version_path
        if p.exists():
            version = _read_version_from_file(p)
            if version:
                return (
                    version,
                    f"Source: {p.relative_to(project_dir).as_posix()}"
                    " | Method: dynamic_extraction",
                )

    package_name = pyproject_data.get("project", {}).get("name", "").replace("-", "_")
    candidates = [
        project_dir / "src" / package_name / "__about__.py",
        project_dir / "src" / package_name / "__version__.py",
        project_dir / "src" / "__about__.py",
        project_dir / "src" / "__version__.py",
        project_dir / package_name / "__about__.py",
        project_dir / package_name / "__version__.py",
        project_dir / "__about__.py",
        project_dir / "__version__.py",
    ]
    for p in candidates:
        if p.exists():
            version = _read_version_from_file(p)
            if version:
                return (
                    version,
                    f"Source: {p.relative_to(project_dir).as_posix()}"
                    " | Method: dynamic_extraction",
                )

    return None, None


def _read_version_from_file(file_path: Path) -> str | None:
    """Extract ``__version__ = "x.y.z"`` from a Python source file."""
    try:
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if "__version__" in line and "=" in line:
                # partition() on a line already confirmed to contain "="
                # always finds the separator, so value is never the
                # empty-string not-found case.
                _, _, value = line.partition("=")
                return value.strip().strip('"').strip("'")
    except (OSError, UnicodeDecodeError):
        pass
    return None
