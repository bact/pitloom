# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The build and temporary-directory families: each entry's code, level,
condition, effect, actor, release and fields; each line printed through the
real sink after its frame and trusted; the closed ``signal`` and
``activity`` fields and the ``exit_code`` and ``process_group`` patterns;
the helpers that choose a line; and ``build_error``.

See also: tests/messages/test_build_hostile.py (a hostile value in each new
field), tests/messages/test_frames_build.py (the frames and the signal
line of each activity), tests/core/models_wheel/test_models_wheel_build_codes.py
(the lines a real build says) and tests/messages/test_build_surfaces.py (the
command line and the library).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.logging_config import CODE_ATTR, configure_logging
from pitloom.messages import (
    BUILD_FRAME,
    FAMILY_TOPICS,
    GIT_FRAME,
    HF_FRAME,
    HOOK_STEP_FRAME,
    MESSAGES,
    PYPI_FRAME,
    SCAN_FRAME,
    Frame,
    Line,
    Message,
    code_of,
    emit,
    trusted_message,
)
from pitloom.messages.build import (
    BUILD_CODE_UNSAFE,
    BUILD_EMPTY_WHEEL_LINE,
    BUILD_EXIT_LINE,
    BUILD_FAILED,
    BUILD_INTERPRETER_LINE,
    BUILD_PROCESSES_UNSAFE,
    BUILD_TIMED_OUT_LINE,
    BUILD_TIMED_OUT_UNCONFIRMED_LINE,
    BUILD_TIMEOUT,
    BUILD_UNUSABLE_LINE,
    BUILD_WHEEL_COUNT_LINE,
    INTERRUPTED,
    INTERRUPTED_AFTER_LINE,
    INTERRUPTED_DURING_LINE,
    PROCESSES_KILLED_LINE,
    TEMP_DIR_UNWRITABLE,
    UNSAFE_NO_MODULE_LINE,
    UNSAFE_NO_MODULE_SHARED_LINE,
    UNSAFE_STATIC_FAILED_LINE,
    UNSAFE_STATIC_FAILED_SHARED_LINE,
    BuildFailedError,
    build_error,
    interrupted_line,
    timeout_line,
    unsafe_line,
)
from tests._message_drift import SAMPLES

pytestmark = pytest.mark.platform  # a Windows path value, escapes

_LOG = logging.getLogger("pitloom.test_build")
_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

_Shape = tuple[str, frozenset[str]]


def _shapes(*lines: tuple[str, str]) -> list[_Shape]:
    """``(level, "a b")`` pairs as ``(level, {"a", "b"})`` pairs, sorted."""
    return sorted((lv, frozenset(names.split())) for lv, names in lines)


_UNSAFE = ("WARNING", "dir duration backend")

#: Each entry: its code, condition, effect, actor, subject key and the
#: (level, fields) of each of its lines, spelt out here and not read from the
#: entry.
_ENTRIES = [
    (
        BUILD_CODE_UNSAFE,
        ("build-code-unsafe", "unsafe", "none", "user", "DIR"),
        _shapes(_UNSAFE, _UNSAFE, _UNSAFE, _UNSAFE),
    ),
    (
        BUILD_FAILED,
        ("build-failed", "build-failed", "weaker", "user", "DIR"),
        _shapes(
            ("WARNING", "dir"),
            ("WARNING", "dir exit_code output"),
            ("WARNING", "dir number"),
            ("WARNING", "dir"),
            ("WARNING", "dir failure"),
        ),
    ),
    (
        BUILD_TIMEOUT,
        ("build-timeout", "timeout", "weaker", "user", "DIR"),
        _shapes(("WARNING", "dir duration"), ("WARNING", "dir duration")),
    ),
    (
        BUILD_PROCESSES_UNSAFE,
        ("build-processes-unsafe", "unsafe", "none", "user", ""),
        _shapes(("INFO", "process_group"), ("WARNING", "process_group")),
    ),
    (
        TEMP_DIR_UNWRITABLE,
        ("temp-dir-unwritable", "unwritable", "none", "user", "DIR"),
        _shapes(("WARNING", "dir")),
    ),
    (
        INTERRUPTED,
        ("interrupted", "interrupted", "not-written", "user", ""),
        _shapes(
            ("WARNING", "signal activity"),
            ("WARNING", "signal activity"),
            ("ERROR", ""),
        ),
    ),
]
_ENTRY_IDS = ["unsafe", "failed", "timeout", "processes", "temp-dir", "interrupted"]


@pytest.mark.parametrize(("message", "facts", "shapes"), _ENTRIES, ids=_ENTRY_IDS)
def test_each_new_entry_says_what_the_plan_names(
    message: Message, facts: tuple[str, ...], shapes: list[_Shape]
) -> None:
    code, condition, effect, actor, subject = facts
    assert (message.code, message.condition) == (code, condition)
    assert (message.effect, message.actor) == (effect, actor)
    assert message.since == "0.25.0"
    assert (message.subject_key or "") == subject
    assert MESSAGES[code] is message
    assert sorted((ln.level, ln.fields) for ln in message.lines) == shapes


def test_the_build_families_are_on_the_build_page() -> None:
    assert {FAMILY_TOPICS[m.family] for m, *_ in _ENTRIES} == {"build"}


# -- every line, printed through the sink after its frame ------------------------


def _values(line: Line) -> dict[str, Any]:
    """A sample value of each field *line* names."""
    return {n: SAMPLES[n] for n in line.fields}


def _say(
    capsys: pytest.CaptureFixture[str],
    message: Message,
    line: Line,
    frame: Frame | None = BUILD_FRAME,
    **values: Any,
) -> str:
    """What *line* of *message* prints after *frame*, for *values*."""
    configure_logging()
    level = getattr(logging, line.level)
    emit(_LOG, message, level, line=line, frame=frame, **values)
    return capsys.readouterr().err


def _frame_of(line: Line) -> Frame | None:
    """The frame a line is said after: the Ctrl-C line has none."""
    return None if line.level == "ERROR" else BUILD_FRAME


@pytest.mark.parametrize(
    ("message", "line"),
    [
        pytest.param(m, ln, id=f"{m.code}-{i}")
        for m in (message for message, *_ in _ENTRIES)
        for i, ln in enumerate(m.lines)
    ],
)
def test_each_printed_line_is_trusted_after_its_frame(
    capsys: pytest.CaptureFixture[str], message: Message, line: Line
) -> None:
    frame = _frame_of(line)
    (err,) = _say(capsys, message, line, frame, **_values(line)).splitlines()
    prefix = "" if frame is None else frame.render({})
    assert err.startswith(f"{line.level}: {prefix}")
    assert err.endswith(f" [{message.code}]")
    assert trusted_message(err) is message


@pytest.mark.parametrize(
    "frame",
    [GIT_FRAME, HF_FRAME, PYPI_FRAME, SCAN_FRAME, HOOK_STEP_FRAME, BUILD_FRAME],
    ids=["git", "hf", "pypi", "scan", "hook", "build"],
)
def test_the_temp_dir_line_is_trusted_after_every_frame_that_allows_it(
    capsys: pytest.CaptureFixture[str], frame: Frame
) -> None:
    (line,) = TEMP_DIR_UNWRITABLE.lines
    err = _say(capsys, TEMP_DIR_UNWRITABLE, line, frame, dir="pitloom-x1y2z3")
    assert err == (
        f"WARNING: {frame.render({})}DIR=pitloom-x1y2z3: could not be fully "
        "removed; left in the system temp directory [temp-dir-unwritable]\n"
    )
    assert trusted_message(err.rstrip("\n")) is TEMP_DIR_UNWRITABLE


def test_the_code_and_the_frame_ride_on_the_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        emit(
            _LOG,
            BUILD_PROCESSES_UNSAFE,
            logging.INFO,
            frame=BUILD_FRAME,
            process_group=4321,
        )
    (record,) = caplog.records
    assert getattr(record, CODE_ATTR) == "build-processes-unsafe"
    assert record.getMessage() == (
        "Build: the build left processes running (process group 4321); killed"
    )


# -- the helpers that choose a line ------------------------------------------------


@pytest.mark.parametrize(
    ("static_failed", "isolated", "line", "words"),
    [
        (False, True, UNSAFE_NO_MODULE_LINE, ("no discovery module", "isolated")),
        (
            True,
            True,
            UNSAFE_STATIC_FAILED_LINE,
            ("static discovery failed", "isolated"),
        ),
        (
            False,
            False,
            UNSAFE_NO_MODULE_SHARED_LINE,
            ("no discovery module", "Pitloom"),
        ),
        (
            True,
            False,
            UNSAFE_STATIC_FAILED_SHARED_LINE,
            ("static discovery", "no build"),
        ),
    ],
    ids=["no-module", "static-failed", "no-module-shared", "static-failed-shared"],
)
def test_unsafe_line_is_chosen_by_both_flags(
    static_failed: bool, isolated: bool, line: Line, words: tuple[str, str]
) -> None:
    chosen = unsafe_line(static_failed=static_failed, isolated=isolated)
    assert chosen is line and line in BUILD_CODE_UNSAFE.lines
    assert all(word in line.template for word in words)
    texts = {
        unsafe_line(static_failed=s, isolated=i).template
        for s in (False, True)
        for i in (False, True)
    }
    assert len(texts) == 4  # no two choices say the same


@pytest.mark.parametrize(
    ("tree_terminated", "line"),
    [(True, BUILD_TIMED_OUT_LINE), (False, BUILD_TIMED_OUT_UNCONFIRMED_LINE)],
    ids=["terminated", "unconfirmed"],
)
def test_timeout_line_is_chosen_by_the_confirmation(
    tree_terminated: bool, line: Line
) -> None:
    assert timeout_line(tree_terminated=tree_terminated) is line
    assert ("its process tree was stopped" in line.template) is tree_terminated
    assert ("could not confirm" in line.template) is not tree_terminated


@pytest.mark.parametrize(
    ("in_hold", "line", "word"),
    [
        (True, INTERRUPTED_DURING_LINE, "during"),
        (False, INTERRUPTED_AFTER_LINE, "after"),
    ],
    ids=["during", "after"],
)
def test_interrupted_line_is_chosen_by_the_hold(
    in_hold: bool, line: Line, word: str
) -> None:
    assert interrupted_line(in_hold=in_hold) is line
    assert f"received %(signal)s {word} " in line.template


# -- build_error --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "values"),
    [
        (BUILD_INTERPRETER_LINE, {"dir": Path("p")}),
        (BUILD_EXIT_LINE, {"dir": Path("p"), "exit_code": 1, "output": "boom"}),
        (BUILD_WHEEL_COUNT_LINE, {"dir": Path("p"), "number": 2}),
        (BUILD_EMPTY_WHEEL_LINE, {"dir": Path("p")}),
        (BUILD_UNUSABLE_LINE, {"dir": Path("p"), "failure": OSError("no space")}),
    ],
    ids=["interpreter", "exit", "wheel-count", "empty", "unusable"],
)
def test_build_error_carries_its_line_values_and_code(
    line: Line, values: dict[str, Any]
) -> None:
    error = build_error(line, **values)
    assert isinstance(error, BuildFailedError)
    assert error.said == (line, values) and error.said[1] is not values
    assert code_of(error) == getattr(error, CODE_ATTR) == "build-failed"
    # Its text is the line only: no frame, level or code (said again later).
    text = str(error)
    assert text.startswith("DIR=") and "Build:" not in text and "[" not in text


@pytest.mark.parametrize(
    ("line", "values"),
    [
        (BUILD_EXIT_LINE, {"dir": Path("p")}),  # a value missing
        (BUILD_EXIT_LINE, {"dir": Path("p"), "exit_code": 1, "output": "x", "y": 1}),
        (BUILD_TIMED_OUT_LINE, {"dir": Path("p"), "duration": 1}),  # another entry's
        (BUILD_WHEEL_COUNT_LINE, {"dir": Path("p"), "number": -1}),
        (BUILD_EXIT_LINE, {"dir": Path("p"), "exit_code": "1", "output": "x"}),
    ],
    ids=["missing", "extra", "other-entry", "negative-count", "text-exit-code"],
)
def test_build_error_refuses_a_line_or_value_that_does_not_fit(
    line: Line, values: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        build_error(line, **values)


# -- the closed and patterned fields ---------------------------------------------------


def _processes(group: object) -> str:
    return PROCESSES_KILLED_LINE.render({"process_group": group})


def _exit(code: object) -> str:
    return BUILD_EXIT_LINE.render({"dir": "p", "exit_code": code, "output": "x"})


@pytest.mark.parametrize("code", [0, 1, -9, -15, 255, 3221225786])
def test_an_exit_code_is_digits_negative_or_large(code: int) -> None:
    text = _exit(code)
    assert f"exited with code {code};" in text
    assert trusted_message(f"WARNING: Build: {text} [build-failed]") is BUILD_FAILED


@pytest.mark.parametrize("code", [True, "1", 1.5, None, b"1"], ids=repr)
def test_an_exit_code_that_is_no_int_is_refused(code: object) -> None:
    with pytest.raises(ValueError, match="exit code"):
        _exit(code)


@pytest.mark.parametrize("shown", ["01", "1x", "--1", "+1", " 1", "0x1", "1.0"])
def test_a_line_with_a_malformed_exit_code_is_not_trusted(shown: str) -> None:
    text = _exit(1).replace("code 1;", f"code {shown};")
    assert trusted_message(f"WARNING: Build: {text} [build-failed]") is None


@pytest.mark.parametrize("group", [0, -5, True, "12", 1.0, None], ids=repr)
def test_a_process_group_is_a_positive_whole_number(group: object) -> None:
    with pytest.raises(ValueError):
        _processes(group)


@pytest.mark.parametrize("shown", ["0", "01", "-3", "4x", ""])
def test_a_line_with_a_malformed_process_group_is_not_trusted(shown: str) -> None:
    text = _processes(4321).replace("group 4321", f"group {shown}")
    line = f"INFO: Build: {text} [build-processes-unsafe]"
    assert trusted_message(line) is None
    assert trusted_message(line.replace(f"group {shown}", "group 4321")) is not None


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("signal", "SIGKILL"),
        ("signal", "sigterm"),
        ("signal", "SIGTERM "),
        ("signal", "SIGTERM|SIGHUP"),
        ("signal", ""),
        ("activity", "the scan"),
        ("activity", "The build"),
        ("activity", "the build; and more"),
    ],
)
def test_signal_and_activity_are_closed(field: str, bad: str) -> None:
    good = {"signal": "SIGHUP", "activity": "the AI model file copy"}
    assert INTERRUPTED_DURING_LINE.render(good)
    with pytest.raises(ValueError, match=field):
        INTERRUPTED_DURING_LINE.render({**good, field: bad})
    printed = INTERRUPTED_DURING_LINE.render(good).replace(good[field], bad)
    assert trusted_message(f"WARNING: Build: {printed} [interrupted]") is None
