# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Clean up after a build-and-read before SIGTERM/SIGHUP/SIGBREAK ends
the process.

The build runs as a child process tree in its own POSIX session, and its
result lives in a temporary directory until the SBOM no longer needs it.
Under ``SIG_DFL`` a signal would end Pitloom with neither the tree killed
nor the directories removed.

Contract of :class:`TerminationGuard`:

- The outermost guard in a thread owns the handling; a nested guard
  yields to it and does nothing on its own exit. Every entry point that
  holds a build-and-read result enters one, so the outermost sets the
  protected lifetime.
- Nothing is installed until :meth:`~TerminationGuard.hold` is first
  entered (a build starts); the handlers then stay until the owner exits.
- Inside a hold (creating the temp directories, running the build) the
  handler only records the signal; the build's wait loop polls
  :meth:`~TerminationGuard.raise_if_pending`, kills and reaps the tree,
  and the process ends when the hold is left.
- Outside a hold (extraction, hashing, scanning) the handler itself runs
  the :meth:`~TerminationGuard.add_cleanup` callbacks, newest first, and
  ends the process at once; a removal it cut short is repeated.
- Ending: handlers reset to ``SIG_DFL`` and the signal is re-raised, so
  the exit status reads "killed by SIGTERM"; ``finally`` blocks up the
  stack don't run. If the re-raise returns (PID 1), ``SystemExit(128 +
  signum)`` is raised from the handler instead. If an interrupt cuts the
  callbacks short, the owner's exit finishes the termination.
- Callbacks also run when the owner's block ends by an exception, and are
  dropped on a normal exit (the owner released or handed on the resource).
- The owner's exit resets the guard; entering it while entered raises
  :class:`RuntimeError`.

See also: :mod:`pitloom.core._models_wheel_build_subprocess` (the wait
loop) and :mod:`pitloom.core._models_wheel_build_and_read` (registers the
temp directories).
"""

from __future__ import annotations

import contextlib
import logging
import signal
import threading
from collections.abc import Callable, Iterator
from types import FrameType, TracebackType

from pitloom.core._models_wheel_types import BUILD_LOG_PREFIX

log = logging.getLogger(__name__)

# Looked up with getattr: SIGHUP is POSIX-only, SIGBREAK (Ctrl-Break)
# Windows-only.
_TERMINATION_SIGNAL_NAMES = ("SIGTERM", "SIGHUP", "SIGBREAK")

# Per thread: signal handlers run in the main thread only, and a library
# call from another thread must never join the main thread's guard.
_thread_state = threading.local()


class TerminationSignal(BaseException):
    """A termination signal recorded by a :class:`TerminationGuard`, raised
    by :meth:`TerminationGuard.raise_if_pending`.

    A :class:`BaseException`, like :class:`KeyboardInterrupt`: a broad
    ``except Exception`` fallback must not turn a request to terminate
    into "carry on with static discovery".
    """

    def __init__(self, signum: int) -> None:
        super().__init__(f"received {signal.Signals(signum).name}")
        self.signum: int = signum


class TerminationGuard:
    """Context manager owning SIGTERM/SIGHUP/SIGBREAK handling while a
    build-and-read is running or its result is in use (see the module
    docstring for the full contract).

    Handles a signal only on the main thread and only while its handler
    is ``SIG_DFL`` -- the process would die from it anyway, without
    cleanup. A host application's own handler, or ``SIG_IGN``
    (``nohup``), is left untouched, and the guard then never records
    anything. Not entered, it records nothing either: a plain
    ``TerminationGuard()`` is the "no signal handling" value.

    As PID 1 in a container (no ``--init``) the kernel drops a
    ``SIG_DFL`` signal the process sends itself, so there the
    ``SystemExit(128 + signum)`` fallback is what ends the process
    (``docker stop`` reports 143). The same applies to a signal blocked
    in this thread.

    Windows: SIGTERM is never delivered from outside (``taskkill /F`` is
    ``TerminateProcess``, which cannot be intercepted); Ctrl-Break
    (SIGBREAK) also reaches the build directly, as it shares Pitloom's
    console.
    """

    def __init__(self) -> None:
        self.pending: signal.Signals | None = None
        self._owner: TerminationGuard | None = None
        # Handlers installed and not yet restored: only then does _handle act.
        self._armed = False
        self._pending_in_hold = False
        self._terminated = False
        self._holds = 0
        self._cleanups: list[Callable[[], None]] = []
        self._installed: list[signal.Signals] = []
        # One bound method, so "is it still ours" is an identity check.
        self._handler: Callable[[int, FrameType | None], None] = self._handle

    def raise_if_pending(self) -> None:
        """Raise :class:`TerminationSignal` once a signal was recorded."""
        if self.pending is not None:
            raise TerminationSignal(self.pending)

    def add_cleanup(self, callback: Callable[[], None]) -> None:
        """Run *callback* should the process be terminated by a signal, or
        the owner's block end by an exception, before the resource's owner
        released it. Must be idempotent and must not raise: it may run
        again after the owner's own call, or from the signal handler while
        an earlier run was cut short."""
        self._cleanups.append(callback)

    @contextlib.contextmanager
    def hold(self) -> Iterator[TerminationGuard]:
        """Hold a signal until the block is left, then end the process.

        For code that must not be cut short (creating the temporary
        directories and registering their removal, starting and killing
        the build tree); it may poll :meth:`raise_if_pending` to stop
        early. The first hold on an owning guard installs the handlers.
        """
        self._holds += 1
        try:
            self._arm()
            yield self
        finally:
            # Decrement first: a signal after it sees no hold and acts in
            # the handler; one before it is pending for the check below.
            self._holds -= 1
            if self.pending is not None and not self._holds:
                self._terminate(self.pending)

    def __enter__(self) -> TerminationGuard:
        if self._owner is not None:
            raise RuntimeError("TerminationGuard is already entered")
        owner: TerminationGuard | None = getattr(_thread_state, "owner", None)
        if owner is None:
            _thread_state.owner = owner = self
        self._owner = owner
        return owner

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        owner, self._owner = self._owner, None
        if owner is not self:
            return  # Nested: the owner's exit acts.
        try:
            if self.pending is not None and not self._terminated:
                # A termination an interrupt cut short, or a recorded
                # signal nothing acted on: the first signal still ends it.
                self._terminate(self.pending)
            elif exc is not None and not self._terminated:
                # The block failed before its owner released the resources.
                self._run_cleanups()
        finally:
            self._restore()
            self.pending = None
            self._pending_in_hold = False
            self._terminated = False
            self._cleanups.clear()
            _thread_state.owner = None

    def _handle(self, signum: int, frame: FrameType | None) -> None:
        del frame
        if not self._armed:
            # Installed although the guard no longer is (a failed restore,
            # or other code put it back): never swallow the signal, behave
            # as SIG_DFL would.
            signal.signal(signum, signal.SIG_DFL)
            signal.raise_signal(signum)
            return
        # The first signal wins; a repeat must not change the exit status
        # nor restart a termination under way.
        if self.pending is not None:
            return
        self.pending = signal.Signals(signum)
        self._pending_in_hold = self._holds > 0
        if not self._holds:
            self._terminate(self.pending)

    def _terminate(self, signum: signal.Signals) -> None:
        """Run the cleanups, then end the process by *signum*."""
        try:
            self._run_cleanups()
        finally:
            # Also when an interrupt cuts the cleanups short: a handler left
            # installed would swallow every later signal. The owner's exit
            # then finishes the termination (_terminated still unset).
            self._restore()
        self._terminated = True
        # Best effort: running in the handler, this may interrupt a write
        # to the same stream, which then raises instead of writing.
        with contextlib.suppress(Exception):
            log.warning(
                "%sreceived %s %s the build -- exiting after cleanup",
                BUILD_LOG_PREFIX,
                signum.name,
                "during" if self._pending_in_hold else "after",
            )
        signal.raise_signal(signum)
        raise SystemExit(128 + signum)

    def _arm(self) -> None:
        if self._owner is not self or self._armed:
            return
        self._armed = True
        for name in _TERMINATION_SIGNAL_NAMES:
            signum: signal.Signals | None = getattr(signal, name, None)
            if signum is None or signal.getsignal(signum) != signal.SIG_DFL:
                continue
            # Listed first, so an interrupt right after signal.signal()
            # cannot leave an unlisted handler behind.
            self._installed.append(signum)
            try:
                signal.signal(signum, self._handler)
            # ValueError: not the main thread (of the main interpreter).
            except (OSError, ValueError) as exc:
                self._installed.pop()
                log.debug("%scannot handle %s: %s", BUILD_LOG_PREFIX, name, exc)

    def _restore(self) -> None:
        while self._installed:
            signum = self._installed.pop()
            try:
                # Only while still ours: a handler other code installed
                # meanwhile replaced ours on purpose, and stays.
                if signal.getsignal(signum) is self._handler:
                    signal.signal(signum, signal.SIG_DFL)
            except (OSError, ValueError) as exc:
                log.debug("%scannot restore %s: %s", BUILD_LOG_PREFIX, signum.name, exc)
        # Last: a signal while restoring is still handled, not swallowed.
        self._armed = False

    def _run_cleanups(self) -> None:
        # Newest first, and kept rather than popped: when the handler cuts
        # this loop short, its own run repeats the interrupted callback.
        for cleanup in reversed(self._cleanups):
            # Must not raise; if one does anyway (e.g. its WARNING: hit a
            # write the handler interrupted), the rest still run.
            with contextlib.suppress(Exception):
                cleanup()
