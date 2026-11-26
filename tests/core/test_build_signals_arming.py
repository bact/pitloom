# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pitloom.core.build_signals.TerminationGuard``: when a held
signal ends the process (the outermost hold's exit), which guard installs
the handlers (the entered owner, at its first hold, each signal on its own)
and the order and reuse of its cleanups.

A signal is simulated by calling the installed handler directly, and
``signal.raise_signal`` is a spy, as in test_build_signals.py.

See also: tests/core/test_build_signals.py (the guard's other rules;
these tests were split from it).
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Iterator
from types import FrameType
from unittest import mock

import pytest

from pitloom.core import build_signals
from pitloom.core.build_signals import (
    BUILD_ACTIVITY,
    MODEL_SCAN_ACTIVITY,
    TerminationGuard,
)
from pitloom.messages.build import TERMINATION_SIGNALS
from tests.build_and_read_shared import deliver_sigterm, spied_raise_signal


@pytest.fixture(name="raise_spy")
def fixture_raise_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[mock.Mock]:
    with spied_raise_signal(monkeypatch) as spy:
        yield spy


def test_a_signal_in_a_hold_ends_the_process_at_the_hold_exit(
    raise_spy: mock.Mock,
) -> None:
    """The hold finishes; the owner's block after it never runs."""
    events: list[str] = []
    with pytest.raises(SystemExit) as excinfo:
        with TerminationGuard() as guard:
            with guard.hold(BUILD_ACTIVITY):
                deliver_sigterm()
                events.append("hold still running")
            events.append("after the hold")
    assert events == ["hold still running"]
    assert excinfo.value.code == 128 + signal.SIGTERM
    raise_spy.assert_called_once_with(signal.SIGTERM)


def test_a_signal_in_a_nested_hold_waits_for_the_outer_hold(
    raise_spy: mock.Mock,
) -> None:
    """Leaving the inner hold must not cut the outer one short."""
    events: list[str] = []
    with pytest.raises(SystemExit):
        with TerminationGuard() as guard, guard.hold(BUILD_ACTIVITY):
            with guard.hold(MODEL_SCAN_ACTIVITY):
                deliver_sigterm()
            events.append("outer hold still running")
            raise_spy.assert_not_called()
    assert events == ["outer hold still running"]
    raise_spy.assert_called_once_with(signal.SIGTERM)


@pytest.mark.usefixtures("raise_spy")
def test_a_guard_not_entered_installs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not entered, a guard is the "no signal handling" value."""
    spy = mock.Mock(wraps=signal.signal)
    monkeypatch.setattr(signal, "signal", spy)
    with TerminationGuard().hold(BUILD_ACTIVITY):
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    spy.assert_not_called()


@pytest.mark.usefixtures("raise_spy")
def test_only_the_first_hold_installs() -> None:
    """A handler other code puts back after the first hold stays."""
    with TerminationGuard() as guard:
        with guard.hold(BUILD_ACTIVITY):
            assert callable(signal.getsignal(signal.SIGTERM))
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        with guard.hold(BUILD_ACTIVITY):
            assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


@pytest.mark.usefixtures("raise_spy")
def test_other_threads_neither_install_nor_join_the_main_owner(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Off the main thread ``signal.signal()`` raises ``ValueError``: a
    guard there is its own owner, installs nothing, and says so at DEBUG
    once per signal it would handle."""
    caplog.set_level(logging.DEBUG, logger=build_signals.__name__)
    seen: list[object] = []

    def worker() -> None:
        with TerminationGuard() as guard, guard.hold(BUILD_ACTIVITY):
            seen.append(guard)
            seen.append(signal.getsignal(signal.SIGTERM))

    with TerminationGuard() as owner:
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
    assert seen[0] is not owner
    assert seen[1] == signal.SIG_DFL
    debug = [
        r
        for r in caplog.records
        if r.name == build_signals.__name__ and r.levelno == logging.DEBUG
    ]
    assert len(debug) == sum(hasattr(signal, n) for n in TERMINATION_SIGNALS)


@pytest.mark.usefixtures("raise_spy")
def test_cleanups_run_newest_first_when_the_block_ends_by_an_exception() -> None:
    calls: list[str] = []
    with pytest.raises(KeyboardInterrupt):
        with TerminationGuard() as guard:
            guard.add_cleanup(lambda: calls.append("older"))
            guard.add_cleanup(lambda: calls.append("newer"))
            raise KeyboardInterrupt
    assert calls == ["newer", "older"]


@pytest.mark.usefixtures("raise_spy")
def test_handler_keeps_host_handler() -> None:
    """A host's own SIGTERM handler is left alone, during and after;
    SIGHUP (POSIX) or SIGBREAK (Windows) is still handled, then restored."""
    other = next(
        getattr(signal, name)
        for name in ("SIGHUP", "SIGBREAK")
        if hasattr(signal, name)
    )

    def host_handler(signum: int, frame: FrameType | None) -> None:
        del signum, frame

    signal.signal(signal.SIGTERM, host_handler)
    with TerminationGuard() as guard, guard.hold(BUILD_ACTIVITY):
        assert signal.getsignal(signal.SIGTERM) is host_handler
        installed = signal.getsignal(other)
        assert callable(installed)
        assert installed is not host_handler
    assert signal.getsignal(signal.SIGTERM) is host_handler
    assert signal.getsignal(other) == signal.SIG_DFL


@pytest.mark.usefixtures("raise_spy")
def test_a_reused_guard_still_runs_cleanups_on_an_exception() -> None:
    """The owner's exit resets the guard: a second block ending by an
    exception runs its cleanups as the first would."""
    guard = TerminationGuard()
    with guard:
        pass
    cleanup = mock.Mock()
    with pytest.raises(KeyboardInterrupt):
        with guard as owner:
            owner.add_cleanup(cleanup)
            raise KeyboardInterrupt
    cleanup.assert_called_once_with()
