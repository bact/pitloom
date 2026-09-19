# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Kill a build's child process tree, and what it leaves behind.

Split out of :mod:`pitloom.core._models_wheel_build_subprocess`, which
starts the tree (POSIX: in its own session, so the process group ID is
the direct child's PID) and calls :func:`kill_process_tree` on a timeout
or interrupt and :func:`kill_leftover_descendants` after a normal exit.

POSIX: SIGTERM to the group, a grace period, SIGKILL to the group and
the direct child, reap, then poll until the group is gone, so the
caller's temp-dir removal does not race dying descendants. Windows:
``taskkill /F /T`` (the tree by parent PID), then kill and reap the
direct child.

See also: :mod:`pitloom.core._models_wheel_build_subprocess` (sole
caller) and :mod:`pitloom.core.build_signals`
(SIGTERM/SIGHUP/SIGBREAK handling around a build).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess  # nosec B404
import sys
import time
from collections.abc import Callable
from pathlib import Path

from pitloom.core._models_wheel_types import BUILD_LOG_PREFIX

log = logging.getLogger(__name__)

# Worst case after the deadline or signal: POSIX 3 + 2 + 3 s (plus the
# wait loop's slice), within "docker stop"'s default 10 s before SIGKILL;
# Windows 60 + 30 s.
_TERM_GRACE_SECONDS = 3.0
_KILL_WAIT_SECONDS = 2.0
_GROUP_POLL_SECONDS = 0.1
_GROUP_POLL_MAX_SECONDS = 3.0
_TASKKILL_TIMEOUT_SECONDS = 60
_WINDOWS_WAIT_SECONDS = 30.0

# killpg() errors meaning "no process left in the group". macOS also
# reports EPERM once only zombies remain -- and when every live member
# belongs to another user, which it can't be told apart from, so such a
# survivor counts as gone there. Elsewhere (Linux) EPERM means a live
# member this process may not signal (e.g. a setuid child): not gone.
_GROUP_GONE_ERRORS: tuple[type[OSError], ...] = (
    (ProcessLookupError, PermissionError)
    if sys.platform == "darwin"
    else (ProcessLookupError,)
)


def kill_process_tree(proc: subprocess.Popen[bytes]) -> bool:
    """Kill *proc* and its descendants, then reap *proc*; return whether
    the tree was confirmed gone.

    Raises nothing of its own: it runs while a timeout or interrupt is
    propagating, and raising would mask that and leave *proc* un-waited.
    A :class:`BaseException` arriving mid-way (a second Ctrl-C) cuts the
    SIGTERM grace short but skips none of the later steps (SIGKILL, the
    direct child's kill and reap, the group poll); the first one is
    re-raised once they are done.
    """
    if sys.platform == "win32":
        return _kill_windows_tree(proc)
    pgid = proc.pid
    pending: BaseException | None = None
    try:
        _signal_group(pgid, signal.SIGTERM)
        _wait_quietly(proc, _TERM_GRACE_SECONDS)
    # pylint: disable-next=broad-exception-caught
    except BaseException as exc:
        pending = exc
    # Unconditional: a descendant may ignore SIGTERM or outlive the child.
    pending = _hold(pending, _signal_group, pgid, signal.SIGKILL)
    # The direct child too, should it not lead the group (no own session,
    # or it moved itself out): "with Popen" would otherwise wait forever.
    pending = _hold(pending, _kill_quietly, proc)
    # Reap first: an unreaped child keeps the group "alive" on Linux.
    pending = _reap(proc, _KILL_WAIT_SECONDS, pending)
    terminated = False
    try:
        terminated = _wait_for_group_exit(pgid)
    # pylint: disable-next=broad-exception-caught
    except BaseException as exc:
        pending = exc if pending is None else pending
    if pending is not None:
        raise pending
    return terminated


def kill_leftover_descendants(proc: subprocess.Popen[bytes]) -> None:
    """After the build's own exit, SIGKILL what it left running in its
    process group, and wait for that to go.

    A backend's background child would otherwise outlive the build and
    keep writing into the work dir while the caller removes it. Logs an
    ``INFO:`` when it kills any, and a ``WARNING:`` when it can't confirm
    they are gone. Nothing to do on Windows, where nothing can reach
    them: ``taskkill /T`` finds descendants by parent PID, which an exited
    child no longer anchors.
    """
    if sys.platform == "win32":
        return
    pgid = proc.pid
    # As PID 1 or a subreaper, exited descendants are this process's
    # zombies: reap them first, or they would count as left running.
    _reap_group_children(pgid)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except _GROUP_GONE_ERRORS:
        return  # the normal case: nothing left
    except OSError as exc:
        log.debug("%skillpg(%d) failed: %s", BUILD_LOG_PREFIX, pgid, exc)
        _warn_group_survived(pgid)
        return
    log.info(
        "%skilled processes the build left running (process group %d)",
        BUILD_LOG_PREFIX,
        pgid,
    )
    if not _wait_for_group_exit(pgid):
        _warn_group_survived(pgid)


def _warn_group_survived(pgid: int) -> None:
    """``WARNING:`` that processes the build left may still be running."""
    log.warning(
        "%scould not confirm the processes the build left running "
        "(process group %d) terminated",
        BUILD_LOG_PREFIX,
        pgid,
    )


def _wait_for_group_exit(pgid: int) -> bool:
    """Poll until process group *pgid* is gone, so temp-dir cleanup doesn't
    race dying descendants; return whether it was confirmed gone."""
    if sys.platform == "win32":  # pragma: no cover -- POSIX-only helper
        return False
    deadline = time.monotonic() + _GROUP_POLL_MAX_SECONDS
    while time.monotonic() < deadline:
        _reap_group_children(pgid)
        try:
            os.killpg(pgid, 0)
        except _GROUP_GONE_ERRORS:
            return True
        except OSError as exc:
            log.debug(
                "%sprocess group %d probe failed: %s", BUILD_LOG_PREFIX, pgid, exc
            )
            return False
        time.sleep(_GROUP_POLL_SECONDS)
    log.debug("%sprocess group %d still alive after SIGKILL", BUILD_LOG_PREFIX, pgid)
    return False


def _reap_group_children(pgid: int) -> None:
    """Reap exited processes of group *pgid* that are this process's own
    children.

    Normally there are none: orphans go to init, which reaps them. As PID 1
    in a container, or as a child subreaper, the killed descendants are
    reparented to this process instead, and as unreaped zombies they keep
    the group probe succeeding. ``waitpid(-pgid)`` touches only that group,
    never a host application's other children.
    """
    if sys.platform == "win32":  # pragma: no cover -- POSIX-only helper
        return
    while True:
        try:
            pid, _ = os.waitpid(-pgid, os.WNOHANG)
        except ChildProcessError:
            return
        except OSError as exc:
            log.debug("%swaitpid(-%d) failed: %s", BUILD_LOG_PREFIX, pgid, exc)
            return
        if pid == 0:
            return


def _signal_group(pgid: int, sig: int) -> None:
    """``os.killpg`` that logs instead of raising (group may be gone)."""
    if sys.platform == "win32":  # pragma: no cover -- POSIX-only helper
        return
    try:
        os.killpg(pgid, sig)
    except OSError as exc:
        log.debug("%skillpg(%d, %d) failed: %s", BUILD_LOG_PREFIX, pgid, sig, exc)


def _kill_windows_tree(proc: subprocess.Popen[bytes]) -> bool:
    """``taskkill /F /T`` (whole tree by parent PID), then kill and reap;
    return whether ``taskkill`` reported success.

    ``taskkill /T`` finds descendants through the parent PID. Once the
    direct child has exited, its orphaned descendants are probably no
    longer reachable that way, and nothing here can confirm otherwise.
    """
    # Full path, not a PATH lookup (bandit B607).
    taskkill = Path(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe"
    )
    terminated = False
    pending: BaseException | None = None
    try:
        # bandit B603: fixed system binary, argv list.
        result = subprocess.run(  # nosec B603
            [str(taskkill), "/F", "/T", "/PID", str(proc.pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=_TASKKILL_TIMEOUT_SECONDS,
        )
        terminated = result.returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("%staskkill failed: %s", BUILD_LOG_PREFIX, exc)
    # pylint: disable-next=broad-exception-caught
    except BaseException as exc:
        pending = exc
    pending = _hold(pending, _kill_quietly, proc)
    pending = _reap(proc, _WINDOWS_WAIT_SECONDS, pending)
    if pending is not None:
        raise pending
    return terminated


def _hold(
    pending: BaseException | None, step: Callable[..., object], *args: object
) -> BaseException | None:
    """Run ``step(*args)``; return *pending*, or what *step* raised if
    nothing was pending yet -- so an interrupt skips no later step."""
    try:
        step(*args)
    # pylint: disable-next=broad-exception-caught
    except BaseException as exc:
        return exc if pending is None else pending
    return pending


def _reap(
    proc: subprocess.Popen[bytes], timeout: float, pending: BaseException | None
) -> BaseException | None:
    """Wait up to *timeout* seconds for *proc* to exit, resuming the wait
    after an interrupt; return *pending* or the first interrupt.

    Unreaped, *proc* would outlive a :class:`KeyboardInterrupt`: ``with
    Popen`` then waits only 0.25 s, and the ``Popen`` is garbage-collected
    still running (``ResourceWarning``).
    """
    deadline = time.monotonic() + timeout
    while True:
        remaining = max(deadline - time.monotonic(), 0.0)
        try:
            _wait_quietly(proc, remaining)
            return pending
        # pylint: disable-next=broad-exception-caught
        except BaseException as exc:
            pending = exc if pending is None else pending
            if remaining <= 0:
                return pending


def _kill_quietly(proc: subprocess.Popen[bytes]) -> None:
    """``proc.kill()`` that logs instead of raising."""
    try:
        proc.kill()
    except OSError as exc:
        log.debug("%skill failed: %s", BUILD_LOG_PREFIX, exc)


def _wait_quietly(proc: subprocess.Popen[bytes], timeout: float) -> None:
    """``proc.wait(timeout)`` that logs instead of raising."""
    try:
        proc.wait(timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        # Last resort: the enclosing "with Popen" exit waits without limit.
        log.debug("%swait for pid %d failed: %s", BUILD_LOG_PREFIX, proc.pid, exc)
