# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from tests.cli.shared import _make_simple_project

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_no_args_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["loom"])
    with pytest.raises(SystemExit) as excinfo:
        __main__.main()
    assert excinfo.value.code == 2
    assert "the following arguments are required: command" in capsys.readouterr().err


def test_debug_flag_raises_logger_to_debug_level(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--debug (parsed on the top-level parser, before the subcommand)
    reaches configure_logging() so DEBUG: records are no longer
    suppressed, for any subcommand."""
    # setenv, not delenv: delenv on an already-absent name records no
    # teardown-restore, leaking PITLOOM_DEBUG=1 into later tests (see
    # tests/test_logging_config.py for the mechanism).
    monkeypatch.setenv("PITLOOM_DEBUG", "0")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "--debug",
            "ids",
            "generate",
            str(tmp_path),
            "-o",
            str(tmp_path / "r.json"),
        ],
    )
    result = __main__.main()
    assert result == 0
    assert logging.getLogger("pitloom").getEffectiveLevel() == logging.DEBUG


def test_debug_flag_survives_a_generator_reconfiguring_logging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Regression: `project` dispatches into generate_project_sbom(),
    which calls bare configure_logging() (debug=None) before its own
    work -- without routing --debug through PITLOOM_DEBUG, that second
    call silently reverted the logger to INFO. Every subcommand that
    calls a generator this way (project/generate/wheel/embed-wheel/
    model/enrich/env/merge) shares this risk; only `project` is
    exercised here."""
    monkeypatch.setenv("PITLOOM_DEBUG", "0")  # see setenv-not-delenv note above
    project_dir = _make_simple_project(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "--debug",
            "project",
            str(project_dir),
            "-o",
            str(tmp_path / "sbom.json"),
        ],
    )
    result = __main__.main()
    assert result == 0
    assert logging.getLogger("pitloom").getEffectiveLevel() == logging.DEBUG


def test_debug_flag_omitted_leaves_logger_at_info_level(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PITLOOM_DEBUG", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "ids", "generate", str(tmp_path), "-o", str(tmp_path / "r.json")],
    )
    result = __main__.main()
    assert result == 0
    assert logging.getLogger("pitloom").getEffectiveLevel() == logging.INFO


def test_debug_flag_omitted_respects_ambient_env_var(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--debug/--no-debug both omitted must not clobber an ambient
    PITLOOM_DEBUG=1 -- apply_debug_override(None) is a no-op."""
    monkeypatch.delenv("PITLOOM_DEBUG", raising=False)
    monkeypatch.setenv("PITLOOM_DEBUG", "1")
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "ids", "generate", str(tmp_path), "-o", str(tmp_path / "r.json")],
    )
    result = __main__.main()
    assert result == 0
    assert logging.getLogger("pitloom").getEffectiveLevel() == logging.DEBUG


def test_no_debug_flag_overrides_ambient_env_var(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--no-debug forces the logger back to INFO for this run even when
    PITLOOM_DEBUG=1 is set in the environment."""
    monkeypatch.delenv("PITLOOM_DEBUG", raising=False)
    monkeypatch.setenv("PITLOOM_DEBUG", "1")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "--no-debug",
            "ids",
            "generate",
            str(tmp_path),
            "-o",
            str(tmp_path / "r.json"),
        ],
    )
    result = __main__.main()
    assert result == 0
    assert logging.getLogger("pitloom").getEffectiveLevel() == logging.INFO


def test_creator_type_action_returns_after_parser_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_CreatorTypeAction.__call__`` hits its ``return`` statement right
    after ``parser.error(...)``. Normally unreachable in a real run because
    ``ArgumentParser.error`` calls ``sys.exit(2)`` -- verified separately
    by the ``--creator-type`` before ``--creator-name`` CLI-level tests in
    tests/cli/test_cli_options.py. Here we stub out ``error`` itself (a
    standard technique for testing custom argparse ``Action`` internals)
    to confirm parsing returns cleanly instead of raising, without
    touching the action's own unreachable-return code."""
    from pitloom.cli.parser import _build_parser

    monkeypatch.setattr(argparse.ArgumentParser, "error", lambda self, msg: None)
    parser = _build_parser()
    namespace = parser.parse_args(["project", ".", "--creator-type", "person"])
    assert namespace.creators is None


def test_creator_email_action_returns_after_parser_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same as above for ``_CreatorEmailAction.__call__``."""
    from pitloom.cli.parser import _build_parser

    monkeypatch.setattr(argparse.ArgumentParser, "error", lambda self, msg: None)
    parser = _build_parser()
    namespace = parser.parse_args(["project", ".", "--creator-email", "a@example.com"])
    assert namespace.creators is None


@pytest.mark.parametrize(
    ("command", "target_args"),
    [
        ("generate", ["."]),
        ("project", ["."]),
        ("wheel", ["dummy.whl"]),
        ("embed-wheel", ["dummy.whl"]),
        ("model", ["dummy.gguf"]),
        ("env", []),
    ],
)
def test_offline_flag_supports_three_states(
    command: str, target_args: list[str]
) -> None:
    """``--offline`` must behave like every other boolean CLI flag
    (``--enrich``, ``--pretty``, ...): unset by default (deferring to
    ``[tool.pitloom] offline``), and explicitly overridable back to
    ``False`` via ``--no-offline`` -- not just a one-way ``store_true``
    with no way to force network access back on for a single run."""
    from pitloom.cli.parser import _build_parser

    parser = _build_parser()

    assert parser.parse_args([command, *target_args]).offline is None
    assert parser.parse_args([command, *target_args, "--offline"]).offline is True
    assert parser.parse_args([command, *target_args, "--no-offline"]).offline is False


@pytest.mark.parametrize(
    ("command", "target_args"),
    [
        ("generate", ["."]),
        ("project", ["."]),
        ("enrich", ["dummy.gguf"]),
    ],
)
def test_use_lockfile_flag_supports_three_states(
    command: str, target_args: list[str]
) -> None:
    """``--use-lockfile`` must behave like every other boolean CLI flag:
    unset by default (deferring to ``[tool.pitloom] use-lockfile``), and
    explicitly overridable back to ``False`` via ``--no-use-lockfile``.
    Only offered on commands that read a lock/pin file cascade at all --
    not ``wheel``/``embed-wheel``/``model``/``env``."""
    from pitloom.cli.parser import _build_parser

    parser = _build_parser()

    assert parser.parse_args([command, *target_args]).use_lockfile is None
    assert (
        parser.parse_args([command, *target_args, "--use-lockfile"]).use_lockfile
        is True
    )
    assert (
        parser.parse_args([command, *target_args, "--no-use-lockfile"]).use_lockfile
        is False
    )


@pytest.mark.parametrize(
    ("command", "target_args"),
    [
        ("generate", ["."]),
        ("project", ["."]),
        ("embed-wheel", ["dummy.whl"]),
    ],
)
def test_allow_build_flags_present_and_plain_bool(
    command: str, target_args: list[str]
) -> None:
    """``--allow-build``/``--no-build-isolation`` are only offered on
    commands that reach ``get_wheel_files()`` for a project directory
    (``generate``, ``project``, ``embed-wheel``) -- not ``wheel``,
    ``enrich``, ``env``, or ``model``. Unlike ``--offline``/
    ``--use-lockfile`` above, both are a plain ``store_true`` defaulting
    to ``False`` (no tri-state/``--no-...`` counterpart), matching their
    deliberate lack of a ``[tool.pitloom]`` config-file equivalent."""
    from pitloom.cli.parser import _build_parser

    parser = _build_parser()

    assert parser.parse_args([command, *target_args]).allow_build is False
    assert parser.parse_args([command, *target_args]).no_build_isolation is False
    args = parser.parse_args(
        [command, *target_args, "--allow-build", "--no-build-isolation"]
    )
    assert args.allow_build is True
    assert args.no_build_isolation is True


@pytest.mark.parametrize(
    ("command", "target_args"),
    [
        ("wheel", ["dummy.whl"]),
        ("enrich", ["dummy.gguf"]),
        ("env", []),
    ],
)
def test_allow_build_flags_absent_on_non_project_commands(
    command: str, target_args: list[str]
) -> None:
    """A command that never calls ``get_wheel_files()`` on a project
    directory must not advertise ``--allow-build``/``--no-build-isolation``
    at all -- an accepted-but-silently-inert flag is exactly the
    ``--debug``-shipped-before-subcommands-honoured-it bug class CLAUDE.md's
    "Usage surfaces" section warns about."""
    from pitloom.cli.parser import _build_parser

    parser = _build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([command, *target_args, "--allow-build"])


# The stray/no-effect build-flag warnings for every command and target kind
# are covered by tests/test_build_flag_warnings.py's cross-surface matrix.
