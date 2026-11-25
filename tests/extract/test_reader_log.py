# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``capture_reader_logs`` when several threads capture at once: each gets
only its own records, a thread not capturing is passed on as usual, and the
logger's state is restored whatever order the blocks end in.

See also: :mod:`tests.extract.scanner.test_scanner_reader_logs`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest

from pitloom.extract import _reader_log
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


@pytest.mark.uncoded_output(r"^WARNING: from [AB]$")
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


@pytest.mark.uncoded_output(r"^WARNING: from A$", r"^WARNING: from the main thread$")
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


@pytest.mark.uncoded_output(r"^WARNING: from the main thread$")
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


@pytest.mark.uncoded_output(r"^WARNING: (before|inside|after)$")
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


@pytest.mark.uncoded_output(r"^WARNING: no thread id$")
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


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.said: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.said.append(record.getMessage())


_VALUES = "pitloom.extract.dataset.values"


@pytest.mark.uncoded_output(
    r"^WARNING: a value check, not captured$", r"^WARNING: a child, not captured$"
)
def test_a_non_capturing_record_goes_on_through_its_own_captured_logger() -> None:
    """A dataset value check's record goes on to that logger's parent, not
    to the readers' parent: a handler on ``pitloom.extract.dataset`` gets
    it, one on ``pitloom.extract.ai_model``'s parent only once."""
    dataset, extract = _Collect(), _Collect()
    logging.getLogger("pitloom.extract.dataset").addHandler(dataset)
    logging.getLogger("pitloom.extract").addHandler(extract)
    a = _Worker("A")
    a.start()
    try:
        a.step("enter")
        logging.getLogger(_VALUES).warning("a value check, not captured")
        logging.getLogger(f"{_VALUES}.sub").warning("a child, not captured")
        a.step("exit")
    finally:
        logging.getLogger("pitloom.extract.dataset").removeHandler(dataset)
        logging.getLogger("pitloom.extract").removeHandler(extract)
    said = ["a value check, not captured", "a child, not captured"]
    assert dataset.said == said
    assert extract.said == said  # through the dataset logger, once each
    assert a.tags() == []


@pytest.mark.uncoded_output(r"^WARNING: captured$")
@pytest.mark.parametrize("propagate", [True, False])
def test_every_captured_logger_is_restored(
    propagate: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    loggers = [_LOGGER, logging.getLogger(_VALUES)]
    for logger in loggers:
        monkeypatch.setattr(logger, "propagate", propagate)
    before = [(lg.propagate, list(lg.handlers)) for lg in loggers]
    with capture_reader_logs() as records:
        assert [lg.propagate for lg in loggers] == [False, False]  # changed
        logging.getLogger(_VALUES).warning("captured")
    assert [r.getMessage() for r in records] == ["captured"]
    assert [(lg.propagate, list(lg.handlers)) for lg in loggers] == before


@pytest.mark.parametrize(
    ("name", "home"),
    [
        ("pitloom.extract.ai_model", "pitloom.extract.ai_model"),
        ("pitloom.extract.ai_model.gguf", "pitloom.extract.ai_model"),
        ("pitloom.extract.dataset.values", "pitloom.extract.dataset.values"),
        # Not a child: a name that only shares the spelling's start.
        ("pitloom.extract.ai_modelx", "pitloom.extract.ai_model"),
        ("pitloom.extract.dataset.valuesx", "pitloom.extract.ai_model"),
        ("elsewhere", "pitloom.extract.ai_model"),
    ],
    ids=["readers", "reader-child", "values", "prefix-only", "values-prefix", "other"],
)
def test_a_record_is_passed_on_through_its_captured_logger(
    name: str, home: str
) -> None:
    assert _reader_log._home(name) == home
