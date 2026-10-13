# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[tool.setuptools.dynamic]`` ``dependencies`` and ``optional-dependencies``.

setuptools fills a ``[project]`` field listed in ``dynamic`` from this
table: ``dependencies = {file = [...]}`` and, per extra,
``optional-dependencies.<extra> = {file = [...]}``. ``file`` is one path
or a list, relative to the project directory; the files' text is joined
with ``\\n`` and read as setuptools reads it
(:func:`requirements_and_options`). A key the ``dynamic`` list does not
name is ignored, as setuptools ignores it, and so is the table under a
build backend other than setuptools.

Deliberate differences from setuptools, each with a ``WARNING:``:

* a file it could not read (missing, not a regular file, not UTF-8,
  over :data:`MAX_REQUIREMENTS_FILE_BYTES`) is skipped; setuptools warns
  of a missing one too, and fails the build on the others;
* a file listed twice is read once, known by the file opened (a hard
  link, or a symlink spelling the project in another letter case, is the
  same file); setuptools reads it each time;
* past :data:`MAX_REQUIREMENTS_TOTAL_BYTES` for the table, the files not
  yet read are skipped; setuptools reads them all;
* a path outside the project directory, ``..``, absolute or through a
  symlink, is not read; setuptools fails the build, but follows a
  symlink (:func:`~pitloom.core.path_confine.open_inside`);
* a pip option line (``-r``, ``-e``, ``--index-url``) is skipped;
  setuptools fails the build on it, so ``-r`` is not followed;
* ``attr`` is not supported; setuptools rejects it for these fields.

See also: :mod:`pitloom.extract.project.pyproject` (the caller) and
:mod:`pitloom.extract.project._optional_dependencies`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from pitloom.core.file_identity import FileId, file_id
from pitloom.core.path_confine import open_inside
from pitloom.core.path_probe import UNREADABLE_FILE_WARNING, is_missing_errno
from pitloom.core.project import ProjectMetadata
from pitloom.core.requirements import normalize_dependency_specifier
from pitloom.extract.project._optional_dependencies import (
    OPTIONAL_DEPENDENCIES_FIELD,
    add_optional_dependencies,
)
from pitloom.extract.project._setuptools_options import requirement_lines
from pitloom.extract.project.setuptools import detect_build_backend
from pitloom.logging_config import Cap, loggable, one_line, warn_over_cap

log = logging.getLogger(__name__)

#: The table, as warnings and provenance name it.
DYNAMIC_TABLE = "tool.setuptools.dynamic"
#: Largest requirements file read; a larger one is skipped with a warning.
MAX_REQUIREMENTS_FILE_BYTES = 1024 * 1024
#: Most bytes of requirements files the table reads, every directive
#: together, a file listed by two directives counted twice. A file that
#: would pass it and the files after it are skipped, with one warning.
MAX_REQUIREMENTS_TOTAL_BYTES = 4 * 1024 * 1024

_FIELDS = ("dependencies", "optional-dependencies")

#: A listed file: its identity, else (none on this file system, or it
#: could not be opened) its path as written.
_FileKey = FileId | Path


@dataclass(frozen=True)
class SetuptoolsDynamic:
    """What ``[tool.setuptools.dynamic]`` gives the dependency fields.

    ``None``: the field is not read from the table (not listed in
    ``dynamic``, no usable key). A list or mapping, even empty: the key
    declares it, so provenance names it.
    """

    dependencies: list[str] | None = None
    optional: dict[str, list[str]] | None = None

    def add_dependencies(self, metadata: ProjectMetadata) -> None:
        """Append the base requirements to *metadata*, crediting the key."""
        if self.dependencies is None:
            return
        metadata.dependencies += [
            normalize_dependency_specifier(d) for d in self.dependencies
        ]
        metadata.provenance["dependencies"] = (
            f"Source: pyproject.toml | Field: {DYNAMIC_TABLE}.dependencies"
        )

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
        add_optional_dependencies(
            metadata,
            self.optional if dynamic else static,
            declared=dynamic or declared,
            source="Source: pyproject.toml",
            quiet=quiet,
            field=(
                f"{DYNAMIC_TABLE}.optional-dependencies"
                if dynamic
                else OPTIONAL_DEPENDENCIES_FIELD
            ),
        )


class _Unreadable(Exception):
    """A listed file is not read; the message says why."""


def requirements_and_options(text: str) -> tuple[list[str], list[str]]:
    """``(requirements, options)`` of a requirements file's *text*, split
    into lines as setuptools does
    (:func:`~pitloom.extract.project._setuptools_options.requirement_lines`).
    A line starting with ``-`` is a pip option: its option name goes to
    *options*. Requirements are not validated here."""
    requirements: list[str] = []
    options: list[str] = []
    for line in requirement_lines(text):
        if line.startswith("-"):
            options.append(line.split()[0].split("=")[0])
        else:
            requirements.append(line)
    return requirements, options


def read_setuptools_dynamic(
    data: dict[str, Any], project_dir: Path, *, quiet: bool = False
) -> SetuptoolsDynamic:
    """The dependency fields *data* (a parsed ``pyproject.toml`` in
    *project_dir*) takes from ``[tool.setuptools.dynamic]``. *quiet*
    silences the ``WARNING:`` lines."""
    project = data.get("project")
    dynamic = project.get("dynamic") if isinstance(project, dict) else None
    table = _subtable(data, "tool", "setuptools", "dynamic")
    if not isinstance(dynamic, list) or table is None:
        return SetuptoolsDynamic()
    wanted = [f for f in _FIELDS if f in dynamic and f in table]
    if not wanted or detect_build_backend(project_dir, pyproject_data=data) not in (
        None,
        "setuptools",
    ):
        return SetuptoolsDynamic()
    files = _Files(project_dir, quiet)
    deps = None
    if "dependencies" in wanted:
        deps = files.directive(table["dependencies"], "dependencies")
    optional = None
    if "optional-dependencies" in wanted:
        optional = _read_extras(files, table["optional-dependencies"])
    files.warn_skipped()
    return SetuptoolsDynamic(deps, optional)


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


def _read_extras(files: _Files, value: object) -> dict[str, list[str]] | None:
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
        requirements = files.directive(directive, f"optional-dependencies.{extra}")
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


class _TooLarge(Exception):
    """A listed file is over :data:`MAX_REQUIREMENTS_FILE_BYTES`."""


class _Files:
    """The requirements files of one table: each file read once, known by
    the identity of the file opened, all of them within
    :data:`MAX_REQUIREMENTS_TOTAL_BYTES`."""

    def __init__(self, project_dir: Path, quiet: bool) -> None:
        self.quiet = quiet
        self._project_dir = project_dir
        # File -> (text, its size in bytes), or why it is not read.
        self._read: dict[_FileKey, tuple[str, int] | Exception] = {}
        self._spent = 0
        self._skipped = 0

    def directive(self, directive: object, key: str) -> list[str] | None:
        """The requirements *directive* (the value of *key*) reads, ``None``
        when it is not a ``{file = ...}`` table."""
        names = _directive_files(directive, key, self.quiet)
        if names is None:
            return None
        texts: list[str] = []
        seen: set[_FileKey] = set()
        for name in names:
            text = self._text(name, key, seen)
            if text is not None:
                texts.append(text)
        requirements, options = requirements_and_options("\n".join(texts))
        if options and not self.quiet:
            log.warning(
                "pyproject.toml: skipping pip option line(s) %s in %s: "
                "setuptools does not accept them",
                ", ".join(loggable(o) for o in dict.fromkeys(options)),
                loggable(f"{DYNAMIC_TABLE}.{key}"),
            )
        return requirements

    def warn_skipped(self) -> None:
        """The one ``WARNING:`` for the files the total cap left unread."""
        if self._skipped and not self.quiet:
            warn_over_cap(
                log,
                Cap(
                    MAX_REQUIREMENTS_TOTAL_BYTES,
                    "byte",
                    "requirements-file total",
                    "FIELD",
                ),
                DYNAMIC_TABLE,
                f"{self._skipped} file(s) listed not read",
            )

    def _text(self, name: str, key: str, seen: set[_FileKey]) -> str | None:
        """The text of the file *name* that *key* lists; ``None`` when it is
        not read (warned), already in *seen*, or past the total cap.

        Opened as written, as setuptools does
        (:func:`~pitloom.core.path_confine.open_inside`, which also refuses
        a file outside the project directory), then known by the file
        opened: a spelling that cannot be opened is never served another
        spelling's text."""
        written = self._project_dir / name
        try:
            handle = open_inside(written, self._project_dir)
        except (OSError, ValueError) as exc:
            if self._first(written, seen):
                self._warn_unreadable(name, key, _unreadable(exc))
            return None
        with handle:
            file = file_id(handle.fileno()) or written
            if not self._first(file, seen):
                return None
            if file not in self._read:
                self._read[file] = _read_text(handle)
        read = self._read[file]
        if isinstance(read, _TooLarge):
            self._warn_over_cap(name, key, file)
            return None
        if isinstance(read, Exception):
            self._warn_unreadable(name, key, read)
            return None
        text, size = read
        if self._spent + size > MAX_REQUIREMENTS_TOTAL_BYTES:
            self._skipped += 1
            return None
        self._spent += size
        return text

    def _first(self, file: _FileKey, seen: set[_FileKey]) -> bool:
        """Whether *file* is new to this directive (*seen*) and within the
        total cap; one past it is counted as skipped."""
        if file in seen:
            return False
        seen.add(file)
        if self._skipped:
            self._skipped += 1
            return False
        return True

    def _warn_over_cap(self, name: str, key: str, file: _FileKey) -> None:
        """The ``WARNING:`` for the file *name* that *key* lists, over
        :data:`MAX_REQUIREMENTS_FILE_BYTES`: once per *file*, however many
        directives list it and however each spells it."""
        if not self.quiet:
            warn_over_cap(
                log,
                Cap(MAX_REQUIREMENTS_FILE_BYTES, "byte", "requirements-file"),
                name,
                f"skipped for {loggable(f'{DYNAMIC_TABLE}.{key}')}",
                once=True,
                # The project too: a deleted file's inode is reused.
                key=f"{self._project_dir}\x00{file}",
            )

    def _warn_unreadable(self, name: str, key: str, exc: Exception) -> None:
        if not self.quiet:
            log.warning(
                UNREADABLE_FILE_WARNING,
                loggable(name),
                f"for {loggable(f'{DYNAMIC_TABLE}.{key}')}",
                exc,
            )


def _unreadable(exc: Exception) -> _Unreadable:
    """*exc*, raised opening or reading a listed file, as the reason it is
    not read."""
    if isinstance(exc, OSError):
        return _Unreadable("not found" if is_missing_errno(exc) else one_line(exc))
    return _Unreadable(one_line(exc))  # an embedded NUL


def _read_text(handle: BinaryIO) -> tuple[str, int] | Exception:
    """The UTF-8 text of the listed file open as *handle* and its size in
    bytes, else why it is not read: :class:`_TooLarge` over
    :data:`MAX_REQUIREMENTS_FILE_BYTES`, :class:`_Unreadable` not UTF-8 or
    not readable."""
    try:
        raw = handle.read(MAX_REQUIREMENTS_FILE_BYTES + 1)
    except OSError as exc:
        return _unreadable(exc)
    if len(raw) > MAX_REQUIREMENTS_FILE_BYTES:
        return _TooLarge()
    try:
        return raw.decode("utf-8"), len(raw)
    except UnicodeDecodeError as exc:
        return _Unreadable(f"not UTF-8: {one_line(exc)}")
