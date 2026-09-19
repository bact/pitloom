# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pitloom.core.build_signals``: ``TerminationGuard``
(SIGTERM/SIGHUP/SIGBREAK handling around a build-and-read).

A signal is simulated by calling the installed handler directly, as the
interpreter would between two bytecodes, so no test depends on timing and
a regression never kills the test process: ``signal.raise_signal`` is
always a spy here. Returning, it behaves as for PID 1 in a container, so
the guard ends in its ``SystemExit(128 + signum)`` fallback.

See also: tests/core/models_wheel/test_models_wheel_build_subprocess.py
(the wait loop that polls the guard),
tests/core/models_wheel/test_models_wheel_build_and_read_cleanup.py
(signals during the build's own cleanup),
tests/assemble/test_build_termination.py (every caller holding a
build-and-read result) and
tests/core/models_wheel/test_models_wheel_build_subprocess_e2e.py (a real
SIGTERM/SIGHUP to a process running a build).
"""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable, Iterator
from types import FrameType
from unittest import mock

import pytest

from pitloom.core import build_signals
from pitloom.core.build_signals import TerminationGuard, TerminationSignal
from tests.build_and_read_shared import spied_raise_signal

_Handler = Callable[[int, FrameType | None], object]


@pytest.fixture(name="raise_spy")
def fixture_raise_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[mock.Mock]:
    with spied_raise_signal(monkeypatch) as spy:
        yield spy


def _current_handler() -> _Handler:
    handler = signal.getsignal(signal.SIGTERM)
    assert callable(handler), "no SIGTERM handler installed"
    return handler


@pytest.mark.usefixtures("raise_spy")
def test_nothing_installed_without_a_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run that never builds (Hatchling hook, static discovery) must not
    touch signal handling at all."""
    spy = mock.Mock(wraps=signal.signal)
    monkeypatch.setattr(signal, "signal", spy)
    cleanup = mock.Mock()
    with TerminationGuard() as guard:
        guard.add_cleanup(cleanup)
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    spy.assert_not_called()
    cleanup.assert_not_called()


def test_hold_records_without_raising(raise_spy: mock.Mock) -> None:
    with TerminationGuard() as guard, guard.hold():
        handler = _current_handler()
        # Never raises: a signal must not abort whatever runs in a hold.
        handler(signal.SIGTERM, None)
        handler(signal.SIGTERM, None)
        assert guard.pending == signal.SIGTERM
        with pytest.raises(TerminationSignal) as excinfo:
            guard.raise_if_pending()
        assert excinfo.value.signum == signal.SIGTERM
        guard.pending = None  # as if never received
    raise_spy.assert_not_called()
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_signal_in_hold_terminates_on_leaving_it_after_cleanups(
    raise_spy: mock.Mock, caplog: pytest.LogCaptureFixture
) -> None:
    events: list[tuple[str, object]] = []
    raise_spy.side_effect = lambda signum: events.append(
        ("raise", signal.getsignal(signum))
    )
    handlers: list[_Handler] = []
    with pytest.raises(SystemExit) as excinfo:
        with TerminationGuard() as guard, guard.hold():
            handlers.append(_current_handler())
            guard.add_cleanup(
                lambda: events.append(("cleanup", signal.getsignal(signal.SIGTERM)))
            )
            handlers[0](signal.SIGTERM, None)
            events.append(("hold still running", None))
    raise_spy.assert_called_once_with(signal.SIGTERM)
    # Cleanup while still handled (a second signal is held), re-raise after.
    assert events == [
        ("hold still running", None),
        ("cleanup", handlers[0]),
        ("raise", signal.SIG_DFL),
    ]
    assert excinfo.value.code == 128 + signal.SIGTERM
    assert "Build: received SIGTERM during the build" in caplog.text


def test_pending_signal_wins_over_exception_in_flight(raise_spy: mock.Mock) -> None:
    with pytest.raises(SystemExit) as excinfo:
        with TerminationGuard() as guard, guard.hold():
            _current_handler()(signal.SIGTERM, None)
            guard.raise_if_pending()
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert excinfo.value.code == 128 + signal.SIGTERM


def test_signal_outside_a_hold_terminates_in_the_handler(
    raise_spy: mock.Mock, caplog: pytest.LogCaptureFixture
) -> None:
    """After the build (hashing, AI-model scanning), a signal must not wait
    for the guarded block to end: the handler itself cleans up and ends
    the process."""
    events: list[tuple[str, object]] = []
    raise_spy.side_effect = lambda signum: events.append(
        ("raise", signal.getsignal(signum))
    )

    def cleanup() -> None:
        # A repeat while the first one is handled changes nothing.
        handler(signal.SIGTERM, None)
        events.append(("cleanup", None))

    with TerminationGuard() as guard:
        with guard.hold():
            handler = _current_handler()
        guard.add_cleanup(cleanup)
        with pytest.raises(SystemExit) as excinfo:
            handler(signal.SIGTERM, None)
    assert events == [("cleanup", None), ("raise", signal.SIG_DFL)]
    assert excinfo.value.code == 128 + signal.SIGTERM
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert "Build: received SIGTERM after the build" in caplog.text


def test_interrupt_in_a_termination_cleanup_is_finished_by_the_owner(
    raise_spy: mock.Mock,
) -> None:
    """Ctrl-C while the handler runs the cleanups: the handlers must not
    stay installed (they would swallow every later SIGTERM), and the
    owner's exit finishes the cleanup and the termination."""
    seen_by_cleanup: list[object] = []
    after_interrupt: list[object] = []

    def cleanup() -> None:
        seen_by_cleanup.append(signal.getsignal(signal.SIGTERM))
        if len(seen_by_cleanup) == 1:
            raise KeyboardInterrupt

    # Caught broadly: a KeyboardInterrupt escaping would end the session.
    outcome: BaseException | None = None
    try:
        with TerminationGuard() as guard:
            with guard.hold():
                handler = _current_handler()
            guard.add_cleanup(cleanup)
            try:
                handler(signal.SIGTERM, None)
            except KeyboardInterrupt:
                after_interrupt.append(signal.getsignal(signal.SIGTERM))
                raise
    # pylint: disable-next=broad-exception-caught
    except BaseException as exc:
        outcome = exc
    assert after_interrupt == [signal.SIG_DFL]
    # First run by the (still installed) handler, then by the owner's exit.
    assert len(seen_by_cleanup) == 2 and callable(seen_by_cleanup[0])
    assert seen_by_cleanup[1] == signal.SIG_DFL
    assert isinstance(outcome, SystemExit)
    assert getattr(outcome, "code", None) == 128 + signal.SIGTERM
    raise_spy.assert_called_once_with(signal.SIGTERM)


@pytest.mark.usefixtures("raise_spy")
def test_cleanups_run_when_the_block_ends_by_an_exception() -> None:
    cleanup = mock.Mock()
    with pytest.raises(KeyboardInterrupt):
        with TerminationGuard() as guard:
            guard.add_cleanup(cleanup)
            raise KeyboardInterrupt
    cleanup.assert_called_once_with()


def test_cleanups_dropped_on_normal_exit(raise_spy: mock.Mock) -> None:
    cleanup = mock.Mock()
    with TerminationGuard() as guard, guard.hold():
        guard.add_cleanup(cleanup)
    cleanup.assert_not_called()
    raise_spy.assert_not_called()


@pytest.mark.usefixtures("raise_spy")
def test_nested_guard_joins_the_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the outermost guard installs and restores the handlers and
    acts on an exception; a nested one (build_and_read_wheel's inside a
    caller's) yields the owner and does nothing on its own exit."""
    spy = mock.Mock(wraps=signal.signal)
    monkeypatch.setattr(signal, "signal", spy)
    cleanup = mock.Mock()
    with TerminationGuard() as owner:
        with TerminationGuard() as nested, nested.hold():
            assert nested is owner
            nested.add_cleanup(cleanup)
        # Still installed after the nested exit; its cleanup not run yet.
        handler = _current_handler()
        with pytest.raises(KeyboardInterrupt):
            with TerminationGuard():
                raise KeyboardInterrupt
        cleanup.assert_not_called()
        with owner.hold():
            pass
    installs = [c for c in spy.call_args_list if c.args[1] is not signal.SIG_DFL]
    restores = [c for c in spy.call_args_list if c.args[1] is signal.SIG_DFL]
    assert installs and {c.args[1] for c in installs} == {handler}
    assert sorted(c.args[0] for c in restores) == sorted(c.args[0] for c in installs)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    cleanup.assert_not_called()


def test_signal_while_installing_handlers(
    raise_spy: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A signal once the SIGTERM handler is installed, while the next one
    is looked up, must neither escape as a bare exception nor leave the
    handler installed."""
    real_getsignal = signal.getsignal
    fired: list[bool] = []

    def getsignal(signum: int) -> object:
        current = real_getsignal(signal.SIGTERM)
        if signum != signal.SIGTERM and callable(current) and not fired:
            fired.append(True)
            current(signal.SIGTERM, None)
        return real_getsignal(signum)

    monkeypatch.setattr(signal, "getsignal", getsignal)
    with pytest.raises(SystemExit) as excinfo:
        with TerminationGuard() as guard, guard.hold():
            pass
    assert fired, "no second termination signal to look up"
    assert excinfo.value.code == 128 + signal.SIGTERM
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert real_getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_interrupt_while_installing_restores_handlers(
    raise_spy: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_signal = signal.signal

    def interrupted_signal(signum: int, handler: object) -> object:
        previous = real_signal(signum, handler)  # type: ignore[arg-type]
        if handler is not signal.SIG_DFL:
            raise KeyboardInterrupt
        return previous

    monkeypatch.setattr(signal, "signal", interrupted_signal)
    with pytest.raises(KeyboardInterrupt):
        with TerminationGuard() as guard, guard.hold():
            pytest.fail("entered")
    raise_spy.assert_not_called()
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_handler_after_the_block_does_not_swallow(raise_spy: mock.Mock) -> None:
    """A handler left installed after the block (its restore failed)
    behaves as SIG_DFL would."""
    with TerminationGuard() as guard, guard.hold():
        handler = _current_handler()
    signal.signal(signal.SIGTERM, handler)
    handler(signal.SIGTERM, None)
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_failing_warning_does_not_stop_termination(
    raise_spy: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run from the handler, the WARNING: may hit a stream write the
    signal interrupted (``RuntimeError: reentrant call``); the process
    must still end by the signal."""
    warning = mock.Mock(side_effect=RuntimeError("reentrant call"))
    monkeypatch.setattr(build_signals.log, "warning", warning)
    with TerminationGuard() as guard:
        with guard.hold():
            handler = _current_handler()
        with pytest.raises(SystemExit):
            handler(signal.SIGTERM, None)
    warning.assert_called_once()
    raise_spy.assert_called_once_with(signal.SIGTERM)


@pytest.mark.usefixtures("raise_spy")
def test_restore_keeps_a_handler_installed_meanwhile() -> None:
    """A handler other code installs while the guard is active replaced
    ours on purpose: the guard's exit must not reset it to SIG_DFL."""

    def third_party(signum: int, frame: object) -> None:
        del signum, frame

    with TerminationGuard() as guard, guard.hold():
        signal.signal(signal.SIGTERM, third_party)
    assert signal.getsignal(signal.SIGTERM) is third_party


def test_guard_can_be_entered_again(raise_spy: mock.Mock) -> None:
    """The owner's exit resets the guard: after a termination that did not
    end the process (its SystemExit fallback caught), a second block
    installs the handlers again, handles a new signal, and runs only its
    own cleanups."""
    guard = TerminationGuard()
    cleanups = [mock.Mock(), mock.Mock()]
    for cleanup in cleanups:
        with pytest.raises(SystemExit), guard as owner:
            with owner.hold():
                handler = _current_handler()
            owner.add_cleanup(cleanup)
            handler(signal.SIGTERM, None)
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    for cleanup in cleanups:
        cleanup.assert_called_once_with()
    assert raise_spy.call_count == 2


@pytest.mark.usefixtures("raise_spy")
def test_entering_an_entered_guard_raises() -> None:
    """A nested exit of the same guard would end the outer block's
    protection early."""
    with TerminationGuard() as guard:
        with pytest.raises(RuntimeError, match="already entered"), guard:
            pytest.fail("entered twice")
    # The failed entry left the owner intact: its exit released it.
    fresh = TerminationGuard()
    with fresh as owner:
        assert owner is fresh


@pytest.mark.usefixtures("raise_spy")
def test_handler_keeps_host_handler() -> None:
    def host_handler(signum: int, frame: object) -> None:
        del signum, frame

    signal.signal(signal.SIGTERM, host_handler)
    with TerminationGuard() as guard, guard.hold():
        assert signal.getsignal(signal.SIGTERM) is host_handler
    assert signal.getsignal(signal.SIGTERM) is host_handler


@pytest.mark.usefixtures("raise_spy")
def test_other_threads_neither_install_nor_join_the_main_owner() -> None:
    seen: list[object] = []

    def worker() -> None:
        with TerminationGuard() as guard, guard.hold():
            seen.append(guard)
            seen.append(signal.getsignal(signal.SIGTERM))

    with TerminationGuard() as owner:
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
    assert seen[0] is not owner
    assert seen[1] == signal.SIG_DFL


@pytest.mark.usefixtures("raise_spy")
def test_sigbreak_handled_when_the_platform_has_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ctrl-Break (Windows SIGBREAK); elsewhere SIGUSR1 stands in for it."""
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is None:
        sigbreak = signal.Signals(signal.SIGUSR1)  # pylint: disable=no-member
        monkeypatch.setattr(signal, "SIGBREAK", sigbreak, raising=False)
    previous = signal.signal(sigbreak, signal.SIG_DFL)
    try:
        with TerminationGuard() as guard, guard.hold():
            handler = signal.getsignal(sigbreak)
            assert callable(handler)
            handler(sigbreak, None)
            assert guard.pending == sigbreak
            guard.pending = None
        assert signal.getsignal(sigbreak) == signal.SIG_DFL
    finally:
        signal.signal(sigbreak, previous)


def test_termination_signal_is_not_an_exception() -> None:
    # A broad "except Exception" fallback must not swallow it.
    assert not issubclass(TerminationSignal, Exception)
