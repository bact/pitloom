# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[tool.poetry.extras]``: which dependencies each extra lists, and
which ``[tool.poetry]`` tables a build reads: whether Poetry builds the
dependency lists from ``[tool.poetry]`` or ``[project]``, and whether the
build backend is Poetry's at all.

See also: :mod:`pitloom.extract.project.poetry` and
:mod:`pitloom.extract.project.pyproject` (the callers).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.core.project import ProjectMetadata, provenance_key_for
from pitloom.core.requirements import (
    warn_skipped_dependency,
    warn_skipped_extra_entry,
)
from pitloom.extract.project.setuptools import (
    backend_identifier,
    declared_build_backend,
)

log = logging.getLogger(__name__)

#: ``[project] dynamic`` entries that make poetry-core add
#: ``[tool.poetry.dependencies]`` to a ``[project]`` list.
_LIST_FIELDS = {"dependencies", "optional-dependencies"}
#: ``[tool.poetry]`` keys by the :class:`ProjectMetadata` field they fill.
_GAP_FIELDS = {
    "version": "version",
    "description": "description",
    "readme": "readme",
    "authors": "authors",
    "license": "license_name",
    "keywords": "keywords",
    "homepage": "urls",
    "repository": "urls",
    "documentation": "urls",
    "dependencies": "dependencies",
    "extras": "dependencies",
}


def project_lists_used(data: dict[str, Any]) -> bool:
    """Whether Poetry builds the dependency lists from ``[project]``, not
    ``[tool.poetry]``: ``dependencies`` or ``optional-dependencies`` there
    is non-empty. poetry-core 2.4 tests their truthiness
    (``Factory._configure_package_dependencies``), so a list declared
    empty counts as absent."""
    project = data.get("project")
    return isinstance(project, dict) and bool(
        project.get("dependencies") or project.get("optional-dependencies")
    )


def defer_to_poetry_lists(
    metadata: ProjectMetadata,
    poetry_meta: ProjectMetadata | None,
    data: dict[str, Any],
) -> bool:
    """Whether *poetry_meta*'s dependency lists (``[tool.poetry]``
    ``dependencies`` and ``extras``) replace ``[project]``'s, each empty
    (:func:`project_lists_used`), as *metadata*'s (another source, such as
    a setuptools requirements file, may have filled it). If so,
    *metadata*'s claim to an empty ``dependencies`` (its provenance) is
    dropped, so :func:`~pitloom.core.project.merge_project_metadata` fills
    it from *poetry_meta*, and the caller must not count ``[project]``'s
    ``optional-dependencies`` as declared."""
    if (
        poetry_meta is None
        or metadata.dependencies
        or "dependencies" not in poetry_meta.provenance
        or project_lists_used(data)
    ):
        return False
    metadata.provenance.pop("dependencies", None)
    return True


def drop_ignored_extras(
    poetry: dict[str, Any], data: dict[str, Any], *, quiet: bool
) -> dict[str, Any]:
    """*poetry* without ``extras`` when ``[project]`` has a non-empty
    ``dependencies`` or ``optional-dependencies``
    (:func:`project_lists_used`): Poetry then reads those and ignores
    ``[tool.poetry.extras]``; with a ``WARNING:``."""
    if "extras" not in poetry or not project_lists_used(data):
        return poetry
    warn_ignored_poetry_table(
        "[tool.poetry.extras]",
        "[project] declares dependencies or optional-dependencies, "
        "which Poetry reads instead",
        quiet=quiet,
    )
    return {key: value for key, value in poetry.items() if key != "extras"}


def drop_ignored_dependencies(
    poetry: dict[str, Any], data: dict[str, Any], *, quiet: bool
) -> tuple[dict[str, Any], bool]:
    """*poetry* with only the ``python`` key of ``dependencies``, and
    ``True``, when poetry-core 2.4 ignores the table's dependencies:
    ``[project]`` has a non-empty ``optional-dependencies`` entry, no
    non-empty ``dependencies`` and lists neither in ``dynamic``
    (``DependencyGroup.dependencies``, measured). One ``WARNING:`` when a
    dependency is dropped."""
    deps = poetry.get("dependencies")
    project = data.get("project")
    if not isinstance(deps, dict) or not isinstance(project, dict):
        return poetry, False
    optional = project.get("optional-dependencies")
    dynamic = project.get("dynamic")
    if (
        project.get("dependencies")
        or not (isinstance(optional, dict) and any(optional.values()))
        or (isinstance(dynamic, list) and _LIST_FIELDS & set(map(str, dynamic)))
    ):
        return poetry, False
    kept = {name: spec for name, spec in deps.items() if name.lower() == "python"}
    if len(kept) < len(deps):
        warn_ignored_poetry_table(
            "[tool.poetry.dependencies]",
            "[project] declares optional-dependencies and no dependencies, "
            "which Poetry reads instead",
            quiet=quiet,
        )
    return {**poetry, "dependencies": kept}, True


def poetry_backend_reads(data: dict[str, Any]) -> bool:
    """Whether the build backend reads ``[tool.poetry]``: it is Poetry's,
    or no ``build-backend`` is declared (read as before, see
    ``docs/dependency-sources.md``)."""
    backend = declared_build_backend(data)
    return backend is None or backend_identifier(backend) == "poetry"


def warn_unread_poetry_fields(
    metadata: ProjectMetadata, data: dict[str, Any], *, quiet: bool
) -> None:
    """One ``WARNING:`` naming the ``[tool.poetry]`` keys that would fill
    a gap in *metadata* but are not read: the build backend is not
    Poetry's (:func:`poetry_backend_reads`)."""
    backend = declared_build_backend(data)
    tool = data.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    if poetry_backend_reads(data) or not isinstance(poetry, dict):
        return
    unread = [
        key
        for key, field in _GAP_FIELDS.items()
        if key in poetry
        and not getattr(metadata, field)
        and provenance_key_for(field) not in metadata.provenance
    ]
    if unread:
        warn_ignored_poetry_table(
            f"[tool.poetry] {', '.join(unread)}",
            f"build-backend {backend!r} does not read it",
            quiet=quiet,
        )


def warn_ignored_poetry_table(what: str, reason: str, *, quiet: bool) -> None:
    """``WARNING:`` that *what* (a table, or a table's keys) is not read,
    and why: the one wording of every ignored ``[tool.poetry]`` part.
    Silent when *quiet*."""
    if not quiet:
        log.warning("Ignoring %s: %s", what, reason)


def requirements_per_table(
    constraint: Any, convert: Callable[[Any], str | None]
) -> tuple[list[str], list[str]]:
    """``(every, required)`` PEP 508 strings of one Poetry dependency, each
    once: *convert* of each table of the list form (one per environment,
    each ``optional = true`` or not), else of *constraint*; *required*
    leaves out the optional ones. *convert* returns ``None`` to skip one."""
    tables = constraint if isinstance(constraint, list) else [constraint]
    every: dict[str, None] = {}
    required: dict[str, None] = {}
    for table in tables:
        dep = convert(table)
        if dep is not None:
            every[dep] = None
            if not (isinstance(table, dict) and table.get("optional") is True):
                required[dep] = None
    return list(every), list(required)


def extras_requirements(
    extras: Any,
    entries: dict[str, tuple[str, list[str]]],
    optional: set[str],
    deps: dict[str, Any],
    *,
    quiet: bool,
    warn_unlisted: bool = True,
) -> tuple[dict[str, list[str]], set[str]]:
    """Map each extra of ``[tool.poetry.extras]`` to its requirements.

    *entries* holds the representable dependencies by canonical name
    (declared name, PEP 508 strings: one per table of the list form),
    *optional* those with every table ``optional = true``. As in a built
    wheel, every string of a dependency an extra lists is tagged with that
    extra and is not also a base requirement, ``optional = true`` or not.
    A name an extra lists that is not declared in *deps* is skipped with a
    ``WARNING:``. An optional dependency no extra lists is dropped with a
    ``WARNING:``.

    Returns:
        ``(requirements per extra, canonical names an extra lists)``.
    """
    declared = {canonicalize_name(pkg) for pkg in deps}
    by_extra: dict[str, list[str]] = {}
    listed: set[str] = set()
    for extra, names in extras.items() if isinstance(extras, dict) else ():
        by_extra[extra] = []
        for name in names if isinstance(names, list) else ():
            key = canonicalize_name(name) if isinstance(name, str) else ""
            if key in entries:
                by_extra[extra].extend(entries[key][1])
                listed.add(key)
            elif key not in declared:
                warn_skipped_extra_entry(
                    "Poetry",
                    extra,
                    name,
                    "not declared in [tool.poetry.dependencies]",
                    quiet=quiet,
                )
    for key in sorted(optional - listed if warn_unlisted else ()):
        warn_skipped_dependency(
            "Poetry",
            entries[key][0],
            "optional and listed in no [tool.poetry.extras] extra",
            quiet=quiet,
        )
    return by_extra, listed
