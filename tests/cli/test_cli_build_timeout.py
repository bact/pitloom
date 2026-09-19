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
from pitloom.core.build_options import BuildOptions
from tests.cli.shared import _make_simple_project

_PROJECT_COMMANDS = [
    ("generate", ["."]),
    ("project", ["."]),
    ("embed-wheel", ["dummy.whl"]),
]


@pytest.mark.parametrize(("command", "target_args"), _PROJECT_COMMANDS)
def test_build_timeout_default_is_none(command: str, target_args: list[str]) -> None:
    from pitloom.cli.parser import _build_parser

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
    from pitloom.cli.parser import _build_parser

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
    from pitloom.cli.parser import _build_parser

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
        ("generate", "pitloom.cli.commands.generate.generate_project_sbom"),
        ("generate-sdist", "pitloom.cli.commands.generate.generate"),
        ("embed-wheel", "pitloom.cli.commands.embed_wheel.embed_wheel_sbom"),
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
        from tests.assemble.conftest import _make_dummy_wheel

        wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
        argv = ["embed-wheel", str(wheel), "--project-dir", str(project_dir)]
    elif command == "generate-sdist":
        from tests.assemble.conftest import _make_sdist

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
        # The CLI handler now settles this before calling generate() --
        # BuildOptions.settle_not_applicable(), with the sdist-specific
        # reason -- so the build-flag "has no effect" warning precedes
        # any metadata warning generate()'s own dispatch could trigger
        # (see tests/test_build_flag_warning_ordering.py). generate()
        # therefore receives defaults, not the raw flags: nothing is
        # left for its own (now redundant) warning to re-emit.
        assert received == BuildOptions()
    else:
        assert received == _EXPECTED
