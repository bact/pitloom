# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from pyproject.toml.

Supports ``[project]`` (PEP 517/518/621) and ``[tool.poetry]`` sections.
When both are present, ``[project]`` values take precedence and
``[tool.poetry]`` fills any gaps.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pyproject_metadata import StandardMetadata

from pitloom.core.config import PitloomConfig, _read_pitloom_config
from pitloom.core.project import ProjectMetadata
from pitloom.extract._license import (
    _looks_like_spdx_license_expression,
    _looks_like_spdx_license_id,
    detect_license_for_project,
)
from pitloom.extract.poetry import extract_poetry_metadata

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def read_pyproject(pyproject_path: Path) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from a ``pyproject.toml`` file.

    Parses the ``[project]`` section via ``pyproject-metadata``, resolves
    dynamic versions, and reads Pitloom-specific settings from ``[tool.pitloom]``.
    When ``[project]`` is absent or has no ``name``, falls back to
    ``[tool.poetry]``.  When both sections are present, ``[project]`` wins
    field-by-field and ``[tool.poetry]`` fills any gaps.

    Args:
        pyproject_path: Path to the ``pyproject.toml`` file.

    Returns:
        A 2-tuple of:

        * :class:`~pitloom.core.project.ProjectMetadata` -- populated project
          metadata.
        * :class:`~pitloom.core.config.PitloomConfig` -- settings from
          ``[tool.pitloom]`` (all fields default gracefully when the section is
          absent).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If ``pyproject-metadata`` cannot parse the ``[project]`` section.
    """
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data: dict[str, Any] = tomllib.load(f)

    project_data: dict[str, Any] = data.get("project", {})
    pitloom_config = _read_pitloom_config(data)

    name: str = (project_data.get("name") or "").strip()

    if not project_data or not name:
        # No [project] section (or no name) -- try [tool.poetry] as primary source.
        poetry_meta = _try_read_poetry(data)
        if poetry_meta is not None:
            return poetry_meta, pitloom_config
        license_name, license_prov = detect_license_for_project(pyproject_path.parent)
        prov: dict[str, str] = {}
        if name:
            prov["name"] = "Source: pyproject.toml | Field: project.name"
        if license_prov:
            prov["license"] = license_prov
        return (
            ProjectMetadata(name=name, license_name=license_name, provenance=prov),
            pitloom_config,
        )

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

    try:
        std = StandardMetadata.from_pyproject(
            data,
            project_dir=str(pyproject_path.parent),
            dynamic_metadata=dynamic_fields or None,
            allow_extra_keys=True,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to parse project metadata: {exc}") from exc

    license_name, license_prov = _extract_and_detect_license(std, pyproject_path.parent)

    metadata = ProjectMetadata(
        name=std.name,
        version=str(std.version) if std.version else None,
        description=std.description,
        readme=_extract_readme(std, readme_override),
        requires_python=str(std.requires_python) if std.requires_python else None,
        license_name=license_name,
        keywords=std.keywords or [],
        authors=_extract_authors(std),
        urls=std.urls or {},
        dependencies=[str(d) for d in std.dependencies],
        provenance=_build_provenance(
            data.get("project", {}), version_source, license_prov
        ),
    )

    # Fill any remaining gaps from [tool.poetry] (project fields win).
    poetry_meta = _try_read_poetry(data)
    if poetry_meta is not None:
        metadata = _merge_with_poetry(metadata, poetry_meta)

    return metadata, pitloom_config


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
    license_prov_override: str | None = None,
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
        if field_key == "license":
            if license_prov_override:
                prov["license"] = license_prov_override
            elif field_key in project_data:
                prov["license"] = source
        elif field_key in project_data:
            prov[field_key] = source

    if license_prov_override and "license" not in prov:
        prov["license"] = license_prov_override

    if project_data.get("authors"):
        prov["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )

    return prov


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


def _resolve_license_hint(
    license_obj: Any,
    project_dir: Path,
) -> tuple[str | None, str, tuple[str | None, str | None]]:
    """Extract ``(hint, base_prov, fallback)`` from a raw license object.

    *hint* is the text or string to attempt detection on.  *fallback* is the
    ``(license_id, provenance)`` pair to return when detection finds nothing
    new.  Returns ``hint=None`` when the object format is unrecognised or the
    referenced file cannot be read.
    """
    base = "Source: pyproject.toml | Field: project.license"
    if isinstance(license_obj, str):
        # str: let detect_license_for_project provide the fallback
        return license_obj.strip(), base, (None, None)
    if hasattr(license_obj, "text") and license_obj.text:
        hint = license_obj.text
        return hint, f"{base}.text", (hint, None)
    if hasattr(license_obj, "file") and license_obj.file:
        fname = str(license_obj.file)
        try:
            text = (project_dir / fname).read_text(encoding="utf-8", errors="replace")
            return text, f"Source: {fname}", (fname, None)
        except OSError:
            return None, base, (fname, None)
    return None, base, (str(license_obj), None)


def _extract_and_detect_license(
    std: StandardMetadata,
    project_dir: Path,
) -> tuple[str | None, str | None]:
    """Return ``(license_id, provenance_override)`` from StandardMetadata.

    Handles both plain string format (PEP 639) and License object format.
    When the metadata field contains license text rather than an SPDX License ID,
    falls back to :func:`~pitloom.extract._license.detect_license_for_project`
    which searches the project directory and uses the ``licenseid`` library for
    text-based detection.

    Returns a 2-tuple:

    * ``license_id`` -- SPDX License ID, SPDX License Expression,
      or raw string fallback.
    * ``provenance_override`` -- non-``None`` when provenance differs from the
      default ``pyproject.toml`` field string (e.g. detected from a file).
    """
    license_obj = std.license
    if not license_obj:
        return detect_license_for_project(project_dir)

    hint, base_prov, fallback = _resolve_license_hint(license_obj, project_dir)
    if hint is None:
        return fallback

    if _looks_like_spdx_license_id(hint) or _looks_like_spdx_license_expression(hint):
        return hint, None

    detected, prov = detect_license_for_project(project_dir, hint)
    if detected and detected != hint:
        return detected, f"{base_prov} | Method: licenseid_detection"

    fallback_id, fallback_prov = fallback
    if fallback_id is not None:
        return fallback_id, fallback_prov
    return detected, prov


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


def _try_read_poetry(
    data: dict[str, Any],
) -> ProjectMetadata | None:
    """Return poetry metadata when ``[tool.poetry]`` is present, else ``None``."""
    if not data.get("tool", {}).get("poetry"):
        return None
    try:
        return extract_poetry_metadata(data)
    except (ValueError, KeyError):
        return None


def _merge_with_poetry(
    primary: ProjectMetadata,
    secondary: ProjectMetadata,
) -> ProjectMetadata:
    """Return *primary* with empty/falsy fields filled from *secondary*.

    ``primary`` is always the ``[project]`` metadata; ``secondary`` is the
    ``[tool.poetry]`` metadata.  Provenance entries are merged with primary
    entries winning on key conflicts.
    """

    def _pick(p: Any, s: Any) -> Any:
        return p if p else s

    return ProjectMetadata(
        name=primary.name,
        version=_pick(primary.version, secondary.version),
        description=_pick(primary.description, secondary.description),
        readme=_pick(primary.readme, secondary.readme),
        requires_python=_pick(primary.requires_python, secondary.requires_python),
        license_name=_pick(primary.license_name, secondary.license_name),
        keywords=_pick(primary.keywords, secondary.keywords),
        authors=_pick(primary.authors, secondary.authors),
        urls=_pick(primary.urls, secondary.urls),
        dependencies=_pick(primary.dependencies, secondary.dependencies),
        provenance={**secondary.provenance, **primary.provenance},
        files=_pick(primary.files, secondary.files),
    )
