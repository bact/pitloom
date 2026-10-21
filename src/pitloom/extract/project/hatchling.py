# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for project metadata resolved by the Hatchling build backend.

Unlike :func:`~pitloom.extract.project.pyproject.read_pyproject`, which re-parses
``pyproject.toml`` from scratch, this module maps the metadata that
Hatchling has *already resolved* -- including dynamic ``version``,
``dependencies``, and metadata-hook-populated fields -- into Pitloom's
format-neutral :class:`~pitloom.core.project.ProjectMetadata`.  Only the
Hatchling build hook (:mod:`pitloom.plugins.hatch`) uses it; the CLI uses
:func:`~pitloom.extract.project.pyproject.read_pyproject`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom._toml_io import load_toml_file
from pitloom.core.project import ProjectMetadata
from pitloom.core.requirements import normalize_dependency_specifier
from pitloom.extract._core_metadata import license_or_classifier
from pitloom.extract._extract_utils import field_declared
from pitloom.extract._license import (
    apply_in_package_license_files,
    stated_license,
)
from pitloom.extract._license_detect import read_license_members
from pitloom.extract.authors import collapse_whitespace
from pitloom.extract.project._optional_dependencies import add_optional_dependencies
from pitloom.extract.project.pyproject import fill_from_poetry

_PROVENANCE_SOURCE = "Source: Hatchling build backend"


def _poetry_fallback_metadata(
    metadata: ProjectMetadata, project_dir: Path
) -> tuple[ProjectMetadata, bool]:
    """*metadata* with gaps filled from *project_dir*'s ``[tool.poetry]``
    as :func:`~pitloom.extract.project.pyproject.read_pyproject` fills them
    (:func:`~pitloom.extract.project.pyproject.fill_from_poetry`), and
    whether its dependency lists replace ``[project]``'s. *metadata* is
    returned as is when ``pyproject.toml`` is missing.

    Passes ``include_locked_dependencies=False``: this path runs from the
    Hatchling build hook (build/embed stage), where ``poetry.lock`` --
    a source-stage-only artifact never consulted by the real build -- must
    not influence the emitted SBOM. See
    :mod:`pitloom.extract.lock.poetry`'s module docstring.
    """
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return metadata, False
    data: dict[str, Any] = load_toml_file(pyproject_path)
    return fill_from_poetry(
        metadata, data, project_dir, include_locked_dependencies=False
    )


def _declared_authors(authors: list[dict[str, str]]) -> list[dict[str, str]]:
    """Hatchling's ``authors`` as ``[{name?, email?}, ...]`` in declared
    order, without empty values and entries left with neither, a name's
    white space collapsed
    (:func:`~pitloom.extract.authors.collapse_whitespace`)."""
    result = []
    for entry in authors:
        named = {**entry, "name": collapse_whitespace(entry.get("name") or "")}
        author = {k: v for k, v in named.items() if k in ("name", "email") and v}
        if author:
            result.append(author)
    return result


def _field_provenance(field_name: str) -> str:
    """Return the standard provenance string for a resolved core-metadata field."""
    return f"{_PROVENANCE_SOURCE} | Field: project.{field_name}"


def _hatchling_field_declared(core: Any, project_key: str) -> bool:
    """Return whether ``[project.<project_key>]`` was actually declared,
    via ``core.config`` (the raw, unprocessed ``[project]`` table) --
    never a container field's own *parsed* truthiness, which can't
    distinguish "declared but empty" (e.g. ``dependencies = []``, a
    genuine, authoritative zero) from "not declared at all" (fall back to
    a lower-priority source in :func:`pitloom.core.project.merge_project_metadata`).
    ``core.config`` access can raise ``OSError`` the same way the
    property accessors it backs can (see :func:`_resolve_hatchling_readme`),
    so the lookup goes through :func:`field_declared` rather than a bare
    ``in`` check.
    """
    try:
        config = core.config
    except OSError:
        return False
    return field_declared(config, project_key)


def _resolve_hatchling_readme(core: Any) -> str | None:
    """Extract readme string or path safely from Hatchling core metadata."""
    try:
        return core.readme_path or core.readme or None
    except OSError:
        return None


def _resolve_hatchling_license(core: Any, provenance: dict[str, str]) -> str | None:
    """The licence Hatchling core states: ``project.license``, then a
    ``License ::`` classifier (the rule every surface uses). The project's
    own licence files follow in :func:`metadata_from_hatchling`."""
    try:
        license_hint = core.license_expression or core.license or None
    except OSError:
        license_hint = None

    license_hint, from_classifier = license_or_classifier(
        license_hint, core.classifiers or []
    )
    if from_classifier:
        provenance["license"] = _field_provenance("classifiers")
        return license_hint
    license_name, license_prov = stated_license(
        license_hint, _field_provenance("license")
    )
    if license_prov:
        provenance["license"] = license_prov
    elif license_name:
        provenance["license"] = _field_provenance("license")
    return license_name


def metadata_from_hatchling(
    hatch_metadata: Any,
    project_dir: Path,
) -> ProjectMetadata:
    """Map Hatchling's resolved project metadata into a :class:`ProjectMetadata`."""
    core = hatch_metadata.core
    version = str(hatch_metadata.version) if hatch_metadata.version else None
    provenance: dict[str, str] = {
        "name": _field_provenance("name"),
    }
    if version:
        provenance["version"] = _field_provenance("version")

    description = core.description or None
    if description:
        provenance["description"] = _field_provenance("description")

    readme = _resolve_hatchling_readme(core)
    if _hatchling_field_declared(core, "readme"):
        provenance["readme"] = _field_provenance("readme")

    requires_python = core.requires_python or None
    # Presence-gated, not truthy-gated -- see AGENTS.md's "``None``/absent
    # vs ``[]``/``{}``" rule: an explicit `requires-python = ""` is PEP 621's
    # equivalent of Poetry's `python = "*"`.
    if _hatchling_field_declared(core, "requires-python"):
        provenance["requires_python"] = _field_provenance("requires-python")

    # Provenance for a container field is gated on presence in the raw
    # [project] table (`_hatchling_field_declared`), not on the resolved
    # value's truthiness -- an explicitly declared but empty
    # `dependencies = []` is a genuine, authoritative "zero" that
    # merge_project_metadata() must not silently fill in from a
    # lower-priority source ([tool.poetry] gap-fill below).
    authors = _declared_authors(core.authors or [])
    if _hatchling_field_declared(core, "authors"):
        provenance["authors"] = _field_provenance("authors")

    urls = dict(core.urls or {})
    if _hatchling_field_declared(core, "urls"):
        provenance["urls"] = _field_provenance("urls")

    dependencies = [
        normalize_dependency_specifier(dep) for dep in (core.dependencies or [])
    ]
    if _hatchling_field_declared(core, "dependencies"):
        provenance["dependencies"] = _field_provenance("dependencies")

    if _hatchling_field_declared(core, "keywords"):
        provenance["keywords"] = _field_provenance("keywords")

    license_name = _resolve_hatchling_license(core, provenance)

    metadata = ProjectMetadata(
        name=core.raw_name,
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
    apply_in_package_license_files(metadata, read_license_members(project_dir))

    # Fill any remaining gaps from [tool.poetry], exactly mirroring what
    # read_pyproject() does for the CLI path (project fields always win).
    metadata, from_poetry = _poetry_fallback_metadata(metadata, project_dir)
    # Hatchling has already expanded a self-reference (`demo[dev]`).
    add_optional_dependencies(
        metadata,
        core.optional_dependencies,
        declared=_hatchling_field_declared(core, "optional-dependencies")
        and not from_poetry,
        source=_PROVENANCE_SOURCE,
    )

    return metadata


__all__ = ["metadata_from_hatchling"]
