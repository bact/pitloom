# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for project metadata resolved by the Hatchling build backend.

Unlike :func:`~pitloom.extract.pyproject.read_pyproject`, which re-parses
``pyproject.toml`` from scratch, this module maps the metadata that
Hatchling has *already resolved* -- including dynamic ``version``,
``dependencies``, and metadata-hook-populated fields -- into Pitloom's
format-neutral :class:`~pitloom.core.project.ProjectMetadata`.  It is used
exclusively by the Hatchling build hook
(:mod:`pitloom.plugins.hatch`); the CLI continues to use
:func:`~pitloom.extract.pyproject.read_pyproject`.
"""

from __future__ import annotations

from email.utils import parseaddr
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

from pitloom.core.project import ProjectMetadata
from pitloom.extract._license import detect_license_for_project

_PROVENANCE_SOURCE = "Source: Hatchling build backend"


def _normalize_dependencies(raw_dependencies: list[str]) -> list[str]:
    """Return dependency specifiers in ``packaging`` canonical string form.

    Hatchling exposes ``core.dependencies`` as raw strings whose environment
    markers keep their source quoting (e.g. ``python_version < '3.11'``),
    whereas ``pyproject-metadata`` (used by the CLI via ``read_pyproject``)
    stringifies through ``packaging.Requirement`` (``python_version <
    "3.11"``).  Canonicalising here keeps the two paths byte-identical, so a
    project built via the hook and one described via the CLI share the same
    deterministic document UUID.  Unparseable specifiers are passed through
    unchanged rather than dropped.
    """
    normalized: list[str] = []
    for dep in raw_dependencies:
        try:
            normalized.append(str(Requirement(dep)))
        except InvalidRequirement:
            normalized.append(dep)
    return normalized


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

    readme = core.readme_path or core.readme or None

    requires_python = core.requires_python or None

    authors = _authors_from_data(core.authors_data)
    if authors:
        provenance["authors"] = _field_provenance("authors")
        provenance["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )

    urls = dict(core.urls or {})
    if urls:
        provenance["urls"] = _field_provenance("urls")

    dependencies = _normalize_dependencies(list(core.dependencies or []))
    if dependencies:
        provenance["dependencies"] = _field_provenance("dependencies")

    license_hint = core.license_expression or core.license or None
    license_name, license_prov = detect_license_for_project(project_dir, license_hint)
    if license_prov:
        provenance["license"] = license_prov
    elif license_name:
        provenance["license"] = _field_provenance("license")

    return ProjectMetadata(
        name=hatch_metadata.name,
        version=version,
        description=description,
        readme=readme,
        requires_python=requires_python,
        license_name=license_name,
        keywords=list(core.keywords or []),
        authors=authors,
        urls=urls,
        dependencies=dependencies,
        provenance=provenance,
    )


__all__ = ["metadata_from_hatchling"]
