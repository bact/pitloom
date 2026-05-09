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
from pitloom.core.creation import CreationMetadata

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAFETENSORS_FIXTURE = FIXTURE_DIR / "safetensors" / "whisper-tiny-random.safetensors"
ONNX_FIXTURE = FIXTURE_DIR / "onnx" / "squeezenet1.1-7.onnx"


def test_main_uses_pretty_from_pyproject(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When --pretty is absent, main must pass pyproject pretty setting through."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    pyproject_path = project_dir / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
name = "demo"
version = "1.0.0"

[tool.pitloom]
pretty = true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = project_dir / "out.spdx3.json"
    captured: dict[str, object] = {}

    def _fake_generate_sbom(
        project_dir: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool | None = None,
        describe_relationship: bool | None = None,
    ) -> str:
        captured["project_dir"] = project_dir
        captured["output_path"] = output_path
        captured["creation_info"] = creation_info
        captured["pretty"] = pretty
        captured["describe_relationship"] = describe_relationship
        return "{}"

    monkeypatch.setattr(__main__, "generate_sbom", _fake_generate_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", str(project_dir), "-o", str(output_path)],
    )

    exit_code = __main__.main()

    assert exit_code == 0
    assert captured["pretty"] is True


def test_main_uses_legacy_creation_datetime_from_pyproject(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Legacy flat key ``[tool.pitloom] creation-datetime`` must be respected."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    pyproject_path = project_dir / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
name = "demo"
version = "1.0.0"

[tool.pitloom]
creation-datetime = "2026-04-01T00:00:00Z"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_generate_sbom(
        project_dir: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool | None = None,
        describe_relationship: bool | None = None,
    ) -> str:
        _ = (project_dir, output_path, pretty, describe_relationship)
        captured["creation_info"] = creation_info
        return "{}"

    monkeypatch.setattr(__main__, "generate_sbom", _fake_generate_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", str(project_dir)])

    exit_code = __main__.main()

    assert exit_code == 0
    assert isinstance(captured["creation_info"], CreationMetadata)
    creation = captured["creation_info"]
    assert creation.creation_datetime == "2026-04-01T00:00:00Z"


def test_main_reads_config_from_target_project_not_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """CLI config resolution must always use the input project directory."""
    current_dir = tmp_path / "current"
    current_dir.mkdir()
    (current_dir / "pyproject.toml").write_text(
        """
[project]
name = "current"
version = "0.1.0"

[tool.pitloom]
pretty = true
creation-datetime = "2040-01-01T00:00:00Z"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "pyproject.toml").write_text(
        """
[project]
name = "target"
version = "0.1.0"

[tool.pitloom]
pretty = false
creation-datetime = "2030-01-02T03:04:05Z"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_generate_sbom(
        project_dir: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool | None = None,
        describe_relationship: bool | None = None,
    ) -> str:
        _ = (project_dir, output_path, describe_relationship)
        captured["creation_info"] = creation_info
        captured["pretty"] = pretty
        return "{}"

    monkeypatch.chdir(current_dir)
    monkeypatch.setattr(__main__, "generate_sbom", _fake_generate_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", str(target_dir)])

    exit_code = __main__.main()

    assert exit_code == 0
    assert captured["pretty"] is False
    assert isinstance(captured["creation_info"], CreationMetadata)
    creation = captured["creation_info"]
    assert creation.creation_datetime == "2030-01-02T03:04:05Z"


def test_verbose_shows_target_config_file_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verbose output must show the target project's config file path."""
    current_dir = tmp_path / "current"
    current_dir.mkdir()
    (current_dir / "pyproject.toml").write_text(
        """
[project]
name = "current"
version = "0.1.0"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target_pyproject = target_dir / "pyproject.toml"
    target_pyproject.write_text(
        """
[project]
name = "target"
version = "0.1.0"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def _fake_generate_sbom(
        project_dir: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool | None = None,
        describe_relationship: bool | None = None,
    ) -> str:
        _ = (project_dir, output_path, creation_info, pretty, describe_relationship)
        return "{}"

    monkeypatch.chdir(current_dir)
    monkeypatch.setattr(__main__, "generate_sbom", _fake_generate_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", str(target_dir), "-v"])

    exit_code = __main__.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert str(target_pyproject) in captured.out
    assert "Config file" in captured.out
    assert "creation_datetime     : None" in captured.out
    assert "creation_comment      : None" in captured.out


# ---------------------------------------------------------------------------
# -m / --aimodel: model-mode tests
# ---------------------------------------------------------------------------


def test_model_mode_no_project_dir_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (creation_info, pretty, describe_relationship)
        captured["model_path"] = model_path
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(__main__, "generate_ai_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "-m", str(SAFETENSORS_FIXTURE)])

    assert __main__.main() == 0
    assert captured["model_path"] == SAFETENSORS_FIXTURE.resolve()


def test_model_mode_explicit_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit_out = tmp_path / "my-model.spdx3.json"
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_path, creation_info, pretty, describe_relationship)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(__main__, "generate_ai_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(
        sys, "argv", ["loom", "-m", str(ONNX_FIXTURE), "-o", str(explicit_out)]
    )

    assert __main__.main() == 0
    assert captured["output_path"] == explicit_out


def test_model_mode_default_output_path_uses_stem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_path, creation_info, pretty, describe_relationship)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(__main__, "generate_ai_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "-m", str(SAFETENSORS_FIXTURE)])

    assert __main__.main() == 0
    out = captured["output_path"]
    assert isinstance(out, Path)
    assert out.name == "whisper-tiny-random.spdx3.json"
    assert out.parent == Path.cwd()


def test_model_mode_passes_pretty_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_path, output_path, creation_info, describe_relationship)
        captured["pretty"] = pretty
        return "{}"

    monkeypatch.setattr(__main__, "generate_ai_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "-m", str(ONNX_FIXTURE), "--pretty"])

    assert __main__.main() == 0
    assert captured["pretty"] is True


def test_model_mode_passes_creation_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_path, output_path, pretty, describe_relationship)
        captured["creation_info"] = creation_info
        return "{}"

    monkeypatch.setattr(__main__, "generate_ai_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", str(SAFETENSORS_FIXTURE), "--creator-name", "TestBot"],
    )

    assert __main__.main() == 0
    ci = captured["creation_info"]
    assert isinstance(ci, CreationMetadata)
    assert ci.creator_name == "TestBot"


def test_model_mode_nonexistent_file_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["loom", "-m", str(tmp_path / "no-such-model.safetensors")]
    )
    assert __main__.main() == 1


def test_no_args_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["loom"])
    assert __main__.main() == 1
    assert "project_dir" in capsys.readouterr().err


def test_model_mode_verbose_shows_model_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _fake_generate_model_sbom(
        model_path: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_path, output_path, creation_info, pretty, describe_relationship)
        return "{}"

    monkeypatch.setattr(__main__, "generate_ai_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "-m", str(ONNX_FIXTURE), "-v"])

    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert str(ONNX_FIXTURE.resolve()) in out
    assert "Pitloom version" in out


# ---------------------------------------------------------------------------
# -m / --aimodel: integration tests with real model fixtures
# ---------------------------------------------------------------------------


def test_model_mode_safetensors_produces_ai_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "whisper.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", str(SAFETENSORS_FIXTURE), "-o", str(out)],
    )

    assert __main__.main() == 0
    assert out.exists()

    doc = json.loads(out.read_text())
    graph = doc.get("@graph", [])
    types = [node.get("type") for node in graph]
    assert "ai_AIPackage" in types


def test_model_mode_onnx_produces_ai_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "squeezenet.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", str(ONNX_FIXTURE), "-o", str(out)],
    )

    assert __main__.main() == 0
    assert out.exists()

    doc = json.loads(out.read_text())
    graph = doc.get("@graph", [])
    types = [node.get("type") for node in graph]
    assert "ai_AIPackage" in types


def test_model_mode_safetensors_no_software_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "whisper.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", str(SAFETENSORS_FIXTURE), "-o", str(out)],
    )

    assert __main__.main() == 0

    doc = json.loads(out.read_text())
    graph = doc.get("@graph", [])
    types = [node.get("type") for node in graph]
    assert "software_Package" not in types


def test_model_mode_onnx_sbom_root_is_ai_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "squeezenet.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", str(ONNX_FIXTURE), "-o", str(out)],
    )

    assert __main__.main() == 0

    doc = json.loads(out.read_text())
    graph = doc.get("@graph", [])
    sbom = next((n for n in graph if n.get("type") == "software_Sbom"), None)
    assert sbom is not None
    ai_pkg = next((n for n in graph if n.get("type") == "ai_AIPackage"), None)
    assert ai_pkg is not None
    assert ai_pkg["spdxId"] in sbom.get("rootElement", [])


# ---------------------------------------------------------------------------
# -m / --aimodel: HuggingFace URL / model-ID mode tests (mocked)
# ---------------------------------------------------------------------------


def test_hf_url_routes_to_huggingface_sbom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_info: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (output_path, creation_info, pretty, describe_relationship)
        captured["model_source"] = model_source
        return "{}"

    monkeypatch.setattr(__main__, "generate_huggingface_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", "https://huggingface.co/mistralai/Mistral-7B-v0.1"],
    )

    assert __main__.main() == 0
    assert captured["model_source"] == "mistralai/Mistral-7B-v0.1"


def test_hf_model_id_routes_to_huggingface_sbom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_info: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (output_path, creation_info, pretty, describe_relationship)
        captured["model_source"] = model_source
        return "{}"

    monkeypatch.setattr(__main__, "generate_huggingface_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "-m", "Qwen/Qwen3-235B-A22B"])

    assert __main__.main() == 0
    assert captured["model_source"] == "Qwen/Qwen3-235B-A22B"


def test_hf_mode_default_output_uses_model_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_info: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_source, creation_info, pretty, describe_relationship)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(__main__, "generate_huggingface_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", "https://huggingface.co/mistralai/Mistral-7B-v0.1"],
    )

    assert __main__.main() == 0
    out = captured["output_path"]
    assert isinstance(out, Path)
    assert out.name == "Mistral-7B-v0.1.spdx3.json"
    assert out.parent == Path.cwd()


def test_hf_mode_explicit_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit_out = tmp_path / "mistral.spdx3.json"
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_info: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_source, creation_info, pretty, describe_relationship)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(__main__, "generate_huggingface_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "-m",
            "mistralai/Mistral-7B-v0.1",
            "-o",
            str(explicit_out),
        ],
    )

    assert __main__.main() == 0
    assert captured["output_path"] == explicit_out


def test_hf_mode_passes_creation_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_info: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_source, output_path, pretty, describe_relationship)
        captured["creation_info"] = creation_info
        return "{}"

    monkeypatch.setattr(__main__, "generate_huggingface_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "-m",
            "Qwen/Qwen3-235B-A22B",
            "--creator-name",
            "Researcher",
        ],
    )

    assert __main__.main() == 0
    ci = captured["creation_info"]
    assert isinstance(ci, CreationMetadata)
    assert ci.creator_name == "Researcher"


def test_hf_mode_passes_pretty_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_info: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_source, output_path, creation_info, describe_relationship)
        captured["pretty"] = pretty
        return "{}"

    monkeypatch.setattr(__main__, "generate_huggingface_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", "mistralai/Mistral-7B-v0.1", "--pretty"],
    )

    assert __main__.main() == 0
    assert captured["pretty"] is True


def test_hf_mode_verbose_shows_model_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_info: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (model_source, output_path, creation_info, pretty, describe_relationship)
        return "{}"

    monkeypatch.setattr(__main__, "generate_huggingface_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "-m", "https://huggingface.co/Qwen/Qwen3-235B-A22B", "-v"],
    )

    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert "Qwen/Qwen3-235B-A22B" in out
    assert "Pitloom version" in out


def test_hf_url_with_tree_path_resolves_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_info: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
    ) -> str:
        _ = (output_path, creation_info, pretty, describe_relationship)
        captured["model_source"] = model_source
        return "{}"

    monkeypatch.setattr(__main__, "generate_huggingface_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "-m",
            "https://huggingface.co/mistralai/Mistral-7B-v0.1/tree/main",
        ],
    )

    assert __main__.main() == 0
    # Tree path stripped - only owner/name retained
    assert captured["model_source"] == "mistralai/Mistral-7B-v0.1"
