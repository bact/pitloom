# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the trace and profile hooks of :mod:`threading` in the usage
scan's parse thread (:mod:`pitloom.extract._usage_parse`): the parse runs,
and its caller gets the tree, whatever installing a hook does.

On Python 3.10 and 3.11 installing a hook raises ``RuntimeError`` while
another thread is installing one, which an audit hook written in Python
(Pitloom's own, say) lets happen.

See also: :mod:`tests.extract.scanner.test_usage_parse` (the parse thread's
stack).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import sys
import threading
from unittest.mock import MagicMock, patch

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


@pytest.mark.parametrize(
    ("failures", "waits"),
    [(0, []), (1, [0.001]), (3, [0.001, 0.004, 0.016])],
    ids=["first-try", "second-try", "last-try"],
)
def test_a_hook_is_tried_again_after_a_wait(
    failures: int, waits: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    attempts: list[object] = []

    def install(hook: object) -> None:
        attempts.append(hook)
        if len(attempts) <= failures:
            raise RuntimeError("another trace function is being installed")

    work = MagicMock()
    with (
        patch.object(_usage_parse, "gettrace", return_value=_hook),
        patch.object(_usage_parse, "getprofile", return_value=None),
        patch.object(_usage_parse, "settrace", side_effect=install),
        patch.object(_usage_parse, "setprofile") as setprofile,
        patch.object(_usage_parse, "sleep", autospec=True) as sleep,
        caplog.at_level(logging.DEBUG, logger="pitloom.extract.scanner"),
    ):
        _usage_parse._under_threading_hooks(  # pylint: disable=protected-access
            work
        )
    assert attempts == [_hook] * (failures + 1)
    assert [call.args[0] for call in sleep.call_args_list] == waits
    # No profile hook set: none installed, as threading.Thread does.
    setprofile.assert_not_called()
    work.assert_called_once_with()
    assert not caplog.records


@pytest.mark.parametrize("kind", ["trace", "profile"])
def test_a_hook_never_installed_is_said_at_debug_and_the_work_runs(
    kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    refused = RuntimeError("another function is being installed")
    work = MagicMock()
    with (
        patch.object(_usage_parse, "gettrace", return_value=_hook),
        patch.object(_usage_parse, "getprofile", return_value=_hook),
        patch.object(
            _usage_parse, "settrace", side_effect=refused if kind == "trace" else None
        ) as settrace,
        patch.object(
            _usage_parse,
            "setprofile",
            side_effect=refused if kind == "profile" else None,
        ) as setprofile,
        patch.object(_usage_parse, "sleep", autospec=True) as sleep,
        caplog.at_level(logging.DEBUG, logger="pitloom.extract.scanner"),
    ):
        _usage_parse._under_threading_hooks(  # pylint: disable=protected-access
            work
        )
    # Four tries of the refused hook, one of the other.
    tries = {"trace": settrace.call_count, "profile": setprofile.call_count}
    assert tries == {kind: 4, ({"trace", "profile"} - {kind}).pop(): 1}
    assert sleep.call_count == 3
    work.assert_called_once_with()
    assert [r.levelno for r in caplog.records] == [logging.DEBUG]
    assert f"without the {kind} hook" in caplog.records[0].getMessage()


@pytest.mark.parametrize("profile", [None, _hook], ids=["none", "profile-only"])
def test_only_a_hook_that_is_set_is_installed(profile: object) -> None:
    work = MagicMock()
    with (
        patch.object(_usage_parse, "gettrace", return_value=None),
        patch.object(_usage_parse, "getprofile", return_value=profile),
        patch.object(_usage_parse, "settrace") as settrace,
        patch.object(_usage_parse, "setprofile") as setprofile,
    ):
        _usage_parse._under_threading_hooks(  # pylint: disable=protected-access
            work
        )
    settrace.assert_not_called()
    assert [call.args for call in setprofile.call_args_list] == (
        [(profile,)] if profile else []
    )
    work.assert_called_once_with()


def test_the_work_runs_even_when_the_install_is_interrupted() -> None:
    work = MagicMock()
    with (
        patch.object(_usage_parse, "gettrace", return_value=_hook),
        patch.object(_usage_parse, "settrace", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        _usage_parse._under_threading_hooks(  # pylint: disable=protected-access
            work
        )
    work.assert_called_once_with()
