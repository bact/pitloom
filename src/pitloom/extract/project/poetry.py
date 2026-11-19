# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from ``[tool.poetry]`` in pyproject.toml.

Supports Poetry-based projects that declare metadata under ``[tool.poetry]``
(and optionally ``[tool.poetry.dependencies]``).

.. rubric:: Field mapping

+----------------------------------+----------------------------------+
| ``[tool.poetry]`` key            | :class:`~pitloom.core.project`   |
|                                  | ``.ProjectMetadata`` field       |
+==================================+==================================+
| ``name``                         | ``name``                         |
+----------------------------------+----------------------------------+
| ``version``                      | ``version``                      |
+----------------------------------+----------------------------------+
| ``description``                  | ``description``                  |
+----------------------------------+----------------------------------+
| ``readme``                       | ``readme``                       |
+----------------------------------+----------------------------------+
| ``authors``                      | ``authors``                      |
+----------------------------------+----------------------------------+
| ``license``                      | ``license_name``                 |
+----------------------------------+----------------------------------+
| ``keywords``                     | ``keywords``                     |
+----------------------------------+----------------------------------+
| ``homepage``                     | ``urls["Homepage"]``             |
+----------------------------------+----------------------------------+
| ``repository``                   | ``urls["Repository"]``           |
+----------------------------------+----------------------------------+
| ``documentation``                | ``urls["Documentation"]``        |
+----------------------------------+----------------------------------+
| ``dependencies.python``          | ``requires_python``              |
+----------------------------------+----------------------------------+
| ``dependencies`` (non-python)    | ``dependencies``                 |
+----------------------------------+----------------------------------+
| ``extras``                       | ``dependencies`` (tagged         |
|                                  | ``extra == "x"``)                |
+----------------------------------+----------------------------------+

.. rubric:: Dependency conversion

Each dependency becomes the requirement poetry-core writes for it
(:mod:`pitloom.extract.project._poetry_requirements`): its version
constraint, ``extras``, ``git``/``url`` source and ``markers``/``python``/
``platform`` keys; a ``path`` source is skipped with a ``WARNING:``. The
``python`` key's own constraint (``requires_python``) is converted on a
best-effort basis:

* ``^X.Y.Z`` (X > 0) -> ``>=X.Y.Z,<X+1.0.0``
* ``^0.Y.Z``          -> ``>=0.Y.Z,<0.Y+1.0``
* ``~X.Y.Z``          -> ``>=X.Y.Z,<X.Y+1.0``
* ``*``               -> no constraint
* Anything else       -> passed through unchanged.

With a non-empty ``[project] optional-dependencies``, no ``[project]
dependencies`` and neither in ``[project] dynamic``, poetry-core ignores
the table's dependencies, and so does this module, with a ``WARNING:``.

.. rubric:: Extras

A dependency with ``optional = true`` belongs to no base requirement; it is
listed once per extra that names it in ``[tool.poetry.extras]``, tagged
``extra == "x"`` as a built wheel's ``Requires-Dist`` has it. An optional
dependency named by no extra is dropped with a ``WARNING:`` (Poetry never
installs it). ``group.*`` tables are not listed (no wheel equivalent).

Wrong-typed keys are dropped first by
:mod:`pitloom.extract.project._poetry_fields`; ``[tool.poetry.extras]`` is
read by :mod:`pitloom.extract.project._poetry_extras`.

See Also:
    https://python-poetry.org/docs/pyproject/
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pitloom.core.internal_error import InternalError
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import provenance_segment, provenance_source
from pitloom.extract._extract_utils import field_declared
from pitloom.extract._license import (
    apply_in_package_license_files,
)
from pitloom.extract._license_detect import read_license_members
from pitloom.extract.authors import collapse_whitespace
from pitloom.extract.project._poetry_deps import parse_poetry_deps
from pitloom.extract.project._poetry_extras import (
    drop_ignored_dependencies,
    drop_ignored_extras,
)
from pitloom.extract.project._poetry_fields import (
    drop_wrong_typed_fields,
    is_table,
    read_poetry_section,
    warn_wrong_type,
)
from pitloom.messages import CodedValueError
from pitloom.messages.metadata import (
    METADATA_INVALID,
    POETRY_NAME_LINE,
    PROJECT_NAME_MISSING,
    TYPE_ERROR_LINE,
)

log = logging.getLogger(__name__)

#: The provenance of authors read from ``[tool.poetry].authors``.
POETRY_AUTHORS_SOURCE = "Source: pyproject.toml | Field: tool.poetry.authors"

# Matches "Name <email>", "Name", or "<email>"
_AUTHOR_RE = re.compile(r"^(?P<name>[^<]*?)\s*(?:<(?P<email>[^>]+)>)?$")


# pylint: disable-next=too-many-locals
def extract_poetry_metadata(
    data: dict[str, Any],
    project_dir: Path,
    *,
    quiet: bool = False,
) -> ProjectMetadata:
    """Extract :class:`~pitloom.core.project.ProjectMetadata` from pre-loaded data.

    Reads ``[tool.poetry]`` and ``[tool.poetry.dependencies]`` from a
    previously parsed ``pyproject.toml`` dict.  This is the internal entry
    point used by :func:`~pitloom.extract.project.pyproject.read_pyproject` so the
    file is not read twice. A key of the wrong type (``version = 3``) is
    treated as absent with one ``WARNING:``; so is a ``[tool]`` or
    ``[tool.poetry]`` that is not a table.

    Args:
        data: Full parsed ``pyproject.toml`` dict.
        project_dir: Project root directory -- its licence files, read
            by the one rule every project reader applies
            (:func:`~pitloom.extract._license.apply_in_package_license_files`).
        quiet: Suppress this extraction's own ``WARNING:`` lines (default
            ``False``) -- for a caller re-reading the same, already-read
            *data* a second time; see
            :func:`pitloom.extract.project.read_project`'s own ``quiet``.

    Returns:
        A populated :class:`~pitloom.core.project.ProjectMetadata`.

    Raises:
        pitloom.messages.CodedValueError: ``[tool.poetry]`` is not a table
            (``metadata-invalid``), or neither it nor ``[project]`` has a
            string ``name`` (``project-name-missing``).
        pitloom.core.internal_error.InternalError: ``[tool.poetry]`` is
            absent or empty (the one caller returns before that).
    """
    pyproject_path = project_dir / "pyproject.toml"
    poetry = read_poetry_section(data, pyproject_path, quiet=quiet)
    if poetry is not None and not is_table(poetry):
        # The one say of a non-table: the caller does not relay this error.
        warn_wrong_type(pyproject_path, "[tool.poetry]", poetry, "table", quiet=quiet)
        raise CodedValueError(
            METADATA_INVALID,
            line=TYPE_ERROR_LINE,
            file=pyproject_path,
            field="[tool.poetry]",
            got=poetry,
            expected="table",
        )
    if not poetry:
        # _try_read_poetry, the one caller, returns before it for an absent
        # or empty table.
        raise InternalError("extract_poetry_metadata: [tool.poetry] is absent")
    poetry = drop_wrong_typed_fields(poetry, pyproject_path, quiet=quiet)
    had_extras = "extras" in poetry
    poetry = drop_ignored_extras(poetry, data, pyproject_path, quiet=quiet)
    extras_ignored = had_extras and "extras" not in poetry
    poetry, deps_ignored = drop_ignored_dependencies(
        poetry, data, pyproject_path, quiet=quiet
    )

    name = (poetry.get("name") or "").strip()
    name_field = "tool.poetry.name"
    if not name:  # Poetry 2: [project] names it, [tool.poetry] adds the rest
        name, name_field = _project_table_name(data), "project.name"
    if not name:
        raise CodedValueError(
            PROJECT_NAME_MISSING, line=POETRY_NAME_LINE, file=pyproject_path
        )

    version = (poetry.get("version") or "").strip() or None
    description = (poetry.get("description") or "").strip() or None

    readme = _parse_poetry_readme(poetry.get("readme"))

    licence_files = _resolve_poetry_license(poetry, project_dir)

    keywords: list[str] = poetry.get("keywords", [])

    authors = parse_poetry_authors(poetry.get("authors", []))
    urls = _parse_poetry_urls(poetry)

    dependencies, requires_python, python_declared = parse_poetry_deps(
        poetry.get("dependencies", {}),
        extras=poetry.get("extras"),
        project_name=name,
        quiet=quiet,
        warn_unlisted=not extras_ignored,
    )
    if is_table(poetry.get("group")):
        log.debug("[tool.poetry.group.*] dependencies are not listed")
    prov = _build_poetry_provenance(
        poetry,
        version=version,
        description=description,
        readme=readme,
        license_prov=licence_files.provenance,
        python_declared=python_declared,
    )
    if deps_ignored:
        prov.pop("dependencies", None)
    prov = {"name": _pyproject_source(name_field), **prov}

    return ProjectMetadata(
        name=name,
        version=version,
        description=description,
        readme=readme,
        requires_python=requires_python,
        license_name=licence_files.license_name,
        license_concluded=licence_files.license_concluded,
        copyright_text=licence_files.copyright_text,
        keywords=keywords,
        authors=authors,
        urls=urls,
        dependencies=dependencies,
        provenance=prov,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _project_table_name(data: dict[str, Any]) -> str:
    """``[project].name``, stripped; ``""`` when not a string."""
    project = data.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    return name.strip() if isinstance(name, str) else ""


def _pyproject_source(field: str) -> str:
    """``"Source: pyproject.toml | Field: <field>"``."""
    return provenance_segment(provenance_source("pyproject.toml"), "Field", field)


def _build_poetry_provenance(
    poetry: dict[str, Any],
    *,
    version: str | None,
    description: str | None,
    readme: str | None,
    license_prov: dict[str, str],
    python_declared: bool,
) -> dict[str, str]:
    """Build :func:`extract_poetry_metadata`'s provenance dict."""
    prov: dict[str, str] = {}
    if version:
        prov["version"] = "Source: pyproject.toml | Field: tool.poetry.version"
    if description:
        prov["description"] = "Source: pyproject.toml | Field: tool.poetry.description"
    if readme:
        prov["readme"] = "Source: pyproject.toml | Field: tool.poetry.readme"
    prov.update(license_prov)
    # A container field's provenance is gated on the raw key's *presence*
    # in [tool.poetry], not on whether parsing it produced a non-empty
    # result -- an explicitly declared but empty `keywords = []` is a
    # genuine, authoritative "zero" that merge_project_metadata() must not
    # silently fill in from a lower-priority source, the same None-vs-[]
    # distinction pyproject.py's [project]-table path already applies.
    if field_declared(poetry, "authors"):
        prov["authors"] = POETRY_AUTHORS_SOURCE
    if any(
        field_declared(poetry, key)
        for key in ("homepage", "repository", "documentation")
    ):
        prov["urls"] = (
            "Source: pyproject.toml"
            " | Field: tool.poetry.homepage/repository/documentation"
        )
    if field_declared(poetry, "dependencies"):
        fields = "tool.poetry.dependencies"
        if field_declared(poetry, "extras"):
            fields += ", tool.poetry.extras"
        prov["dependencies"] = _pyproject_source(fields)
    # Presence-gated like the container fields above, not truthy-gated --
    # see AGENTS.md's "``None``/absent vs ``[]``/``{}``" rule.
    if python_declared:
        prov["requires_python"] = (
            "Source: pyproject.toml | Field: tool.poetry.dependencies.python"
        )
    if field_declared(poetry, "keywords"):
        prov["keywords"] = "Source: pyproject.toml | Field: tool.poetry.keywords"
    return prov


def _parse_poetry_readme(readme_raw: str | list[str] | None) -> str | None:
    """Normalise ``[tool.poetry].readme``, which may be a bare string or a
    list of strings (multiple readme files -- only the first is used)."""
    if isinstance(readme_raw, list):
        return readme_raw[0].strip() if readme_raw else None
    return (readme_raw or "").strip() or None


def _parse_poetry_urls(poetry: dict[str, Any]) -> dict[str, str]:
    """Collect ``homepage``/``repository``/``documentation`` into a URL dict."""
    urls: dict[str, str] = {}
    for toml_key, label in (
        ("homepage", "Homepage"),
        ("repository", "Repository"),
        ("documentation", "Documentation"),
    ):
        val = poetry.get(toml_key)
        if isinstance(val, str) and val.strip():
            urls[label] = val.strip()
    return urls


def _resolve_poetry_license(
    poetry: dict[str, Any], project_dir: Path
) -> ProjectMetadata:
    """Resolve ``[tool.poetry]``'s declared licence, then what the
    project's own licence files say
    (:func:`~pitloom.extract._license.apply_in_package_license_files`).

    Returns a nameless :class:`ProjectMetadata` holding ``license_name``,
    ``license_concluded``, ``copyright_text`` and their provenance, ready
    to merge into the caller's provenance dict directly.
    """
    license_name = (poetry.get("license") or "").strip() or None
    resolved = ProjectMetadata(name="", license_name=license_name)
    if license_name:
        resolved.provenance["license"] = (
            "Source: pyproject.toml | Field: tool.poetry.license"
        )
    apply_in_package_license_files(resolved, read_license_members(project_dir))
    return resolved


def parse_poetry_authors(authors: list[Any]) -> list[dict[str, str]]:
    """Parse Poetry ``"Name <email>"`` author strings into dicts, one per
    string, never split, a name's white space collapsed
    (:func:`~pitloom.extract.authors.collapse_whitespace`; the directory and
    sdist routes' one reading)."""
    result: list[dict[str, str]] = []
    for author in authors:
        if not isinstance(author, str):
            continue
        m = _AUTHOR_RE.match(author.strip())
        if not m:
            continue
        entry: dict[str, str] = {}
        name_part = collapse_whitespace(m.group("name") or "")
        email_part = (m.group("email") or "").strip()
        if name_part:
            entry["name"] = name_part
        if email_part:
            entry["email"] = email_part
        if entry:
            result.append(entry)
    return result
