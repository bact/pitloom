# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An sdist archive's metadata from its root ``pyproject.toml``, when it
has no usable ``PKG-INFO``: the static ``[project]`` fields only, since
a field ``dynamic`` lists is the build's to compute.

See also: :mod:`pitloom.extract.project.sdist` (the caller).
"""

from __future__ import annotations

import logging
from typing import Any

from pitloom.core.project import ProjectMetadata
from pitloom.core.requirements import normalize_dependency_specifier
from pitloom.extract._extract_utils import field_declared
from pitloom.extract.project._optional_dependencies import add_optional_dependencies
from pitloom.extract.project._pyproject_license import license_from_project_table
from pitloom.extract.project._sdist_scan import PKG_INFO, PYPROJECT
from pitloom.logging_config import field_loss_suffix, loggable

log = logging.getLogger(__name__)

_PYPROJECT_LICENSE_SOURCE = "Source: pyproject.toml | Field: project.license"
_PYPROJECT_DEPENDENCIES_SOURCE = "Source: pyproject.toml | Field: project.dependencies"


def _warn_ignored(where: str, key: str, value: object, expected: str) -> None:
    """One ``WARNING:``: *key* of the archive's ``pyproject.toml`` (*where*,
    ``<archive>:pyproject.toml``) is ignored for not being *expected*. The
    key may hold an untrusted extra name: ``%r`` escapes it."""
    log.warning(
        "%s: %r is %s, expected %s -- ignoring it",
        loggable(where),
        key,
        type(value).__name__,
        expected,
    )


def _base_dependencies(proj: dict[str, Any], where: str) -> list[str] | None:
    """``[project].dependencies`` as normalised requirement strings.

    A value that is not a list of strings is ignored with one ``WARNING:``.
    ``None`` when not declared or ignored."""
    deps = proj.get("dependencies")
    if deps is None:
        return None
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        _warn_ignored(where, "project.dependencies", deps, "list of strings")
        return None
    return [normalize_dependency_specifier(d) for d in deps]


def _optional_dependencies_table(
    proj: dict[str, Any], where: str
) -> dict[str, list[str]] | None:
    """``[project.optional-dependencies]`` as extra -> requirement strings.

    A table that is not a table, an extra that is not a list, or an item
    that is not a string is ignored with one ``WARNING:``; the other
    entries stay. ``None`` when not declared or not a table."""
    table = proj.get("optional-dependencies")
    if table is None:
        return None
    if not isinstance(table, dict):
        _warn_ignored(where, "project.optional-dependencies", table, "table")
        return None
    usable: dict[str, list[str]] = {}
    for extra, items in table.items():
        if isinstance(items, list) and all(isinstance(i, str) for i in items):
            usable[extra] = items
            continue
        key = f"project.optional-dependencies.{extra}"
        _warn_ignored(where, key, items, "list of strings")
    return usable


def metadata_from_pyproject(
    data: Any, licence: dict[str, bytes], sdist_name: str
) -> ProjectMetadata:
    """Fallback ProjectMetadata from a parsed ``pyproject.toml``; its
    licence as a directory reads it, a ``license.file`` from *licence*.
    A warning names the member as *sdist_name*:``pyproject.toml``."""
    where = f"{sdist_name}:{PYPROJECT}"
    proj = data.get("project", {}) if isinstance(data, dict) else {}
    if not isinstance(proj, dict):
        proj = {}
    license_name, license_prov = license_from_project_table(proj, licence.get)
    dependencies = _base_dependencies(proj, where)
    metadata = ProjectMetadata(
        name=proj.get("name", "unknown"),
        version=proj.get("version"),
        description=proj.get("description"),
        license_name=license_name,
        dependencies=dependencies or [],
    )
    if dependencies is not None:
        metadata.provenance["dependencies"] = _PYPROJECT_DEPENDENCIES_SOURCE
    optional = _optional_dependencies_table(proj, where)
    add_optional_dependencies(
        metadata,
        optional,
        declared=optional is not None,  # a non-table is ignored: not credited
        source="Source: pyproject.toml",
    )
    if license_prov or field_declared(proj, "license"):
        metadata.provenance["license"] = license_prov or _PYPROJECT_LICENSE_SOURCE
    _warn_dynamic_unresolved(proj, where)
    return metadata


#: The ``[project]`` fields :func:`_metadata_from_pyproject` reads.
_FALLBACK_FIELDS = (
    "version",
    "description",
    "dependencies",
    "optional-dependencies",
    "license",
    "authors",
)


def _warn_dynamic_unresolved(proj: dict[str, Any], where: str) -> None:
    """One ``WARNING:`` naming each field :func:`_metadata_from_pyproject`
    reads that ``dynamic`` lists: the build computes it, and without
    ``PKG-INFO`` (which a real sdist carries, built) the archive holds
    no value for it."""
    dynamic = proj.get("dynamic")
    if not isinstance(dynamic, list):
        return
    unresolved = [field for field in _FALLBACK_FIELDS if field in dynamic]
    if unresolved:
        log.warning(
            "%s: dynamic field(s) not resolved without %s%s",
            loggable(where),
            PKG_INFO,
            field_loss_suffix("skipped", *unresolved),
        )
