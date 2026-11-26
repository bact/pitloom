# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parse a script for the usage scan on a stack sized to its text.

Turning a long left-recursive chain (``a.b.b...``, ``f()()...``,
``a[0][0]...``, ``"a" + "a" + ...``) into a tree recurses once per link in
C. Python 3.10 checks no depth there and overflows the stack: the process
dies with no message, at about 40,000 links on a 2 MiB stack (the main thread
on Windows) and 130,000 on 8 MiB. Python 3.11 to 3.13 raise
``RecursionError`` on a stack of 2 MiB or more, but still crash on a thread
of 512 KiB. So the parse runs in a thread of its own, with a stack of 8 MiB.
On Python 3.10 that stack grows with the text: a link takes two characters
or more and about 64 bytes of stack (CPython 3.10 on Linux), so
:data:`_PARSE_STACK_PER_CHAR` leaves a fourfold margin for the 1 MiB the
usage scan reads. Later versions keep 8 MiB, the depth they refuse on the
main thread of Linux (3.14 measures its stack, and would read deeper chains
on a larger one).

See also: :mod:`pitloom.extract._usage_ast` (the walk of the tree) and
:mod:`pitloom.extract._usage_attach` (what a parse failure says).
"""

from __future__ import annotations

import ast
import logging
import sys
import warnings
from _thread import LockType, allocate_lock, start_new_thread
from collections import deque
from collections.abc import Callable
from functools import partial
from operator import methodcaller
from sys import setprofile, settrace
from threading import Lock, getprofile, gettrace, stack_size
from time import sleep
from typing import Final, TypeVar

from pitloom.core.internal_error import reraise_internal
from pitloom.core.warning_capture import WARNINGS_LOCK

__all__ = ["PARSE_ERRORS", "parse_python", "python_version", "stack_bytes"]

log = logging.getLogger("pitloom.extract.scanner")

#: What parsing a file can raise besides a mistake in it: a null byte
#: (``ValueError`` before Python 3.12), a tree too deep for the parser
#: (``MemoryError``) or the compiler (``RecursionError``). A file can also
#: fail only on this Python: syntax it is too old to know.
PARSE_ERRORS: Final = (SyntaxError, ValueError, MemoryError, RecursionError)

_MIB: Final = 1024 * 1024
#: Stack per character of text, and the bounds of the parse thread's stack:
#: 8 MiB is the default main-thread stack on Linux; Windows refuses a thread
#: stack of 256 MiB or more. Whole MiB fit every page size (4 to 64 KiB).
_PARSE_STACK_PER_CHAR: Final = 128
_PARSE_STACK_FLOOR: Final = 8 * _MIB
_PARSE_STACK_CEILING: Final = 255 * _MIB
#: Whether this Python checks the depth of the tree it builds (3.11 or later).
_CHECKS_DEPTH: Final = sys.version_info >= (3, 11)
#: ``threading.stack_size`` is process-wide: one caller sets it at a time.
_STACK_SIZE_LOCK: Final = Lock()
_CALL: Final = methodcaller("__call__")
#: Seconds the parse thread waits before each new try to install the hooks
#: of :mod:`threading` and begin its work: on Python 3.10 and 3.11 an install
#: fails while another thread is installing one, until that one is done.
_HOOK_RETRY_WAITS: Final = (0.001, 0.004, 0.016)

_T = TypeVar("_T")


def python_version() -> str:
    """The running interpreter as ``3.10``: the grammar a file was read as."""
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _parse(source: str) -> ast.Module:
    """*source* as a module tree, its warnings dropped. The filters are
    process-wide: :data:`pitloom.core.warning_capture.WARNINGS_LOCK` keeps
    Pitloom's other blocks that change them out meanwhile."""
    with WARNINGS_LOCK, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(source)


def stack_bytes(chars: int, *, checks_depth: bool = _CHECKS_DEPTH) -> int:
    """The parse thread's stack for a text of *chars* characters, in whole
    MiB between the floor and the ceiling; the floor on a Python that
    *checks_depth*."""
    if checks_depth:
        return _PARSE_STACK_FLOOR
    wanted = -(-chars * _PARSE_STACK_PER_CHAR // _MIB) * _MIB
    return min(max(wanted, _PARSE_STACK_FLOOR), _PARSE_STACK_CEILING)


def _in_order(*calls: Callable[[], object]) -> Callable[[], object]:
    """One call, good once, that makes *calls* in turn from C (``map`` over
    them): the interpreter switches threads only between bytecodes, so no
    other Python thread runs between two calls of C functions that run no
    Python code themselves."""
    return partial(deque, map(_CALL, calls), 0)


def _hooked_call(call: Callable[[], _T], begun: Callable[[], bool]) -> _T:
    """*call* in this thread under the trace and profile hooks of
    :mod:`threading` (coverage, profilers), installed as
    :class:`threading.Thread` does when one is set; *call* begins at most
    once.

    A try fails when an install raises or when a hook raises at *call*'s
    first event, which aborts the call before its first statement (CPython
    then unsets that hook). On Python 3.10 and 3.11 both happen while
    another thread installs a hook: the flag is process-wide, an audit hook
    written in Python lets threads switch in between, and coverage installs
    its tracer from within its trace function. A failed try is made again
    after each of :data:`_HOOK_RETRY_WAITS`, then *call* runs with both
    hooks unset (said at DEBUG: the thread is only unseen by a coverage
    tool or profiler). Once *begun* says true, an exception propagates.
    *begun* must be a C callable: a Python one would be a call a hook can
    abort."""
    trace, profile = gettrace(), getprofile()
    failures: list[Exception] = []
    for wait in _HOOK_RETRY_WAITS:
        try:
            if trace is not None:
                settrace(trace)
            if profile is not None:
                setprofile(profile)
            return call()
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:  # tried again, else run without the hooks
            if begun():
                raise
            failures[:] = [exc]
        sleep(wait)
    # Unset before the log: logging is a call a hook can abort.
    for unset in (settrace, setprofile):
        try:
            unset(None)
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:  # a hook left set: the call runs under it
            failures.append(exc)
    log.debug(
        "Usage scan: parse thread runs without hooks%s: %s",
        ", but one may stay set" if len(failures) > 1 else "",
        failures[-1],
    )
    return call()


def _hooked_outcome(
    call: Callable[[], _T],
    begun: Callable[[], bool],
    outcome: list[_T | BaseException],
    done: LockType,
) -> None:
    """The parse thread's first frame: :func:`_hooked_call` of *call*, its
    result or exception put in *outcome*, then *done* released. The frame
    is entered before any hook is installed, and a trace hook, or a hook
    at an earlier event, cannot stop it short of the release, whatever it
    does in the frames below. A profile hook that raises at the very C
    call that releases *done* still can (a ``c_call`` event fires in this
    frame, and a raise there skips the call; CPython then unsets the
    hook): that needs a deliberately hostile hook, and no known tool does
    it. Coverage uses a trace function only."""
    try:
        outcome.append(_hooked_call(call, begun))
    # pylint: disable-next=broad-exception-caught
    except BaseException as exc:  # raised again in the caller's thread
        outcome.append(exc)
    finally:
        done.release()


def _start_with_stack(work: Callable[[], None], size: int) -> bool:
    """Run *work* on a new thread with a stack of *size* bytes; ``False``
    when the size or the thread is refused (it is then not started). The
    thread starts with no trace or profile hook, so *work*'s own frame
    sees none: it can install them (see :func:`_hooked_call`).

    ``threading.stack_size`` is process-wide, so the size is set, the thread
    started and the size put back in one :func:`_in_order` call.
    ``_thread.start_new_thread`` returns once the thread exists, without
    waiting for it to run as ``threading.Thread.start`` does (that wait lets
    other threads run and start theirs with this size). On Python 3.10 and
    3.11 no other Python thread, the host's included, runs while the size is
    set. From 3.12 ``_thread.start_new_thread`` raises an audit event, so a
    Python audit hook (the host's, or the one
    :mod:`pitloom.core._models_wheel_unlistable` installs) runs in between,
    and other threads with it; they can then see, and start a thread with,
    only the floor, since every size above it is Python 3.10's.
    """
    with _STACK_SIZE_LOCK:
        previous = stack_size()
        start = _in_order(
            partial(stack_size, size),
            partial(start_new_thread, work, ()),
            partial(stack_size, previous),
        )
        try:
            start()
        except (ValueError, RuntimeError) as exc:
            reraise_internal(exc)
            log.debug("Usage scan: no parse thread with a %d-byte stack: %s", size, exc)
            return False
        finally:
            stack_size(previous)
    return True


def parse_python(text: str) -> ast.Module:
    """*text* as a module tree, parsed on a stack sized to it (see the module
    docstring). A leading byte-order mark is dropped. An invalid escape
    (``"data\\model.ftz"``) only warns on the way, whatever the user's
    warning filters say, so the warning is dropped. When the stack or the
    thread is refused, a text that wants more than the floor (Python 3.10)
    is tried on a thread with the floor's stack and else refused as too
    deep, since the caller's own stack could overflow; any other text is
    parsed on the caller's stack.

    Raises:
        SyntaxError: Not Python of this interpreter's grammar (or, after
            3.12, a null byte).
        ValueError: A null byte (before Python 3.12).
        MemoryError: The source nests too deeply for the parser, or wants a
            larger stack than any thread could be started with.
        RecursionError: The source nests too deeply for the compiler.
    """
    source = text.removeprefix("\ufeff")
    outcome: list[ast.Module | BaseException] = []
    done = allocate_lock()
    done.acquire()
    begun: list[None] = []

    def parse() -> ast.Module:
        begun.append(None)  # first: a hook can abort the call before it
        return _parse(source)

    work = partial(_hooked_outcome, parse, partial(bool, begun), outcome, done)
    size = stack_bytes(len(source))
    # More than the floor only on Python 3.10, which would crash, not raise,
    # on a stack too small for the text.
    beyond_floor = size > _PARSE_STACK_FLOOR
    started = _start_with_stack(work, size) or (
        beyond_floor and _start_with_stack(work, _PARSE_STACK_FLOOR)
    )
    if not started:
        if beyond_floor:
            raise MemoryError
        return _parse(source)
    done.acquire()
    result = outcome.pop()
    if isinstance(result, BaseException):
        raise result
    return result
