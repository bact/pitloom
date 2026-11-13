# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying ``input-not-found``: the error to raise for a path named for
Pitloom to read that is not there (:func:`input_not_found`), the command
line's ``ERROR:`` line for one (:func:`say_input_not_found`), and the
``WARNING:`` for a configured SBOM fragment that is not there
(:func:`warn_fragment_not_found`).

See also: :mod:`pitloom.messages._input_not_found` (the entries).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.core.url_masking import masked_given_path
from pitloom.logging_config import print_error
from pitloom.messages._emit import CodedFileNotFoundError, emit
from pitloom.messages._field_tables import INPUT_KINDS
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


def _line(kind: str, path: str | os.PathLike[str]) -> Line:
    """The line for *path*, named as *kind*: not found when nothing is
    there (:func:`os.path.exists`, which never raises; a dangling link
    leads nowhere, so it is not found too), else not a file or not a
    directory, as *kind* expects.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not one of
            :data:`~pitloom.messages._field_tables.INPUT_KINDS`.
    """
    if kind not in INPUT_KINDS:
        raise InternalError(f"input kind {kind!r} is not in INPUT_KINDS")
    if kind in _EITHER_KINDS or not os.path.exists(path):
        return INPUT_LINE
    return _WRONG_KIND_LINES[kind]


def _render(kind: str, path: str | os.PathLike[str]) -> tuple[Line, dict[str, object]]:
    """The line for *path*, named as *kind* (:func:`_line`, the one probe),
    and the values it is written from, *path* shown with a URL in it masked
    (:func:`~pitloom.core.url_masking.masked_given_path`): what
    :func:`input_not_found` raises and :func:`say_input_not_found` prints.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not one of
            :data:`~pitloom.messages._field_tables.INPUT_KINDS`.
    """
    line = _line(kind, path)
    text = os.fspath(path)
    shown = masked_given_path(text)
    return line, {"input": kind, "path": path if shown == text else shown}


def input_not_found(kind: str, path: str | os.PathLike[str]) -> CodedFileNotFoundError:
    """The error to raise for *path*, named as *kind* (one of
    :data:`~pitloom.messages._field_tables.INPUT_KINDS`), which is not there, or is
    not a file or not a directory as *kind* expects (the line says which).

    *path* is named as the user gave it (the argument as typed, or the
    configured value), when the caller has that spelling: a caller that
    resolves a path for the check still passes the given one here, so the
    line names what the user wrote, never a resolved or absolute form of it.
    A URL in it (one Pitloom does not read, taken for a path) is named with
    its credentials masked.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not one of
            :data:`~pitloom.messages._field_tables.INPUT_KINDS`.
    """
    line, values = _render(kind, path)
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
