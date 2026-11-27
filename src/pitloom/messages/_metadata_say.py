# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying a coded error a project reader caught and went on past, as a
``WARNING`` (:func:`relay_coded_warning`), and a file discovery line
(:func:`warn_discovery`).

See also: :mod:`pitloom.messages._metadata_read` (the entries a relay
carries), :mod:`pitloom.messages._file_discovery` (the discovery lines).
"""

from __future__ import annotations

import logging

from pitloom.core.internal_error import InternalError
from pitloom.messages._emit import code_of, emit, relay_extra
from pitloom.messages._file_discovery import (
    FILE_DISCOVERY_CONFLICT,
    FILE_DISCOVERY_NEEDS_BUILD,
    FILE_DISCOVERY_UNUSABLE,
)
from pitloom.messages._surface import Twins
from pitloom.messages._types import Line

#: The entries :func:`warn_discovery` says, each named here so a check can
#: see which entry a helper call says.
_DISCOVERY_ENTRIES = (
    FILE_DISCOVERY_UNUSABLE,
    FILE_DISCOVERY_NEEDS_BUILD,
    FILE_DISCOVERY_CONFLICT,
)


def relay_coded_warning(
    log: logging.Logger, exc: BaseException, *, quiet: bool
) -> None:
    """The one ``WARNING:`` on *log* that says *exc*, a coded error a reader
    caught and read on past, in its own words and with its code; nothing
    when *quiet*. The outcome is its entry's ``did``, not a tail: the text
    stays one of the entry's lines.

    Raises:
        pitloom.core.internal_error.InternalError: *exc* carries no
            catalogued code, or its entry has no ``WARNING`` line of its
            text (a twin missing), *quiet* or not: never said uncoded.
    """
    code = code_of(exc)
    text = str(exc)
    extra = None if code is None else relay_extra(code, "WARNING", text)
    if extra is None:
        raise InternalError(
            f"{code or type(exc).__name__}: no WARNING line relays it"
        ) from exc
    if not quiet:
        log.warning("%s", text, extra=extra)


def warn_discovery(
    log: logging.Logger, line: Line | Twins[Line], **values: object
) -> None:
    """The one ``WARNING:`` on *log* of the file discovery *line* (a line
    of :mod:`pitloom.messages.file_discovery`; twins say the surface's
    wording), with *values*, carrying the code of the entry that holds it.

    Raises:
        pitloom.core.internal_error.InternalError: *line* is no file
            discovery line.
        ValueError: *values* are not the line's fields, or a value does not
            have its field's shape.
    """
    if isinstance(line, Twins):
        line = line.current()
    entry = next((e for e in _DISCOVERY_ENTRIES if line in e.lines), None)
    if entry is None:
        raise InternalError(f"{line.template!r} is no file discovery line")
    # The keywords bound by name: no value can take their place.
    emit(
        log,
        entry,
        logging.WARNING,
        line=line,
        once=None,
        extra=None,
        frame=None,
        frame_values=None,
        **values,
    )
