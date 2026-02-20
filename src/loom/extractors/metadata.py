# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from pyproject.toml."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pyproject_metadata import StandardMetadata

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ProjectMetadata:
    """Wrapper around StandardMetadata with provenance tracking.

    This class wraps pyproject_metadata.StandardMetadata and adds
    provenance tracking for metadata fields to support SBOM generation.
    """

    def __init__(
        self,
        standard_metadata: StandardMetadata,
        provenance: dict[str, str] | None = None,
        readme_override: str | None = None,
    ) -> None:
        """Initialize ProjectMetadata from StandardMetadata.

        Args:
            standard_metadata: The StandardMetadata instance from pyproject-metadata
            provenance: Dictionary tracking the source of each metadata field
            readme_override: Optional readme value to use when file doesn't exist
        """
        self._standard_metadata = standard_metadata
        self.provenance = provenance or {}
        self._readme_override = readme_override
        self.fragments: list[str] = []

    @property
    def name(self) -> str:
        """Project name."""
        return self._standard_metadata.name

    @property
    def version(self) -> str | None:
        """Project version."""
        version = self._standard_metadata.version
        return str(version) if version else None

    @property
    def description(self) -> str | None:
        """Project description."""
        return self._standard_metadata.description

    @property
    def readme(self) -> str | None:
        """Project readme file or text."""
        # Use override if provided (for cases where file doesn't exist)
        if self._readme_override is not None:
            return self._readme_override

        readme = self._standard_metadata.readme
        if readme:
            # readme is a Readme object with .file or .text attributes
            if hasattr(readme, "file") and readme.file:
                return str(readme.file)
            elif hasattr(readme, "text") and readme.text:
                return readme.text
        return None

    @property
    def requires_python(self) -> str | None:
        """Python version requirement."""
        requires_python = self._standard_metadata.requires_python
        return str(requires_python) if requires_python else None

    @property
    def license_name(self) -> str | None:
        """Project license.

        Returns the SPDX license identifier as a string.
        Handles both plain string format (PEP 639 recommended)
        and License object format (from table-based format).

        Current implementation does not handle license expression.
        """
        # TODO:
        # - Handle license expression,
        #   could use https://pypi.org/project/license-expression/
        # - Validate license name of SPDX License List
        #   https://spdx.org/licenses/ and ScanCode LicenseDB
        #   https://scancode-licensedb.aboutcode.org/,
        #   and display warning if license is not found in
        #   those lists
        license_obj = self._standard_metadata.license
        if license_obj:
            # In pyproject-metadata 0.10.0+:
            # - Plain string format (license = "Apache-2.0") returns str
            # - Table format (license = {text = "..."}) returns License object
            if isinstance(license_obj, str):
                return license_obj
            elif hasattr(license_obj, "text") and license_obj.text:
                return license_obj.text
            elif hasattr(license_obj, "file") and license_obj.file:
                # TODO: Identify actual SPDX License ID from the license text.
                # Few libraries are available for this task:
                # - https://pypi.org/project/scancode-toolkit/
                #   (Python, extremely accurate)
                # - https://pypi.org/project/spdx-matcher/
                #   (Python, lightweight)
                # - https://github.com/jpeddicord/askalono
                #   (Rust, very fast)
                # - https://github.com/spdx/spdx-license-matcher
                #   (Python, from SPDX project, no wheels, needs Java and Redis)
                return str(license_obj.file)
            else:
                return str(license_obj)
        return None

    @property
    def keywords(self) -> list[str]:
        """Project keywords."""
        return self._standard_metadata.keywords or []

    @property
    def authors(self) -> list[dict[str, str]]:
        """Project authors as list of dicts with 'name' and optional 'email'."""
        authors_list = []
        for name, email in self._standard_metadata.authors:
            author_dict = {"name": name}
            if email:
                author_dict["email"] = email
            authors_list.append(author_dict)
        return authors_list

    @property
    def urls(self) -> dict[str, str]:
        """Project URLs."""
        return self._standard_metadata.urls or {}

    @property
    def dependencies(self) -> list[str]:
        """Project dependencies as list of requirement strings."""
        return [str(dep) for dep in self._standard_metadata.dependencies]


def extract_metadata_from_pyproject(pyproject_path: Path) -> ProjectMetadata:
    """Extract project metadata from pyproject.toml using pyproject-metadata.

    Note: This function uses pyproject_metadata.StandardMetadata which focuses
    on the [project] section. The [tool] and [build-system] sections are not
    processed by StandardMetadata but are preserved in the raw data for dynamic
    version extraction (e.g., [tool.hatch.version]) which is handled separately.

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

    # Check for dynamic version and extract it
    dynamic_fields = project_data.get("dynamic", [])
    dynamic_metadata = list(dynamic_fields) if dynamic_fields else []

    if "version" in dynamic_fields:
        # Extract version from file for provenance tracking
        version, version_source = _extract_dynamic_version(pyproject_path.parent, data)
        if version:
            # Inject the extracted version into the data
            data = dict(data)  # Make a copy
            data["project"] = dict(project_data)  # Make a copy of project section
            data["project"]["version"] = version
            # Remove version from dynamic list
            data["project"]["dynamic"] = [f for f in dynamic_fields if f != "version"]
            # Update dynamic_metadata
            dynamic_metadata = [f for f in dynamic_fields if f != "version"]
        if version_source:
            provenance["version"] = version_source
    elif "version" in project_data:
        provenance["version"] = "Source: pyproject.toml | Field: project.version"

    # Track provenance for other fields
    if "description" in project_data:
        provenance["description"] = (
            "Source: pyproject.toml | Field: project.description"
        )

    if "urls" in project_data:
        provenance["urls"] = "Source: pyproject.toml | Field: project.urls"

    if "dependencies" in project_data:
        provenance["dependencies"] = (
            "Source: pyproject.toml | Field: project.dependencies"
        )

    if "authors" in project_data:
        provenance["authors"] = "Source: pyproject.toml | Field: project.authors"

    if "license" in project_data:
        provenance["license"] = "Source: pyproject.toml | Field: project.license"

    # Extract copyright text (inferred from authors and current year)
    if project_data.get("authors"):
        provenance["copyright_text"] = (
            "Source: Loom generator | Method: inferred_from_authors"
        )

    # Check if readme file exists, if not, remove it from data to avoid validation errors
    readme_field = project_data.get("readme")
    readme_override = None
    if readme_field and isinstance(readme_field, str):
        readme_path = pyproject_path.parent / readme_field
        if not readme_path.exists():
            # Store the readme value for the override
            readme_override = readme_field
            # Create a modified copy of the data without the readme field
            data = dict(
                data
            )  # Make a copy (may already be a copy from version handling)
            data["project"] = dict(
                data["project"]
            )  # Make a copy of project section (use current data, not original)
            del data["project"]["readme"]  # Remove readme to skip validation

    # Extract Loom specific configuration
    tool_data = data.get("tool", {})
    loom_data = tool_data.get("loom", {})
    fragments_data = loom_data.get("fragments", {})
    fragments = fragments_data.get("files", [])

    # Use StandardMetadata to parse and validate
    try:
        standard_metadata = StandardMetadata.from_pyproject(
            data,
            project_dir=str(pyproject_path.parent),
            dynamic_metadata=dynamic_metadata if dynamic_metadata else None,
            allow_extra_keys=True,
        )
    except Exception as e:
        raise ValueError(f"Failed to parse project metadata: {e}") from e

    metadata_instance = ProjectMetadata(
        standard_metadata=standard_metadata,
        provenance=provenance,
        readme_override=readme_override,
    )
    if isinstance(fragments, list):
        metadata_instance.fragments = [str(f) for f in fragments]
    
    return metadata_instance


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
