# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel pattern (a glob) given to every command that takes wheel files:
one ``glob`` cannot expand is one coded line, never a bare exception text,
and a path whose brackets read as a pattern still names its file.

See also: tests/messages/test_input_not_found_surfaces.py (a pattern that
matches nothing) and :func:`pitloom.cli.commands.utils._collect_wheel_paths`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.messages.targets import INPUT_NOT_FOUND, WHEEL_PATTERN_TOO_DEEP_LINE

pytestmark = pytest.mark.platform

_COMMANDS = ["verify-wheel", "validate-wheel", "embed-wheel"]


def _loom(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, err: pytest.CaptureFixture[str]
) -> tuple[int, list[str]]:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    status = __main__.main()
    return status, err.readouterr().err.splitlines()


@pytest.mark.parametrize("command", _COMMANDS)
def test_a_pattern_too_deep_to_expand_is_one_coded_line(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``glob.glob`` raises ``RecursionError`` on a pattern with more
    wildcard directories than the recursion limit (no such directory need
    exist); the line names the pattern as typed, with its code."""
    pattern = "*/" * (sys.getrecursionlimit() + 50) + "x*.whl"
    status, lines = _loom([command, pattern], monkeypatch, capsys)
    assert status == 1
    (line,) = lines
    expected = WHEEL_PATTERN_TOO_DEEP_LINE.render({"path": pattern})
    assert line == f"ERROR: loom {command}: {expected} [{INPUT_NOT_FOUND.code}]"
    assert "recursion" not in line


@pytest.mark.parametrize("command", _COMMANDS)
def test_a_bracketed_path_that_matches_nothing_names_its_file(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``d[1]/x.whl`` is a pattern that matches ``d1/x.whl`` only; with no
    such file, the file named as typed is read (here: no ZIP, so refused
    as a damaged wheel, not as a pattern matching nothing)."""
    wheel = tmp_path / "d[1]" / "x-1.0-py3-none-any.whl"
    wheel.parent.mkdir()
    wheel.write_bytes(b"not a zip")
    _, lines = _loom([command, str(wheel)], monkeypatch, capsys)
    assert lines and not any("no wheel file matches" in line for line in lines)
    assert any("BadZipFile" in line or "not a zip" in line.lower() for line in lines)


def test_a_bracketed_pattern_that_matches_prefers_the_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """As a shell expands it: a pattern that matches a file is that match,
    not the file its text names."""
    for folder, name in (("d[1]", "x"), ("d1", "y")):
        wheel = tmp_path / folder / f"{name}-1.0-py3-none-any.whl"
        wheel.parent.mkdir()
        wheel.write_bytes(b"not a zip")
    pattern = str(tmp_path / "d[1]" / "*.whl")
    _, lines = _loom(["verify-wheel", pattern], monkeypatch, capsys)
    assert any("y-1.0-py3-none-any.whl" in line for line in lines), lines
    assert not any("x-1.0-py3-none-any.whl" in line for line in lines), lines
