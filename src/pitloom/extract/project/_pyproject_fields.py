# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[project]`` fields of a ``pyproject.toml`` as
:class:`pyproject_metadata.StandardMetadata` reads them: readme, authors,
the provenance of each declared field, and the confinement of a file it
would read to the project directory.

See also: :mod:`pitloom.extract.project.pyproject` (the caller).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pyproject_metadata import StandardMetadata

from pitloom.core.path_confine import OutsideRootError, open_inside
from pitloom.extract._extract_utils import field_declared
from pitloom.extract.authors import collapse_whitespace
from pitloom.messages import warn_file_unreadable

log = logging.getLogger(__name__)

#: The suffixes from which ``pyproject-metadata`` infers a readme's type.
_README_SUFFIXES = (".md", ".rst")

FIELD_PROVENANCE = {
    "description": "Source: pyproject.toml | Field: project.description",
    "urls": "Source: pyproject.toml | Field: project.urls",
    "dependencies": "Source: pyproject.toml | Field: project.dependencies",
    "authors": "Source: pyproject.toml | Field: project.authors",
    "license": "Source: pyproject.toml | Field: project.license",
    "keywords": "Source: pyproject.toml | Field: project.keywords",
    "readme": "Source: pyproject.toml | Field: project.readme",
}


def build_provenance(
    project_data: dict[str, Any],
    version_source: str | None,
    license_prov_override: str | None = None,
    description_source: str | None = None,
) -> dict[str, str]:
    """Build the provenance dict from the raw project section data."""
    prov: dict[str, str] = {
        "name": "Source: pyproject.toml | Field: project.name",
    }
    if version_source:
        prov["version"] = version_source
    elif field_declared(project_data, "version"):
        prov["version"] = "Source: pyproject.toml | Field: project.version"

    for field_key, source in FIELD_PROVENANCE.items():
        if field_key == "description" and description_source:
            prov["description"] = description_source
        elif field_key == "license":
            # license_prov_override, when truthy, always sets prov["license"]
            # here -- nothing downstream can unset it, so no post-loop
            # fallback is needed for that case.
            if license_prov_override:
                prov["license"] = license_prov_override
            elif field_declared(project_data, field_key):
                prov["license"] = source
        elif field_declared(project_data, field_key):
            prov[field_key] = source

    return prov


def strip_missing_readme(
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


def drop_outside_file(
    data: dict[str, Any],
    project_dir: Path,
    key: str,
    file: tuple[str, str],
    *,
    quiet: bool = False,
) -> dict[str, Any]:
    """*data* (a parsed ``pyproject.toml`` in *project_dir*) without
    ``project.<key>`` when the file *file* names, ``(name, field)``, is
    outside *project_dir* (``..``, absolute or a symlink out;
    :func:`~pitloom.core.path_confine.open_inside`), which
    ``pyproject-metadata`` would read, with one
    ``file-unreadable/outside-project`` ``WARNING:`` per file, field and
    process unless *quiet*. Any other failure to open it is left for
    ``pyproject-metadata`` to report."""
    name, field = file
    try:
        with open_inside(project_dir / name, project_dir):
            return data
    except OutsideRootError as exc:
        if not quiet:
            warn_file_unreadable(
                log,
                exc,
                file=name,
                field=field,
                once=f"outside:{field}:{project_dir / name}",
            )
    except (OSError, ValueError):
        return data
    kept = {k: v for k, v in data["project"].items() if k != key}
    return {**data, "project": kept}


def _readme_file(readme: object) -> tuple[str, str] | None:
    """``(name, field)`` of the file ``pyproject-metadata`` reads for
    ``project.readme``: a name with a suffix it infers a type from, or a
    table of exactly a ``file`` and a ``content-type``. ``None`` for text,
    or a shape it rejects (or ignores) without reading a file."""
    if isinstance(readme, str):
        return (readme, "project.readme") if readme.endswith(_README_SUFFIXES) else None
    if (
        isinstance(readme, dict)
        and set(readme) == {"file", "content-type"}
        and all(isinstance(v, str) and v for v in readme.values())
    ):
        return readme["file"], "project.readme.file"
    return None


def confine_readme_file(
    data: dict[str, Any], project_dir: Path, *, quiet: bool = False
) -> dict[str, Any]:
    """*data* (with a ``[project]`` table) without ``project.readme`` when
    the file it names is outside *project_dir* (:func:`drop_outside_file`)."""
    file = _readme_file(data["project"].get("readme"))
    if file is None:
        return data
    return drop_outside_file(data, project_dir, "readme", file, quiet=quiet)


def extract_readme(std: StandardMetadata, override: str | None) -> str | None:
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


def extract_authors(
    std: StandardMetadata, project_data: dict[str, Any]
) -> list[dict[str, str]]:
    """Return authors as a list of ``{name, email?}`` dicts.

    ``pyproject_metadata`` fills ``"Unknown"`` for an entry declaring only an
    ``email``; the raw ``[project].authors`` entry (same order) says whether a
    name was declared, and an undeclared one stays absent. A name has its
    white space collapsed, as every surface reads it
    (:func:`~pitloom.extract.authors.collapse_whitespace`).
    """
    result = []
    # std.authors is validated one-to-one with the raw entries.
    raws = project_data.get("authors", [])
    for (name, email), raw in zip(std.authors, raws, strict=True):
        name = collapse_whitespace(name or "") if raw.get("name") else ""
        entry: dict[str, str] = {"name": name} if name else {}
        if email:
            entry["email"] = email
        if entry:
            result.append(entry)
    return result
