# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import wheel as mod_wheel

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def _make_wheel(tmp_path: Path, name: str, version: str) -> Path:
    """Build a minimal .whl containing just a METADATA file."""
    wheel_path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    metadata_body = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(f"{name}-{version}.dist-info/METADATA", metadata_body)
    return wheel_path


def test_analyze_wheel_dispatches_to_wheel_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom wheel foo.whl` must dispatch to generate_wheel_sbom(),
    not the AI-model or Hugging Face paths."""
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_wheel(tmp_path, "pkg", "1.0.0")
    captured: dict[str, object] = {}

    def _fake_generate_analyzed_sbom(
        wheel_path_arg: Path,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object = None,
        offline: bool = False,
        provenance: object = None,
        **kwargs: object,
    ) -> str:
        _ = (creation_metadata, pretty, describe_relationship, registry, offline)
        captured["wheel_path"] = wheel_path_arg
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(mod_wheel, "generate_wheel_sbom", _fake_generate_analyzed_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", str(wheel_path)])

    assert __main__.main() == 0
    assert captured["wheel_path"] == wheel_path.resolve()
