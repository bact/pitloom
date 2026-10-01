# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Per-thread capture of what a parser writes to ``sys.stderr``: the sink's
bound, routing by thread, and leaving ``sys.stderr`` as it was found however
the blocks of several threads overlap.

See also: :mod:`tests.extract.ai_model.test_model_bounds` (fickling's stderr
as a warning).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import io
import sys
import threading
from types import SimpleNamespace
from unittest import mock

import pytest

from pitloom.extract.ai_model import pytorch
from pitloom.extract.ai_model._stderr_capture import (
    _STATE,
    BoundedStderr,
    capture_stderr,
)

_WAIT = 10  # seconds; a hang fails the test instead of the run


def test_the_sink_keeps_the_first_4096_characters_and_is_writable() -> None:
    sink = BoundedStderr()
    assert sink.writable()
    assert [sink.write("a" * 3000), sink.write("b" * 3000), sink.write("c")] == [
        3000,
        3000,
        1,
    ]
    assert sink.text() == "a" * 3000 + "b" * 1096


def test_a_block_captures_its_own_thread_and_restores_stderr() -> None:
    before = sys.stderr
    with capture_stderr() as sink:
        assert sys.stderr is not before
        sys.stderr.write("held")
        sys.stderr.flush()  # the sink's own: nothing reaches the real stream
        assert sys.stderr.encoding == before.encoding  # anything else passes on
    assert sys.stderr is before
    assert sink.text() == "held"
    assert _STATE.users == 0


def test_another_thread_is_not_captured(capsys: pytest.CaptureFixture[str]) -> None:
    def other() -> None:
        sys.stderr.write("from-other")
        sys.stderr.flush()

    with capture_stderr() as sink:
        thread = threading.Thread(target=other)
        thread.start()
        thread.join(_WAIT)
    assert sink.text() == ""
    assert "from-other" in capsys.readouterr().err


def test_a_nested_block_hands_back_to_the_outer_one() -> None:
    with capture_stderr() as outer:
        sys.stderr.write("1")
        with capture_stderr() as inner:
            sys.stderr.write("2")
        sys.stderr.write("3")
    assert (outer.text(), inner.text()) == ("13", "2")


def test_a_stderr_replaced_meanwhile_is_left_alone() -> None:
    before = sys.stderr
    other = io.StringIO()
    try:
        with capture_stderr():
            sys.stderr = other
        assert sys.stderr is other  # not put back over the other party's
    finally:
        sys.stderr = before
    assert _STATE.users == 0


def test_a_write_of_lines_is_captured_like_a_write() -> None:
    before = io.StringIO()
    kept: list[str] = []
    held, release = threading.Event(), threading.Event()

    def capturing() -> None:
        with capture_stderr() as sink:
            sys.stderr.writelines(["a", "b"])
            held.set()
            assert release.wait(_WAIT)
        kept.append(sink.text())

    with mock.patch.object(sys, "stderr", before):
        thread = threading.Thread(target=capturing)
        thread.start()
        assert held.wait(_WAIT)
        sys.stderr.writelines(["c"])  # the proxy is installed; not this thread's
        release.set()
        thread.join(_WAIT)
    assert (kept, before.getvalue()) == (["ab"], "c")


def test_a_block_entered_after_stderr_was_replaced_still_captures() -> None:
    """Thread A captures and someone else replaces ``sys.stderr``; thread B
    then enters: it needs a proxy of its own, though A's still has sinks."""
    base, other = io.StringIO(), io.StringIO()
    kept: list[str] = []

    def second() -> None:
        with capture_stderr() as sink:
            sys.stderr.write("b")
        kept.append(sink.text())

    with mock.patch.object(sys, "stderr", base):
        with capture_stderr():
            sys.stderr = other
            thread = threading.Thread(target=second)
            thread.start()
            thread.join(_WAIT)
            sys.stderr = base  # theirs to restore; here, for the proxy to leave
    assert (kept, other.getvalue()) == (["b"], "")


def test_without_a_stderr_attribute_access_is_answered_by_a_null_stream() -> None:
    with mock.patch.object(sys, "stderr", None):
        with capture_stderr():
            assert sys.stderr.isatty() is False
            assert sys.stderr.encoding is None  # the null stream's


def test_without_a_stderr_other_threads_write_nothing_and_do_not_fail() -> None:
    """``sys.stderr`` is ``None`` under ``pythonw``: a thread that is not
    capturing used to get an ``AttributeError`` while another captured."""
    errors: list[BaseException] = []

    def other() -> None:
        try:
            assert sys.stderr.write("x") == 1
            sys.stderr.writelines(["y"])
            sys.stderr.flush()
        except BaseException as exc:  # pylint: disable=broad-exception-caught
            errors.append(exc)

    with mock.patch.object(sys, "stderr", None):
        with capture_stderr() as sink:
            sys.stderr.write("held")
            sys.stderr.flush()
            thread = threading.Thread(target=other)
            thread.start()
            thread.join(_WAIT)
        assert sys.stderr is None
    assert (errors, sink.text()) == ([], "held")


def _fake_fickling(
    monkeypatch: pytest.MonkeyPatch, gate: dict[str, threading.Event]
) -> None:
    """A ``Pickled`` whose ``load`` writes its thread's name to stderr, then
    waits for that thread's gate."""
    fickle = pytest.importorskip("fickling.fickle")

    def load(_data: object) -> SimpleNamespace:
        name = threading.current_thread().name
        sys.stderr.write(f"noise-{name}")
        gate[f"in-{name}"].set()
        assert gate[f"go-{name}"].wait(_WAIT)
        return SimpleNamespace(ast=None)

    monkeypatch.setattr(fickle, "Pickled", SimpleNamespace(load=load))
    monkeypatch.setattr(pytorch, "_top_class", lambda _pkl: None)


def test_two_overlapping_threads_leave_stderr_as_found(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression: with ``redirect_stderr``, thread A leaving before thread B
    left the process with A's sink as ``sys.stderr`` for good."""
    gate = {f"{k}-{n}": threading.Event() for k in ("in", "go") for n in "AB"}
    _fake_fickling(monkeypatch, gate)
    before = sys.stderr
    pickle = b"\x80\x02N."

    def run() -> None:
        pytorch._fickling_get_top_class(io.BytesIO(pickle))

    threads = {n: threading.Thread(target=run, name=n) for n in "AB"}
    for name in "AB":
        threads[name].start()
        assert gate[f"in-{name}"].wait(_WAIT)
    sys.stderr.write("from-main")  # neither thread's
    for name in "AB":  # A leaves first
        gate[f"go-{name}"].set()
        threads[name].join(_WAIT)
        assert not threads[name].is_alive()
    assert sys.stderr is before
    assert "from-main" in capsys.readouterr().err
    messages = sorted(r.getMessage() for r in caplog.records)
    assert [m for m in messages if "noise-A" in m and "noise-B" not in m]
    assert [m for m in messages if "noise-B" in m and "noise-A" not in m]
