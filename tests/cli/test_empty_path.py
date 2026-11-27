# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An empty path argument names nothing: an input path (a command's
positional target) is ``input-not-found``, an empty path or file-name
option (``-o``, ``--project-dir``, ``--id-registry``, ``--config``,
``--sbom``, ``--sbom-basename``, ``--sbom-filename``) is
``option-invalid``; never the current directory read as ``.``, nor the
default name.

The commands and their arguments are read from the real parser, so a new
command is covered without a new case here.

See also: tests/test_library_empty_path.py (the library entries).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli._path_args import non_empty_name, non_empty_path
from pitloom.cli.parser import _build_parser

pytestmark = pytest.mark.platform

#: What else a command needs to reach its target check.
_NEEDS: dict[tuple[str, ...], list[str]] = {
    ("generate",): ["-o", "out.json"],
    ("id", "generate"): ["--id-registry", "r.json"],
    ("id", "import"): ["--id-registry", "r.json"],
}
#: Options naming where Pitloom writes or looks, or a file name.
_PATH_OPTIONS = (
    "-o",
    "--project-dir",
    "--id-registry",
    "--config",
    "--sbom",
    "--sbom-basename",
    "--sbom-filename",
)


def _actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """*parser*'s arguments (argparse keeps them in a private list)."""
    # pylint: disable-next=protected-access
    return parser._actions


def _commands(
    parser: argparse.ArgumentParser, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    """Each command of *parser* (nested ones included) and its parser."""
    for action in _actions(parser):
        # pylint: disable-next=protected-access
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                yield path + (name,), sub
                yield from _commands(sub, path + (name,))


def _param(case: str, argv: list[str]) -> object:
    """*argv* as the case *case*."""
    return pytest.param(argv, id=case)


def _positional_cases() -> list[object]:
    """Each command with a positional argument, given as empty."""
    return [
        _param(" ".join(path), [*path, *_NEEDS.get(path, []), ""])
        for path, sub in _commands(_build_parser())
        if any(
            not a.option_strings and a.nargs != argparse.PARSER for a in _actions(sub)
        )
    ]


def _option_cases() -> list[object]:
    """Each path option of each command, given as empty."""
    return [
        _param(" ".join((*path, option)), [*path, option, ""])
        for path, sub in _commands(_build_parser())
        for action in _actions(sub)
        for option in action.option_strings
        if option in _PATH_OPTIONS
    ]


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    """``loom <argv>``'s exit status, argparse's own included."""
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    try:
        return __main__.main()
    except SystemExit as exc:
        return int(exc.code or 0)


@pytest.mark.parametrize("argv", _positional_cases())
def test_empty_input_is_not_found(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One ``input-not-found`` line, nothing written, the current directory
    (a project with a fragment, which ``.`` would read) left as it was."""
    (tmp_path / "pyproject.toml").write_bytes(b'[project]\nname = "p"\nversion = "1"\n')
    (tmp_path / "a.json").write_bytes(b"{}")
    before = sorted(tmp_path.iterdir())
    monkeypatch.chdir(tmp_path)
    assert _run(argv, monkeypatch) == 1
    errors = [ln for ln in capsys.readouterr().err.splitlines() if "ERROR" in ln]
    assert len(errors) == 1 and errors[0].endswith(": '' [input-not-found]")
    assert sorted(tmp_path.iterdir()) == before


@pytest.mark.parametrize("argv", _option_cases())
def test_empty_path_option_is_invalid(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """argparse's refusal of the option, coded ``option-invalid``."""
    assert _run(argv, monkeypatch) == 2
    (error,) = [ln for ln in capsys.readouterr().err.splitlines() if "ERROR" in ln]
    assert f"argument {argv[-2]}" in error or "/" + argv[-2] in error
    assert error.endswith(
        "must be a non-empty string, got a string '' [option-invalid]"
    )


def test_an_empty_generate_target_comes_before_the_missing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom generate ''`` names the empty target, not the missing ``-o``:
    nothing is there to read, so ``-o`` is moot."""
    monkeypatch.chdir(tmp_path)
    assert _run(["generate", ""], monkeypatch) == 1
    errors = [ln for ln in capsys.readouterr().err.splitlines() if "ERROR" in ln]
    assert errors == ["ERROR: loom generate: target not found: '' [input-not-found]"]


def test_every_path_option_refuses_an_empty_value() -> None:
    """Each option taking a path (``FILE``, ``DIR``) or one of the named file
    names refuses ``''`` in argparse: a new one cannot be added with a plain
    ``type=TypedPath`` or ``type=str``."""
    found = {
        (" ".join(path), action.option_strings[-1]): action.type
        for path, sub in _commands(_build_parser())
        for action in _actions(sub)
        if action.option_strings
        and (
            action.metavar in ("FILE", "DIR")
            or set(action.option_strings) & set(_PATH_OPTIONS)
        )
    }
    assert found, "no path option found"
    assert {
        key: kind
        for key, kind in found.items()
        if kind not in (non_empty_path, non_empty_name)
        # ``id``'s -o/--id-registry checks '-' too, then non_empty_path.
        and getattr(kind, "__name__", "") != "registry_file_arg"
    } == {}


def test_every_command_is_walked() -> None:
    """The walk reaches the commands this file was written against: a guard
    against a walk that finds nothing and passes vacuously."""
    positional = {c.id for c in _positional_cases()}  # type: ignore[attr-defined]
    assert {"wheel", "merge", "project", "fragment validate", "id import"} <= positional
    assert len(_option_cases()) >= 22
