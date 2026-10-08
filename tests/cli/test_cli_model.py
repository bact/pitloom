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
import os
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.__about__ import __version__
from pitloom.cli.commands import model as mod_model
from pitloom.core.creation import CreationMetadata
from tests.cli.shared import ONNX_FIXTURE, SAFETENSORS_FIXTURE
from tests.json_text_helpers import without_token_whitespace
from tests.kv_helpers import info_kv, sbom_output_path


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
    captured = capsys.readouterr()
    verbose = info_kv(captured.err)
    assert verbose["MODEL_FILE"] == str(ONNX_FIXTURE.resolve())
    assert verbose["PITLOOM_VERSION"] == __version__
    assert sbom_output_path(captured.out) == verbose["OUTPUT_PATH"]


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


def test_model_command_invalid_hf_target(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid HF target format returns exit code 1 with stderr error."""
    with monkeypatch.context() as m:
        m.setattr("pitloom.cli.commands.model.is_huggingface_source", lambda _t: True)
        m.setattr("pitloom.cli.commands.model.parse_hf_model_id", lambda _t: None)
        m.setattr(sys, "argv", ["loom", "model", "hf://invalid"])
        assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: not a valid Hugging Face URL or model ID" in err


def test_env_command_verbose(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """loom env -v prints version and output path."""
    out = tmp_path / "env.spdx3.json"
    monkeypatch.setattr(
        "pitloom.cli.commands.env.generate_env_sbom", lambda *a, **k: "{}"
    )
    monkeypatch.setattr(sys, "argv", ["loom", "env", "-v", "-o", str(out)])
    assert __main__.main() == 0
    captured = capsys.readouterr()
    verbose = info_kv(captured.err)
    assert verbose["PITLOOM_VERSION"] == __version__
    assert verbose["OUTPUT_PATH"] == str(out)
    assert sbom_output_path(captured.out) == str(out)


def _spaced_target(tmp_path: Path, *, sub_exists: bool) -> str:
    """``<tmp>/sub/../m.safetensors`` with the model in ``<tmp>``; ``sub``
    is a real directory only when *sub_exists* (else the path opens on no OS,
    though it resolves to a file)."""
    (tmp_path / "m.safetensors").write_bytes(SAFETENSORS_FIXTURE.read_bytes())
    if sub_exists:
        (tmp_path / "sub").mkdir()
    return f"{tmp_path}{os.sep}sub{os.sep}..{os.sep}m.safetensors"


@pytest.mark.parametrize("command", ["model", "enrich"])
@pytest.mark.parametrize("sub_exists", [True, False])
def test_dotdot_path_through_a_missing_directory_still_works(
    command: str,
    sub_exists: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The existence check and the generator agree on which file is read."""
    target = _spaced_target(tmp_path, sub_exists=sub_exists)
    out = tmp_path / "out.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", command, target, "-o", str(out)])
    assert __main__.main() == 0
    assert out.is_file()
    assert "not found" not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("command", "attr"),
    [
        ("model", "pitloom.cli.commands.model.generate_model_sbom"),
        ("enrich", "pitloom.cli.commands.enrich.enrich_model"),
    ],
)
def test_the_path_as_typed_reaches_the_generator_when_it_opens(
    command: str,
    attr: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Its log lines then name the file as the user wrote it."""
    target = _spaced_target(tmp_path, sub_exists=True)
    seen: list[object] = []

    def _spy(model_path: object, *_a: object, **_k: object) -> str:
        seen.append(model_path)
        return "{}"

    monkeypatch.setattr(attr, _spy)
    monkeypatch.setattr(sys, "argv", ["loom", command, target, "-o", "x.json"])
    __main__.main()
    assert seen == [Path(target)]
    assert ".." in str(seen[0])


def test_model_pretty_is_the_compact_sbom_with_indentation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End to end: ``--pretty`` adds whitespace between tokens only."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    outputs: dict[str, str] = {}
    for name, extra in (("compact", []), ("pretty", ["--pretty"])):
        out = tmp_path / f"{name}.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["loom", "model", str(SAFETENSORS_FIXTURE), "-o", str(out), *extra],
        )
        assert __main__.main() == 0
        outputs[name] = out.read_text(encoding="utf-8")
    assert outputs["pretty"] != outputs["compact"]
    assert without_token_whitespace(outputs["pretty"]).rstrip() == (
        outputs["compact"].rstrip()
    )
