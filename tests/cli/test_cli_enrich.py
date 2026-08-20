# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pitloom import __main__

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_enrich_command_writes_fragment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`loom enrich <model>` must write a bare-@graph fragment containing
    the enrichment findings -- it always runs enrichment regardless of
    [tool.pitloom] enrich (calling it is itself the opt-in)."""
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(SAFETENSORS_FIXTURE.read_bytes())
    (tmp_path / "README.md").write_text(
        "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
    )
    out = tmp_path / "model.enrich.spdx3.json"

    monkeypatch.setattr(
        sys, "argv", ["loom", "enrich", str(model_path), "-o", str(out)]
    )

    assert __main__.main() == 0
    assert out.exists()

    doc = json.loads(out.read_text())
    assert set(doc.keys()) == {"@context", "@graph"}
    types = {node.get("type") for node in doc["@graph"]}
    assert "SpdxDocument" not in types
    assert "ai_AIPackage" not in types
    ds_pkgs = [n for n in doc["@graph"] if n.get("type") == "dataset_DatasetPackage"]
    assert len(ds_pkgs) == 1
    assert ds_pkgs[0]["name"] == "tiny-imagenet"


def test_enrich_command_default_output_path_uses_full_filename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "mymodel.safetensors"
    model_path.write_bytes(SAFETENSORS_FIXTURE.read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "enrich", str(model_path)])

    assert __main__.main() == 0
    assert (tmp_path / "mymodel.safetensors.enrich.spdx3.json").exists()


def test_enrich_command_no_enrich_flag_suppresses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`loom enrich --no-enrich` must write an empty (but valid) fragment
    rather than silently ignoring the flag -- calling `loom enrich` is
    normally itself the opt-in, but --no-enrich is the documented escape
    hatch for scripting symmetry with the other subcommands' flag."""
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(SAFETENSORS_FIXTURE.read_bytes())
    (tmp_path / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")
    out = tmp_path / "model.enrich.spdx3.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "enrich", str(model_path), "--no-enrich", "-o", str(out)],
    )

    assert __main__.main() == 0
    doc = json.loads(out.read_text())
    assert not [n for n in doc["@graph"] if n.get("type") == "dataset_DatasetPackage"]


def test_enrich_command_verbose_mode_without_project_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`loom enrich --verbose` without `--project-dir` must skip the
    "Project dir" line entirely, not print it empty."""
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(SAFETENSORS_FIXTURE.read_bytes())
    out = tmp_path / "model.enrich.spdx3.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "enrich", str(model_path), "-o", str(out), "--verbose"],
    )
    result = __main__.main()
    assert result == 0

    captured = capsys.readouterr()
    assert "Pitloom version:" in captured.out
    assert "Model file      :" in captured.out
    assert "Project dir     :" not in captured.out


def test_enrich_command_model_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nonexistent = tmp_path / "does_not_exist.safetensors"
    monkeypatch.setattr(sys, "argv", ["loom", "enrich", str(nonexistent)])
    result = __main__.main()
    assert result == 1
    assert "ERROR: model file not found" in capsys.readouterr().err


def test_enrich_command_verbose_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(SAFETENSORS_FIXTURE.read_bytes())

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname="foo"\nversion="1.0"\n'
    )

    out = tmp_path / "model.enrich.spdx3.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "enrich",
            str(model_path),
            "-o",
            str(out),
            "--verbose",
            "--project-dir",
            str(project_dir),
        ],
    )
    result = __main__.main()
    assert result == 0

    captured = capsys.readouterr()
    assert "Pitloom version:" in captured.out
    assert "Model file      :" in captured.out
    assert "Project dir     :" in captured.out
