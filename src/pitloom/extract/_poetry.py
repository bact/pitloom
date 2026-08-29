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

.. rubric:: Dependency conversion

Poetry uses ``^X.Y`` / ``~X.Y`` version specifiers which are not valid
PEP 508.  This module converts them to PEP 440 ranges on a best-effort
basis:

* ``^X.Y.Z`` (X > 0) -> ``>=X.Y.Z,<X+1.0.0``
* ``^0.Y.Z``          -> ``>=0.Y.Z,<0.Y+1.0``
* ``~X.Y.Z``          -> ``>=X.Y.Z,<X.Y+1.0``
* ``*``               -> no constraint (package name only)
* Anything else       -> passed through unchanged.

See Also:
    https://python-poetry.org/docs/pyproject/
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pitloom.core.project import ProjectMetadata
from pitloom.extract._license import (
    detect_license_for_project,
    resolve_license_concluded,
)

# Matches "Name <email>", "Name", or "<email>"
_AUTHOR_RE = re.compile(r"^(?P<name>[^<]*?)\s*(?:<(?P<email>[^>]+)>)?$")


def extract_poetry_metadata(
    data: dict[str, Any],
    project_dir: Path,
) -> ProjectMetadata:
    """Extract :class:`~pitloom.core.project.ProjectMetadata` from pre-loaded data.

    Reads ``[tool.poetry]`` and ``[tool.poetry.dependencies]`` from a
    previously parsed ``pyproject.toml`` dict.  This is the internal entry
    point used by :func:`~pitloom.extract._pyproject.read_pyproject` so the
    file is not read twice.

    Args:
        data: Full parsed ``pyproject.toml`` dict.
        project_dir: Project root directory -- used for the same license
            fallback-detection and G2 independent-scan every other project
            extractor performs; see
            :func:`~pitloom.extract._license.resolve_license_concluded`'s
            docstring for why every extractor must call it.

    Returns:
        A populated :class:`~pitloom.core.project.ProjectMetadata`.

    Raises:
        ValueError: If ``[tool.poetry]`` is absent or has no ``name``.
    """
    poetry: dict[str, Any] = data.get("tool", {}).get("poetry", {})
    if not poetry:
        raise ValueError("[tool.poetry] section not found in pyproject.toml")

    name = (poetry.get("name") or "").strip()
    if not name:
        raise ValueError("Project name is required in [tool.poetry] section")

    version = (poetry.get("version") or "").strip() or None
    description = (poetry.get("description") or "").strip() or None

    readme = _parse_poetry_readme(poetry.get("readme"))

    license_name, license_concluded, license_prov = _resolve_poetry_license(
        poetry, project_dir
    )

    raw_keywords = poetry.get("keywords", [])
    keywords: list[str] = raw_keywords if isinstance(raw_keywords, list) else []

    authors = _parse_poetry_authors(poetry.get("authors", []))
    urls = _parse_poetry_urls(poetry)

    dependencies, requires_python = _parse_poetry_deps(poetry.get("dependencies", {}))

    prov: dict[str, str] = {
        "name": "Source: pyproject.toml | Field: tool.poetry.name",
    }
    if version:
        prov["version"] = "Source: pyproject.toml | Field: tool.poetry.version"
    if description:
        prov["description"] = "Source: pyproject.toml | Field: tool.poetry.description"
    if readme:
        prov["readme"] = "Source: pyproject.toml | Field: tool.poetry.readme"
    prov.update(license_prov)
    if authors:
        prov["authors"] = "Source: pyproject.toml | Field: tool.poetry.authors"
        prov["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )
    if urls:
        prov["urls"] = (
            "Source: pyproject.toml"
            " | Field: tool.poetry.homepage/repository/documentation"
        )
    if dependencies:
        prov["dependencies"] = (
            "Source: pyproject.toml | Field: tool.poetry.dependencies"
        )
    if requires_python:
        prov["requires_python"] = (
            "Source: pyproject.toml | Field: tool.poetry.dependencies.python"
        )
    if keywords:
        prov["keywords"] = "Source: pyproject.toml | Field: tool.poetry.keywords"

    return ProjectMetadata(
        name=name,
        version=version,
        description=description,
        readme=readme,
        requires_python=requires_python,
        license_name=license_name,
        license_concluded=license_concluded,
        keywords=keywords,
        authors=authors,
        urls=urls,
        dependencies=dependencies,
        provenance=prov,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_poetry_readme(readme_raw: Any) -> str | None:
    """Normalize ``[tool.poetry].readme``, which may be a bare string or a
    list of strings (multiple readme files -- only the first is used)."""
    if isinstance(readme_raw, list):
        return readme_raw[0].strip() if readme_raw else None
    if isinstance(readme_raw, str):
        return readme_raw.strip() or None
    return None


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
) -> tuple[str | None, str | None, dict[str, str]]:
    """Resolve ``[tool.poetry]``'s declared license, falling back to
    directory detection when absent, plus G2's independent second opinion.

    Returns ``(license_name, license_concluded, license_prov)`` -- pulled
    out of :func:`extract_poetry_metadata` so its own local-variable count
    stays under pylint's ``too-many-locals`` threshold; ``license_prov`` is
    ready to merge into the caller's provenance dict directly.
    """
    license_name = (poetry.get("license") or "").strip() or None
    has_declared_license = bool(license_name)
    license_prov_override: str | None = None
    if not license_name:
        # No [tool.poetry] license declared -- fall back to directory
        # detection, same baseline every other extractor has.
        license_name, license_prov_override = detect_license_for_project(project_dir)
    # G2: independently scan for a second opinion when a license *was*
    # declared, via the shared resolver every extractor must call.
    license_concluded, license_concluded_prov = resolve_license_concluded(
        has_declared_license, project_dir
    )

    license_prov: dict[str, str] = {}
    if license_name:
        license_prov["license"] = (
            license_prov_override
            or "Source: pyproject.toml | Field: tool.poetry.license"
        )
    if license_concluded and license_concluded_prov:
        license_prov["license_concluded"] = license_concluded_prov
    return license_name, license_concluded, license_prov


def _parse_poetry_authors(authors: list[Any]) -> list[dict[str, str]]:
    """Parse Poetry ``"Name <email>"`` author strings into dicts."""
    result: list[dict[str, str]] = []
    for author in authors:
        if not isinstance(author, str):
            continue
        m = _AUTHOR_RE.match(author.strip())
        if not m:
            continue
        entry: dict[str, str] = {}
        name_part = (m.group("name") or "").strip()
        email_part = (m.group("email") or "").strip()
        if name_part:
            entry["name"] = name_part
        if email_part:
            entry["email"] = email_part
        if entry:
            result.append(entry)
    return result


def _parse_poetry_deps(
    deps: Any,
) -> tuple[list[str], str | None]:
    """Convert ``[tool.poetry.dependencies]`` to a PEP 508 list plus requires-python.

    The ``python`` key is extracted as ``requires_python``; all other entries
    are converted to PEP 508 strings on a best-effort basis.

    Returns:
        ``(dependencies, requires_python)`` where ``requires_python`` may be
        ``None`` when the ``python`` key is absent.
    """
    if not isinstance(deps, dict):
        return [], None

    requires_python: str | None = None
    dependencies: list[str] = []

    for pkg, constraint in deps.items():
        if pkg.lower() == "python":
            requires_python = _poetry_constraint_to_pep440(constraint)
            continue
        dep = _poetry_dep_to_pep508(pkg, constraint)
        if dep is not None:
            dependencies.append(dep)

    return dependencies, requires_python


def _convert_caret(ver: str) -> str:
    """Convert a Poetry caret constraint (without the ``^``) to PEP 440."""
    parts = ver.split(".")
    try:
        major = int(parts[0])
        if major > 0:
            return f">={ver},<{major + 1}.0.0"
        if len(parts) > 1:
            minor = int(parts[1])
            return f">={ver},<0.{minor + 1}.0"
        return f">={ver}"
    except (ValueError, IndexError):
        return f">={ver}"


def _convert_tilde(ver: str) -> str:
    """Convert a Poetry tilde constraint (without the ``~``) to PEP 440."""
    parts = ver.split(".")
    try:
        if len(parts) >= 2:
            major = int(parts[0])
            minor = int(parts[1])
            return f">={ver},<{major}.{minor + 1}.0"
        return f">={ver}"
    except (ValueError, IndexError):
        return f">={ver}"


def _poetry_constraint_to_pep440(constraint: Any) -> str | None:
    """Convert a Poetry version constraint to a PEP 440 specifier string.

    Handles ``^X.Y.Z``, ``~X.Y.Z``, ``*``, and plain PEP 440 specifiers.
    Returns ``None`` for ``*`` or unrecognised input.
    """
    if isinstance(constraint, dict):
        constraint = constraint.get("version", "*")
    if not isinstance(constraint, str):
        return None
    constraint = constraint.strip()
    if not constraint or constraint == "*":
        return None

    # Bare version (no operator): Poetry treats "X.Y.Z" as exact (==X.Y.Z).
    if constraint[0].isdigit():
        return f"=={constraint}"

    if constraint.startswith("^"):
        return _convert_caret(constraint[1:])

    if constraint.startswith("~"):
        return _convert_tilde(constraint[1:])

    return str(constraint)


def _poetry_dep_to_pep508(name: str, constraint: Any) -> str | None:
    """Convert a single Poetry dependency entry to a PEP 508 string.

    Handles string constraints, inline-table constraints (``{version = "^1.0",
    ...}``), and skips entries with ``path``, ``git``, or ``url`` sources that
    cannot be represented as simple specifiers.

    Returns ``None`` when the entry cannot be represented.
    """
    if isinstance(constraint, dict):
        if any(k in constraint for k in ("path", "git", "url")):
            return None
        constraint = constraint.get("version", "*")

    ver_spec = _poetry_constraint_to_pep440(constraint)
    if ver_spec is None:
        return name
    return f"{name}{ver_spec}"
