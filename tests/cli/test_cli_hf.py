# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI Hugging Face URL/model-id routing.

See also: tests/cli/test_cli_model.py for ``model``/``enrich`` command
behaviour.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import model as mod_model
from pitloom.core.creation import CreationMetadata


def test_hf_url_routes_to_huggingface_sbom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        **kwargs: object,
    ) -> str:
        _ = (output_path, creation_metadata, pretty, describe_relationship, kwargs)
        captured["model_source"] = model_source
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", "https://huggingface.co/mistralai/Mistral-7B-v0.1"],
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
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        **kwargs: object,
    ) -> str:
        _ = (output_path, creation_metadata, pretty, describe_relationship, kwargs)
        captured["model_source"] = model_source
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", "Qwen/Qwen3-235B-A22B"])

    assert __main__.main() == 0
    assert captured["model_source"] == "Qwen/Qwen3-235B-A22B"


def test_hf_command_default_output_uses_model_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        **kwargs: object,
    ) -> str:
        _ = (model_source, creation_metadata, pretty, describe_relationship, kwargs)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", "https://huggingface.co/mistralai/Mistral-7B-v0.1"],
    )

    assert __main__.main() == 0
    out = captured["output_path"]
    assert isinstance(out, Path)
    assert out.name == "Mistral-7B-v0.1.spdx3.json"
    assert out.parent == Path.cwd()


def test_hf_command_explicit_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit_out = tmp_path / "mistral.spdx3.json"
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        **kwargs: object,
    ) -> str:
        _ = (model_source, creation_metadata, pretty, describe_relationship, kwargs)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "model",
            "mistralai/Mistral-7B-v0.1",
            "-o",
            str(explicit_out),
        ],
    )

    assert __main__.main() == 0
    assert captured["output_path"] == explicit_out


def test_hf_command_passes_creation_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        **kwargs: object,
    ) -> str:
        _ = (model_source, output_path, pretty, describe_relationship, kwargs)
        captured["creation_metadata"] = creation_metadata
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "model",
            "Qwen/Qwen3-235B-A22B",
            "--creator-name",
            "Researcher",
        ],
    )

    assert __main__.main() == 0
    ci = captured["creation_metadata"]
    assert isinstance(ci, CreationMetadata)
    assert [c.name for c in ci.creators] == ["Researcher"]


def test_hf_command_passes_pretty_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        **kwargs: object,
    ) -> str:
        _ = (
            model_source,
            output_path,
            creation_metadata,
            describe_relationship,
            kwargs,
        )
        captured["pretty"] = pretty
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", "mistralai/Mistral-7B-v0.1", "--pretty"],
    )

    assert __main__.main() == 0
    assert captured["pretty"] is True


def test_hf_command_verbose_shows_model_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _fake_generate_hf_sbom(
        model_source: str,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        **kwargs: object,
    ) -> str:
        _ = (
            model_source,
            output_path,
            creation_metadata,
            pretty,
            describe_relationship,
            kwargs,
        )
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", "https://huggingface.co/Qwen/Qwen3-235B-A22B", "-v"],
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
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        **kwargs: object,
    ) -> str:
        _ = (output_path, creation_metadata, pretty, describe_relationship, kwargs)
        captured["model_source"] = model_source
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "model",
            "https://huggingface.co/mistralai/Mistral-7B-v0.1/tree/main",
        ],
    )

    assert __main__.main() == 0
    # Tree path stripped - only owner/name retained
    assert captured["model_source"] == "mistralai/Mistral-7B-v0.1"
