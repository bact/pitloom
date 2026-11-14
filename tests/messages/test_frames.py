# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The frames: every ``ERROR:`` line the command line prints starts with
``loom <command>: `` (``loom: `` where no command is known), the Hatchling
hook's with its own frame, and the catalogue's table lists exactly those, so a
line a surface prints is trusted and no other. The library prints no ``ERROR:``
line and puts no frame on an exception's text.

See also: tests/messages/test_messages_fields.py (a frame's own rules),
tests/cli/test_cli_error_lines.py (the lines under hostile values).
"""

from __future__ import annotations

import argparse
import ast
import logging
import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.cli.parser import (
    COMMAND_DESTS,
    _build_parser,
    command_frame,
    command_path,
)
from pitloom.logging_config import (
    CODE_ATTR,
    configure_logging,
    error_frame,
    print_error,
    set_error_frame,
)
from pitloom.messages import (
    COMMAND_FRAME,
    FRAMES,
    HOOK_FRAME,
    LOOM_COMMANDS,
    RELAY_FRAME,
    TOP_FRAME,
    says,
    trusted_message,
)
from pitloom.messages.targets import (
    INPUT_NOT_FOUND,
    MODEL_FILE_NOT_FOUND_LINE,
)
from tests._message_drift import SRC_ROOT, source_modules

pytestmark = pytest.mark.platform  # argv, stderr lines, a hook

_LINE = MODEL_FILE_NOT_FOUND_LINE.render({"path": "m.gguf"})


def _subparser_progs(parser: argparse.ArgumentParser) -> tuple[set[str], set[str]]:
    """The ``prog`` of every sub-parser, and the ``dest`` of each level."""
    progs: set[str] = set()
    dests: set[str] = set()
    for action in parser._actions:  # pylint: disable=protected-access
        if isinstance(action, argparse._SubParsersAction):  # pylint: disable=W0212
            dests.add(action.dest)
            for sub in action.choices.values():
                progs.add(sub.prog.removeprefix("loom "))
                found_progs, found_dests = _subparser_progs(sub)
                progs |= found_progs
                dests |= found_dests
    return progs, dests


def test_the_commands_and_dests_are_the_parsers() -> None:
    progs, dests = _subparser_progs(_build_parser())
    assert progs == set(LOOM_COMMANDS)
    assert dests == set(COMMAND_DESTS)
    assert list(LOOM_COMMANDS) == sorted(LOOM_COMMANDS)


@pytest.mark.parametrize(
    ("args", "path"),
    [
        ({}, ""),
        ({"command": "generate"}, "generate"),
        ({"command": "fragment", "fragment_command": "list"}, "fragment list"),
        ({"command": "id", "id_command": "import"}, "id import"),
        ({"command": None, "id_command": 3}, ""),
    ],
    ids=["none", "command", "nested", "nested-id", "not-text"],
)
def test_the_command_path_comes_from_the_parsed_dests(
    args: dict[str, object], path: str
) -> None:
    assert command_path(argparse.Namespace(**args)) == path


def test_a_frame_names_its_command_or_loom_alone() -> None:
    assert command_frame("fragment validate") == "loom fragment validate: "
    assert command_frame("") == TOP_FRAME.render({}) == "loom: "
    assert HOOK_FRAME.render({}) == "Pitloom build hook: "


@pytest.mark.parametrize("command", LOOM_COMMANDS, ids=str)
def test_a_line_framed_by_any_command_is_trusted_and_a_forged_one_is_not(
    command: str,
) -> None:
    framed = f"{command_frame(command)}{_LINE}"
    assert says(INPUT_NOT_FOUND, "ERROR", framed)
    line = f"ERROR: {framed} [{INPUT_NOT_FOUND.code}]"
    assert trusted_message(line) is INPUT_NOT_FOUND
    for forged in (
        f"loom nope: {_LINE}",  # a command the parser has not
        f"{command_frame(command)}{command_frame(command)}{_LINE}",  # two frames
        f"{command_frame(command).rstrip()}{_LINE}",  # no space after the colon
    ):
        assert not says(INPUT_NOT_FOUND, "ERROR", forged), forged
    assert not says(INPUT_NOT_FOUND, "WARNING", framed)  # a frame is an ERROR's


def test_the_table_is_the_four_frames() -> None:
    assert FRAMES == (COMMAND_FRAME, TOP_FRAME, HOOK_FRAME, RELAY_FRAME)
    assert {f.surface for f in FRAMES} == {
        "the command line, each subcommand",
        "the command line, before a subcommand is known",
        "the Hatchling build hook",
        "a model scan, before a model reader's own line",
    }


def _argv(command: str, tmp: Path) -> list[str]:
    """An invocation of *command* that ends in an ``ERROR:`` line: a missing
    input, or a missing value (a parse error of that command's own parser)."""
    missing = str(tmp / "missing")
    out = ["-o", str(tmp / "out.json")]
    argv = {
        "embed-wheel": ["embed-wheel", missing + ".whl"],
        "enrich": ["enrich", missing + ".gguf", *out],
        "env": ["env", "-o"],
        "fragment": ["fragment"],
        "fragment list": ["fragment", "list"],
        "fragment validate": ["fragment", "validate", missing + ".json"],
        "generate": ["generate", missing],
        "id": ["id"],
        "id generate": ["id", "generate", "--project-dir", missing],
        "id import": ["id", "import"],
        "merge": ["merge", missing],
        "model": ["model", missing + ".gguf", *out],
        "project": ["project", missing, *out],
        "validate-wheel": ["validate-wheel", missing + ".whl"],
        "verify-wheel": ["verify-wheel", missing + ".whl"],
        "wheel": ["wheel", missing + ".whl", *out],
    }
    return argv[command]


@pytest.mark.parametrize("command", LOOM_COMMANDS, ids=str)
def test_every_error_line_of_a_command_starts_with_its_frame(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)  # `fragment list` reads ./pyproject.toml
    monkeypatch.setattr(sys, "argv", ["loom", *_argv(command, tmp_path)])
    try:
        status = main()
    except SystemExit as stop:  # a parse error of the command's own parser
        status = int(stop.code or 0)
    assert status != 0
    lines = [ln for ln in capsys.readouterr().err.splitlines() if ln[:6] == "ERROR:"]
    assert lines, "the invocation printed no ERROR line"
    assert all(ln.startswith(f"ERROR: loom {command}: ") for ln in lines), lines


@pytest.mark.parametrize(
    ("argv", "frame"),
    [
        ([], "loom: "),  # no command: the top parser refuses
        (["generate", "x", "--no-such-option"], "loom: "),  # leftover: top parser
    ],
    ids=["no-command", "unrecognised"],
)
def test_a_line_before_a_command_is_known_starts_with_loom_alone(
    argv: list[str],
    frame: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    with pytest.raises(SystemExit) as stop:
        main()
    assert stop.value.code == 2
    err = capsys.readouterr().err
    assert f"ERROR: {frame}" in err and "ERROR: loom: loom" not in err


def test_ctrl_c_is_framed_by_the_command_that_was_running(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupted(_args: argparse.Namespace) -> int:
        raise KeyboardInterrupt

    parser = _build_parser()
    monkeypatch.setattr("pitloom.__main__._build_parser", lambda: parser)
    for action in parser._actions:  # pylint: disable=protected-access
        if isinstance(action, argparse._SubParsersAction):  # pylint: disable=W0212
            action.choices["merge"].set_defaults(func=interrupted)
    monkeypatch.setattr(sys, "argv", ["loom", "merge", "x"])
    assert main() == 130
    assert "ERROR: loom merge: interrupted\n" in capsys.readouterr().err


def test_ctrl_c_before_the_arguments_parse_is_framed_by_loom_alone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupted() -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr("pitloom.__main__._run", interrupted)
    assert main() == 130
    assert "ERROR: loom: interrupted\n" in capsys.readouterr().err


def test_print_error_is_unframed_where_nothing_set_a_frame(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The library, the hook and a unit test set none."""
    print_error("plain", code="x-y")
    assert capsys.readouterr().err == "ERROR: plain [x-y]\n"


def test_a_frame_lasts_the_block_and_an_explicit_frame_wins(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with error_frame("loom a: "):
        print_error("one")
        set_error_frame("loom b: ")
        print_error("two")
        print_error("three", frame="")
        print_error("four", frame="loom c: ")
        with pytest.raises(RuntimeError), error_frame("loom d: "):
            print_error("five")
            raise RuntimeError
        print_error("six")  # the block's own frame is back after an exception
    print_error("seven")
    assert capsys.readouterr().err.splitlines() == [
        "ERROR: loom a: one",
        "ERROR: loom b: two",
        "ERROR: three",
        "ERROR: loom c: four",
        "ERROR: loom d: five",
        "ERROR: loom b: six",
        "ERROR: seven",
    ]


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == name
    ]


def test_a_cli_error_handler_is_a_bare_decorator() -> None:
    """It names no text: the frame is the command's, set once for the run."""
    uses = 0
    for _, tree in source_modules():
        assert not _calls(tree, "cli_error_handler"), "a call, not a decorator"
        uses += sum(
            isinstance(d, ast.Name) and d.id == "cli_error_handler"
            for fn in ast.walk(tree)
            if isinstance(fn, ast.FunctionDef)
            for d in fn.decorator_list
        )
    assert uses >= 12  # the scan finds the handlers


@pytest.mark.parametrize(
    ("level", "framed"),
    [
        (logging.CRITICAL, True),
        (logging.ERROR, True),
        (logging.WARNING, False),
        (logging.INFO, False),
    ],
    ids=["critical", "error", "warning", "info"],
)
def test_an_error_record_is_framed_as_print_error_is_and_a_warning_is_not(
    level: int, framed: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    """The frame is the logging formatter's too, so a command's ``log.error``
    reads as its ``print_error`` does (the code still ends the line)."""
    configure_logging()
    log = logging.getLogger("pitloom.test_frames")
    extra = {CODE_ATTR: "x-y"}
    with error_frame("loom wheel: "):
        log.log(level, "reason\nSECOND", extra=extra)
    name = logging.getLevelName(level)
    wanted = f"{name}: {'loom wheel: ' if framed else ''}reason\\nSECOND [x-y]"
    assert capsys.readouterr().err.splitlines() == [wanted]


def test_an_error_record_outside_a_frame_has_none(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The library, the hook and a unit test set no frame."""
    configure_logging()
    logging.getLogger("pitloom.test_frames").error("plain")
    assert capsys.readouterr().err == "ERROR: plain\n"


def test_the_build_hook_reports_its_failure_with_its_frame() -> None:
    """The hook's one failure line is ``<frame><exception>``."""
    tree = ast.parse((SRC_ROOT / "plugins" / "hatch.py").read_bytes())
    errors = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "error"
    ]
    assert len(errors) == 1
    first, second = errors[0].args[:2]
    assert isinstance(first, ast.Constant) and first.value == "%s%s"
    assert ast.unparse(second) == "HOOK_FRAME.render({})"
