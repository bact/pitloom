# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying ``input-not-found``: the one probe of a path named for Pitloom to
read (:func:`input_exists`, :func:`is_input_file`, :func:`is_input_dir`),
the error to raise for one that is not there (:func:`input_not_found`), the
command line's ``ERROR:`` line for one (:func:`say_input_not_found`), and the
``WARNING:`` for a configured SBOM fragment that is not there
(:func:`warn_fragment_not_found`).

An input check goes through the probe, never :func:`os.path.isfile` and its
siblings, which say ``False`` for a path the system will not let Pitloom
look at (a directory above it without search permission): that is
``file-unreadable``, not ``input-not-found``.

See also: :mod:`pitloom.messages._input_not_found` (the entries).
"""

from __future__ import annotations

import logging
import os
import stat
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.core.path_probe import stat_if_present
from pitloom.logging_config import print_error
from pitloom.messages._emit import CodedFileNotFoundError, emit
from pitloom.messages._field_tables import INPUT_KINDS, INPUT_USE
from pitloom.messages._file_unreadable_warning import file_unreadable_error
from pitloom.messages._input_not_found import (
    FRAGMENT_LINE,
    INPUT_LINE,
    INPUT_NOT_DIR_LINE,
    INPUT_NOT_FILE_LINE,
    INPUT_NOT_FOUND,
    INPUT_NOT_FOUND_FRAGMENT,
    REQUIRED_FRAGMENT_LINE,
)
from pitloom.messages._types import Line

#: The kinds of :data:`~pitloom.messages._field_tables.INPUT_KINDS` that name a
#: directory; ``project path`` names either, so none is expected of it.
_DIRECTORY_KINDS: Final = frozenset({"fragments directory", "project directory"})
_EITHER_KINDS: Final = frozenset({"project path"})
#: The line said when something of the wrong kind is at the path, by kind.
_WRONG_KIND_LINES: Final[Mapping[str, Line]] = MappingProxyType(
    {
        kind: INPUT_NOT_DIR_LINE if kind in _DIRECTORY_KINDS else INPUT_NOT_FILE_LINE
        for kind in INPUT_KINDS
        if kind not in _EITHER_KINDS
    }
)


def _input_stat(
    path: str | os.PathLike[str], shown: str | os.PathLike[str] | None
) -> os.stat_result | None:
    """``os.stat(path)``, or ``None`` when nothing is there: missing
    (:func:`~pitloom.core.path_probe.is_missing_errno`, a link loop
    included), a dangling link (it leads nowhere), or a path no file can
    have (an embedded NUL).

    Raises:
        pitloom.messages.CodedValueError: The system will not let Pitloom
            look (a directory above *path* without search permission, an
            I/O error): ``file-unreadable``, naming *shown*, else *path*.
    """
    try:
        return stat_if_present(path)
    except ValueError:
        return None
    except OSError as exc:
        named = path if shown is None else shown
        raise file_unreadable_error(exc, file=named, use=INPUT_USE) from exc


def input_exists(
    path: str | os.PathLike[str], *, shown: str | os.PathLike[str] | None = None
) -> bool:
    """Whether something is at the input *path* (:func:`_input_stat`, which
    raises ``file-unreadable`` naming *shown*, else *path*, for an access
    failure)."""
    return _input_stat(path, shown) is not None


def is_input_file(
    path: str | os.PathLike[str], *, shown: str | os.PathLike[str] | None = None
) -> bool:
    """Whether a regular file is at the input *path*, as
    :func:`input_exists` looks."""
    result = _input_stat(path, shown)
    return result is not None and stat.S_ISREG(result.st_mode)


def is_input_dir(
    path: str | os.PathLike[str], *, shown: str | os.PathLike[str] | None = None
) -> bool:
    """Whether a directory is at the input *path*, as :func:`input_exists`
    looks."""
    result = _input_stat(path, shown)
    return result is not None and stat.S_ISDIR(result.st_mode)


def _line(
    kind: str, path: str | os.PathLike[str], shown: str | os.PathLike[str]
) -> Line:
    """The line for *path*, named as *kind*: not found when nothing is
    there (:func:`input_exists`), else not a file or not a directory, as
    *kind* expects.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not one of
            :data:`~pitloom.messages._field_tables.INPUT_KINDS`.
        pitloom.messages.CodedValueError: *path* cannot be looked at
            (``file-unreadable``, naming *shown*).
    """
    if kind not in INPUT_KINDS:
        raise InternalError(f"input kind {kind!r} is not in INPUT_KINDS")
    # An either kind has no wrong-kind line and is never probed: a path that
    # appears after the caller's probe still reads as not found.
    wrong = _WRONG_KIND_LINES.get(kind)
    if wrong is None or not input_exists(path, shown=shown):
        return INPUT_LINE
    return wrong


def _render(
    kind: str,
    path: str | os.PathLike[str],
    at: str | os.PathLike[str] | None = None,
) -> tuple[Line, dict[str, object]]:
    """The line for *path*, named as *kind* (:func:`_line`, the one probe,
    of *at* when given, else of *path*), and the values it is written from
    (the path field names *path* as given, a URL in it masked:
    :func:`~pitloom.messages._field_writers.path_text`): what
    :func:`input_not_found` raises and :func:`say_input_not_found` prints.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not one of
            :data:`~pitloom.messages._field_tables.INPUT_KINDS`.
    """
    line = _line(kind, path if at is None else at, path)
    return line, {"input": kind, "path": path}


def input_not_found(
    kind: str,
    path: str | os.PathLike[str],
    *,
    at: str | os.PathLike[str] | None = None,
) -> CodedFileNotFoundError:
    """The error to raise for *path*, named as *kind* (one of
    :data:`~pitloom.messages._field_tables.INPUT_KINDS`), which is not there, or is
    not a file or not a directory as *kind* expects (the line says which).

    *path* is named as the user gave it (the argument as typed, or the
    configured value), when the caller has that spelling: a caller that
    resolves a path for the check still passes the given one here, so the
    line names what the user wrote, never a resolved or absolute form of it.
    A URL in it (one Pitloom does not read, taken for a path) is named with
    its credentials masked. *at* is where the caller looked, when that is
    not *path* as the current directory reads it (a relative path resolved
    against a project directory): it decides whether the line says what is
    there instead.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not one of
            :data:`~pitloom.messages._field_tables.INPUT_KINDS`.
    """
    line, values = _render(kind, path, at)
    return CodedFileNotFoundError(INPUT_NOT_FOUND, line=line, **values)


def say_input_not_found(kind: str, path: str | os.PathLike[str]) -> None:
    """Print the command line's ``ERROR:`` line for *path*, as
    :func:`input_not_found` words it, with its code, after the frame of the
    command running (:func:`~pitloom.logging_config.print_error`). The
    caller returns its failure status. *path* is named as
    :func:`input_not_found` names it: as the user gave it.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not one of
            :data:`~pitloom.messages._field_tables.INPUT_KINDS`.
    """
    line, values = _render(kind, path)
    print_error(line.render(values), code=INPUT_NOT_FOUND.code)


def warn_fragment_not_found(
    log: logging.Logger, path: str | os.PathLike[str], *, required: bool
) -> None:
    """The one ``WARNING:`` on *log* for the configured SBOM fragment
    *path* that is not there, ``input-not-found/fragment``: left out of the
    merge, or, *required*, the merge will fail."""
    line = REQUIRED_FRAGMENT_LINE if required else FRAGMENT_LINE
    emit(log, INPUT_NOT_FOUND_FRAGMENT, logging.WARNING, line=line, path=path)
