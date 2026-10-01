# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``KeyboardInterrupt`` at any step of a stderr capture block leaves
nothing behind: ``sys.stderr`` is the stream found, the thread's later writes
reach it, and no thread counts as capturing.

An interrupt is injected before each statement of the entry (through
``sys.settrace``, which makes the step deterministic) and of the undo.

See also: :mod:`tests.extract.ai_model.test_stderr_capture`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import contextlib
import io
import sys
import threading
from unittest import mock

import pytest

from pitloom.extract._interrupt_hold import HOLD_LIMIT
from pitloom.extract.ai_model import _stderr_capture as sc
from tests._interrupt import run_interrupted, statement_lines


def _block() -> None:
    with sc.capture_stderr():
        pass


_ENTRY = statement_lines(sc.capture_stderr, "sink = ", "yield sink")
_UNDO = statement_lines(sc._undo, "if proxy.sinks.get", "sys.stderr = ")


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("step", ["entry", "undo"])
def test_an_interrupt_at_any_step_leaves_stderr_as_found(
    step: str, nested: bool
) -> None:
    target = _ENTRY if step == "entry" else _UNDO
    original = io.StringIO()
    steps = 0
    with mock.patch.object(sys, "stderr", original):
        with contextlib.ExitStack() as stack:
            outer = stack.enter_context(sc.capture_stderr()) if nested else None
            for n in range(1, 40):
                if not run_interrupted(_block, target, n):
                    break
                steps += 1
                sys.stderr.write(f"later{n};")
                # The thread's own sink again, or the stream found.
                assert (sc._STATE.users, sys.stderr is original) == (
                    (1, False) if nested else (0, True)
                ), f"{step} {n}"
                reached = outer.text() if outer is not None else original.getvalue()
                assert f"later{n};" in reached, f"{step} {n}"
        assert sys.stderr is original
    assert steps >= 4  # the injection reached the statements it names
    assert sc._STATE.users == 0


class _Unreleased:
    """A lock that is taken once, then interrupted whenever it is taken: as
    one left held for good by an interrupt, whose waiter keeps being
    interrupted. Past *limit* takes, the wait is evidently unbounded."""

    def __init__(self, limit: int) -> None:
        self.takes = 0
        self.limit = limit

    def acquire(self, timeout: float = -1) -> bool:
        self.takes += 1
        if self.takes == 1:
            return True
        if self.takes > self.limit:
            raise RuntimeError("an interrupt held for ever")
        raise KeyboardInterrupt

    def release(self) -> None:
        """Nothing to give back."""


def test_a_second_interrupt_in_the_undo_is_held_for_a_few_tries() -> None:
    real = sc._LOCK

    class _Flaky:
        """The lock, interrupted on its second use: the undo's first try."""

        def __init__(self) -> None:
            self.uses = 0

        def acquire(self, timeout: float = -1) -> bool:
            self.uses += 1
            if self.uses == 2:
                raise KeyboardInterrupt
            return real.acquire(timeout=timeout)

        def release(self) -> None:
            real.release()

    original = io.StringIO()
    flaky = _Flaky()
    with (
        mock.patch.object(sys, "stderr", original),
        mock.patch.object(sc, "_LOCK", flaky),
    ):
        with pytest.raises(KeyboardInterrupt):
            _block()
        assert flaky.uses == 3  # entry, the interrupted undo, the undo
        assert sys.stderr is original
    assert sc._STATE.users == 0


def test_interrupts_the_undo_cannot_outlast_are_raised_within_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lock left held by an interrupt (as CPython 3.14 can) is never
    released: the undo must give up, not retry every interrupt for ever. The
    state it could not undo is left, so the test uses a state of its own."""
    unreleased = _Unreleased(limit=100)
    monkeypatch.setattr(sc, "_STATE", sc._State())
    monkeypatch.setattr(sc, "_LOCK", unreleased)
    with mock.patch.object(sys, "stderr", io.StringIO()):
        with pytest.raises(KeyboardInterrupt):
            _block()
    assert unreleased.takes == 1 + HOLD_LIMIT  # the entry, then the tries


def test_the_undo_removes_only_its_own_sink() -> None:
    sink = sc.BoundedStderr()
    sc._leave(None, 1, sink, None)  # nothing was entered
    with sc.capture_stderr():
        proxy = sc._STATE.proxy
        sc._leave(proxy, threading.get_ident(), sink, None)  # not registered
        assert sc._STATE.users == 1
        assert sys.stderr is proxy
    assert sc._STATE.users == 0
