# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Bounded waiting for the undo of a capture block.

A capture block (:mod:`pitloom.extract._reader_log`,
:mod:`pitloom.extract.ai_model._stderr_capture`) undoes what it did while a
``KeyboardInterrupt`` may arrive again. :func:`run_held` retries the undo a
few times, then raises; :func:`locked` gives up on a lock that is not
released instead of waiting for it for ever.

The bounds matter on CPython 3.14, where an interrupt can arrive between a
lock being taken and the ``try`` that releases it, leaving the lock held for
good. Waiting for it, or retrying every interrupt, would make the process
unkillable. The cost of giving up is that the state the lock guards may stay
as it was: the process is ending on that interrupt anyway.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator

#: Tries the undo gets; an interrupt that arrives in the last one is raised.
HOLD_LIMIT = 3

#: Seconds to wait for a lock. It guards a few assignments, so waiting this
#: long means that it was never released.
LOCK_TIMEOUT = 5.0


class LockNotReleased(RuntimeError):
    """A lock guarding capture state was not released within
    :data:`LOCK_TIMEOUT`."""


@contextlib.contextmanager
def locked(lock: threading.Lock) -> Iterator[None]:
    """Hold *lock* for the block, or raise :class:`LockNotReleased`."""
    if not lock.acquire(timeout=LOCK_TIMEOUT):
        raise LockNotReleased("capture state lock was not released")
    try:
        yield
    finally:
        lock.release()


def run_held(undo: Callable[[], None]) -> None:
    """Run *undo* (idempotent) to the end, holding interrupts that arrive in
    it for up to :data:`HOLD_LIMIT` tries, then raise the last one held."""
    interrupt: KeyboardInterrupt | None = None
    for _ in range(HOLD_LIMIT):
        try:
            undo()
        except KeyboardInterrupt as exc:
            interrupt = exc
        else:
            break
    if interrupt is not None:
        raise interrupt
