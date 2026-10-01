# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``KeyboardInterrupt`` at any step of a reader-log capture block leaves
the readers' logger as found, and the enclosing capture of a nested block
intact.

See also: :mod:`tests.extract.test_reader_log`,
:mod:`tests.extract.ai_model.test_stderr_capture_interrupt`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import contextlib
import logging

import pytest

from pitloom.extract import _reader_log as rl
from tests._interrupt import run_interrupted, statement_lines

_LOGGER = logging.getLogger("pitloom.extract.ai_model")
_ENTRY = statement_lines(rl._enter, "if not _STATE.installed", "_STATE.dispatcher")
_UNDO = statement_lines(rl._undo, "if captures.get", "_STATE.installed = False")


def _block() -> None:
    with rl.capture_reader_logs():
        pass


@pytest.mark.parametrize("propagate", [True, False])
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("step", ["entry", "undo"])
def test_an_interrupt_at_any_step_leaves_the_logger_as_found(
    step: str, nested: bool, propagate: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _ENTRY if step == "entry" else _UNDO
    monkeypatch.setattr(_LOGGER, "propagate", propagate)
    handlers = list(_LOGGER.handlers)
    steps = 0
    with contextlib.ExitStack() as stack:
        outer = stack.enter_context(rl.capture_reader_logs()) if nested else []
        # An interrupt may only undo this block: an enclosing one survives.
        inside = list(_LOGGER.handlers)
        for n in range(1, 40):
            if not run_interrupted(_block, target, n):
                break
            steps += 1
            assert list(_LOGGER.handlers) == inside, f"{step} {n}"
            logging.getLogger("pitloom.extract.ai_model.x").warning("kept %d", n)
        if nested:
            assert [r.getMessage() for r in outer] == [
                f"kept {n}" for n in range(1, steps + 1)
            ]
    assert steps >= 3  # the injection reached the statements it names
    assert (_LOGGER.propagate, list(_LOGGER.handlers)) == (propagate, handlers)
    assert not rl._STATE.dispatcher.captures
    assert not rl._STATE.installed


def test_a_second_interrupt_in_the_undo_is_held_until_it_has_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    undo = rl._undo
    calls: list[int] = []

    def flaky(block: rl._Block) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise KeyboardInterrupt
        undo(block)

    monkeypatch.setattr(rl, "_undo", flaky)
    handlers = list(_LOGGER.handlers)
    with pytest.raises(KeyboardInterrupt):
        _block()
    assert len(calls) == 2
    assert list(_LOGGER.handlers) == handlers
    assert not rl._STATE.installed


def test_the_undo_is_idempotent() -> None:
    block = rl._Block()
    rl._enter(block)
    rl._undo(block)
    rl._undo(block)  # a retry after a partial undo
    assert not rl._STATE.installed
    assert not rl._STATE.dispatcher.captures
