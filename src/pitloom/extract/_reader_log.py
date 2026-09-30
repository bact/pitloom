# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Capture of the log records an AI model reader emits.

A reader names a file by the path it was given, and quotes member names of
the archive it reads; the scanner hands it a temporary copy, and the
archive is untrusted. The scanner captures the records while a reader runs
and logs them again under the stable ``FORMAT=``/``FILE=`` prefix, with the
text escaped and the temporary path removed: one route for every reader,
present and future.

See also: :mod:`pitloom.extract.scanner`.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field

#: The logger every reader's own logger is a child of.
_READERS_LOGGER = "pitloom.extract.ai_model"

# Guards _STATE. Never held while logging, so a handler may take it.
_LOCK = threading.Lock()


class _Dispatcher(logging.Handler):
    """Hands a record to the capture of the thread that logged it, or on to
    the logger's parent when that thread is not capturing."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.captures: dict[int, list[logging.LogRecord]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        records = self.captures.get(record.thread or 0)
        if records is not None:
            records.append(record)
        elif (parent := logging.getLogger(_READERS_LOGGER).parent) is not None:
            parent.handle(record)


@dataclass
class _State:
    """The logger's saved configuration, while any thread is capturing."""

    users: int = 0
    propagate: bool = True
    dispatcher: _Dispatcher = field(default_factory=_Dispatcher)


_STATE = _State()


def _enter(records: list[logging.LogRecord]) -> None:
    logger = logging.getLogger(_READERS_LOGGER)
    with _LOCK:
        if _STATE.users == 0:
            _STATE.propagate = logger.propagate
            logger.addHandler(_STATE.dispatcher)
            logger.propagate = False
        _STATE.users += 1
        _STATE.dispatcher.captures[threading.get_ident()] = records


def _exit() -> None:
    logger = logging.getLogger(_READERS_LOGGER)
    with _LOCK:
        _STATE.dispatcher.captures.pop(threading.get_ident(), None)
        _STATE.users -= 1
        if _STATE.users == 0:
            logger.removeHandler(_STATE.dispatcher)
            logger.propagate = _STATE.propagate


@contextlib.contextmanager
def capture_reader_logs() -> Iterator[list[logging.LogRecord]]:
    """Collect, instead of passing on, what the readers log in the block,
    in this thread only.

    The list is complete once the block is left. Records are not logged
    by this function; the caller logs the ones it wants. Blocks of several
    threads may overlap in any order: the logger's propagation is saved by
    the first to enter and restored by the last to leave, and a thread not
    in a block has its records passed on as usual.
    """
    records: list[logging.LogRecord] = []
    _enter(records)
    try:
        yield records
    finally:
        _exit()
