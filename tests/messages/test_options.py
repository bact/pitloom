# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The option families: argparse's refusals carry ``option-invalid``,
``option-conflict`` or ``option-missing`` only when their wording is
catalogued; an option with no
effect is one coded line at its level and prefix; a build timeout out of
range is ``option-invalid`` on the command line and in the library.

See also: tests/core/test_no_effect.py (the no-effect shape),
tests/assemble/test_embed_cli.py (``option-conflict``).
"""

from __future__ import annotations

import argparse
import logging
import sys

import pytest

from pitloom import __main__
from pitloom.core._models_wheel_types import BUILD_LOG_PREFIX
from pitloom.core.build_options import BuildOptions
from pitloom.core.internal_error import InternalError
from pitloom.core.no_effect import INERT_LOG_PREFIX, warn_no_effect
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    Message,
    code_of,
    trusted_message,
)
from pitloom.messages.options import (
    BUILD_PREFIX,
    OPTION_CONFLICT,
    OPTION_INVALID,
    OPTION_MISSING,
    OPTION_NO_EFFECT,
    OPTIONS_PREFIX,
    usage_code,
    warn_option_no_effect,
)

pytestmark = pytest.mark.platform

_LOG = logging.getLogger("pitloom.test")


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("argument -o/--output: expected one argument", "option-missing"),
        ("argument --n: expected 2 arguments", "option-missing"),
        ("argument --n: expected at least one argument", "option-missing"),
        ("argument --b: not allowed with argument --a", "option-conflict"),
        ("argument command: invalid choice: 'x'\n(choose)", "option-invalid"),
        ("unrecognized arguments: --bogus", "option-invalid"),
        (
            "ambiguous option: --c could match --config, --content-type",
            "option-invalid",
        ),
        ("the following arguments are required: command", "option-missing"),
        ("argument : no name", None),
        ("argument -o: expected a value", None),
        ("argument --b: not allowed with argument", None),
        ("expected one argument", None),
        ("", None),
    ],
    ids=[
        "missing-value",
        "missing-values",
        "missing-at-least",
        "conflict",
        "newline",
        "unknown",
        "ambiguous",
        "required",
        "noname",
        "expected-other",
        "conflict-no-other",
        "bare",
        "empty",
    ],
)
def test_usage_code_codes_only_catalogued_wording(text: str, code: str | None) -> None:
    assert usage_code(text) == code


@pytest.mark.parametrize(
    ("argv", "line", "entry"),
    [
        (
            [],
            "ERROR: loom: the following arguments are required: command",
            OPTION_MISSING,
        ),
        (
            ["wheel"],
            "ERROR: loom wheel: the following arguments are required: target",
            OPTION_MISSING,
        ),
        (
            ["wheel", "-o"],
            "ERROR: loom wheel: argument -o/--output: expected one argument",
            OPTION_MISSING,
        ),
        (
            ["nosuch"],
            "ERROR: loom: argument command: invalid choice: 'nosuch'",
            OPTION_INVALID,
        ),
        (
            ["wheel", "x.whl", "--bogus"],
            "ERROR: loom: unrecognized arguments: --bogus",
            OPTION_INVALID,
        ),
        (
            ["project", "--build-timeout", "0", "."],
            "ERROR: loom project: argument --build-timeout: build timeout must be "
            "1-604800 seconds, got 0",
            OPTION_INVALID,
        ),
    ],
    ids=["missing", "required", "no-value", "choice", "unknown", "timeout"],
)
def test_the_parser_line_is_framed_coded_and_trusted(
    argv: list[str],
    line: str,
    entry: Message,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    with pytest.raises(SystemExit) as caught:
        __main__.main()
    assert caught.value.code == 2
    errors = [
        ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("ERROR")
    ]
    assert len(errors) == 1 and errors[0].startswith(line)
    assert errors[0].endswith(f" [{entry.code}]")
    assert trusted_message(errors[0]) is entry


def test_argparse_conflict_wording_is_option_conflict() -> None:
    """No command has a mutually exclusive group yet: the wording comes
    from this interpreter's argparse, so a later one's change shows here."""
    parser = argparse.ArgumentParser(exit_on_error=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--a", action="store_true")
    group.add_argument("--b", action="store_true")
    with pytest.raises(argparse.ArgumentError) as caught:
        parser.parse_args(["--a", "--b"])
    assert usage_code(str(caught.value)) == OPTION_CONFLICT.code


def test_the_prefix_constants_are_the_templates_leading_text() -> None:
    assert INERT_LOG_PREFIX is OPTIONS_PREFIX and BUILD_LOG_PREFIX is BUILD_PREFIX
    leads = {ln.template.split("%")[0] for ln in OPTION_NO_EFFECT.lines}
    assert leads == {OPTIONS_PREFIX, BUILD_PREFIX} == {"Options: ", "Build: "}


@pytest.mark.parametrize("timeout", [0, 604801], ids=["low", "high"])
def test_the_library_raises_a_timeout_out_of_range_coded(timeout: int) -> None:
    with pytest.raises(ValueError, match="build timeout must be 1-604800") as caught:
        BuildOptions(allow=True, timeout=timeout)
    assert code_of(caught.value) == "option-invalid"


@pytest.mark.parametrize(
    ("build", "level", "text"),
    [
        (False, logging.WARNING, "Options: a b: --pretty has no effect for x"),
        (False, logging.INFO, "Options: a b: --pretty has no effect for x"),
        (True, logging.WARNING, "Build: a b: --pretty has no effect for x"),
    ],
    ids=["options", "options-info", "build"],
)
def test_an_option_with_no_effect_is_one_coded_line(
    build: bool, level: int, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="pitloom.test"):
        warn_option_no_effect(
            _LOG,
            build=build,
            subject="a b",
            option="--pretty",
            when="for x",
            level=level,
        )
    (record,) = caplog.records
    assert (record.levelno, record.getMessage()) == (level, text)
    assert getattr(record, CODE_ATTR) == "option-no-effect"
    printed = f"{logging.getLevelName(level)}: {text} [option-no-effect]"
    assert trusted_message(printed) is OPTION_NO_EFFECT


@pytest.mark.parametrize(
    ("build", "level", "when", "error"),
    [
        (True, logging.INFO, "for x", InternalError),
        (False, logging.ERROR, "for x", InternalError),
        (False, logging.WARNING, "because x", ValueError),
    ],
    ids=["build-info", "error-level", "when-shape"],
)
def test_a_no_effect_line_out_of_its_shapes_is_refused(
    build: bool, level: int, when: str, error: type[Exception]
) -> None:
    with pytest.raises(error):
        warn_option_no_effect(
            _LOG, build=build, subject="a", option="--pretty", when=when, level=level
        )


def test_warn_no_effect_masks_and_escapes_the_subject_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_no_effect("https://u:p@h/a\nb", ("--offline",), "for a model")
    (message,) = caplog.messages
    assert "u:p" not in message and "\n" not in message
    assert message.count("\\n") == 1


def test_warn_no_effect_refuses_info_for_a_build_flag() -> None:
    with pytest.raises(InternalError, match="option-no-effect"):
        warn_no_effect(
            "a", ("--no-isolation",), "for a model", build=True, level=logging.INFO
        )
