# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

from pitloom import __main__

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
