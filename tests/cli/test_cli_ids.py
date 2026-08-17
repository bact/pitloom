# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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


def test_ids_generate_registry_load_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # _load_or_create_registry returns None when it fails (e.g. invalid JSON)
    registry_path = tmp_path / "loom-ids.json"
    registry_path.write_text("invalid json")

    monkeypatch.setattr(
        sys, "argv", ["loom", "ids", "generate", "--registry", str(registry_path)]
    )
    result = __main__.main()
    assert result == 1


def test_ids_generate_no_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)

    # We provide no paths and the default path resolution fails
    monkeypatch.setattr(sys, "argv", ["loom", "ids", "generate"])
    result = __main__.main()
    assert result == 1
    assert "ERROR: no source/data directories found" in capsys.readouterr().err


def test_ids_import_sbom_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nonexistent = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(sys, "argv", ["loom", "ids", "import", str(nonexistent)])
    result = __main__.main()
    assert result == 1
    assert "ERROR: SBOM file not found" in capsys.readouterr().err


def test_ids_import_registry_load_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sbom_path = tmp_path / "valid.json"
    sbom_path.write_text("{}")

    registry_path = tmp_path / "loom-ids.json"
    registry_path.write_text("invalid json")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "ids", "import", str(sbom_path), "--registry", str(registry_path)],
    )
    result = __main__.main()
    assert result == 1


def test_ids_import_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sbom_path = tmp_path / "valid.json"
    sbom_path.write_text("{}")

    # Force an exception during import_sbom
    from pitloom.ids import IdRegistry

    def fake_import(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("Simulated failure")

    monkeypatch.setattr(IdRegistry, "import_sbom", fake_import)

    monkeypatch.setattr(sys, "argv", ["loom", "ids", "import", str(sbom_path)])
    result = __main__.main()
    assert result == 1
    assert "ERROR: failed to import SBOM" in capsys.readouterr().err


def test_ids_cli_invalid_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # argparse will normally catch this, but if we bypass it
    # or test `_run_ids_cli` directly
    import argparse

    from pitloom.cli.ids import _run_ids_cli

    args = argparse.Namespace(ids_command="invalid")
    result = _run_ids_cli(args)
    assert result == 1
