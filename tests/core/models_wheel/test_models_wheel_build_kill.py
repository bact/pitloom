# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pitloom.core._models_wheel_build_kill``:
``kill_process_tree`` and ``kill_leftover_descendants`` (mocked processes).

See also: tests/core/models_wheel/test_models_wheel_build_subprocess.py
(the module that calls these),
tests/core/models_wheel/test_models_wheel_build_subprocess_e2e.py (real
process trees: a second Ctrl-C during the kill, descendants left by a
finished build, a real SIGTERM/SIGHUP to a process running a real build),
and tests/core/test_build_signals.py
(``TerminationGuard``, SIGTERM/SIGHUP/SIGBREAK handling).
"""

# The private helpers are the unit under test here.
# pylint: disable=protected-access

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core import _models_wheel_build_kill as bk
from pitloom.core import _models_wheel_build_subprocess as bs

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="process groups are POSIX-only"
)


@pytest.fixture(autouse=True, name="fake_waitpid")
def fixture_fake_waitpid(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The fake pgid 4321 must never reach a real ``waitpid()``."""
    waitpid = mock.Mock(side_effect=ChildProcessError())
    monkeypatch.setattr(os, "waitpid", waitpid, raising=False)
    return waitpid


# bk._GROUP_GONE_ERRORS per platform: EPERM means "only zombies left"
# on macOS, a live member this process may not signal elsewhere.
_GONE_DARWIN = (ProcessLookupError, PermissionError)
_GONE_OTHER = (ProcessLookupError,)


def _fake_proc(pid: int = 4321) -> mock.Mock:
    proc: mock.Mock = mock.create_autospec(subprocess.Popen, instance=True)
    proc.pid = pid
    return proc


def test_group_gone_errors_match_the_platform() -> None:
    """EPERM counts as "group gone" on macOS only (see _GONE_DARWIN)."""
    expected = _GONE_DARWIN if sys.platform == "darwin" else _GONE_OTHER
    assert bk._GROUP_GONE_ERRORS == expected


# --- kill_process_tree: POSIX, mocked --------------------------------------


@posix_only
def test_kill_process_tree_posix_signal_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killpg = mock.create_autospec(
        os.killpg, side_effect=[None, None, ProcessLookupError()]
    )
    monkeypatch.setattr(os, "killpg", killpg)
    proc = _fake_proc()
    assert bk.kill_process_tree(proc) is True
    assert killpg.call_args_list == [
        mock.call(4321, signal.SIGTERM),
        mock.call(4321, signal.SIGKILL),
        mock.call(4321, 0),
    ]
    assert proc.wait.call_count == 2


@posix_only
@pytest.mark.parametrize(
    ("probe_error", "gone_errors", "confirmed"),
    [
        (ProcessLookupError(), _GONE_OTHER, True),
        (PermissionError(), _GONE_DARWIN, True),
        (PermissionError(), _GONE_OTHER, False),
        (OSError(22), _GONE_DARWIN, False),
    ],
    ids=["ESRCH", "EPERM-macos", "EPERM-linux", "EINVAL"],
)
@pytest.mark.parametrize(
    "wait_error", [subprocess.TimeoutExpired("x", 5), OSError(10, "ECHILD")]
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_kill_process_tree_posix_never_raises(
    monkeypatch: pytest.MonkeyPatch,
    probe_error: OSError,
    gone_errors: tuple[type[OSError], ...],
    confirmed: bool,
    wait_error: Exception,
) -> None:
    killpg = mock.create_autospec(
        os.killpg, side_effect=[OSError(1, "EPERM"), OSError(3, "ESRCH"), probe_error]
    )
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(bk, "_GROUP_GONE_ERRORS", gone_errors)
    proc = _fake_proc()
    proc.wait.side_effect = wait_error
    assert bk.kill_process_tree(proc) is confirmed  # must return normally
    assert killpg.call_count == 3


@posix_only
def test_kill_process_tree_posix_gives_up_on_live_group(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    killpg = mock.create_autospec(os.killpg, return_value=None)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(bk, "_GROUP_POLL_MAX_SECONDS", 0.3)
    caplog.set_level("DEBUG", logger=bk.__name__)
    assert bk.kill_process_tree(_fake_proc()) is False
    assert killpg.call_count > 3
    assert "still alive" in caplog.text


@posix_only
def test_kill_process_tree_posix_interrupt_in_grace_still_sigkills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killpg = mock.create_autospec(
        os.killpg, side_effect=[None, None, ProcessLookupError()]
    )
    monkeypatch.setattr(os, "killpg", killpg)
    proc = _fake_proc()
    # A second Ctrl-C during the SIGTERM grace wait.
    proc.wait.side_effect = [KeyboardInterrupt(), 0]
    with pytest.raises(KeyboardInterrupt):
        bk.kill_process_tree(proc)
    assert mock.call(4321, signal.SIGKILL) in killpg.call_args_list
    assert proc.wait.call_count == 2  # reaped after the SIGKILL


@posix_only
def test_group_poll_reaps_own_zombie_children_first(
    monkeypatch: pytest.MonkeyPatch, fake_waitpid: mock.Mock
) -> None:
    # As PID 1 (or a subreaper) killed descendants become this process's
    # children; unreaped, they keep the group probe succeeding.
    zombies = [111, 222]

    def waitpid(pid: int, options: int) -> tuple[int, int]:
        assert (pid, options) == (-4321, os.WNOHANG)
        return (zombies.pop(), 9) if zombies else (0, 0)

    def killpg(pgid: int, sig: int) -> None:
        del pgid
        if sig == 0 and not zombies:
            raise ProcessLookupError

    fake_waitpid.side_effect = waitpid
    monkeypatch.setattr(os, "killpg", killpg)
    assert bk.kill_process_tree(_fake_proc()) is True
    assert not zombies


@posix_only
def test_kill_process_tree_posix_kills_direct_child_outside_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No such group (the child did not get its own session): the direct
    child is still killed, so "with Popen" does not wait forever."""
    killpg = mock.create_autospec(os.killpg, side_effect=ProcessLookupError())
    monkeypatch.setattr(os, "killpg", killpg)
    proc = _fake_proc()
    bk.kill_process_tree(proc)
    proc.kill.assert_called_once_with()


@posix_only
def test_kill_process_tree_posix_interrupt_in_reap_still_reaps_and_polls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killpg = mock.create_autospec(
        os.killpg, side_effect=[None, None, ProcessLookupError()]
    )
    monkeypatch.setattr(os, "killpg", killpg)
    proc = _fake_proc()
    # Grace expires, then a Ctrl-C lands in the wait after SIGKILL.
    proc.wait.side_effect = [
        subprocess.TimeoutExpired("x", 3),
        KeyboardInterrupt(),
        0,
    ]
    with pytest.raises(KeyboardInterrupt):
        bk.kill_process_tree(proc)
    assert proc.wait.call_count == 3  # the interrupted reap resumed
    assert killpg.call_args_list[-1] == mock.call(4321, 0)  # group polled


@posix_only
def test_kill_process_tree_posix_interrupt_in_group_poll_reraised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killpg = mock.create_autospec(os.killpg, side_effect=[None, None, SystemExit(2)])
    monkeypatch.setattr(os, "killpg", killpg)
    proc = _fake_proc()
    with pytest.raises(SystemExit):
        bk.kill_process_tree(proc)
    proc.kill.assert_called_once_with()
    assert proc.wait.call_count == 2


# --- kill_leftover_descendants ---------------------------------------------


@posix_only
@pytest.mark.parametrize(
    ("error", "gone_errors"),
    [(ProcessLookupError(), _GONE_OTHER), (PermissionError(), _GONE_DARWIN)],
    ids=["ESRCH", "EPERM-macos"],
)
def test_kill_leftover_descendants_nothing_left(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: OSError,
    gone_errors: tuple[type[OSError], ...],
) -> None:
    killpg = mock.create_autospec(os.killpg, side_effect=error)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(bk, "_GROUP_GONE_ERRORS", gone_errors)
    caplog.set_level("INFO", logger=bk.__name__)
    bk.kill_leftover_descendants(_fake_proc())
    killpg.assert_called_once_with(4321, signal.SIGKILL)
    assert not caplog.records


@posix_only
def test_kill_leftover_descendants_unsignalable_member_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Linux EPERM: a live member this process may not signal (e.g. a
    setuid child) survives -- a WARNING:, never a silent return."""
    killpg = mock.create_autospec(os.killpg, side_effect=PermissionError())
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(bk, "_GROUP_GONE_ERRORS", _GONE_OTHER)
    bk.kill_leftover_descendants(_fake_proc())
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "could not confirm the processes the build left" in caplog.text


@posix_only
def test_kill_leftover_descendants_waits_for_group(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    killpg = mock.create_autospec(
        os.killpg, side_effect=[None, None, ProcessLookupError()]
    )
    monkeypatch.setattr(os, "killpg", killpg)
    caplog.set_level("INFO", logger=bk.__name__)
    bk.kill_leftover_descendants(_fake_proc())
    assert killpg.call_args_list == [
        mock.call(4321, signal.SIGKILL),
        mock.call(4321, 0),
        mock.call(4321, 0),
    ]
    assert [r.levelname for r in caplog.records] == ["INFO"]
    assert "killed processes the build left running" in caplog.text


@posix_only
def test_kill_leftover_descendants_warns_when_group_survives(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    killpg = mock.create_autospec(os.killpg, return_value=None)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(bk, "_GROUP_POLL_MAX_SECONDS", 0.3)
    caplog.set_level("INFO", logger=bk.__name__)
    bk.kill_leftover_descendants(_fake_proc())
    assert [r.levelname for r in caplog.records] == ["INFO", "WARNING"]


@posix_only
def test_kill_leftover_descendants_reaps_own_zombies_first(
    monkeypatch: pytest.MonkeyPatch, fake_waitpid: mock.Mock
) -> None:
    """As PID 1/subreaper, exited descendants are this process's zombies:
    reaped before the SIGKILL, so they don't count as left running."""
    calls: list[str] = []

    def _waitpid(*_args: object) -> tuple[int, int]:
        calls.append("waitpid")
        return (0, 0)

    def _killpg(*_args: object) -> None:
        calls.append("killpg")
        raise ProcessLookupError()

    fake_waitpid.side_effect = _waitpid
    monkeypatch.setattr(
        os, "killpg", mock.create_autospec(os.killpg, side_effect=_killpg)
    )
    bk.kill_leftover_descendants(_fake_proc())
    assert calls == ["waitpid", "killpg"]
    fake_waitpid.assert_called_once_with(-4321, os.WNOHANG)


def test_kill_leftover_descendants_windows_is_a_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    killpg = mock.Mock()
    monkeypatch.setattr(os, "killpg", killpg, raising=False)
    run_spy = mock.create_autospec(subprocess.run)
    monkeypatch.setattr(subprocess, "run", run_spy)
    bk.kill_leftover_descendants(_fake_proc())
    killpg.assert_not_called()
    run_spy.assert_not_called()


def test_kill_worst_case_fits_docker_stop_grace() -> None:
    # "docker stop" sends SIGKILL 10 s after SIGTERM; leave headroom. The
    # wait loop notices a signal within one slice.
    total = bs._WAIT_SLICE_SECONDS + bk._TERM_GRACE_SECONDS + bk._KILL_WAIT_SECONDS
    assert total + bk._GROUP_POLL_MAX_SECONDS <= 8.5


# --- kill_process_tree: Windows, mocked ------------------------------------


@pytest.mark.parametrize(
    ("system_root", "expected_root"),
    [("custom-root", None), (None, r"C:\Windows")],
    ids=["SystemRoot", "default"],
)
@pytest.mark.parametrize("returncode", [0, 128])
def test_kill_process_tree_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system_root: str | None,
    expected_root: str | None,
    returncode: int,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    if system_root is None:
        monkeypatch.delenv("SystemRoot", raising=False)
    else:
        expected_root = str(tmp_path / system_root)
        monkeypatch.setenv("SystemRoot", expected_root)
    run_spy = mock.create_autospec(
        subprocess.run, return_value=subprocess.CompletedProcess([], returncode)
    )
    monkeypatch.setattr(subprocess, "run", run_spy)
    killpg = mock.Mock()
    monkeypatch.setattr(os, "killpg", killpg, raising=False)
    proc = _fake_proc()

    # 128: taskkill found no such process (e.g. the child already exited).
    assert bk.kill_process_tree(proc) is (returncode == 0)

    assert expected_root is not None
    taskkill = str(Path(expected_root, "System32", "taskkill.exe"))
    run_spy.assert_called_once()
    assert run_spy.call_args.args[0] == [taskkill, "/F", "/T", "/PID", "4321"]
    assert run_spy.call_args.kwargs["check"] is False
    assert run_spy.call_args.kwargs["timeout"] > 0
    proc.kill.assert_called_once_with()
    proc.wait.assert_called_once()
    killpg.assert_not_called()


@pytest.mark.parametrize(
    "run_error", [OSError(2, "ENOENT"), subprocess.TimeoutExpired("taskkill", 60)]
)
def test_kill_process_tree_windows_never_raises(
    monkeypatch: pytest.MonkeyPatch, run_error: Exception
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    run_spy = mock.create_autospec(subprocess.run, side_effect=run_error)
    monkeypatch.setattr(subprocess, "run", run_spy)
    proc = _fake_proc()
    proc.kill.side_effect = OSError(5, "EACCES")
    proc.wait.side_effect = subprocess.TimeoutExpired("x", 30)
    assert bk.kill_process_tree(proc) is False  # must return normally
    proc.kill.assert_called_once_with()
    proc.wait.assert_called_once()


def test_kill_process_tree_windows_interrupt_in_taskkill_still_kills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    run_spy = mock.create_autospec(subprocess.run, side_effect=KeyboardInterrupt)
    monkeypatch.setattr(subprocess, "run", run_spy)
    proc = _fake_proc()
    with pytest.raises(KeyboardInterrupt):
        bk.kill_process_tree(proc)
    proc.kill.assert_called_once_with()
    proc.wait.assert_called_once()


def test_kill_process_tree_windows_interrupt_in_wait_resumes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    run_spy = mock.create_autospec(
        subprocess.run, return_value=subprocess.CompletedProcess([], 0)
    )
    monkeypatch.setattr(subprocess, "run", run_spy)
    proc = _fake_proc()
    proc.wait.side_effect = [KeyboardInterrupt(), 0]
    with pytest.raises(KeyboardInterrupt):
        bk.kill_process_tree(proc)
    assert proc.wait.call_count == 2


@posix_only
def test_kill_leftover_descendants_reaps_every_own_zombie(
    monkeypatch: pytest.MonkeyPatch,
    fake_waitpid: mock.Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Several exited descendants (PID 1/subreaper): all are reaped before
    the SIGKILL, not just the first -- a zombie left behind would let
    killpg() succeed on Linux and log a false INFO."""
    fake_waitpid.side_effect = [(111, 0), (222, 0), (0, 0)]
    killpg = mock.create_autospec(os.killpg, side_effect=ProcessLookupError())
    monkeypatch.setattr(os, "killpg", killpg)
    caplog.set_level("INFO", logger=bk.__name__)
    bk.kill_leftover_descendants(_fake_proc())
    assert fake_waitpid.call_count == 3
    assert not caplog.records
