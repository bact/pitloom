# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[tool.setuptools.dynamic]`` ``dependencies`` and ``optional-dependencies``.

setuptools fills a ``[project]`` field listed in ``dynamic`` from this
table: ``dependencies = {file = [...]}`` and, per extra,
``optional-dependencies.<extra> = {file = [...]}``. ``file`` is one path
or a list, relative to the project directory, read as
:mod:`pitloom.extract.project._requirements_files` reads it (its
deliberate differences from setuptools apply). A key the ``dynamic`` list
does not name is ignored, as setuptools ignores it, and so is the table
under a build backend other than setuptools. ``attr`` is not supported;
setuptools rejects it for these fields.

A field listed in ``dynamic`` that the table has no key for keeps what
``setup.cfg`` and ``setup.py`` state (``install_requires``,
``extras_require``), as setuptools keeps it; the table's key wins over
them.

See also: :mod:`pitloom.extract.project.pyproject` (the caller) and
:mod:`pitloom.extract.project._optional_dependencies`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import parse_provenance_value, provenance_source
from pitloom.core.requirements import normalize_dependency_specifier
from pitloom.extract.project._optional_dependencies import (
    OPTIONAL_DEPENDENCIES_FIELD,
    add_optional_dependencies,
)
from pitloom.extract.project._requirements_files import (
    RequirementsFiles,
    pep508_only,
    requirement_lines,
)
from pitloom.extract.project._setuptools_options import (
    SetupOptions,
    merge_setup_options,
    read_listed_requirements,
    split_extras,
)
from pitloom.extract.project.setuptools import detect_build_backend
from pitloom.extract.project.setuptools_cfg import read_setup_cfg_options
from pitloom.extract.project.setuptools_py import read_setup_py_options
from pitloom.logging_config import loggable, one_line

log = logging.getLogger(__name__)

#: The table, as warnings and provenance name it.
DYNAMIC_TABLE = "tool.setuptools.dynamic"
_PYPROJECT = "Source: pyproject.toml"

_FIELDS = ("dependencies", "optional-dependencies")
#: The setuptools option a dynamic field keeps when the table has no key.
_SETUP_OPTION = {
    "dependencies": "install_requires",
    "optional-dependencies": "extras_require",
}


@dataclass(frozen=True)
class SetuptoolsDynamic:
    """What setuptools gives the dynamic dependency fields.

    ``None``: the field is not read (not listed in ``dynamic``, no usable
    key). A list or mapping, even empty: it is declared, so provenance
    names it: *dependencies_source* and *optional_source* (``(Source,
    Field)``). *files*: the requirements files read, as listed.
    """

    dependencies: list[str] | None = None
    optional: dict[str, list[str]] | None = None
    files: tuple[str, ...] = ()
    dependencies_source: str = f"{_PYPROJECT} | Field: {DYNAMIC_TABLE}.dependencies"
    optional_source: tuple[str, str] = (
        _PYPROJECT,
        f"{DYNAMIC_TABLE}.optional-dependencies",
    )

    def add_dependencies(self, metadata: ProjectMetadata) -> None:
        """Append the base requirements to *metadata*, crediting their
        source, and record the files read as its ``dependency_files``."""
        metadata.dependency_files = list(self.files)
        if self.dependencies is None:
            return
        metadata.dependencies += [
            normalize_dependency_specifier(d) for d in self.dependencies
        ]
        metadata.provenance["dependencies"] = self.dependencies_source

    def add_extras(
        self,
        metadata: ProjectMetadata,
        static: dict[str, list[str]],
        *,
        declared: bool,
        quiet: bool = False,
    ) -> None:
        """:func:`add_optional_dependencies` with the extras read here, else
        with *static* (``[project.optional-dependencies]``, *declared*)."""
        dynamic = self.optional is not None
        source, field = (
            self.optional_source
            if dynamic
            else (_PYPROJECT, OPTIONAL_DEPENDENCIES_FIELD)
        )
        add_optional_dependencies(
            metadata,
            self.optional if dynamic else static,
            declared=dynamic or declared,
            source=source,
            quiet=quiet,
            field=field,
        )


def read_setuptools_dynamic(
    data: dict[str, Any], project_dir: Path, *, quiet: bool = False
) -> SetuptoolsDynamic:
    """The dependency fields *data* (a parsed ``pyproject.toml`` in
    *project_dir*) lists in ``dynamic``, as setuptools fills them: from
    ``[tool.setuptools.dynamic]``, else from ``setup.cfg``/``setup.py``.
    *quiet* silences the ``WARNING:`` lines."""
    project = data.get("project")
    dynamic = project.get("dynamic") if isinstance(project, dict) else None
    if not isinstance(dynamic, list):
        return SetuptoolsDynamic()
    table = _subtable(data, "tool", "setuptools", "dynamic") or {}
    listed = [f for f in _FIELDS if f in dynamic]
    if not listed or detect_build_backend(project_dir, pyproject_data=data) not in (
        None,
        "setuptools",
    ):
        return SetuptoolsDynamic()
    files = RequirementsFiles(project_dir, "pyproject.toml", DYNAMIC_TABLE, quiet)
    deps = None
    if "dependencies" in table and "dependencies" in listed:
        deps = _directive(files, table["dependencies"], "dependencies")
        field = files.field("dependencies")
        deps = None if deps is None else pep508_only(deps, field, quiet)
    optional = None
    if "optional-dependencies" in table and "optional-dependencies" in listed:
        optional = _read_extras(files, table["optional-dependencies"])
    files.warn_skipped()
    found = SetuptoolsDynamic(deps, optional, tuple(files.used))
    rest = [f for f in listed if f not in table]
    return _from_setup_files(found, rest, project_dir, quiet) if rest else found


def _subtable(data: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    """The table at *keys* under *data*, ``None`` when any level is absent
    or not a table."""
    node: Any = data
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else None


def _warn_ignored(key: str, reason: str, quiet: bool) -> None:
    if not quiet:
        log.warning(
            "pyproject.toml: '%s' %s -- ignoring it",
            loggable(f"{DYNAMIC_TABLE}.{key}"),
            reason,
        )


def _directive(
    files: RequirementsFiles, directive: object, key: str
) -> list[str] | None:
    """The requirements *directive* (the value of *key*) reads, ``None``
    when it is not a ``{file = ...}`` table."""
    names = _directive_files(directive, key, files.quiet)
    if names is None:
        return None
    return files.requirements(names, key, requirement_lines)


def _read_extras(
    files: RequirementsFiles, value: object
) -> dict[str, list[str]] | None:
    """Each extra's requirements; an extra whose directive is not usable
    is left out (warned). ``None`` when *value* is not a table."""
    if not isinstance(value, dict):
        _warn_ignored(
            "optional-dependencies",
            f"is {type(value).__name__}, expected table",
            files.quiet,
        )
        return None
    extras: dict[str, list[str]] = {}
    for extra, directive in value.items():
        requirements = _directive(files, directive, f"optional-dependencies.{extra}")
        if requirements is not None:
            extras[extra] = requirements
    return extras


def _directive_files(directive: object, key: str, quiet: bool) -> list[str] | None:
    """The paths a ``{file = ...}`` *directive* lists, ``None`` (warned)
    when it is not one."""
    if isinstance(directive, dict) and "file" in directive:
        files = directive["file"]
        if isinstance(files, str):
            return [files]
        if isinstance(files, list) and all(isinstance(f, str) for f in files):
            return files
        _warn_ignored(
            key, f"has 'file' {type(files).__name__}, expected string or list", quiet
        )
    elif isinstance(directive, dict) and "attr" in directive:
        _warn_ignored(key, "has 'attr', not supported for requirements", quiet)
    else:
        _warn_ignored(key, "is not a table with 'file'", quiet)
    return None


def _setup_options(project_dir: Path, rest: list[str], quiet: bool) -> SetupOptions:
    """``setup.cfg``'s and ``setup.py``'s options merged as setuptools
    merges them; one that cannot be read is left out with one
    ``WARNING:`` naming the dynamic *rest* fields it would fill."""

    def read(name: str, reader: Callable[[], SetupOptions]) -> SetupOptions:
        try:
            return reader()
        except FileNotFoundError:
            return {}
        except ValueError as exc:
            if not quiet:
                log.warning(
                    "pyproject.toml: dynamic %s not read from %s: %s",
                    ", ".join(rest),
                    name,
                    one_line(exc),
                )
            return {}

    cfg = read(
        "setup.cfg", lambda: read_setup_cfg_options(project_dir, read_config=False)[0]
    )
    py = read("setup.py", lambda: read_setup_py_options(project_dir, quiet=quiet))
    return merge_setup_options(cfg, py)


def _from_setup_files(
    found: SetuptoolsDynamic, rest: list[str], project_dir: Path, quiet: bool
) -> SetuptoolsDynamic:
    """*found* with the dynamic fields *rest*, which the table has no key
    for, filled from ``setup.cfg``/``setup.py`` as setuptools fills them:
    ``install_requires`` and ``extras_require`` (an ``extra:marker`` key
    with no extra unconditional), each crediting its own source. An
    option no field in *rest* takes is not read."""
    options = _setup_options(project_dir, rest, quiet)
    taken = {_SETUP_OPTION[field] for field in rest}
    merged, files = read_listed_requirements(
        {key: option for key, option in options.items() if key in taken},
        quiet=quiet,
    )
    deps, deps_source = found.dependencies, found.dependencies_source
    optional, optional_source = found.optional, found.optional_source
    if "extras_require" in merged:
        unconditional, optional = split_extras(merged, quiet)
        option = parse_provenance_value(merged["extras_require"].source)
        optional_source = (provenance_source(option["source"]), option["location"])
        if unconditional and deps is None:
            deps_source = merged["extras_require"].source
        if unconditional:
            deps = (deps or []) + unconditional
    if "install_requires" in merged:
        deps = list(merged["install_requires"].value) + (deps or [])
        deps_source = merged["install_requires"].source
    return SetuptoolsDynamic(
        deps,
        optional,
        tuple(dict.fromkeys(found.files + tuple(files))),
        deps_source,
        optional_source,
    )
