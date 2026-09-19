# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Run PyPA ``build``'s CLI as one child process tree with a hard timeout.

``--allow-build`` runs a third-party PEP 517 build. A build can hang
(network fetch of build requirements, a backend reading stdin, a
misbehaving build script), and neither a thread nor ``build``'s own
``runner=`` hook can be stopped once started -- so the whole build runs as
``python -m build --wheel`` in its own process tree, which this module
waits on with a deadline and kills as a whole when the deadline passes or
the wait is interrupted (Ctrl-C, or a SIGTERM/SIGHUP/SIGBREAK recorded by
a :class:`~pitloom.core.build_signals.TerminationGuard`).
After a normal exit, whatever the build left running in its process
group is killed too (POSIX only).

The build runs in its own POSIX session, so a signal sent to Pitloom
alone never reaches it: the tree is orphaned when Pitloom dies without
running this module's kill path -- SIGKILL, a host application's own
SIGTERM/SIGHUP handler that ends the process without unwinding (e.g.
``os._exit()``; one raising ``SystemExit`` unwinds through the wait loop,
which kills the tree), a call from a non-main thread, a build
descendant that calls ``setsid()`` itself, or on Windows a forced
termination (``TerminateProcess``), which cannot be intercepted. On
Windows, descendants still running after the build's own exit are not
reachable either (see
:func:`~pitloom.core._models_wheel_build_kill.kill_leftover_descendants`).

Layout inside the caller-owned *work_dir*: ``o/`` (wheel output), ``t/``
(the child's temp dir) and ``build.log`` (combined stdout/stderr). Names
stay short: a backend using :mod:`multiprocessing` on macOS creates an
AF_UNIX socket under temp, whose path limit is 104 bytes.

See also: :mod:`pitloom.core._models_wheel_build_and_read` (sole caller)
and :mod:`pitloom.core.build_signals` (SIGTERM/SIGHUP/
SIGBREAK handling around a build and while its result is in use).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess  # nosec B404
import sys
import time
from importlib.util import find_spec
from pathlib import Path
from typing import IO

from pitloom.core._models_wheel_build_kill import (
    kill_leftover_descendants,
    kill_process_tree,
)
from pitloom.core._models_wheel_types import BUILD_LOG_PREFIX
from pitloom.core.build_signals import TerminationGuard

log = logging.getLogger(__name__)

_OUT_DIR_NAME = "o"
_TMP_DIR_NAME = "t"
_LOG_FILE_NAME = "build.log"

# Worst case from a signal to the kill: this slice, plus the kill itself
# (see pitloom.core._models_wheel_build_kill).
_WAIT_SLICE_SECONDS = 0.25

_LOG_TAIL_BYTES = 8192
_MESSAGE_MAX_CHARS = 200

# CSI escape sequences (colours, cursor moves), then any other C0/C1 control.
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class BuildTimeoutError(Exception):
    """The build did not finish within *timeout* seconds; its process tree
    has been killed.

    *tree_terminated* is whether the kill was confirmed: false when a
    process in the tree was still alive after the kill (or, on Windows,
    ``taskkill`` could not report success).
    """

    def __init__(self, timeout: int, *, tree_terminated: bool) -> None:
        super().__init__(f"build timed out after {timeout}s")
        self.timeout: int = timeout
        self.tree_terminated: bool = tree_terminated


class BuildSubprocessError(Exception):
    """The build process finished but did not produce exactly one wheel."""


def build_wheel_command(
    project_dir: Path, out_dir: Path, *, isolated: bool
) -> list[str]:
    """Return the ``python -m build`` argv building *project_dir*'s wheel
    into *out_dir*.

    ``--wheel`` builds straight from source (no sdist first). With
    *isolated* false the running interpreter's own packages are used.
    """
    cmd = [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)]
    if not isolated:
        # --no-isolation alone makes build's CLI refuse on any missing
        # build requirement; the in-process API never checked that.
        cmd += ["--no-isolation", "--skip-dependency-check"]
    cmd.append(str(project_dir.resolve()))
    return cmd


def run_build_subprocess(
    project_dir: Path,
    work_dir: Path,
    *,
    isolated: bool,
    timeout: int,
    termination: TerminationGuard,
) -> Path:
    """Build *project_dir*'s wheel in a child process, returning its path.

    *work_dir* is an empty directory owned (and removed) by the caller.
    Raises :class:`BuildTimeoutError` when *timeout* seconds pass first
    (the process tree is killed before raising),
    :class:`~pitloom.core.build_signals.TerminationSignal`
    when *termination* records a signal before the build has finished
    (likewise),
    :class:`BuildSubprocessError` on a non-zero exit or when the output
    directory holds anything other than exactly one wheel, and
    :class:`RuntimeError` when PyPA ``build`` or the interpreter path is
    unavailable.
    """
    _require_build_package()
    if not sys.executable:
        raise RuntimeError("cannot locate the Python interpreter to run PyPA 'build'")

    out_dir = work_dir / _OUT_DIR_NAME
    tmp_dir = work_dir / _TMP_DIR_NAME
    log_path = work_dir / _LOG_FILE_NAME
    out_dir.mkdir(exist_ok=True)
    tmp_dir.mkdir(exist_ok=True)

    cmd = build_wheel_command(project_dir, out_dir, isolated=isolated)
    try:
        returncode = _run_with_timeout(
            cmd,
            # Never project_dir nor the inherited cwd: "-m" puts cwd first on
            # sys.path, so a project's own build.py would shadow PyPA build.
            cwd=work_dir,
            env=_child_env(tmp_dir),
            log_path=log_path,
            timeout=timeout,
            termination=termination,
        )
    except BuildTimeoutError:
        _debug_log_tail(log_path)
        raise
    if returncode != 0:
        tail = _debug_log_tail(log_path)
        raise BuildSubprocessError(
            f"build exited with code {returncode}: {_last_message_line(tail)}"
        )
    wheels = sorted(out_dir.glob("*.whl"))
    if len(wheels) != 1:
        _debug_log_tail(log_path)
        raise BuildSubprocessError(
            f"build produced {len(wheels)} wheels, expected exactly 1"
        )
    return wheels[0]


def _require_build_package() -> None:
    """Raise :class:`RuntimeError` unless PyPA ``build`` is importable.

    Checked here: in the child, a missing module is just exit code 1.
    """
    spec = find_spec("build")
    # A namespace package (no origin) is a bare "build/" directory on
    # sys.path, e.g. setuptools' output dir in the cwd -- not PyPA build,
    # and the child (cwd=work_dir) would not see it anyway.
    if spec is None or spec.origin is None:
        raise RuntimeError("PyPA 'build' is not installed -- install pitloom[build]")


def _child_env(tmp_dir: Path) -> dict[str, str]:
    """The build's environment: Pitloom's own, with temp redirected."""
    env = os.environ.copy()
    # Isolated build venvs and pip temp dirs land inside work_dir, so a
    # build killed by this module leaves nothing in the system temp dir.
    for name in ("TMPDIR", "TEMP", "TMP"):
        env[name] = str(tmp_dir)
    env["PYTHONUNBUFFERED"] = "1"
    # Python descendants write the log in the encoding it is read back in,
    # not the locale's (e.g. cp1252 on Windows).
    env["PYTHONIOENCODING"] = "utf-8"
    # build's CLI colours its error line; ANSI residue would reach WARNING:.
    env["NO_COLOR"] = "1"
    env.pop("FORCE_COLOR", None)
    return env


def _run_with_timeout(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    timeout: int,
    termination: TerminationGuard,
) -> int:
    """Run *cmd* with output to *log_path*; return its exit code.

    Raises :class:`BuildTimeoutError` after *timeout* seconds, and
    :class:`~pitloom.core.build_signals.TerminationSignal`
    once *termination* has recorded a signal (then without starting
    *cmd* at all if it came first). On those or any other exception
    (e.g. :class:`KeyboardInterrupt`) the whole process tree is killed
    before the exception propagates. After a normal exit, what *cmd* left
    running in its process group is killed.
    """
    termination.raise_if_pending()
    deadline = time.monotonic() + timeout
    # Output goes to a file, never a PIPE: a full pipe deadlocks the child,
    # and a surviving grandchild holding it would block reading after a kill.
    with (
        log_path.open("wb") as log_file,
        _start_process(cmd, cwd=cwd, env=env, log_file=log_file) as proc,
    ):
        try:
            returncode = _wait_until(proc, deadline, termination)
        except BaseException:
            kill_process_tree(proc)
            raise
        if returncode is None:
            # Unconditional, not only while the direct child still runs: it
            # may exit just after the deadline and leave grandchildren behind.
            terminated = kill_process_tree(proc)
            raise BuildTimeoutError(timeout, tree_terminated=terminated)
        kill_leftover_descendants(proc)
        return returncode


def _wait_until(
    proc: subprocess.Popen[bytes], deadline: float, termination: TerminationGuard
) -> int | None:
    """*proc*'s exit code, or ``None`` once *deadline* (monotonic) passes.

    Raises :class:`~pitloom.core.build_signals.TerminationSignal`
    once *termination* has recorded a signal, even when *proc* has exited
    meanwhile: a signal that reached the build too (Windows Ctrl-Break)
    is a request to stop, not a failed build.
    """
    while True:
        termination.raise_if_pending()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        # Short slices: the signal check runs between them, and on Windows
        # a long wait ignores Ctrl-C.
        try:
            returncode = proc.wait(timeout=min(_WAIT_SLICE_SECONDS, remaining))
        except subprocess.TimeoutExpired:
            continue
        termination.raise_if_pending()
        return returncode


def _start_process(
    cmd: list[str], *, cwd: Path, env: dict[str, str], log_file: IO[bytes]
) -> subprocess.Popen[bytes]:
    """Start *cmd* with stdin closed and stdout+stderr into *log_file*.

    Two explicit calls: mypy's ``Popen`` overloads reject a kwargs dict.
    """
    if sys.platform == "win32":
        # No CREATE_NEW_PROCESS_GROUP: it would disable Ctrl-C in the
        # child, and taskkill /T walks the tree by parent PID anyway.
        # bandit B603: argv list, no shell.
        return subprocess.Popen(  # nosec B603
            cmd,
            cwd=cwd,
            env=env,
            # A stdin-reading backend gets EOF instead of hanging.
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    # bandit B603: argv list, no shell.
    return subprocess.Popen(  # nosec B603
        cmd,
        cwd=cwd,
        env=env,
        # A stdin-reading backend gets EOF instead of hanging.
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        # Own session: pgid == child pid, so killpg reaches every descendant.
        start_new_session=True,
    )


def _read_log_tail(log_path: Path) -> list[str]:
    """Return the lines of at most the last 8 KiB of *log_path*.

    Seeks from the end rather than reading the whole log. A partial first
    line (cut by the 8 KiB window) is dropped when more lines follow.
    """
    try:
        with log_path.open("rb") as log_file:
            size = log_file.seek(0, os.SEEK_END)
            log_file.seek(max(0, size - _LOG_TAIL_BYTES))
            data = log_file.read(_LOG_TAIL_BYTES)
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    if size > _LOG_TAIL_BYTES and len(lines) > 1:
        lines = lines[1:]
    return lines


def _clean_line(line: str) -> str:
    """*line* without ANSI sequences or control characters."""
    return _CONTROL_CHARS_RE.sub("", _ANSI_CSI_RE.sub("", line)).strip()


def _last_message_line(lines: list[str]) -> str:
    """The last non-empty cleaned line, capped for a one-line WARNING:."""
    for line in reversed(lines):
        cleaned = _clean_line(line)
        if cleaned:
            if len(cleaned) > _MESSAGE_MAX_CHARS:
                return cleaned[: _MESSAGE_MAX_CHARS - 3] + "..."
            return cleaned
    return "(no output)"


def _debug_log_tail(log_path: Path) -> list[str]:
    """DEBUG-log the build output tail; return its raw lines.

    Every line carries the prefix, so a raw ``::`` line from the build
    never starts a line a GitHub runner would read as a workflow command.
    """
    lines = _read_log_tail(log_path)
    for line in lines:
        log.debug("%sbuild output: %s", BUILD_LOG_PREFIX, _clean_line(line))
    return lines
