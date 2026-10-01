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

import io
import sys
import threading
from typing import Any
from unittest import mock

import pytest

from pitloom.extract.ai_model import _stderr_capture as sc
from tests._interrupt import run_interrupted, statement_lines


def _block() -> None:
    with sc.capture_stderr():
        pass


_ENTRY = statement_lines(sc.capture_stderr, "sink = ", "yield sink")
_UNDO = statement_lines(sc._leave, "if proxy.sinks.get", "break")


@pytest.mark.parametrize("step", ["entry", "undo"])
def test_an_interrupt_at_any_step_leaves_stderr_as_found(step: str) -> None:
    target = _ENTRY if step == "entry" else _UNDO
    original = io.StringIO()
    steps = 0
    with mock.patch.object(sys, "stderr", original):
        for n in range(1, 40):
            if not run_interrupted(_block, target, n):
                break
            steps += 1
            assert sys.stderr is original, f"{step} {n}"
            sys.stderr.write(f"later{n};")
            assert sc._STATE.users == 0, f"{step} {n}"
            assert f"later{n};" in original.getvalue(), f"{step} {n}"
    assert steps >= 5  # the injection reached the statements it names


def test_a_second_interrupt_in_the_undo_is_held_until_it_has_run() -> None:
    real = sc._LOCK

    class _Flaky:
        """The lock, interrupted on its second use: the undo's first try."""

        def __init__(self) -> None:
            self.uses = 0

        def __enter__(self) -> bool:
            self.uses += 1
            if self.uses == 2:
                raise KeyboardInterrupt
            return real.__enter__()

        def __exit__(self, *exc: Any) -> None:
            real.__exit__(*exc)

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


def test_the_undo_removes_only_its_own_sink() -> None:
    sink = sc.BoundedStderr()
    sc._leave(None, 1, sink, None)  # nothing was entered
    with sc.capture_stderr():
        proxy = sc._STATE.proxy
        sc._leave(proxy, threading.get_ident(), sink, None)  # not registered
        assert sc._STATE.users == 1
        assert sys.stderr is proxy
    assert sc._STATE.users == 0
