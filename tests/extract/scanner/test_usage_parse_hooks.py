# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the trace and profile hooks of :mod:`threading` in the usage
scan's parse thread (:mod:`pitloom.extract._usage_parse`): the parse runs,
and its caller gets the tree, whatever installing a hook does.

On Python 3.10 and 3.11 installing a hook raises ``RuntimeError`` while
another thread is installing one, which an audit hook written in Python
(Pitloom's own, say) lets happen. Coverage installs its tracer from within
its trace function, at the thread's first call: when that raises, CPython
aborts the call before its first statement.

See also: :mod:`tests.extract.scanner.test_usage_parse` (the parse thread's
stack).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from unittest.mock import MagicMock, call, patch

import pytest

from pitloom.extract import _usage_parse
from tests._bounded import run_bounded_in_child


def _hook(*_: object) -> None:
    """A trace or profile function that sees nothing."""


def parse_with_the_hook_refused(event: str) -> int:
    """In a child: the statements :func:`parse_python` finds while an audit
    hook refuses *event* (``sys.settrace`` or ``sys.setprofile``) and the
    hooks of :mod:`threading` are set, as under coverage or a profiler."""

    def refuse(name: str, _: tuple[object, ...]) -> None:
        if name == event:
            raise RuntimeError(f"{event} refused")

    sys.addaudithook(refuse)
    threading.settrace(_hook)
    threading.setprofile(_hook)
    return len(_usage_parse.parse_python("x = 1\ny = 2\n").body)


@pytest.mark.parametrize("event", ["sys.settrace", "sys.setprofile"])
def test_a_refused_hook_still_parses_and_returns(event: str) -> None:
    # The parse thread used to stop at the refused install, before the
    # parse: the caller then waited for it for ever.
    assert run_bounded_in_child(f"{__name__}:parse_with_the_hook_refused", event) == 2


def parse_with_a_hook_raising_first(kind: str) -> tuple[int, int, bool]:
    """In a child: the statements :func:`parse_python` finds when the trace
    or profile hook of :mod:`threading` (*kind*) raises at its first event
    in each thread, as coverage's own install can on Python 3.10 and 3.11;
    with how often it raised, and whether it saw any event after."""
    raised: set[int] = set()
    later: list[str] = []

    def hook(_: object, event: str, __: object) -> None:
        if threading.get_ident() not in raised:
            raised.add(threading.get_ident())
            raise RuntimeError("Cannot install a trace function while ...")
        later.append(event)

    getattr(threading, f"set{kind}")(hook)
    statements = len(_usage_parse.parse_python("x = 1\ny = 2\n").body)
    return statements, len(raised), bool(later)


@pytest.mark.parametrize("kind", ["trace", "profile"])
def test_a_hook_raising_at_the_first_call_still_parses_and_returns(
    kind: str,
) -> None:
    # A trace function raising at the parse's first call used to abort it
    # before its first statement: the caller then waited for it for ever.
    # The hook, tried again, then sees the parse.
    assert run_bounded_in_child(
        f"{__name__}:parse_with_a_hook_raising_first", kind
    ) == (2, 1, True)


def _hooked_call(
    work: Callable[[], object], begun: Callable[[], bool] = lambda: False
) -> object:
    return _usage_parse._hooked_call(  # pylint: disable=protected-access
        work, begun
    )


@pytest.mark.parametrize(
    ("failures", "waits"),
    [(0, []), (1, [0.001]), (2, [0.001, 0.004])],
    ids=["first-try", "second-try", "third-try"],
)
@pytest.mark.parametrize("failing", ["install", "call"])
def test_a_failed_try_is_made_again_after_a_wait(
    failures: int, waits: list[float], failing: str, caplog: pytest.LogCaptureFixture
) -> None:
    tries: list[str] = []

    def install(_: object) -> None:
        tries.append("install")
        if failing == "install" and tries.count("install") <= failures:
            raise RuntimeError("another trace function is being installed")

    def work() -> str:
        tries.append("call")
        if failing == "call" and tries.count("call") <= failures:
            raise RuntimeError("raised at the call event")
        return "tree"

    with (
        patch.object(_usage_parse, "gettrace", return_value=_hook),
        patch.object(_usage_parse, "getprofile", return_value=None),
        patch.object(_usage_parse, "settrace", side_effect=install),
        patch.object(_usage_parse, "setprofile") as setprofile,
        patch.object(_usage_parse, "sleep", autospec=True) as sleep,
        caplog.at_level(logging.DEBUG, logger="pitloom.extract.scanner"),
    ):
        assert _hooked_call(work) == "tree"
    # Each try installs the hook again; a refused install makes no call.
    each = ["install"] if failing == "install" else ["install", "call"]
    assert tries == each * failures + ["install", "call"]
    assert [c.args[0] for c in sleep.call_args_list] == waits
    # No profile hook set: none installed, as threading.Thread does.
    setprofile.assert_not_called()
    assert not caplog.records


@pytest.mark.parametrize("unset_refused", [False, True], ids=["unset", "refused"])
def test_the_last_try_runs_with_the_hooks_unset_and_says_so(
    unset_refused: bool, caplog: pytest.LogCaptureFixture
) -> None:
    def install(hook: object) -> None:
        if hook is not None or unset_refused:
            raise RuntimeError("another trace function is being installed")

    work = MagicMock(return_value="tree")
    with (
        patch.object(_usage_parse, "gettrace", return_value=_hook),
        patch.object(_usage_parse, "getprofile", return_value=_hook),
        patch.object(_usage_parse, "settrace", side_effect=install) as settrace,
        patch.object(_usage_parse, "setprofile") as setprofile,
        patch.object(_usage_parse, "sleep", autospec=True) as sleep,
        caplog.at_level(logging.DEBUG, logger="pitloom.extract.scanner"),
    ):
        assert _hooked_call(work) == "tree"
    # Three refused tries, then both hooks unset (each tried), then the call.
    assert settrace.call_args_list == [call(_hook)] * 3 + [call(None)]
    assert setprofile.call_args_list == [call(None)]
    assert sleep.call_count == 3
    work.assert_called_once_with()
    assert [r.levelno for r in caplog.records] == [logging.DEBUG]
    said = caplog.records[0].getMessage()
    assert "runs without hooks" in said
    assert ("may stay set" in said) is unset_refused


def test_the_call_is_never_made_again_once_begun() -> None:
    begun: list[None] = []

    def work() -> None:
        begun.append(None)
        raise RuntimeError("raised in the work")

    with (
        patch.object(_usage_parse, "gettrace", return_value=_hook),
        patch.object(_usage_parse, "settrace"),
        patch.object(_usage_parse, "sleep", autospec=True) as sleep,
        pytest.raises(RuntimeError, match="raised in the work"),
    ):
        _hooked_call(work, lambda: bool(begun))
    assert len(begun) == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("profile", [None, _hook], ids=["none", "profile-only"])
def test_only_a_hook_that_is_set_is_installed(profile: object) -> None:
    work = MagicMock()
    with (
        patch.object(_usage_parse, "gettrace", return_value=None),
        patch.object(_usage_parse, "getprofile", return_value=profile),
        patch.object(_usage_parse, "settrace") as settrace,
        patch.object(_usage_parse, "setprofile") as setprofile,
    ):
        _hooked_call(work)
    settrace.assert_not_called()
    assert [c.args for c in setprofile.call_args_list] == (
        [(profile,)] if profile else []
    )
    work.assert_called_once_with()


def test_an_interrupted_install_is_not_tried_again() -> None:
    work = MagicMock()
    with (
        patch.object(_usage_parse, "gettrace", return_value=_hook),
        patch.object(_usage_parse, "settrace", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        _hooked_call(work)
    work.assert_not_called()


def parse_interrupted() -> str:
    """In a child: what :func:`parse_python` raises when the parse thread
    is interrupted before the parse."""
    with patch.object(_usage_parse, "_hooked_call", side_effect=KeyboardInterrupt):
        try:
            _usage_parse.parse_python("x = 1\n")
        except KeyboardInterrupt as exc:
            return type(exc).__name__
    return "returned"


def test_an_interrupt_in_the_parse_thread_reaches_the_caller() -> None:
    assert run_bounded_in_child(f"{__name__}:parse_interrupted") == (
        "KeyboardInterrupt"
    )
