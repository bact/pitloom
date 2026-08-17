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


def test_no_args_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["loom"])
    with pytest.raises(SystemExit) as excinfo:
        __main__.main()
    assert excinfo.value.code == 2
    assert "the following arguments are required: command" in capsys.readouterr().err
