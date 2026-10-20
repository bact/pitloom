# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Run a call with a time bound, for tests of input whose cost could grow
without bound: a slow call fails the test instead of hanging CI. The bound
is generous; only an unbounded cost misses it.

Which to use:

* :func:`run_bounded_in_child` for a call that may spend its time in one
  C call -- a regular expression (author splitters, copyright notices)
  holds the GIL until it returns, so no thread of this process can stop
  it, nor even time it out. The call runs in a child interpreter, killed
  at the bound.
* :func:`run_bounded` for a pure-Python loop or recursion: it gives the
  GIL back, so the join times out; it takes any callable (a closure), and
  the call's log records reach ``caplog``. A call still running at the
  bound keeps running in a daemon thread until the session ends.
"""

from __future__ import annotations

import pickle  # nosec B403 -- this process's own objects, to its own child
import subprocess  # nosec B404
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import pytest

_T = TypeVar("_T")

#: Seconds a bounded call may take: tens of times what it needs.
BOUND_SECONDS = 20.0


def run_bounded(call: Callable[[], _T], seconds: float = BOUND_SECONDS) -> _T:
    """*call*'s result, or a test failure when it is still running after
    *seconds*, or took longer. An exception it raises is raised here. For
    a pure-Python call only: see the module's docstring."""
    results: list[_T] = []
    errors: list[BaseException] = []
    took: list[float] = []

    def _target() -> None:
        start = time.monotonic()
        try:
            results.append(call())
        # pylint: disable-next=broad-exception-caught
        except BaseException as exc:  # re-raised below, in the test's thread
            errors.append(exc)
        took.append(time.monotonic() - start)

    # A daemon thread: one still running does not hold the test run open.
    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=seconds)
    if worker.is_alive() or took[0] > seconds:
        pytest.fail(f"still running after {seconds} s")
    if errors:
        raise errors[0]
    return results[0]


#: The child: loads ``(sys.path, target, args, kwargs)``, calls the target
#: (``module:qualified.name``) with stdout sent to stderr, and writes
#: ``(raised, result or exception)`` to its stdout.
_CHILD = """\
import importlib, pickle, sys
path, target, args, kwargs = pickle.load(sys.stdin.buffer)
sys.path[:0] = path
out, sys.stdout = sys.stdout.buffer, sys.stderr
module, _, name = target.partition(":")
call = importlib.import_module(module)
for part in name.split("."):
    call = getattr(call, part)
try:
    outcome = (False, call(*args, **kwargs))
except BaseException as exc:
    outcome = (True, exc)
out.write(pickle.dumps(outcome))
"""


def run_bounded_in_child(
    target: str, *args: Any, seconds: float = BOUND_SECONDS, **kwargs: Any
) -> Any:
    """``target(*args, **kwargs)`` run in a child interpreter, *target*
    named ``"module:qualified.name"``; its result, or a test failure when
    the child is still running after *seconds* (it is killed then: the
    test fails at the bound, and nothing is left running). Arguments,
    result and an exception it raises (raised here) must pickle. The child
    sees this process's ``sys.path``; its log records do not reach
    ``caplog``."""
    request = pickle.dumps((sys.path, target, args, kwargs))
    start = time.monotonic()
    try:
        # pylint: disable-next=subprocess-run-check
        done = subprocess.run(  # nosec B603 -- this interpreter, fixed code
            [sys.executable, "-c", _CHILD],
            input=request,
            capture_output=True,
            timeout=seconds,
            cwd=Path(__file__).resolve().parents[1],
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        pytest.fail(f"{target}: killed, still running after {elapsed:.1f} s")
    if done.returncode:
        tail = done.stderr.decode(errors="replace")[-2000:]
        pytest.fail(f"{target}: child exited {done.returncode}\n{tail}")
    raised, value = pickle.loads(done.stdout)  # nosec B301
    if raised:
        raise value
    return value
