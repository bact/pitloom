# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for project metadata resolved by the Hatchling build backend.

Unlike :func:`~pitloom.extract._pyproject.read_pyproject`, which re-parses
``pyproject.toml`` from scratch, this module maps the metadata that
Hatchling has *already resolved* -- including dynamic ``version``,
``dependencies``, and metadata-hook-populated fields -- into Pitloom's
format-neutral :class:`~pitloom.core.project.ProjectMetadata`.  It is used
exclusively by the Hatchling build hook
(:mod:`pitloom.plugins.hatch`); the CLI continues to use
:func:`~pitloom.extract._pyproject.read_pyproject`.
"""

from __future__ import annotations

import sys
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from pitloom.core.models import normalize_dependency_specifier
from pitloom.core.project import ProjectMetadata, merge_project_metadata
from pitloom.extract._license import (
    detect_license_for_project,
    resolve_license_concluded,
)
from pitloom.extract._pyproject import _try_read_poetry

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_PROVENANCE_SOURCE = "Source: Hatchling build backend"


def _poetry_fallback_metadata(project_dir: Path) -> ProjectMetadata | None:
    """Return ``[tool.poetry]`` gap-fill metadata for *project_dir*, or ``None``.

    Mirrors the fallback :func:`~pitloom.extract._pyproject.read_pyproject`
    already performs: re-reads ``pyproject.toml`` and reuses
    :func:`~pitloom.extract._pyproject._try_read_poetry` so the Hatchling hook
    path can also recover ``authors``/``keywords``/``urls`` (and similar)
    from ``[tool.poetry]`` when ``[project]`` is incomplete. Returns ``None``
    when ``pyproject.toml`` is missing or has no usable ``[tool.poetry]``
    section.
    """
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return None
    with open(pyproject_path, "rb") as f:
        data: dict[str, Any] = tomllib.load(f)
    return _try_read_poetry(data, project_dir)


def _authors_from_data(authors_data: dict[str, list[str]]) -> list[dict[str, str]]:
    """Convert Hatchling's ``authors_data`` into ``[{name, email?}, ...]``.

    ``authors_data`` has two keys populated by
    ``hatchling.metadata.core.CoreMetadata.authors_data``:

    - ``"name"``: authors that declared only a ``name`` (no email).
    - ``"email"``: RFC 5322 address strings for authors that declared an
      ``email`` (``"Name <email>"`` when a name was also given, or a bare
      ``"email"`` otherwise).
    """
    result: list[dict[str, str]] = []

    for name in authors_data.get("name", []):
        if name:
            result.append({"name": name})

    for entry in authors_data.get("email", []):
        display_name, email_address = parseaddr(entry)
        author: dict[str, str] = {}
        if display_name:
            author["name"] = display_name
        if email_address:
            author["email"] = email_address
        if author:
            result.append(author)

    return result


def _field_provenance(field_name: str) -> str:
    """Return the standard provenance string for a resolved core-metadata field."""
    return f"{_PROVENANCE_SOURCE} | Field: project.{field_name}"


def metadata_from_hatchling(
    hatch_metadata: Any,
    project_dir: Path,
) -> ProjectMetadata:
    """Map Hatchling's resolved project metadata into a :class:`ProjectMetadata`.

    Args:
        hatch_metadata: An object exposing ``.core`` (Hatchling's
            ``CoreMetadata``, resolved PEP 621 fields) and ``.version`` (the
            resolved project version). In production this is
            ``hatchling.metadata.core.ProjectMetadata``
            (``BuildHookInterface.metadata``); tests may pass a lightweight
            duck-typed stand-in exposing the same two attributes.
        project_dir: Project root directory, used for the license-detection
            fallback when neither ``license`` nor ``license_expression`` is
            declared.

    Returns:
        Populated :class:`~pitloom.core.project.ProjectMetadata` with
        per-field provenance recorded in
        :attr:`~pitloom.core.project.ProjectMetadata.provenance`.
    """
    core = hatch_metadata.core
    version = str(hatch_metadata.version) if hatch_metadata.version else None

    provenance: dict[str, str] = {"name": _field_provenance("name")}
    if version:
        provenance["version"] = _field_provenance("version")

    description = core.description or None
    if description:
        provenance["description"] = _field_provenance("description")

    # core.readme / core.readme_path are lazily evaluated and raise a bare
    # OSError when the declared readme file does not exist on disk. Degrade
    # gracefully instead of crashing the build, mirroring read_pyproject()'s
    # tolerance for the same situation (_strip_missing_readme).
    try:
        readme = core.readme_path or core.readme or None
    except OSError:
        readme = None

    requires_python = core.requires_python or None

    authors = _authors_from_data(core.authors_data or {})
    if authors:
        provenance["authors"] = _field_provenance("authors")
        provenance["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )

    urls = dict(core.urls or {})
    if urls:
        provenance["urls"] = _field_provenance("urls")

    dependencies = [
        normalize_dependency_specifier(dep) for dep in (core.dependencies or [])
    ]
    if dependencies:
        provenance["dependencies"] = _field_provenance("dependencies")

    # core.license / core.license_expression can likewise raise a bare
    # OSError when a declared license *file* does not exist on disk.
    try:
        license_hint = core.license_expression or core.license or None
    except OSError:
        license_hint = None
    license_name, license_prov = detect_license_for_project(project_dir, license_hint)
    if license_prov:
        provenance["license"] = license_prov
    elif license_name:
        provenance["license"] = _field_provenance("license")

    # G2: independently scan project_dir for a second opinion when a license
    # was declared, exactly like read_pyproject() does for the CLI path --
    # via the shared resolve_license_concluded() so this can't drift out of
    # sync again (see its docstring for why this was previously missing here).
    license_concluded, license_concluded_prov = resolve_license_concluded(
        bool(license_hint), project_dir
    )
    if license_concluded and license_concluded_prov:
        provenance["license_concluded"] = license_concluded_prov

    metadata = ProjectMetadata(
        name=core.raw_name,
        version=version,
        description=description,
        readme=readme,
        requires_python=requires_python,
        license_name=license_name,
        license_concluded=license_concluded,
        keywords=list(core.keywords or []),
        authors=authors,
        urls=urls,
        dependencies=dependencies,
        provenance=provenance,
    )

    # Fill any remaining gaps from [tool.poetry], exactly mirroring what
    # read_pyproject() does for the CLI path (project fields always win).
    poetry_meta = _poetry_fallback_metadata(project_dir)
    if poetry_meta is not None:
        metadata = merge_project_metadata(metadata, poetry_meta)

    return metadata


__all__ = ["metadata_from_hatchling"]
