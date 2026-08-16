# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_creator_type_invalid_choice_rejected_by_argparse(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--creator-type bogus`` is rejected by argparse's ``choices=``
    before Pitloom even sees it -- CLI validation stays uniform with the
    eager ``Creator.__post_init__`` validation used by config/library
    callers."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            ".",
            "--creator-name",
            "Bot",
            "--creator-type",
            "bogus",
        ],
    )
    with pytest.raises(SystemExit):
        __main__.main()
    assert "invalid choice" in capsys.readouterr().err


def test_creator_type_before_creator_name_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--creator-type before any --creator-name is a clear argparse error."""
    monkeypatch.setattr(
        sys, "argv", ["loom", "project", ".", "--creator-type", "organization"]
    )
    with pytest.raises(SystemExit):
        __main__.main()
    assert "--creator-type must come after a --creator-name" in capsys.readouterr().err


def test_creator_email_before_creator_name_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--creator-email before any --creator-name is a clear argparse error."""
    monkeypatch.setattr(
        sys, "argv", ["loom", "project", ".", "--creator-email", "a@example.com"]
    )
    with pytest.raises(SystemExit):
        __main__.main()
    assert "--creator-email must come after a --creator-name" in capsys.readouterr().err
