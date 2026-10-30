# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Requirements as setuptools reads them, and the requirements files a
setuptools directive lists: ``[tool.setuptools.dynamic]``'s
``{file = [...]}`` in ``pyproject.toml`` and ``file:`` in ``setup.cfg``'s
``install_requires`` and ``[options.extras_require]``. One reader for
both: the files' text is joined with ``\\n`` and split into requirements
as the directive's own file splits them.

Deliberate differences from setuptools, each with a ``WARNING:``:

* a file it could not read (missing, not a regular file, not UTF-8,
  over :data:`MAX_REQUIREMENTS_FILE_BYTES`) is skipped; setuptools warns
  of a missing one too, and fails the build on the others;
* a file listed twice is read once, known by the file opened (a hard
  link, or a symlink spelling the project in another letter case, is the
  same file); setuptools reads it each time;
* past :data:`MAX_REQUIREMENTS_TOTAL_BYTES` for one configuration file,
  the files not yet read are skipped; setuptools reads them all;
* a path outside the project directory, ``..``, absolute or through a
  symlink, is not read; setuptools fails the build, but follows a
  symlink (:func:`~pitloom.core.path_confine.open_inside`);
* a pip option line (``-r``, ``-e``, ``--index-url``) is skipped;
  setuptools fails the build on it, so ``-r`` is not followed;
* a base requirement that is not PEP 508 is skipped
  (:func:`pep508_only`), as an extra's is; setuptools fails the build on
  it.

See also: :mod:`pitloom.extract.project._setuptools_dynamic` and
:mod:`pitloom.extract.project._setuptools_options` (the users).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from packaging.requirements import InvalidRequirement

from pitloom.core.file_identity import FileId, file_id
from pitloom.core.path_confine import open_inside
from pitloom.core.path_probe import is_missing_errno
from pitloom.core.pep508 import parse_requirement
from pitloom.core.requirements import NOT_PEP_508, warn_skipped_dependency
from pitloom.logging_config import loggable, one_line
from pitloom.messages import Cap, warn_file_unreadable, warn_over_cap

log = logging.getLogger(__name__)

#: Largest requirements file read; a larger one is skipped with a warning.
MAX_REQUIREMENTS_FILE_BYTES = 1024 * 1024
#: Most bytes of requirements files one configuration file reads, every
#: directive together, a file listed by two directives counted twice. A
#: file that would pass it and the files after it are skipped, with one
#: warning.
MAX_REQUIREMENTS_TOTAL_BYTES = 4 * 1024 * 1024

#: A listed file: its identity, else (none on this file system, or it
#: could not be opened) its path as written.
_FileKey = FileId | Path

#: Splits a requirements text into requirement lines.
LineSplitter = Callable[[str], list[str]]

#: ``log.warning()`` format for a listed file that is absent, or whose name
#: holds a NUL (it names no file): no ``file-unreadable``, which an absent
#: file never is; not catalogued yet. Arguments: the file as listed, the
#: directive, ``not found`` or what refused the name.
_NOT_FOUND_WARNING = "FILE=%s: could not read for %s; %s"


def requirement_lines(text: str) -> list[str]:
    """Requirements in *text* as setuptools reads them
    (``setuptools._reqs.parse_strings``): a line each, blank lines and
    ``#`` lines left out, a `` #`` comment dropped, a line ending in ``\\``
    joined with the next."""
    lines = (line.strip() for line in text.splitlines())
    # The comment cut is not stripped: "x \\  # c" does not continue.
    items = iter(
        line.partition(" #")[0] for line in lines if line and not line.startswith("#")
    )
    requirements: list[str] = []
    for item in items:
        parts = [item]
        while parts and parts[-1].endswith("\\"):
            following = next(items, None)
            if following is None:
                return requirements
            _cut_continuation(parts)
            parts.append(following)
        requirements.append("".join(parts).strip())
    return requirements


def _cut_continuation(parts: list[str]) -> None:
    """``"".join(parts)[:-2].strip()`` in place, in time linear in the
    parts removed: setuptools cuts two characters for the ``\\``. Each
    part starts with a non-blank character, so only the last needs a
    strip, and it never strips to nothing."""
    cut = 2
    while cut and parts:
        last = parts.pop()
        if len(last) > cut:
            parts.append(last[:-cut])
        cut = max(0, cut - len(last))
    if parts:
        parts[-1] = parts[-1].rstrip()


def setup_cfg_requirement_lines(value: str) -> list[str]:
    """A ``setup.cfg`` requirements value, or the text its ``file:``
    directive reads, as setuptools reads it
    (``ConfigHandler._parse_requirements_list``): one item per line when
    it has a newline, else ``;``-separated (so a one-line file's marker
    is cut off), ``#`` items left out, then :func:`requirement_lines`."""
    items = value.splitlines() if "\n" in value else value.split(";")
    kept = (item.strip() for item in items)
    return requirement_lines("\n".join(i for i in kept if not i.startswith("#")))


def setup_cfg_file_names(value: str) -> tuple[str, ...] | None:
    """The files a ``setup.cfg`` ``file:`` *value* lists, comma-separated
    and stripped, a blank entry left out; ``None`` when *value* is not one.
    *value* is stripped first, as for Pitloom's other ``file:`` directives
    (:mod:`pitloom.extract.project._setup_cfg_directives`): setuptools
    reads a directive wrapped from an empty first line as requirements,
    and fails the build on them."""
    value = value.strip()
    if not value.startswith("file:"):
        return None
    names = (name.strip() for name in value.removeprefix("file:").split(","))
    return tuple(name for name in names if name)


@dataclass(frozen=True)
class ListedFiles:
    """A ``setup.cfg`` ``file:`` requirements value not yet read: the
    files it lists, in *project_dir*."""

    project_dir: Path
    names: tuple[str, ...]


def requirements_and_options(
    text: str, lines: LineSplitter = requirement_lines
) -> tuple[list[str], list[str]]:
    """``(requirements, options)`` of a requirements file's *text*, split
    into *lines*. A line starting with ``-`` is a pip option: its option
    name goes to *options*. Requirements are not validated here."""
    requirements: list[str] = []
    options: list[str] = []
    for line in lines(text):
        if line.startswith("-"):
            options.append(line.split()[0].split("=")[0])
        else:
            requirements.append(line)
    return requirements, options


def pep508_only(requirements: list[str], field: str, quiet: bool) -> list[str]:
    """*requirements* (of *field*) but each that is not PEP 508, skipped
    with a ``WARNING:`` as an extra's is
    (:func:`~pitloom.core.requirements.flatten_optional_dependencies`)."""
    kept: list[str] = []
    for text in requirements:
        try:
            parse_requirement(text, quiet=quiet)
        except InvalidRequirement:
            warn_skipped_dependency(field, text, NOT_PEP_508, quiet=quiet)
            continue
        kept.append(text)
    return kept


class _Unreadable(Exception):
    """A listed file is not read: *cause* says why."""

    def __init__(self, cause: OSError | ValueError) -> None:
        super().__init__(type(cause).__name__)
        self.cause = cause


class _TooLarge(Exception):
    """A listed file is over :data:`MAX_REQUIREMENTS_FILE_BYTES`."""


class RequirementsFiles:
    """The requirements files one configuration file's directives list:
    each file read once, known by the identity of the file opened, all of
    them within :data:`MAX_REQUIREMENTS_TOTAL_BYTES`.

    *config* (``pyproject.toml``, ``setup.cfg``) and *table* (the
    directives' table, ``tool.setuptools.dynamic``, ``options``) name them
    in warnings; a directive's key is named under *table*. *quiet*
    silences the ``WARNING:`` lines.
    """

    def __init__(self, project_dir: Path, config: str, table: str, quiet: bool) -> None:
        self.quiet = quiet
        self.table = table
        self._config = config
        self._project_dir = project_dir
        # File -> (text, its size in bytes), or why it is not read.
        self._read: dict[_FileKey, tuple[str, int] | _TooLarge | _Unreadable] = {}
        self._spent = 0
        self._skipped = 0
        #: The files read, as listed, in order: a dict as an ordered set.
        self.used: dict[str, None] = {}

    def field(self, key: str) -> str:
        """The directive *key* as warnings and provenance name it."""
        return f"{self.table}.{key}"

    def requirements(
        self, names: list[str] | tuple[str, ...], key: str, lines: LineSplitter
    ) -> list[str]:
        """The requirements the files *names* (listed by *key*) give, split
        into *lines*; a pip option line is skipped with one ``WARNING:``."""
        texts: list[str] = []
        seen: set[_FileKey] = set()
        for name in names:
            text = self._text(name, key, seen)
            if text is not None:
                texts.append(text)
        requirements, options = requirements_and_options("\n".join(texts), lines)
        if options and not self.quiet:
            log.warning(
                "%s: skipping pip option line(s) %s in %s: "
                "setuptools does not accept them",
                self._config,
                ", ".join(loggable(o) for o in dict.fromkeys(options)),
                loggable(self.field(key)),
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
                self.table,
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
                self._warn_unreadable(name, key, _Unreadable(exc))
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
        if isinstance(read, _Unreadable):
            self._warn_unreadable(name, key, read)
            return None
        text, size = read
        if self._spent + size > MAX_REQUIREMENTS_TOTAL_BYTES:
            self._skipped += 1
            return None
        self._spent += size
        self.used[name] = None
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
                f"skipped for {loggable(self.field(key))}",
                once=True,
                # The project too: a deleted file's inode is reused.
                key=f"{self._project_dir}\x00{file}",
            )

    def _warn_unreadable(self, name: str, key: str, read: _Unreadable) -> None:
        """The ``WARNING:`` for the file *name* that *key* lists, not
        *read*: ``file-unreadable`` (``/outside-project``, ``/not-utf8``)
        for one present, the uncoded line for one absent or no file name."""
        if self.quiet:
            return
        cause = read.cause
        if isinstance(cause, OSError) and is_missing_errno(cause):
            why = "not found"
        elif isinstance(cause, (OSError, UnicodeDecodeError)):
            warn_file_unreadable(log, cause, file=name, field=self.field(key))
            return
        else:  # a NUL: the name names no file
            why = one_line(cause)
        log.warning(_NOT_FOUND_WARNING, loggable(name), loggable(self.field(key)), why)


def _read_text(handle: BinaryIO) -> tuple[str, int] | _TooLarge | _Unreadable:
    """The UTF-8 text of the listed file open as *handle*, less a leading
    byte-order mark (as pip reads a requirements file), and its size in
    bytes, else why it is not read: :class:`_TooLarge` over
    :data:`MAX_REQUIREMENTS_FILE_BYTES`, :class:`_Unreadable` not UTF-8 or
    not readable."""
    try:
        raw = handle.read(MAX_REQUIREMENTS_FILE_BYTES + 1)
    except OSError as exc:
        return _Unreadable(exc)
    if len(raw) > MAX_REQUIREMENTS_FILE_BYTES:
        return _TooLarge()
    try:
        return raw.decode("utf-8-sig"), len(raw)  # a leading BOM is no text
    except UnicodeDecodeError as exc:
        return _Unreadable(exc)
