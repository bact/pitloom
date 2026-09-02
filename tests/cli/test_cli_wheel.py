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


def test_wheel_command_wires_max_source_metadata_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom wheel --max-source-metadata-bytes N` must reach
    generate_wheel_sbom() via resolve_effective_provenance() -- a
    regression test for a call site that was missed when this flag was
    added to every other generate-family command."""
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
        _ = (
            wheel_path_arg,
            output_path,
            creation_metadata,
            pretty,
            describe_relationship,
            registry,
            offline,
        )
        captured["provenance"] = provenance
        return "{}"

    monkeypatch.setattr(mod_wheel, "generate_wheel_sbom", _fake_generate_analyzed_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "wheel", str(wheel_path), "--max-source-metadata-bytes", "5000"],
    )

    assert __main__.main() == 0
    assert captured["provenance"] is not None
    provenance = captured["provenance"]
    assert provenance.max_source_metadata_bytes == 5000  # type: ignore[attr-defined]


def test_wheel_command_nonexistent_and_verbose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Non-existent wheel returns code 1; verbose mode prints wheel info."""
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", str(tmp_path / "missing.whl")])
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: wheel file not found" in err

    # Verbose mode on valid wheel
    wheel_path = _make_wheel(tmp_path, "pkg_v", "1.0.0")
    monkeypatch.setattr(mod_wheel, "generate_wheel_sbom", lambda *a, **k: "{}")
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", "-v", str(wheel_path)])
    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert "Pitloom version" in out
    assert "Wheel file" in out


def test_report_embed_result(capsys: pytest.CaptureFixture[str]) -> None:
    """_report_embed_result prints the confirmation to stdout (this
    command's primary result output) and the two INFO: side-effect lines
    to stderr, matching every other INFO:/WARNING:/ERROR: line."""
    from pitloom.cli.commands.embed_wheel import _report_embed_result
    from pitloom.logging_config import configure_logging

    # The two side-effect lines go through logging (see CLAUDE.md's "CLI
    # output" section), unlike the confirmation line above them -- calling
    # this function directly, without going through __main__.main(), skips
    # the configure_logging() call that normally wires INFO: up to stderr.
    configure_logging()

    _report_embed_result(
        "sbom.spdx.json",
        "pkg.whl",
        ("old_sbom.spdx.json",),
        timestamp_floored=True,
    )
    captured = capsys.readouterr()
    assert "embedded sbom.spdx.json into pkg.whl" in captured.out
    assert "removed stale SBOM old_sbom.spdx.json" in captured.err
    assert "timestamp was before 1980" in captured.err
