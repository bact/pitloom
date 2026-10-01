# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The bounds on a capture block's undo: how many interrupts it holds, and
how long it waits for a lock that was never released (CPython 3.14 can leave
one held when an interrupt arrives right after the lock is taken).

See also: :mod:`tests.extract.test_reader_log_interrupt`,
:mod:`tests.extract.ai_model.test_stderr_capture_interrupt` (the bounds
through each capture block).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import contextlib
import sys
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest

from pitloom.extract import _interrupt_hold as hold
from pitloom.extract import _reader_log as rl
from pitloom.extract.ai_model import _stderr_capture as sc

_WAIT = 10  # seconds; a hang fails the test instead of the run


@pytest.mark.parametrize(
    ("interrupts", "calls", "raised"),
    [
        (0, 1, False),
        (1, 2, True),  # held, then run to the end, then raised
        (hold.HOLD_LIMIT - 1, hold.HOLD_LIMIT, True),
        (hold.HOLD_LIMIT, hold.HOLD_LIMIT, True),
        (100, hold.HOLD_LIMIT, True),  # the bound, not the interrupts
    ],
)
def test_the_undo_is_tried_a_bounded_number_of_times(
    interrupts: int, calls: int, raised: bool
) -> None:
    done: list[int] = []

    def undo() -> None:
        done.append(1)
        if len(done) <= interrupts:
            raise KeyboardInterrupt

    with contextlib.ExitStack() as stack:
        if raised:
            stack.enter_context(pytest.raises(KeyboardInterrupt))
        hold.run_held(undo)
    assert len(done) == calls


def _use(make: Callable[[], AbstractContextManager[object]]) -> None:
    with make():
        pass


def _held_lock_outcome(
    lock: threading.Lock, action: Callable[[], None]
) -> tuple[bool, list[str]]:
    """Run *action* in a thread while *lock* is held elsewhere: whether it was
    still waiting after _WAIT seconds (a hang, not a failed wait), and what
    it raised. The lock is then released, so that a hang cannot outlive the
    test."""
    outcome: list[str] = []

    def run() -> None:
        try:
            action()
            outcome.append("entered")
        except hold.LockNotReleased:
            outcome.append("gave up")

    with lock:
        thread = threading.Thread(target=run)
        thread.start()
        thread.join(_WAIT)
        waiting = thread.is_alive()
    thread.join(_WAIT)
    return waiting, outcome


def test_a_lock_is_given_up_on_when_it_is_not_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hold, "LOCK_TIMEOUT", 0.05)
    lock = threading.Lock()
    with hold.locked(lock):
        assert lock.locked()
    assert not lock.locked()
    waiting, outcome = _held_lock_outcome(lock, lambda: _use(lambda: hold.locked(lock)))
    assert (waiting, outcome) == (False, ["gave up"])
    assert not lock.locked()  # released by its holder, not by the waiter


def _log_block() -> AbstractContextManager[object]:
    return rl.capture_reader_logs()


def _stderr_block() -> AbstractContextManager[object]:
    return sc.capture_stderr()


@pytest.mark.parametrize(
    ("module", "block"), [(rl, _log_block), (sc, _stderr_block)], ids=["log", "stderr"]
)
def test_a_block_does_not_wait_for_ever_for_a_lock_left_held(
    module: object,
    block: Callable[[], AbstractContextManager[object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hold, "LOCK_TIMEOUT", 0.05)
    before = sys.stderr
    leaked = threading.Lock()  # as if an interrupt had left it held
    monkeypatch.setattr(module, "_LOCK", leaked)
    waiting, outcome = _held_lock_outcome(leaked, lambda: _use(block))
    assert (waiting, outcome) == (False, ["gave up"])
    assert sys.stderr is before
    assert not rl._STATE.installed
    assert sc._STATE.users == 0
