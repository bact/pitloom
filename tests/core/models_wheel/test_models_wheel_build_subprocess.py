# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pitloom.core._models_wheel_build_subprocess``: the
``python -m build`` child process tree, its timeout, and its kill path.

Most tests drive real child processes (``python -c`` scripts), so a
leaked or un-waited ``Popen`` surfaces as a ``ResourceWarning`` failure
under ``filterwarnings = ["error"]``.

See also: tests/core/models_wheel/test_models_wheel_build_subprocess_e2e.py
(real ``python -m build`` runs against in-tree backends),
tests/core/models_wheel/test_models_wheel_build_kill.py (the
kill path), tests/core/test_build_signals.py
(SIGTERM/SIGHUP handling) and
tests/core/models_wheel/test_models_wheel_types_build_timeout.py (the
timeout value itself).
"""

# The private helpers are the unit under test here.
# pylint: disable=protected-access

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core import _models_wheel_build_kill as bk
from pitloom.core import _models_wheel_build_subprocess as bs
from pitloom.core._models_wheel_build_subprocess import (
    BuildSubprocessError,
    BuildTimeoutError,
    build_wheel_command,
    run_build_subprocess,
)
from pitloom.core.build_signals import (
    TerminationGuard,
    TerminationSignal,
)

_SLEEPER = [sys.executable, "-c", "import time; time.sleep(120)"]


def _work_dir(tmp_path: Path) -> Path:
    work_dir = tmp_path / "work"
    (work_dir / "t").mkdir(parents=True)
    return work_dir


def _run(
    cmd: list[str],
    work_dir: Path,
    *,
    timeout: int,
    termination: TerminationGuard | None = None,
) -> int:
    return bs._run_with_timeout(
        cmd,
        cwd=work_dir,
        env=bs._child_env(work_dir / "t"),
        log_path=work_dir / "build.log",
        timeout=timeout,
        termination=termination or TerminationGuard(),
    )


# --- build_wheel_command ---------------------------------------------------


@pytest.mark.parametrize("isolated", [True, False], ids=["isolated", "no-isolation"])
def test_build_wheel_command(tmp_path: Path, isolated: bool) -> None:
    project_dir = tmp_path / "proj"
    out_dir = tmp_path / "o"
    cmd = build_wheel_command(project_dir, out_dir, isolated=isolated)
    assert cmd[:6] == [
        sys.executable,
        "-m",
        "build",
        "--wheel",
        "--outdir",
        str(out_dir),
    ]
    assert cmd[-1] == str(project_dir.resolve())
    # --no-isolation without --skip-dependency-check refuses on missing deps.
    flags = {"--no-isolation", "--skip-dependency-check"}
    assert flags.isdisjoint(cmd) if isolated else flags <= set(cmd)


def test_build_wheel_command_project_dir_is_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cmd = build_wheel_command(Path("proj"), tmp_path / "o", isolated=True)
    assert Path(cmd[-1]).is_absolute()


# --- _child_env ------------------------------------------------------------


def test_child_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("PITLOOM_TEST_MARKER", "kept")
    env = bs._child_env(tmp_path / "t")
    assert {env[name] for name in ("TMPDIR", "TEMP", "TMP")} == {str(tmp_path / "t")}
    assert env["NO_COLOR"] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert "FORCE_COLOR" not in env
    assert env["PITLOOM_TEST_MARKER"] == "kept"
    assert "FORCE_COLOR" in os.environ  # a copy, not os.environ itself


# --- _run_with_timeout: real child processes -------------------------------


def test_run_with_timeout_returns_exit_code(tmp_path: Path) -> None:
    cmd = [sys.executable, "-c", "raise SystemExit(7)"]
    assert _run(cmd, _work_dir(tmp_path), timeout=60) == 7


def test_run_with_timeout_kills_on_timeout(tmp_path: Path) -> None:
    start = time.monotonic()
    with pytest.raises(BuildTimeoutError) as excinfo:
        _run(_SLEEPER, _work_dir(tmp_path), timeout=2)
    assert time.monotonic() - start < 60
    assert excinfo.value.timeout == 2
    assert excinfo.value.tree_terminated is True
    assert "timed out after 2s" in str(excinfo.value)


def test_run_with_timeout_reports_unconfirmed_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def kill_unconfirmed(proc: subprocess.Popen[bytes]) -> bool:
        proc.kill()
        proc.wait()
        return False

    monkeypatch.setattr(bs, "kill_process_tree", kill_unconfirmed)
    with pytest.raises(BuildTimeoutError) as excinfo:
        _run(_SLEEPER, _work_dir(tmp_path), timeout=1)
    assert excinfo.value.tree_terminated is False


def test_run_with_timeout_closes_stdin(tmp_path: Path) -> None:
    # Give this process a stdin that never reaches EOF: an inherited stdin
    # would block input() until the timeout; DEVNULL gives EOF at once.
    read_fd, write_fd = os.pipe()
    saved_stdin = os.dup(0)
    os.dup2(read_fd, 0)
    try:
        cmd = [sys.executable, "-c", "input()"]
        returncode = _run(cmd, _work_dir(tmp_path), timeout=20)
    finally:
        os.dup2(saved_stdin, 0)
        for fd in (saved_stdin, read_fd, write_fd):
            os.close(fd)
    assert returncode != 0
    log_text = (tmp_path / "work" / "build.log").read_text(encoding="utf-8")
    assert "EOFError" in log_text


def test_run_with_timeout_log_is_utf8_under_other_io_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # As on a Windows cp1252 locale, where a redirected stdout would
    # otherwise not be UTF-8 -- the encoding the log is read back in.
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    work_dir = _work_dir(tmp_path)
    cmd = [sys.executable, "-c", "print('caf\\u00e9')"]
    assert _run(cmd, work_dir, timeout=60) == 0
    assert bs._read_log_tail(work_dir / "build.log") == ["caf\u00e9"]


def test_run_with_timeout_captures_output(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    script = "import sys\nprint('OUT-MARK')\nprint('ERR-MARK', file=sys.stderr)\n"
    work_dir = _work_dir(tmp_path)
    assert _run([sys.executable, "-c", script], work_dir, timeout=60) == 0
    captured = capfd.readouterr()
    assert "MARK" not in captured.out + captured.err
    log_text = (work_dir / "build.log").read_text(encoding="utf-8")
    assert "OUT-MARK" in log_text
    assert "ERR-MARK" in log_text


def test_run_with_timeout_kills_on_keyboard_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_wait = subprocess.Popen.wait
    calls: list[float | None] = []

    def wait_interrupted_once(
        self: subprocess.Popen[bytes], timeout: float | None = None
    ) -> int:
        calls.append(timeout)
        if len(calls) == 1:
            raise KeyboardInterrupt
        return real_wait(self, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", wait_interrupted_once)
    kill_spy = mock.create_autospec(
        bk.kill_process_tree, side_effect=bk.kill_process_tree
    )
    monkeypatch.setattr(bs, "kill_process_tree", kill_spy)
    # Inside pytest.raises, so the interrupt never reaches pytest itself.
    with pytest.raises(KeyboardInterrupt):
        _run(_SLEEPER, _work_dir(tmp_path), timeout=60)
    kill_spy.assert_called_once()
    (proc,) = kill_spy.call_args.args
    assert proc.returncode is not None  # killed and reaped


# --- _run_with_timeout: termination signals ---------------------------------


def test_run_with_timeout_stops_on_recorded_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kill_spy = mock.create_autospec(
        bk.kill_process_tree, side_effect=bk.kill_process_tree
    )
    monkeypatch.setattr(bs, "kill_process_tree", kill_spy)
    guard = TerminationGuard()
    # As the handler would record it, while the build runs.
    timer = threading.Timer(0.5, setattr, (guard, "pending", signal.SIGTERM))
    start = time.monotonic()
    timer.start()
    try:
        with pytest.raises(TerminationSignal):
            _run(_SLEEPER, _work_dir(tmp_path), timeout=60, termination=guard)
    finally:
        timer.cancel()
    assert time.monotonic() - start < 30
    (proc,) = kill_spy.call_args.args
    assert proc.returncode is not None  # killed and reaped


def test_run_with_timeout_signal_before_start_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start_spy = mock.create_autospec(bs._start_process)
    monkeypatch.setattr(bs, "_start_process", start_spy)
    guard = TerminationGuard()
    guard.pending = signal.SIGTERM
    with pytest.raises(TerminationSignal):
        _run(_SLEEPER, _work_dir(tmp_path), timeout=60, termination=guard)
    start_spy.assert_not_called()


def test_run_with_timeout_signal_during_wait_wins_over_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A signal that also ended the build (Windows Ctrl-Break reaches both)
    is a request to stop, not a failed build."""
    guard = TerminationGuard()
    real_wait = subprocess.Popen.wait

    def wait_then_signal(
        self: subprocess.Popen[bytes], timeout: float | None = None
    ) -> int:
        del timeout  # one wait until exit, not a slice
        returncode = real_wait(self, timeout=30)
        guard.pending = signal.SIGTERM
        return returncode

    monkeypatch.setattr(subprocess.Popen, "wait", wait_then_signal)
    cmd = [sys.executable, "-c", "raise SystemExit(3)"]
    with pytest.raises(TerminationSignal):
        _run(cmd, _work_dir(tmp_path), timeout=60, termination=guard)


# --- Popen arguments -------------------------------------------------------


def _wheel_writing_command(
    project_dir: Path, out_dir: Path, *, isolated: bool
) -> list[str]:
    del project_dir, isolated
    script = (
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1], 'demo-0.1-py3-none-any.whl').write_bytes(b'')\n"
    )
    return [sys.executable, "-c", script, str(out_dir)]


@pytest.mark.parametrize("platform", [None, "win32"], ids=["native", "win32"])
def test_popen_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str | None
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    popen_spy = mock.create_autospec(subprocess.Popen, side_effect=subprocess.Popen)
    monkeypatch.setattr(subprocess, "Popen", popen_spy)
    monkeypatch.setattr(bs, "build_wheel_command", _wheel_writing_command)
    if platform is not None:
        monkeypatch.setattr(sys, "platform", platform)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    wheel = run_build_subprocess(
        tmp_path, work_dir, isolated=True, timeout=60, termination=TerminationGuard()
    )

    assert wheel == work_dir / "o" / "demo-0.1-py3-none-any.whl"
    popen_spy.assert_called_once()
    kwargs = popen_spy.call_args.kwargs
    assert kwargs["cwd"] == work_dir
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.STDOUT
    env = kwargs["env"]
    for name in ("TMPDIR", "TEMP", "TMP"):
        assert env[name] == str(work_dir / "t")
    assert env["NO_COLOR"] == "1"
    assert "FORCE_COLOR" not in env
    if sys.platform == "win32":
        assert "start_new_session" not in kwargs
        assert "creationflags" not in kwargs
    else:
        assert kwargs["start_new_session"] is True


# --- run_build_subprocess: error paths -------------------------------------


def _patch_command(monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    def fake_command(project_dir: Path, out_dir: Path, *, isolated: bool) -> list[str]:
        del project_dir, isolated
        return [sys.executable, "-c", script, str(out_dir)]

    monkeypatch.setattr(bs, "build_wheel_command", fake_command)


def test_run_build_subprocess_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch_command(
        monkeypatch,
        "print('first line')\n"
        "print('\\x1b[91mERROR boom\\x1b[0m')\n"
        "print()\n"
        "raise SystemExit(3)\n",
    )
    caplog.set_level(logging.DEBUG, logger=bs.__name__)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with pytest.raises(BuildSubprocessError) as excinfo:
        run_build_subprocess(
            tmp_path,
            work_dir,
            isolated=True,
            timeout=60,
            termination=TerminationGuard(),
        )
    assert str(excinfo.value) == "build exited with code 3: ERROR boom"
    assert "Build: build output: first line" in caplog.text
    assert "\x1b" not in caplog.text


@pytest.mark.parametrize("count", [0, 2])
def test_run_build_subprocess_needs_exactly_one_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    _patch_command(
        monkeypatch,
        "import pathlib, sys\n"
        f"for i in range({count}):\n"
        "    pathlib.Path(sys.argv[1], f'd{i}-1-py3-none-any.whl').write_bytes(b'')\n",
    )
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with pytest.raises(BuildSubprocessError, match=f"produced {count} wheels"):
        run_build_subprocess(
            tmp_path,
            work_dir,
            isolated=True,
            timeout=60,
            termination=TerminationGuard(),
        )


def test_run_build_subprocess_requires_build_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bs, "find_spec", lambda name: None)
    with pytest.raises(RuntimeError, match=r"pitloom\[build\]"):
        run_build_subprocess(
            tmp_path,
            tmp_path,
            isolated=True,
            timeout=60,
            termination=TerminationGuard(),
        )


def test_build_package_check_ignores_namespace_build_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # setuptools' output dir: a bare "build/" is a namespace package, which
    # the child (cwd=work_dir) never sees. Only this dir is on sys.path, so
    # the installed PyPA build is out of reach, as when it is not installed.
    (tmp_path / "build" / "lib").mkdir(parents=True)
    monkeypatch.setattr(sys, "path", [str(tmp_path)])
    monkeypatch.delitem(sys.modules, "build", raising=False)
    with pytest.raises(RuntimeError, match=r"pitloom\[build\]"):
        bs._require_build_package()


def test_build_package_check_accepts_installed_build() -> None:
    bs._require_build_package()  # PyPA build is a test dependency


def test_run_build_subprocess_requires_interpreter_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "executable", "")
    with pytest.raises(RuntimeError, match="interpreter"):
        run_build_subprocess(
            tmp_path,
            tmp_path,
            isolated=True,
            timeout=60,
            termination=TerminationGuard(),
        )


# --- log tail --------------------------------------------------------------


def test_read_log_tail_reads_only_the_tail(tmp_path: Path) -> None:
    log_path = tmp_path / "build.log"
    log_path.write_bytes(b"".join(b"line-%05d\n" % i for i in range(3000)))
    lines = bs._read_log_tail(log_path)
    assert lines[-1] == "line-02999"
    assert all(len(line) == len("line-00000") for line in lines)  # no partial
    assert sum(len(line) + 1 for line in lines) <= 8192


def test_read_log_tail_single_long_line_kept(tmp_path: Path) -> None:
    log_path = tmp_path / "build.log"
    log_path.write_bytes(b"x" * 20_000)
    assert bs._read_log_tail(log_path) == ["x" * 8192]


def test_read_log_tail_invalid_utf8(tmp_path: Path) -> None:
    log_path = tmp_path / "build.log"
    log_path.write_bytes(b"ok\n\xff\xfebad\n")
    assert bs._read_log_tail(log_path) == ["ok", "\ufffd\ufffdbad"]


def test_read_log_tail_missing_file(tmp_path: Path) -> None:
    assert not bs._read_log_tail(tmp_path / "absent.log")


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["a", "\x1b[1;31mERROR: bad\x1b[0m", "", "  "], "ERROR: bad"),
        (["x\x07y\x00z\x9b"], "xyz"),
        ([], "(no output)"),
        (["", "\x1b[0m"], "(no output)"),
        (["e" * 500], "e" * 197 + "..."),
    ],
    ids=["ansi-and-blank", "control-chars", "empty", "only-escapes", "capped"],
)
def test_last_message_line(lines: list[str], expected: str) -> None:
    assert bs._last_message_line(lines) == expected
