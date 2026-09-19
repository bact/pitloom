# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Real process-tree tests for ``pitloom.core._models_wheel_build_subprocess``:
a real ``python -m build --no-isolation`` run against in-tree PEP 517
backends (``backend-path = ["."]``, so no network and no installed
backend), descendants that survive SIGTERM, a second Ctrl-C during the
kill, a descendant a finished build leaves running, and a real
SIGTERM/SIGHUP to a process running a build.

See also: tests/core/models_wheel/test_models_wheel_build_subprocess.py
and tests/core/models_wheel/test_models_wheel_build_kill.py
(unit tests of the build subprocess and its kill path).
"""

# The private helpers are the unit under test here.
# pylint: disable=protected-access

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core import _models_wheel_build_subprocess as bs
from pitloom.core._models_wheel_build_subprocess import (
    BuildTimeoutError,
    run_build_subprocess,
)
from pitloom.core.build_signals import TerminationGuard

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="process groups are POSIX-only"
)

# Deliberately not installed: with --skip-dependency-check the build must
# still proceed, as the in-process API never checked build requirements.
_MISSING_REQUIREMENT = "pitloom-test-absent-build-requirement"

# Writes a pid file atomically, so a reader never sees it half-written.
_WRITE_PID = """
def _write_pid(path):
    with open(path + ".tmp", "w") as f:
        f.write(str(os.getpid()))
    os.replace(path + ".tmp", path)
"""

# With PITLOOM_TEST_GRANDCHILD set, also starts a grandchild ignoring SIGTERM.
_SLOW_BACKEND = (
    "import os, signal, subprocess, sys, tempfile, time\n"
    + _WRITE_PID
    + textwrap.dedent(
        """
        _HERE = os.path.dirname(os.path.abspath(__file__))
        _GRANDCHILD = (
            "import os, signal, sys, time\\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\\n"
            + %r
            + "_write_pid(sys.argv[1])\\ntime.sleep(300)\\n"
        )

        def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
            with open(os.path.join(_HERE, "tempdir.txt"), "w") as f:
                f.write(tempfile.gettempdir())
            print("slow backend started", flush=True)
            if os.environ.get("PITLOOM_TEST_GRANDCHILD"):
                subprocess.Popen(
                    [sys.executable, "-c", _GRANDCHILD,
                     os.path.join(_HERE, "grandchild.pid")]
                )
            _write_pid(os.path.join(_HERE, "backend.pid"))
            time.sleep(300)
        """
    )
    % _WRITE_PID
)

_FAST_BACKEND = textwrap.dedent(
    """
    import os, zipfile

    NAME = "demo-0.1-py3-none-any.whl"

    def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
        with zipfile.ZipFile(os.path.join(wheel_directory, NAME), "w") as zf:
            zf.writestr("demo/__init__.py", "")
            zf.writestr(
                "demo-0.1.dist-info/METADATA",
                "Metadata-Version: 2.1\\nName: demo\\nVersion: 0.1\\n",
            )
            zf.writestr(
                "demo-0.1.dist-info/WHEEL",
                "Wheel-Version: 1.0\\nGenerator: test\\n"
                "Root-Is-Purelib: true\\nTag: py3-none-any\\n",
            )
            zf.writestr("demo-0.1.dist-info/RECORD", "")
        return NAME
    """
)


def _make_project(root: Path, backend: str, source: str, requires: str) -> Path:
    project = root / "proj"
    project.mkdir()
    (project / f"{backend}.py").write_text(source, encoding="utf-8")
    (project / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [build-system]
            requires = [{requires}]
            build-backend = "{backend}"
            backend-path = ["."]
            """
        ),
        encoding="utf-8",
    )
    return project


def _pid_gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return True
    # Linux: a killed orphan answers kill(pid, 0) until init reaps it.
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def _wait_pid_gone(pid: int, limit: float = 10.0) -> bool:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if _pid_gone(pid):
            return True
        time.sleep(0.1)
    return _pid_gone(pid)


def _rmtree_with_retry(path: Path, limit: float = 10.0) -> None:
    """Remove *path*; on Windows a just-killed process may hold a handle."""
    deadline = time.monotonic() + limit
    while True:
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)


def test_real_build_times_out_and_kills_backend(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _make_project(tmp_path, "slow_backend", _SLOW_BACKEND, "")
    work_dir = tmp_path / "plb-work"
    work_dir.mkdir()
    caplog.set_level(logging.DEBUG, logger=bs.__name__)

    start = time.monotonic()
    # Generous: the backend must start (interpreter + build) before it.
    with pytest.raises(BuildTimeoutError) as excinfo:
        run_build_subprocess(
            project,
            work_dir,
            isolated=False,
            timeout=20,
            termination=TerminationGuard(),
        )
    assert time.monotonic() - start < 90

    # The child's temp dir was redirected into the work dir...
    reported_tmp = Path((project / "tempdir.txt").read_text(encoding="utf-8"))
    assert reported_tmp.resolve() == (work_dir / "t").resolve()
    # ...and nothing still running holds or refills it after the kill.
    _rmtree_with_retry(work_dir)
    assert not work_dir.exists()

    assert excinfo.value.timeout == 20
    assert excinfo.value.tree_terminated is True
    assert "timed out after 20s" in str(excinfo.value)
    assert "Build: build output: slow backend started" in caplog.text
    pid = int((project / "backend.pid").read_text(encoding="ascii"))
    if sys.platform != "win32":  # os.kill() on Windows terminates, not probes
        assert _wait_pid_gone(pid), f"backend process {pid} survived the timeout"


def test_real_build_returns_the_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(
        tmp_path, "fast_backend", _FAST_BACKEND, f'"{_MISSING_REQUIREMENT}"'
    )
    # A shadowing build.py in the inherited cwd must not replace PyPA build.
    (project / "build.py").write_text(
        "raise SystemExit('shadowed PyPA build')\n", encoding="utf-8"
    )
    monkeypatch.chdir(project)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    wheel = run_build_subprocess(
        project,
        work_dir,
        isolated=False,
        timeout=120,
        termination=TerminationGuard(),
    )

    assert wheel == work_dir / "o" / "demo-0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as zf:
        assert "demo/__init__.py" in zf.namelist()


@posix_only
def test_run_with_timeout_kills_grandchild_ignoring_sigterm(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    # The grandchild ignores SIGTERM, so only the SIGKILL to the whole
    # process group stops it; it writes its pid once that is in place.
    grandchild = textwrap.dedent(
        f"""
        import os, signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        with open({str(pid_file) + ".tmp"!r}, "w") as f:
            f.write(str(os.getpid()))
        os.replace({str(pid_file) + ".tmp"!r}, {str(pid_file)!r})
        time.sleep(300)
        """
    )
    child = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "time.sleep(300)\n"
    )
    with pytest.raises(BuildTimeoutError):
        bs._run_with_timeout(
            [sys.executable, "-c", child],
            cwd=tmp_path,
            env=bs._child_env(tmp_path),
            log_path=tmp_path / "build.log",
            timeout=10,
            termination=TerminationGuard(),
        )
    assert pid_file.exists(), "grandchild never started within the timeout"
    pid = int(pid_file.read_text(encoding="ascii"))
    assert _wait_pid_gone(pid), f"grandchild {pid} survived"


@posix_only
def test_second_interrupt_during_grace_still_kills_sigterm_ignoring_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "grandchild.pid"
    grandchild = textwrap.dedent(
        f"""
        import os, signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        with open({str(pid_file) + ".tmp"!r}, "w") as f:
            f.write(str(os.getpid()))
        os.replace({str(pid_file) + ".tmp"!r}, {str(pid_file)!r})
        time.sleep(300)
        """
    )
    # The child ignores SIGTERM too, so the grace wait would run its full
    # length unless the second interrupt cuts it short.
    child = (
        "import signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "time.sleep(300)\n"
    )
    real_wait = subprocess.Popen.wait
    interrupts = 0

    def wait(self: subprocess.Popen[bytes], timeout: float | None = None) -> int:
        nonlocal interrupts
        # First Ctrl-C once the grandchild runs, the second in the grace wait.
        if interrupts == 1 or (interrupts == 0 and pid_file.exists()):
            interrupts += 1
            raise KeyboardInterrupt
        return real_wait(self, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", wait)
    try:
        with pytest.raises(KeyboardInterrupt):
            bs._run_with_timeout(
                [sys.executable, "-c", child],
                cwd=tmp_path,
                env=bs._child_env(tmp_path),
                log_path=tmp_path / "build.log",
                timeout=60,
                termination=TerminationGuard(),
            )
        assert interrupts == 2
        pid = int(pid_file.read_text(encoding="ascii"))
        assert _wait_pid_gone(pid), f"grandchild {pid} survived"
    finally:
        _kill_leftovers(pid_file)


@posix_only
def test_finished_build_leaves_no_descendant_running(tmp_path: Path) -> None:
    """A descendant a successful build left behind (ignoring SIGTERM) is
    killed before the call returns, so before the caller removes the work
    dir."""
    pid_file = tmp_path / "grandchild.pid"
    grandchild = textwrap.dedent(
        f"""
        import os, signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        with open({str(pid_file) + ".tmp"!r}, "w") as f:
            f.write(str(os.getpid()))
        os.replace({str(pid_file) + ".tmp"!r}, {str(pid_file)!r})
        time.sleep(300)
        """
    )
    child = (
        "import os, subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        f"while not os.path.exists({str(pid_file)!r}):\n"
        "    time.sleep(0.05)\n"
    )
    try:
        returncode = bs._run_with_timeout(
            [sys.executable, "-c", child],
            cwd=tmp_path,
            env=bs._child_env(tmp_path),
            log_path=tmp_path / "build.log",
            timeout=60,
            termination=TerminationGuard(),
        )
        assert returncode == 0
        # Polled: macOS shows the killed process as a zombie until reaped.
        pid = int(pid_file.read_text(encoding="ascii"))
        assert _wait_pid_gone(pid), f"grandchild {pid} survived"
    finally:
        _kill_leftovers(pid_file)


def _kill_leftovers(*pid_files: Path) -> None:
    """SIGKILL processes a failed test left behind."""
    for pid_file in pid_files:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text(encoding="ascii")), signal.SIGKILL)
            except (OSError, ValueError):
                pass


# Runs the build path the way the CLI does, in a process of its own.
_DRIVER = textwrap.dedent(
    """
    import logging, sys
    from pathlib import Path
    from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
    logging.basicConfig(format="%(levelname)s: %(message)s")
    build_and_read_wheel(Path(sys.argv[1]), isolated=False, timeout=300)
    print("build_and_read_wheel returned")
    """
)


def _wait_for(predicate: Callable[[], bool], limit: float) -> bool:
    deadline = time.monotonic() + limit
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


@posix_only
@pytest.mark.parametrize("sig_name", ["SIGTERM", "SIGHUP"])
def test_termination_signal_kills_build_tree_and_removes_temp_dirs(
    tmp_path: Path, sig_name: str
) -> None:
    sig = signal.Signals[sig_name]
    project = _make_project(tmp_path, "slow_backend", _SLOW_BACKEND, "")
    sys_tmp = tmp_path / "sys-tmp"
    sys_tmp.mkdir()
    pid_files = (project / "backend.pid", project / "grandchild.pid")
    src_dir = Path(bs.__file__).resolve().parents[2]
    env = {
        **os.environ,
        "TMPDIR": str(sys_tmp),
        "PITLOOM_TEST_GRANDCHILD": "1",
        "PYTHONPATH": os.pathsep.join(
            filter(None, [str(src_dir), os.environ.get("PYTHONPATH")])
        ),
    }
    try:
        out, err, returncode = _run_driver_until_signal(project, env, pid_files, sig)
        for pid_file in pid_files:
            pid = int(pid_file.read_text(encoding="ascii"))
            assert _wait_pid_gone(pid), f"{pid_file.stem} process {pid} survived"
    finally:
        _kill_leftovers(*pid_files)
    assert not list(sys_tmp.iterdir())
    # Terminated by the signal itself, after cleanup; not a normal return.
    assert returncode == -sig
    assert b"build_and_read_wheel returned" not in out
    assert f"WARNING: Build: received {sig_name}".encode() in err


def _run_driver_until_signal(
    project: Path, env: dict[str, str], pid_files: tuple[Path, ...], sig: int
) -> tuple[bytes, bytes, int]:
    """Run :data:`_DRIVER` on *project*; send *sig* once the build runs."""
    sys_tmp = Path(env["TMPDIR"])
    with subprocess.Popen(
        [sys.executable, "-c", _DRIVER, str(project)],
        cwd=project.parent,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as driver:
        try:
            assert _wait_for(lambda: all(p.exists() for p in pid_files), 60)
            # Both temp dirs exist while the build runs, so the emptiness
            # check after the signal is not vacuous.
            prefixes = {p.name.split("-")[0] for p in sys_tmp.iterdir()}
            assert prefixes == {"plb", "pitloom"}
            driver.send_signal(sig)
            out, err = driver.communicate(timeout=60)
        finally:
            if driver.poll() is None:
                driver.kill()
                driver.communicate()
    return out, err, driver.returncode


# Becomes a child subreaper (as PID 1 in a container is), then times out
# a child whose SIGTERM-ignoring grandchild is reparented to it on the kill.
_SUBREAPER_DRIVER = textwrap.dedent(
    """
    import ctypes, sys
    from pathlib import Path
    from pitloom.core import _models_wheel_build_subprocess as bs
    from pitloom.core.build_signals import TerminationGuard
    PR_SET_CHILD_SUBREAPER = 36
    if ctypes.CDLL(None, use_errno=True).prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0):
        sys.exit("prctl failed")
    work = Path(sys.argv[1])
    try:
        bs._run_with_timeout(
            [sys.executable, "-c", sys.argv[2]], cwd=work, env=bs._child_env(work),
            log_path=work / "build.log", timeout=5,
            termination=TerminationGuard(),
        )
    except bs.BuildTimeoutError as exc:
        print("TREE_TERMINATED=%s" % exc.tree_terminated)
    """
)


@pytest.mark.skipif(sys.platform != "linux", reason="PR_SET_CHILD_SUBREAPER")
def test_subreaper_reaps_killed_descendants(tmp_path: Path) -> None:
    grandchild = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(300)\n"
    )
    child = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "time.sleep(300)\n"
    )
    src_dir = Path(bs.__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(None, [str(src_dir), os.environ.get("PYTHONPATH")])
        ),
    }
    result = subprocess.run(
        [sys.executable, "-c", _SUBREAPER_DRIVER, str(tmp_path), child],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
        check=False,
    )
    # Unreaped zombies would keep the group probe succeeding: False.
    assert result.stdout.decode().split() == ["TREE_TERMINATED=True"], result.stderr
