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

The undo holds a second interrupt for a few tries and waits a bounded time
for the lock (:mod:`pitloom.extract._interrupt_hold`): on CPython 3.14 an
interrupt can leave the lock held for good, and the logger may then stay as
it was when the interrupt is raised.

See also: :mod:`pitloom.extract.scanner`.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field

from pitloom.extract._interrupt_hold import locked, run_held

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
        # record.thread is None when logging.logThreads is off: the emitting
        # thread is still this one.
        ident = threading.get_ident() if record.thread is None else record.thread
        records = self.captures.get(ident)
        if records is not None:
            records.append(record)
        elif (parent := logging.getLogger(_READERS_LOGGER).parent) is not None:
            parent.handle(record)


@dataclass
class _State:
    """The logger's saved configuration, while it is changed."""

    installed: bool = False
    propagate: bool = True
    dispatcher: _Dispatcher = field(default_factory=_Dispatcher)


_STATE = _State()


@dataclass
class _Block:
    """One capture block: its records, and the capture of the same thread it
    interrupts, if nested. Filled in place so that an interrupt cannot lose
    the outer capture between taking it and handing it back."""

    records: list[logging.LogRecord] = field(default_factory=list)
    outer: list[logging.LogRecord] | None = None


def _enter(block: _Block) -> None:
    """Start capturing this thread into *block*."""
    logger = logging.getLogger(_READERS_LOGGER)
    with locked(_LOCK):
        if not _STATE.installed:
            _STATE.propagate = logger.propagate
            # Flagged before the logger is changed, so that leaving undoes
            # it even when an interrupt cuts the change short.
            _STATE.installed = True
            logger.addHandler(_STATE.dispatcher)
            logger.propagate = False
        ident = threading.get_ident()
        block.outer = _STATE.dispatcher.captures.get(ident)
        _STATE.dispatcher.captures[ident] = block.records


def _undo(block: _Block) -> None:
    """Take *block* off this thread, and the logger back to what it was
    when no thread captures. Idempotent."""
    logger = logging.getLogger(_READERS_LOGGER)
    ident = threading.get_ident()
    captures = _STATE.dispatcher.captures
    with locked(_LOCK):
        if captures.get(ident) is block.records:
            if block.outer is None:
                del captures[ident]
            else:
                captures[ident] = block.outer
        if _STATE.installed and not captures:
            logger.removeHandler(_STATE.dispatcher)
            logger.propagate = _STATE.propagate
            _STATE.installed = False


def _exit(block: _Block) -> None:
    """Undo :func:`_enter`, and only that: an interrupt may have cut it
    short, so *block* is taken off only if registered.

    A second interrupt in here is held for a few tries, then raised; see
    :func:`pitloom.extract._interrupt_hold.run_held`.
    """
    run_held(lambda: _undo(block))


@contextlib.contextmanager
def capture_reader_logs() -> Iterator[list[logging.LogRecord]]:
    """Collect, instead of passing on, what the readers log in the block,
    in this thread only.

    The list is complete once the block is left. Records are not logged
    by this function; the caller logs the ones it wants. Blocks of several
    threads may overlap in any order: the logger's propagation is saved by
    the first to enter and restored by the last to leave, and a thread not
    in a block has its records passed on as usual. A block inside another of
    the same thread collects on its own, and the outer one resumes after it.
    An interrupt (``KeyboardInterrupt``) at any step leaves the logger as it
    was found.
    """
    block = _Block()
    try:
        _enter(block)
        yield block.records
    finally:
        _exit(block)
