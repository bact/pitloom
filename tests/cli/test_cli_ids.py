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
from pitloom.ids import IdRegistry

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_ids_import_cli_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom ids import` smoke test through main(): harvests ids from a real
    SBOM produced by `loom project`."""
    pyproject_content = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "importable-pkg"
version = "1.0.0"
"""
    (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    sbom_path = tmp_path / "importable-pkg-1.0.0.spdx3.json"
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(tmp_path)])
    assert __main__.main() == 0
    assert sbom_path.exists()

    monkeypatch.setattr(sys, "argv", ["loom", "ids", "import", str(sbom_path)])
    assert __main__.main() == 0

    registry_path = tmp_path / "loom-ids.json"
    assert registry_path.exists()
    registry = IdRegistry.load(registry_path)
    assert "importable-pkg" in registry.entities
