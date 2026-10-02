# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``capture_reader_logs`` when several threads capture at once: each gets
only its own records, a thread not capturing is passed on as usual, and the
logger's state is restored whatever order the blocks end in.

See also: :mod:`tests.extract.scanner.test_scanner_reader_logs`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest

from pitloom.extract._reader_log import capture_reader_logs

_NAME = "pitloom.extract.ai_model.fake"
_LOGGER = logging.getLogger("pitloom.extract.ai_model")


def _state() -> tuple[bool, list[logging.Handler]]:
    return _LOGGER.propagate, list(_LOGGER.handlers)


class _Worker(threading.Thread):
    """A thread that runs one capture block, step by step on request."""

    def __init__(self, tag: str) -> None:
        super().__init__(daemon=True)
        self.tag = tag
        self.records: list[logging.LogRecord] = []
        self._cm: AbstractContextManager[list[logging.LogRecord]] | None = None
        self._steps: list[Callable[[], None]] = []
        self._go = threading.Semaphore(0)
        self._done = threading.Semaphore(0)

    def step(self, action: str) -> None:
        self._steps.append(
            {"enter": self._enter, "log": self._log}.get(action, self._exit)
        )
        self._go.release()
        # pylint: disable-next=consider-using-with
        assert self._done.acquire(timeout=10)

    def run(self) -> None:
        # pylint: disable-next=consider-using-with
        while self._go.acquire(timeout=10):
            self._steps.pop(0)()
            self._done.release()

    def _enter(self) -> None:
        self._cm = capture_reader_logs()
        # pylint: disable-next=unnecessary-dunder-call
        self.records = self._cm.__enter__()

    def _log(self) -> None:
        logging.getLogger(_NAME).warning("from %s", self.tag)

    def _exit(self) -> None:
        assert self._cm is not None
        self._cm.__exit__(None, None, None)

    def tags(self) -> list[str]:
        return [r.getMessage() for r in self.records]


@pytest.mark.parametrize("propagate", [True, False])
def test_overlapping_blocks_restore_the_logger_in_any_order(
    propagate: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_LOGGER, "propagate", propagate)
    before = _state()
    a, b = _Worker("A"), _Worker("B")
    a.start()
    b.start()
    a.step("enter")
    b.step("enter")
    a.step("log")
    b.step("log")
    a.step("exit")  # A leaves first: B must still be capturing, unrestored
    assert _LOGGER.propagate is False
    b.step("log")
    b.step("exit")
    a.join(0.1)
    assert _state() == before
    assert a.tags() == ["from A"]
    assert b.tags() == ["from B", "from B"]


def test_a_thread_outside_a_block_is_passed_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    a = _Worker("A")
    a.start()
    a.step("enter")
    logging.getLogger(_NAME).warning("from the main thread")
    a.step("log")
    a.step("exit")
    assert [r.getMessage() for r in caplog.records] == ["from the main thread"]
    assert a.tags() == ["from A"]


def test_a_block_left_by_an_error_restores_the_logger() -> None:
    before = _state()
    with pytest.raises(RuntimeError):
        with capture_reader_logs():
            raise RuntimeError
    assert _state() == before


def test_a_detached_logger_drops_what_a_non_capturing_thread_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no parent to pass on to, the record is dropped, not an error."""
    a = _Worker("A")
    a.start()
    a.step("enter")
    monkeypatch.setattr(_LOGGER, "parent", None)
    logging.getLogger(_NAME).warning("from the main thread")
    a.step("exit")
    assert a.tags() == []


def test_a_nested_block_collects_alone_and_the_outer_one_resumes() -> None:
    before = _state()
    log = logging.getLogger(_NAME)
    with capture_reader_logs() as outer:
        log.warning("before")
        with capture_reader_logs() as inner:
            log.warning("inside")
        log.warning("after")
    assert [r.getMessage() for r in outer] == ["before", "after"]
    assert [r.getMessage() for r in inner] == ["inside"]
    assert _state() == before


def test_a_record_without_a_thread_id_is_captured_by_the_emitting_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``logging.logThreads = False`` leaves ``record.thread`` as ``None``."""
    monkeypatch.setattr(logging, "logThreads", False)
    with capture_reader_logs() as records:
        logging.getLogger(_NAME).warning("no thread id")
    # pylint: disable-next=unbalanced-tuple-unpacking
    (record,) = records
    assert record.thread is None  # the setup took effect
    assert record.getMessage() == "no thread id"
