# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying an ID registry save that failed (:func:`say_save_failure`) and a
registry with no file to save to (:func:`warn_no_registry_file`).

See also: :mod:`pitloom.messages._registry_save` (the entries and
summaries), :mod:`pitloom.id_registry._persist` (the save).
"""

from __future__ import annotations

import logging
import os

from pitloom.core.internal_error import InternalError
from pitloom.messages._emit import code_of, emit, relay_extra
from pitloom.messages._field_tables import REGISTRY_USE
from pitloom.messages._file_unwritable import FILE_UNWRITABLE
from pitloom.messages._registry_save import REGISTRY_FILE_MISSING


def say_save_failure(
    log: logging.Logger,
    exc: BaseException,
    *,
    file: str | os.PathLike[str],
    fatal: bool,
) -> None:
    """The one line on *log* for a save of the registry file *file* (as the
    line names it) that *exc* stopped: an ``ERROR`` when *fatal* (``loom
    id``, whose output is the registry), else a ``WARNING`` (a run whose
    SBOM is already built). The save adds no condition: a coded *exc*
    says its own line, with its code when that message has the line at
    this level; an uncoded :class:`OSError` is the write the system refused
    (``file-unwritable``).

    Raises:
        pitloom.core.internal_error.InternalError: *exc* is neither coded
            nor an :class:`OSError` (no input of a user reaches a save with
            one), or is coded but its message has no line of this text at
            this level (a ``WARNING`` twin missing): never said uncoded.
    """
    level = logging.ERROR if fatal else logging.WARNING
    code = code_of(exc)
    if code is not None:
        text = str(exc)
        extra = relay_extra(code, logging.getLevelName(level), text)
        if extra is None:
            raise InternalError(
                f"{code}: no {logging.getLevelName(level)} line says a failed "
                "ID registry save"
            ) from exc
        log.log(level, "%s", text, extra=extra)
    elif isinstance(exc, OSError):
        emit(log, FILE_UNWRITABLE, level, file=file, use=REGISTRY_USE, failure=exc)
    else:
        raise InternalError(
            f"an uncoded {type(exc).__name__} from an ID registry save"
        ) from exc


def warn_no_registry_file(log: logging.Logger) -> None:
    """The one ``WARNING:`` on *log* for a registry with no file to save
    the ids a run added to (``registry-file-missing``)."""
    emit(log, REGISTRY_FILE_MISSING, logging.WARNING)
