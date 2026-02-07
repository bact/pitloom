# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from pyproject.toml using Hatchling."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ProjectMetadata:
    """Represents extracted Python project metadata."""

    def __init__(
        self,
        name: str,
        version: str | None = None,
        description: str | None = None,
        readme: str | None = None,
        requires_python: str | None = None,
        license_name: str | None = None,
        keywords: list[str] | None = None,
        authors: list[dict[str, str]] | None = None,
        urls: dict[str, str] | None = None,
        dependencies: list[str] | None = None,
        provenance: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.description = description
        self.readme = readme
        self.requires_python = requires_python
        self.license_name = license_name
        self.keywords = keywords or []
        self.authors = authors or []
        self.urls = urls or {}
        self.dependencies = dependencies or []
        self.provenance = provenance or {}


def extract_metadata_from_pyproject(pyproject_path: Path) -> ProjectMetadata:
    """Extract project metadata from pyproject.toml.

    Args:
        pyproject_path: Path to the pyproject.toml file

    Returns:
        ProjectMetadata: Extracted metadata with provenance information

    Raises:
        FileNotFoundError: If pyproject.toml is not found
        ValueError: If required fields are missing
    """
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    project_data: dict[str, Any] = data.get("project", {})

    if not project_data:
        raise ValueError("No [project] section found in pyproject.toml")

    name = project_data.get("name")
    if not name:
        raise ValueError("Project name is required in pyproject.toml")

    # Track provenance for each field
    provenance: dict[str, str] = {}
    provenance["name"] = "Source: pyproject.toml | Field: project.name"

    # Extract version - handle dynamic versions
    version = project_data.get("version")
    version_source = None
    if not version and "dynamic" in project_data:
        dynamic_fields = project_data.get("dynamic", [])
        if "version" in dynamic_fields:
            # Try to extract from __about__.py or other sources
            version, version_source = _extract_dynamic_version(pyproject_path.parent, data)

    if version:
        if version_source:
            provenance["version"] = version_source
        else:
            provenance["version"] = "Source: pyproject.toml | Field: project.version"

    # Extract description
    description = project_data.get("description")
    if description:
        provenance["description"] = "Source: pyproject.toml | Field: project.description"

    # Extract URLs
    urls = project_data.get("urls", {})
    if urls:
        provenance["urls"] = "Source: pyproject.toml | Field: project.urls"

    # Extract dependencies
    dependencies = project_data.get("dependencies", [])
    if dependencies:
        provenance["dependencies"] = "Source: pyproject.toml | Field: project.dependencies"

    # Extract authors
    authors = project_data.get("authors", [])
    if authors:
        provenance["authors"] = "Source: pyproject.toml | Field: project.authors"

    # Extract license
    license_name = _extract_license(project_data)
    if license_name:
        provenance["license"] = "Source: pyproject.toml | Field: project.license"

    # Extract copyright text (inferred from authors and current year)
    if authors:
        provenance["copyright_text"] = "Source: Loom generator | Method: inferred_from_authors"

    return ProjectMetadata(
        name=name,
        version=version,
        description=description,
        readme=project_data.get("readme"),
        requires_python=project_data.get("requires-python"),
        license_name=license_name,
        keywords=project_data.get("keywords", []),
        authors=authors,
        urls=urls,
        dependencies=dependencies,
        provenance=provenance,
    )


def _extract_license(project_data: dict[str, Any]) -> str | None:
    """Extract license information from project data.

    Args:
        project_data: The [project] section data

    Returns:
        str | None: License name or None if not found
    """
    license_info = project_data.get("license")
    if isinstance(license_info, str):
        return license_info
    elif isinstance(license_info, dict):
        return license_info.get("text") or license_info.get("file")
    return None


def _extract_dynamic_version(
    project_dir: Path, pyproject_data: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Try to extract dynamic version from common patterns.

    Args:
        project_dir: The project root directory
        pyproject_data: The full pyproject.toml data

    Returns:
        tuple[str | None, str | None]: Version string and provenance source,
            or (None, None) if not found
    """
    # Check for hatch version configuration
    hatch_config = pyproject_data.get("tool", {}).get("hatch", {})
    version_config = hatch_config.get("version", {})

    if "path" in version_config:
        version_path = project_dir / version_config["path"]
        if version_path.exists():
            version = _extract_version_from_file(version_path)
            if version:
                rel_path = version_path.relative_to(project_dir)
                return version, f"Source: {rel_path} | Method: dynamic_extraction"

    # Get package name for package-specific paths
    project_name = pyproject_data.get("project", {}).get("name", "")
    package_name = project_name.replace("-", "_")

    # Try common locations
    common_paths = [
        project_dir / "src" / package_name / "__about__.py",
        project_dir / "src" / package_name / "__version__.py",
        project_dir / "src" / "__about__.py",
        project_dir / "src" / "__version__.py",
        project_dir / package_name / "__about__.py",
        project_dir / package_name / "__version__.py",
        project_dir / "__about__.py",
        project_dir / "__version__.py",
    ]

    for path in common_paths:
        if path.exists():
            version = _extract_version_from_file(path)
            if version:
                rel_path = path.relative_to(project_dir)
                return version, f"Source: {rel_path} | Method: dynamic_extraction"

    return None, None


def _extract_version_from_file(file_path: Path) -> str | None:
    """Extract version from a Python file.

    Args:
        file_path: Path to the file containing version

    Returns:
        str | None: Version string or None if not found
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        # Look for __version__ = "x.y.z" pattern
        for line in content.split("\n"):
            if "__version__" in line and "=" in line:
                # Extract version string
                parts = line.split("=", 1)
                if len(parts) == 2:
                    version_str = parts[1].strip().strip('"').strip("'")
                    return version_str
    except (OSError, UnicodeDecodeError):
        # Log error but don't fail - version extraction is optional
        # In production, could use logging.debug() here
        pass
    return None
