# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Capture of what a third-party parser writes to ``sys.stderr``, per thread.

:func:`contextlib.redirect_stderr` swaps ``sys.stderr`` for the whole
process: two threads in it can leave the wrong stream installed for good, and
a thread that is not capturing has its output swallowed. :func:`capture_stderr`
installs one proxy while any thread is capturing; the proxy sends only the
writes of a capturing thread to that thread's bounded sink and everything
else to the stream it replaced (dropped when there is none: ``sys.stderr``
is ``None`` under ``pythonw``). The last thread to leave puts the stream
back, unless something else replaced ``sys.stderr`` meanwhile: the proxy
then stays where it was left, with no sinks, forwarding every write. A block
that an interrupt (``KeyboardInterrupt``) cuts short at any point undoes
only what it did, by identity. The undo holds a second interrupt for a few
tries and waits a bounded time for the lock (:mod:`pitloom.extract._interrupt_hold`):
on CPython 3.14 an interrupt can leave the lock held for good, and the
state may then stay as it was when the interrupt is raised.

See also: :mod:`pitloom.extract._reader_log` (the same shape, for logging).
"""

from __future__ import annotations

import contextlib
import io
import sys
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, TextIO, cast

from pitloom.extract._interrupt_hold import locked, run_held

# Guards _STATE and the proxy's sinks. Never held while writing.
_LOCK = threading.Lock()


class BoundedStderr(io.TextIOBase):
    """A write-only text sink that keeps the first :data:`_KEEP` characters."""

    _KEEP = 4096

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._size = 0

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if self._size < self._KEEP:
            self._parts.append(s[: self._KEEP - self._size])
            self._size += len(self._parts[-1])
        return len(s)

    def text(self) -> str:
        """What was kept."""
        return "".join(self._parts)


# What attribute access (``isatty``, ``encoding``) is answered by when there
# is no ``sys.stderr``.
_NULL_STREAM = io.StringIO()


class _Proxy:
    """Stands in for ``sys.stderr`` while a thread captures it."""

    def __init__(self, original: TextIO | None) -> None:
        self.original = original
        # Thread id -> that thread's sink; the capturing threads are its keys.
        self.sinks: dict[int, BoundedStderr] = {}

    def write(self, s: str) -> int:
        sink = self.sinks.get(threading.get_ident())
        if sink is not None:
            return sink.write(s)
        if self.original is None:
            return len(s)
        return self.original.write(s)

    def writelines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        if self.original is not None and threading.get_ident() not in self.sinks:
            self.original.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(_NULL_STREAM if self.original is None else self.original, name)


@dataclass
class _State:
    proxy: _Proxy | None = None

    @property
    def users(self) -> int:
        """How many threads are capturing."""
        return len(self.proxy.sinks) if self.proxy is not None else 0


_STATE = _State()


@contextlib.contextmanager
def capture_stderr() -> Iterator[BoundedStderr]:
    """Collect, in this thread only, what is written to ``sys.stderr`` in
    the block (the first 4096 characters).

    Blocks of several threads may overlap in any order; a thread not in a
    block writes to the stream as usual. A block entered inside another of
    the same thread has its own sink, and the outer one is back on leaving.
    """
    sink = BoundedStderr()
    ident = threading.get_ident()
    proxy: _Proxy | None = None
    outer: BoundedStderr | None = None
    try:
        with locked(_LOCK):
            proxy = _STATE.proxy
            if proxy is None or sys.stderr is not proxy:
                # A fresh proxy when sys.stderr is not ours: a late writer
                # holding the old one cannot reach this one's sinks.
                proxy = _Proxy(sys.stderr)
                _STATE.proxy = proxy
                sys.stderr = cast(TextIO, proxy)
            outer = proxy.sinks.get(ident)
            proxy.sinks[ident] = sink
        yield sink
    finally:
        _leave(proxy, ident, sink, outer)


def _undo(
    proxy: _Proxy,
    ident: int,
    sink: BoundedStderr,
    outer: BoundedStderr | None,
) -> None:
    """Take *sink* off the thread, and the proxy off ``sys.stderr`` when no
    thread captures. Idempotent: the sink is removed only if it is the
    registered one."""
    with locked(_LOCK):
        if proxy.sinks.get(ident) is sink:
            if outer is None:
                del proxy.sinks[ident]
            else:
                proxy.sinks[ident] = outer
        # Only our own proxy is taken out: another party may have replaced
        # sys.stderr since, and that is theirs to restore.
        if not proxy.sinks and sys.stderr is proxy:
            sys.stderr = cast(TextIO, proxy.original)


def _leave(
    proxy: _Proxy | None,
    ident: int,
    sink: BoundedStderr,
    outer: BoundedStderr | None,
) -> None:
    """Undo what :func:`capture_stderr` did, and only that: an interrupt may
    have cut its entry short at any step.

    A second interrupt in here is held for a few tries, then raised; see
    :func:`pitloom.extract._interrupt_hold.run_held`.
    """
    if proxy is not None:
        run_held(lambda: _undo(proxy, ident, sink, outer))
