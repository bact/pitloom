# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` for a file Pitloom could not read
(:func:`warn_file_unreadable`) and for a directory it could not list
(:func:`warn_dir_unlistable`): the entry chosen by the exception, and never
for one that is absent.

See also: :mod:`pitloom.messages._file_unreadable` (the entries).
"""

from __future__ import annotations

import logging
import os

from pitloom.core.internal_error import InternalError
from pitloom.core.path_confine import OutsideRootError
from pitloom.core.path_probe import is_missing_errno
from pitloom.messages._emit import emit
from pitloom.messages._file_unreadable import (
    DIR_UNLISTABLE,
    FILE_UNREADABLE,
    FILE_UNREADABLE_NOT_UTF8,
    FILE_UNREADABLE_OUTSIDE,
)
from pitloom.messages._types import Message


def _refuse_absent(exc: BaseException) -> None:
    """Raise when *exc* says the path is absent
    (:func:`~pitloom.core.path_probe.is_missing_errno`): absent data is
    quiet, so it never carries an unreadable code. The caller asks first.

    Raises:
        pitloom.core.internal_error.InternalError: It does.
    """
    if isinstance(exc, OSError) and is_missing_errno(exc):
        raise InternalError(f"an absent path is not unreadable (errno {exc.errno})")


def _entry(exc: BaseException) -> Message:
    """The entry *exc* says: a path out of the project, a text not UTF-8,
    else the file's own failure."""
    if isinstance(exc, OutsideRootError):
        return FILE_UNREADABLE_OUTSIDE
    if isinstance(exc, UnicodeDecodeError):
        return FILE_UNREADABLE_NOT_UTF8
    return FILE_UNREADABLE


# pylint: disable-next=too-many-arguments
def warn_file_unreadable(
    log: logging.Logger,
    exc: BaseException,
    *,
    file: str | os.PathLike[str],
    use: str | None = None,
    field: str | None = None,
    model_format: str | None = None,
    once: str | None = None,
) -> None:
    """The one ``WARNING:`` on *log* for the file *file* (as the line names
    it) that *exc* stopped Pitloom reading, for exactly one of: *use* (one
    of :data:`~pitloom.messages._fields.READ_USES`), *field* (the project
    setting that lists the file) or *model_format* (the header read to
    confirm a model of that format).

    The entry is *exc*'s: :class:`~pitloom.core.path_confine.OutsideRootError`
    is ``file-unreadable/outside-project``, :class:`UnicodeDecodeError`
    ``file-unreadable/not-utf8``, anything else ``file-unreadable``; the line
    says what *exc* reports (an :class:`OSError`'s ``strerror``), never its
    text, which quotes the path. *once*: said once per key and process (a
    repeat is ``DEBUG``); the key names the file, as one run may read it
    twice.

    Raises:
        pitloom.core.internal_error.InternalError: *exc* says the file is
            absent (the caller stays quiet about that), or not exactly one of
            *use*, *field* and *model_format* is given.
    """
    _refuse_absent(exc)
    named = {
        key: value
        for key, value in (("use", use), ("field", field), ("format", model_format))
        if value is not None
    }
    if len(named) != 1:
        raise InternalError(f"one of use, field, model_format, not {sorted(named)}")
    entry = FILE_UNREADABLE if model_format is not None else _entry(exc)
    values: dict[str, object] = {"file": file, **named}
    if entry is not FILE_UNREADABLE_OUTSIDE:
        values["failure"] = exc
    # line and extra bound by name: no value can take their place.
    emit(log, entry, logging.WARNING, line=None, once=once, extra=None, **values)


def warn_dir_unlistable(
    log: logging.Logger,
    exc: BaseException,
    *,
    directory: str | os.PathLike[str],
    use: str,
    once: str | None = None,
) -> None:
    """The one ``WARNING:`` on *log* for the directory *directory* (as the
    line names it) that *exc* stopped Pitloom listing for *use* (one of
    :data:`~pitloom.messages._fields.READ_USES`), ``dir-unlistable``: what
    *exc* reports, never its text. *once*: as for
    :func:`warn_file_unreadable`.

    Raises:
        pitloom.core.internal_error.InternalError: *exc* says the directory
            is absent.
    """
    _refuse_absent(exc)
    emit(
        log,
        DIR_UNLISTABLE,
        logging.WARNING,
        once=once,
        dir=directory,
        use=use,
        failure=exc,
    )
