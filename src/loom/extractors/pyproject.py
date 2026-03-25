# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from pyproject.toml."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pyproject_metadata import StandardMetadata

from loom.core.config import LoomConfig
from loom.core.project import ProjectMetadata

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def read_pyproject(pyproject_path: Path) -> tuple[ProjectMetadata, LoomConfig]:
    """Read project metadata from a ``pyproject.toml`` file.

    Parses the ``[project]`` section via ``pyproject-metadata``, resolves
    dynamic versions, and reads Loom-specific settings from ``[tool.loom]``.

    Args:
        pyproject_path: Path to the ``pyproject.toml`` file.

    Returns:
        A 2-tuple of:

        * :class:`~loom.core.project.ProjectMetadata` — populated project
          metadata.
        * :class:`~loom.core.config.LoomConfig` — settings from
          ``[tool.loom]`` (all fields default gracefully when the section is
          absent).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the ``[project]`` section is missing or ``name`` is absent.
    """
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data: dict[str, Any] = tomllib.load(f)

    project_data: dict[str, Any] = data.get("project", {})
    if not project_data:
        raise ValueError("No [project] section found in pyproject.toml")
    if not project_data.get("name"):
        raise ValueError("Project name is required in pyproject.toml")

    dynamic_fields: list[str] = list(project_data.get("dynamic", []))
    version_source: str | None = None

    if "version" in dynamic_fields:
        version, version_source = _extract_dynamic_version(pyproject_path.parent, data)
        if version:
            data = {
                **data,
                "project": {
                    **project_data,
                    "version": version,
                    "dynamic": [f for f in dynamic_fields if f != "version"],
                },
            }
            dynamic_fields = [f for f in dynamic_fields if f != "version"]

    data, readme_override = _strip_missing_readme(project_data, pyproject_path, data)
    loom_config = _read_loom_config(data)

    try:
        std = StandardMetadata.from_pyproject(
            data,
            project_dir=str(pyproject_path.parent),
            dynamic_metadata=dynamic_fields or None,
            allow_extra_keys=True,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to parse project metadata: {exc}") from exc

    metadata = ProjectMetadata(
        name=std.name,
        version=str(std.version) if std.version else None,
        description=std.description,
        readme=_extract_readme(std, readme_override),
        requires_python=str(std.requires_python) if std.requires_python else None,
        license_name=_extract_license_name(std),
        keywords=std.keywords or [],
        authors=_extract_authors(std),
        urls=std.urls or {},
        dependencies=[str(d) for d in std.dependencies],
        provenance=_build_provenance(data.get("project", {}), version_source),
    )
    return metadata, loom_config


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_FIELD_PROVENANCE = {
    "description": "Source: pyproject.toml | Field: project.description",
    "urls": "Source: pyproject.toml | Field: project.urls",
    "dependencies": "Source: pyproject.toml | Field: project.dependencies",
    "authors": "Source: pyproject.toml | Field: project.authors",
    "license": "Source: pyproject.toml | Field: project.license",
}


def _build_provenance(
    project_data: dict[str, Any],
    version_source: str | None,
) -> dict[str, str]:
    """Build the provenance dict from the raw project section data."""
    prov: dict[str, str] = {
        "name": "Source: pyproject.toml | Field: project.name",
    }
    if version_source:
        prov["version"] = version_source
    elif "version" in project_data:
        prov["version"] = "Source: pyproject.toml | Field: project.version"

    for field_key, source in _FIELD_PROVENANCE.items():
        if field_key in project_data:
            prov[field_key] = source

    if project_data.get("authors"):
        prov["copyright_text"] = (
            "Source: Loom generator | Method: inferred_from_authors"
        )

    return prov


def _read_loom_config(data: dict[str, Any]) -> LoomConfig:
    """
    Read ``[tool.loom]`` settings and return
    a :class:`~loom.core.config.LoomConfig`.
    """
    loom_data = data.get("tool", {}).get("loom", {})
    raw_fragments = loom_data.get("fragments", {}).get("files", [])
    fragments = (
        [str(f) for f in raw_fragments] if isinstance(raw_fragments, list) else []
    )
    pretty = bool(loom_data.get("pretty", False))
    return LoomConfig(pretty=pretty, fragments=fragments)


def _strip_missing_readme(
    project_data: dict[str, Any],
    pyproject_path: Path,
    data: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Remove a readme entry whose file does not exist to avoid parse errors.

    Returns the (possibly modified) data dict and an optional readme override
    value that the caller can use to preserve the declared filename.
    """
    readme_field = project_data.get("readme")
    if not (readme_field and isinstance(readme_field, str)):
        return data, None
    if (pyproject_path.parent / readme_field).exists():
        return data, None
    stripped = {
        **data,
        "project": {k: v for k, v in data["project"].items() if k != "readme"},
    }
    return stripped, readme_field


def _extract_readme(std: StandardMetadata, override: str | None) -> str | None:
    """Return the readme text or filename from StandardMetadata."""
    if override is not None:
        return override
    readme = std.readme
    if readme:
        if hasattr(readme, "file") and readme.file:
            return str(readme.file)
        if hasattr(readme, "text") and readme.text:
            return readme.text
    return None


def _extract_license_name(std: StandardMetadata) -> str | None:
    """Return an SPDX license identifier string from StandardMetadata.

    Handles both plain string format (PEP 639) and License object format.

    Note: Does not yet parse or validate full SPDX license expressions.
    See ``docs/design/architecture-overview.md`` for the planned
    ``license-expression`` integration.
    """
    # TODO:
    # - Handle license expression via https://pypi.org/project/license-expression/
    # - Validate against SPDX License List https://spdx.org/licenses/
    license_obj = std.license
    if not license_obj:
        return None
    if isinstance(license_obj, str):
        return license_obj
    if hasattr(license_obj, "text") and license_obj.text:
        return license_obj.text
    if hasattr(license_obj, "file") and license_obj.file:
        return str(license_obj.file)
    return str(license_obj)


def _extract_authors(std: StandardMetadata) -> list[dict[str, str]]:
    """Return authors as a list of ``{name, email?}`` dicts."""
    result = []
    for name, email in std.authors:
        entry: dict[str, str] = {"name": name} if name else {}
        if email:
            entry["email"] = email
        if entry:
            result.append(entry)
    return result


def _extract_dynamic_version(
    project_dir: Path,
    pyproject_data: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Resolve a dynamic version from Hatchling config or common file paths.

    Returns ``(version, provenance_source)`` or ``(None, None)`` if not found.
    """
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
                    f"Source: {p.relative_to(project_dir)}"
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
                    f"Source: {p.relative_to(project_dir)}"
                    " | Method: dynamic_extraction",
                )

    return None, None


def _read_version_from_file(file_path: Path) -> str | None:
    """Extract ``__version__ = "x.y.z"`` from a Python source file."""
    try:
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if "__version__" in line and "=" in line:
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"').strip("'")
    except (OSError, UnicodeDecodeError):
        pass
    return None
