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
else to the stream it replaced, which the last thread to leave puts back.

See also: :mod:`pitloom.extract._reader_log` (the same shape, for logging).
"""

from __future__ import annotations

import contextlib
import io
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, TextIO, cast

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


class _Proxy:
    """Stands in for ``sys.stderr`` while a thread captures it."""

    def __init__(self, original: TextIO) -> None:
        self.original = original
        self.sinks: dict[int, BoundedStderr] = {}

    def write(self, s: str) -> int:
        sink = self.sinks.get(threading.get_ident())
        return (sink or self.original).write(s)

    def flush(self) -> None:
        if threading.get_ident() not in self.sinks:
            self.original.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.original, name)


@dataclass
class _State:
    users: int = 0
    proxy: _Proxy | None = None


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
    with _LOCK:
        if _STATE.users == 0:
            # A fresh proxy each time: a late writer holding the last one
            # cannot reach this one's sinks.
            _STATE.proxy = _Proxy(sys.stderr)
            sys.stderr = cast(TextIO, _STATE.proxy)
        proxy = cast(_Proxy, _STATE.proxy)
        _STATE.users += 1
        outer = proxy.sinks.get(ident)
        proxy.sinks[ident] = sink
    try:
        yield sink
    finally:
        with _LOCK:
            if outer is None:
                proxy.sinks.pop(ident, None)
            else:
                proxy.sinks[ident] = outer
            _STATE.users -= 1
            # Only our own proxy is taken out: another party may have
            # replaced sys.stderr since, and that is theirs to restore.
            if _STATE.users == 0 and sys.stderr is proxy:
                sys.stderr = proxy.original
