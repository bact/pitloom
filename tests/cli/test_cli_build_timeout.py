# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``--build-timeout`` CLI flag: parsing and range/format
validation on every subcommand that offers it (``project``,
``generate``, ``embed-wheel``), and that each command hands all three
build flags to the library as one ``BuildOptions``.

See also: :mod:`tests.cli.test_cli_parser` for the sibling
``--allow-build``/``--no-build-isolation`` parser tests;
:mod:`tests.test_build_flag_warnings` for the "has no effect" warnings,
which the library (not the CLI) emits.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.cli.parser import _build_parser
from pitloom.core.build_options import BuildOptions
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.cli.shared import _make_simple_project

_PROJECT_COMMANDS = [
    ("generate", ["."]),
    ("project", ["."]),
    ("embed-wheel", ["dummy.whl"]),
]


@pytest.mark.parametrize(("command", "target_args"), _PROJECT_COMMANDS)
def test_build_timeout_default_is_none(command: str, target_args: list[str]) -> None:
    parser = _build_parser()
    assert parser.parse_args([command, *target_args]).build_timeout is None


@pytest.mark.parametrize(("command", "target_args"), _PROJECT_COMMANDS)
@pytest.mark.parametrize(
    ("value", "expected_seconds"),
    [("30", 30), ("1h30m", 5400)],
    ids=["seconds", "unit-form"],
)
def test_build_timeout_parses_to_int_seconds(
    command: str, target_args: list[str], value: str, expected_seconds: int
) -> None:
    """The namespace always holds resolved ``int`` seconds, regardless of
    whether the CLI text was a bare number or an h/m/s unit form."""
    parser = _build_parser()
    args = parser.parse_args([command, *target_args, "--build-timeout", value])
    assert args.build_timeout == expected_seconds
    assert isinstance(args.build_timeout, int)


@pytest.mark.parametrize(("command", "target_args"), _PROJECT_COMMANDS)
@pytest.mark.parametrize(
    "bad_value",
    ["0", "-5", "abc", "1.5h", "604801"],
    ids=["zero", "negative", "non-numeric", "fractional-unit", "over-max"],
)
def test_build_timeout_rejects_invalid_values(
    command: str, target_args: list[str], bad_value: str
) -> None:
    """An out-of-range or malformed ``--build-timeout`` value is an
    argparse error (exit code 2), not a raised exception reaching the
    caller as a traceback."""
    parser = _build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args([command, *target_args, "--build-timeout", bad_value])
    assert excinfo.value.code == 2


_ALL_FLAGS = ["--allow-build", "--no-build-isolation", "--build-timeout", "1h"]
_EXPECTED = BuildOptions(allow=True, no_isolation=True, timeout=3600)


@pytest.mark.parametrize(
    ("command", "patched"),
    [
        ("project", "pitloom.cli.commands.project.generate_project_sbom"),
        # `generate` on a project directory or sdist shares `project`'s
        # code path, so both patch the same generate_project_sbom().
        ("generate", "pitloom.cli.commands.project.generate_project_sbom"),
        ("generate-sdist", "pitloom.cli.commands.project.generate_project_sbom"),
        ("embed-wheel", "pitloom.cli.commands._embed_wheel_batch.embed_wheel_sbom"),
    ],
)
def test_command_passes_one_build_options_to_library(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: str, patched: str
) -> None:
    """Every command (and both ``generate`` dispatch branches) passes the
    three flags as one ``BuildOptions``; the library owns the warnings."""
    project_dir = _make_simple_project(tmp_path)
    output = str(tmp_path / "sbom.json")
    if command == "embed-wheel":
        wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
        argv = ["embed-wheel", str(wheel), "--project-dir", str(project_dir)]
    elif command == "generate-sdist":
        argv = ["generate", str(_make_sdist(tmp_path)), "-o", output]
    else:
        argv = [command, str(project_dir), "-o", output]

    captured: list[dict[str, Any]] = []

    def _capture(*_args: object, **kwargs: Any) -> Any:
        captured.append(kwargs)
        # embed_wheel_sbom()'s return shape; the generators' return is unused.
        return tmp_path / "x.whl", "arcname", "{}", (), False

    monkeypatch.setattr(patched, _capture)
    monkeypatch.setattr(sys, "argv", ["loom", *argv, *_ALL_FLAGS])
    assert __main__.main() == 0

    assert len(captured) == 1
    kwargs = captured[0]
    received = (
        kwargs["overrides"].build_options
        if "overrides" in kwargs
        else kwargs["build_options"]
    )
    if command == "generate-sdist":
        # Settled for the sdist before the metadata read, as `loom project`
        # does (see tests/test_build_flag_warning_ordering.py), so the
        # library receives defaults: nothing is left for it to re-warn.
        assert received == BuildOptions()
    else:
        assert received == _EXPECTED


@pytest.mark.parametrize("missing", ["no-such-dir", "no-such-1.0.tar.gz"])
@pytest.mark.parametrize(
    "flags", [["--build-timeout", "5"], ["--allow-build", "--build-timeout", "5"]]
)
@pytest.mark.parametrize("subcommand", ["project", "generate"])
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_missing_target_fails_with_one_error_and_no_build_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    subcommand: str,
    flags: list[str],
    missing: str,
) -> None:
    """A target that doesn't exist fails the command with one ``ERROR:``
    and nothing else -- no build-flag warning about a target that was
    never there -- identically on ``project`` and ``generate``."""
    monkeypatch.chdir(tmp_path)
    argv = ["loom", subcommand, missing, "-o", "out.json", *flags]
    monkeypatch.setattr(sys, "argv", argv)

    assert __main__.main() == 1

    stderr = capsys.readouterr().err.splitlines()
    assert len(stderr) == 1, stderr
    assert stderr[0].startswith("ERROR: ")
    assert missing in stderr[0]


@pytest.mark.parametrize("missing", ["no-such-dir", "no-such-1.0.tar.gz"])
@pytest.mark.parametrize("entry_point", ["generate", "generate_project_sbom"])
def test_library_missing_target_raises_without_build_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    entry_point: str,
    missing: str,
) -> None:
    """The library matches the CLI: ``FileNotFoundError``, and no
    build-flag warning for a target that doesn't exist."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom import assemble

    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="not found"):
        getattr(assemble, entry_point)(missing, build_options=BuildOptions(timeout=5))
    assert "has no effect" not in caplog.text


@pytest.mark.parametrize(
    "flags", [["--build-timeout", "5"], ["--allow-build", "--build-timeout", "5"]]
)
def test_embed_wheel_missing_project_dir_fails_with_one_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: list[str],
) -> None:
    """``embed-wheel --project-dir`` naming a missing directory matches
    ``project``/``generate``: one ``ERROR:``, no build-flag warning."""
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    missing = tmp_path / "no-such-dir"
    argv = ["loom", "embed-wheel", str(wheel), "--project-dir", str(missing)]
    monkeypatch.setattr(sys, "argv", [*argv, *flags])

    assert __main__.main() == 1

    stderr = capsys.readouterr().err.splitlines()
    assert len(stderr) == 1, stderr
    assert stderr[0].startswith("ERROR: ")
    assert "not found" in stderr[0]
