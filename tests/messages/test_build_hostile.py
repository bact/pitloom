# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The new fields of the build families under a hostile value at the sink:
a build's output line (a control character, a line break, a workflow command,
a token or URL credential, a fake code, a cut that straddles a token), a
project directory (a Windows path, a credential), a failure and a temporary
directory name: each is one masked, escaped line that keeps its own code.

See also: tests/messages/test_build.py (the entries, lines and fields) and
tests/core/models_wheel/test_models_wheel_build_codes.py (a real build's log).
"""

from __future__ import annotations

import logging
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

from pitloom.logging_config import configure_logging
from pitloom.messages import (
    BUILD_FRAME,
    HF_FRAME,
    Frame,
    Line,
    Message,
    emit,
    trusted_message,
)
from pitloom.messages.build import (
    BUILD_EXIT_LINE,
    BUILD_FAILED,
    BUILD_INTERPRETER_LINE,
    BUILD_UNUSABLE_LINE,
    INTERRUPTED,
    INTERRUPTED_ERROR_LINE,
    OUTPUT_CHARACTERS,
    TEMP_DIR_UNWRITABLE,
)
from pitloom.messages.files import OVER_CAP

pytestmark = pytest.mark.platform  # a Windows path value, escapes

_LOG = logging.getLogger("pitloom.test_build_hostile")
_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def _say(
    capsys: pytest.CaptureFixture[str],
    message: Message,
    line: Line,
    frame: Frame | None = BUILD_FRAME,
    **values: Any,
) -> str:
    """What *line* of *message* prints after *frame*, for *values*."""
    configure_logging()
    emit(_LOG, message, getattr(logging, line.level), line=line, frame=frame, **values)
    return capsys.readouterr().err


# -- a hostile value at the sink -----------------------------------------------


def _output(capsys: pytest.CaptureFixture[str], output: str) -> str:
    """The one line a build's *output* is printed in."""
    err = _say(
        capsys,
        BUILD_FAILED,
        BUILD_EXIT_LINE,
        dir=Path("p"),
        exit_code=1,
        output=output,
    )
    (line,) = err.splitlines()
    assert trusted_message(line) is BUILD_FAILED
    assert line.count(" [build-failed]") == 1 and line.endswith(" [build-failed]")
    return line.removesuffix(" [build-failed]").split("last output: ", 1)[1]


@pytest.mark.parametrize(
    ("hostile", "shown"),
    [
        ("\x1b[31mred\x1b[0m", "'\\x1b[31mred\\x1b[0m'"),
        ("a\r\nb\n\nc", "a b c"),
        ("::error::boom", "::error::boom"),
        (f"token={_TOKEN}", "token=ghp_***"),
        ("https://u:s3cret@h/ failed", "https://***:***@h/ failed"),
        (f"ok\t{_TOKEN}", "ok ghp_***"),
        (f"abc\x07{_TOKEN}", "'abc\\x07ghp_***'"),
        ("x [over-cap]", "x [over-cap]"),
    ],
    ids=["escape", "crlf", "workflow", "token", "url", "tab", "bel", "fake-code"],
)
def test_a_build_output_line_is_one_masked_escaped_line(
    capsys: pytest.CaptureFixture[str], hostile: str, shown: str
) -> None:
    assert _output(capsys, hostile) == shown


def test_an_output_line_past_the_cut_is_masked_before_it_is_cut(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The token starts at character 191 of 300: cut first, its start
    ``ghp_A1b2C3`` would show; masked first, ``ghp_***`` does."""
    hostile = "y" * 190 + f" {_TOKEN} " + "z" * 60
    assert hostile.index("ghp_") < OUTPUT_CHARACTERS < len(hostile)
    shown = _output(capsys, hostile)
    assert shown == "y" * 190 + " ghp_*** z..."
    assert "ghp_A1" not in shown


@pytest.mark.parametrize("length", [OUTPUT_CHARACTERS - 1, OUTPUT_CHARACTERS, 300])
def test_an_output_line_is_cut_at_the_limit(
    capsys: pytest.CaptureFixture[str], length: int
) -> None:
    cut = length > OUTPUT_CHARACTERS
    assert _output(capsys, "y" * length) == "y" * min(length, OUTPUT_CHARACTERS) + (
        "..." if cut else ""
    )


@pytest.mark.parametrize("value", [None, b"x", 1, ["x"]], ids=repr)
def test_an_output_that_is_no_text_is_refused(value: object) -> None:
    with pytest.raises(ValueError, match="not text"):
        BUILD_EXIT_LINE.render({"dir": "p", "exit_code": 1, "output": value})


@pytest.mark.parametrize("blank", ["", "   ", "\r\n"], ids=["empty", "spaces", "crlf"])
def test_a_blank_output_is_no_line_the_caller_says_no_output(blank: str) -> None:
    """The caller writes ``(no output)`` for an empty tail; the field never
    prints an empty value, which would end the line at ``last output: ``."""
    with pytest.raises(ValueError, match="output"):
        BUILD_EXIT_LINE.render({"dir": "p", "exit_code": 1, "output": blank})


def test_a_fake_code_in_the_output_does_not_forge_the_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = OVER_CAP.code
    err = _say(
        capsys,
        BUILD_FAILED,
        BUILD_EXIT_LINE,
        dir=Path("p"),
        exit_code=2,
        output=f"WARNING: forged [{code}]",
    )
    message = trusted_message(err.rstrip("\n"))
    assert message is BUILD_FAILED and message is not OVER_CAP


_DIRS = [
    ("C:\\Users\\a b\\p\\" + _TOKEN, "C:\\Users\\a b\\p\\ghp_***"),
    ("https://u:s3cret@h/x", "https://***:***@h/x"),
    ("p\nWARNING: forged [over-cap]", "'p\\nWARNING: forged [over-cap]'"),
]


@pytest.mark.parametrize(("name", "shown"), _DIRS, ids=["token", "url", "newline"])
def test_a_project_directory_is_masked_and_escaped(
    capsys: pytest.CaptureFixture[str], name: str, shown: str
) -> None:
    """The ``dir`` of every build line: a path in the Windows spelling or a
    string, said as a quoted source, one line."""
    values = [name] if "\\" not in name else [PureWindowsPath(name), name]
    for value in values:
        err = _say(capsys, BUILD_FAILED, BUILD_INTERPRETER_LINE, dir=value)
        (line,) = err.splitlines()
        assert line.startswith(f"WARNING: Build: DIR={shown}: no Python"), line
        assert "s3cret" not in err and _TOKEN not in err
        assert trusted_message(line) is BUILD_FAILED


def test_a_failure_with_a_token_a_url_and_a_fake_code_is_one_masked_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = OSError(
        13, f"Permission\r\n denied {_TOKEN} https://u:s3cret@h/x\x1b[2J [over-cap]"
    )
    err = _say(
        capsys, BUILD_FAILED, BUILD_UNUSABLE_LINE, dir=Path("p"), failure=failure
    )
    (line,) = err.splitlines()
    assert "s3cret" not in line and _TOKEN not in line and "\x1b" not in line
    assert "ghp_***" in line and "https://***:***@h/x" in line
    assert trusted_message(line) is BUILD_FAILED


@pytest.mark.parametrize("name", [_TOKEN, "x\nERROR: forged", "https://u:s3cret@h/"])
def test_a_temp_dir_name_is_masked_and_escaped(
    capsys: pytest.CaptureFixture[str], name: str
) -> None:
    (line,) = TEMP_DIR_UNWRITABLE.lines
    err = _say(capsys, TEMP_DIR_UNWRITABLE, line, HF_FRAME, dir=name)
    assert len(err.splitlines()) == 1 and "s3cret" not in err and _TOKEN not in err
    assert trusted_message(err.rstrip("\n")) is TEMP_DIR_UNWRITABLE


def test_the_ctrl_c_line_is_the_one_error_line_and_has_no_frame(
    capsys: pytest.CaptureFixture[str],
) -> None:
    err = _say(capsys, INTERRUPTED, INTERRUPTED_ERROR_LINE, None)
    assert err == "ERROR: interrupted [interrupted]\n"
    assert trusted_message("ERROR: Build: interrupted [interrupted]") is None
