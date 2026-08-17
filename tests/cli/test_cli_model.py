# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI ``model``/``enrich`` command behaviour.

See also: tests/cli/test_cli_hf.py for Hugging Face URL/model-id routing
tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import model as mod_model
from pitloom.core.creation import CreationMetadata
from tests.cli.shared import ONNX_FIXTURE, SAFETENSORS_FIXTURE


def test_model_command_explicit_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit_out = tmp_path / "my-model.spdx3.json"
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object | None = None,
        **kwargs: object,
    ) -> str:
        _ = (registry, kwargs)
        _ = (model_path, creation_metadata, pretty, describe_relationship)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(
        sys, "argv", ["loom", "model", str(ONNX_FIXTURE), "-o", str(explicit_out)]
    )

    assert __main__.main() == 0
    assert captured["output_path"] == explicit_out


def test_model_command_default_output_path_uses_full_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object | None = None,
        **kwargs: object,
    ) -> str:
        _ = (registry, kwargs)
        _ = (model_path, creation_metadata, pretty, describe_relationship)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(SAFETENSORS_FIXTURE)])

    assert __main__.main() == 0
    out = captured["output_path"]
    assert isinstance(out, Path)
    assert out.name == "whisper-tiny-random.safetensors.spdx3.json"
    assert out.parent == Path.cwd()


def test_model_command_default_enrich_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No --enrich/--no-enrich flag passed: args.enrich must reach
    generate_model_sbom() as None, deferring to [tool.pitloom] enrich
    (off by default) rather than forcing either state."""
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object | None = None,
        **kwargs: object,
    ) -> str:
        _ = (
            registry,
            model_path,
            output_path,
            creation_metadata,
            pretty,
            describe_relationship,
        )
        captured["enrich"] = kwargs.get("enrich")
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(SAFETENSORS_FIXTURE)])

    assert __main__.main() == 0
    assert captured["enrich"] is None


@pytest.mark.parametrize(
    ("flag", "expected"),
    [("--enrich", True), ("--no-enrich", False)],
)
def test_model_command_enrich_flag_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    expected: bool,
) -> None:
    """--enrich/--no-enrich must override generate_model_sbom()'s enrich
    param explicitly, not just be silently dropped."""
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object | None = None,
        **kwargs: object,
    ) -> str:
        _ = (
            registry,
            model_path,
            output_path,
            creation_metadata,
            pretty,
            describe_relationship,
        )
        captured["enrich"] = kwargs.get("enrich")
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(SAFETENSORS_FIXTURE), flag])

    assert __main__.main() == 0
    assert captured["enrich"] is expected


def test_model_command_passes_pretty_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object | None = None,
        **kwargs: object,
    ) -> str:
        _ = (registry, kwargs)
        _ = (model_path, output_path, creation_metadata, describe_relationship)
        captured["pretty"] = pretty
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(ONNX_FIXTURE), "--pretty"])

    assert __main__.main() == 0
    assert captured["pretty"] is True


def test_model_command_passes_creation_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object | None = None,
        **kwargs: object,
    ) -> str:
        _ = (registry, kwargs)
        _ = (model_path, output_path, pretty, describe_relationship)
        captured["creation_metadata"] = creation_metadata
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", str(SAFETENSORS_FIXTURE), "--creator-name", "TestBot"],
    )

    assert __main__.main() == 0
    ci = captured["creation_metadata"]
    assert isinstance(ci, CreationMetadata)
    assert [c.name for c in ci.creators] == ["TestBot"]


def test_model_command_nonexistent_file_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["loom", "model", str(tmp_path / "no-such-model.safetensors")]
    )
    assert __main__.main() == 1


def test_model_command_verbose_shows_model_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object | None = None,
        **kwargs: object,
    ) -> str:
        _ = (registry, kwargs)
        _ = (model_path, output_path, creation_metadata, pretty, describe_relationship)
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(ONNX_FIXTURE), "-v"])

    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert str(ONNX_FIXTURE.resolve()) in out
    assert "Pitloom version" in out


def test_model_command_safetensors_produces_ai_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "whisper.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", str(SAFETENSORS_FIXTURE), "-o", str(out)],
    )

    assert __main__.main() == 0
    assert out.exists()

    doc = json.loads(out.read_text())
    graph = doc.get("@graph", [])
    types = [node.get("type") for node in graph]
    assert "ai_AIPackage" in types


def test_model_command_onnx_produces_ai_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "squeezenet.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", str(ONNX_FIXTURE), "-o", str(out)],
    )

    assert __main__.main() == 0
    assert out.exists()

    doc = json.loads(out.read_text())
    graph = doc.get("@graph", [])
    types = [node.get("type") for node in graph]
    assert "ai_AIPackage" in types


def test_model_command_safetensors_no_software_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "whisper.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", str(SAFETENSORS_FIXTURE), "-o", str(out)],
    )

    assert __main__.main() == 0

    doc = json.loads(out.read_text())
    graph = doc.get("@graph", [])
    types = [node.get("type") for node in graph]
    assert "software_Package" not in types


def test_model_command_onnx_sbom_root_is_ai_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "squeezenet.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", str(ONNX_FIXTURE), "-o", str(out)],
    )

    assert __main__.main() == 0

    doc = json.loads(out.read_text())
    graph = doc.get("@graph", [])
    sbom = next((n for n in graph if n.get("type") == "software_Sbom"), None)
    assert sbom is not None
    ai_pkg = next((n for n in graph if n.get("type") == "ai_AIPackage"), None)
    assert ai_pkg is not None
    assert ai_pkg["spdxId"] in sbom.get("rootElement", [])


def test_enrich_command_missing_model_file_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["loom", "enrich", str(tmp_path / "no-such-model.safetensors")]
    )
    assert __main__.main() == 1
