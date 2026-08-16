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
from pitloom.cli.commands import env as mod_env
from pitloom.cli.commands import generate as mod_generate
from pitloom.core.creation import CreationMetadata
from pitloom.ids import IdRegistry

from .shared import _make_simple_project

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_generate_mode_honours_project_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``loom generate`` must honour [tool.pitloom] settings from the target project."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "1.0.0"

[tool.pitloom]
pretty = true
describe-relationship = true
creation-datetime = "2026-04-01T00:00:00Z"
creation-comment = "configured in pyproject"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_generate(
        target: object,
        *,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: object = None,
        describe_relationship: object = None,
        registry: object = None,
        **kwargs: object,
    ) -> str:
        _ = (registry, kwargs)
        captured["target"] = target
        captured["output_path"] = output_path
        captured["creation_metadata"] = creation_metadata
        captured["pretty"] = pretty
        captured["describe_relationship"] = describe_relationship
        return "{}"

    monkeypatch.setattr(mod_generate, "generate", _fake_generate)
    monkeypatch.setattr(sys, "argv", ["loom", "generate", str(project_dir)])

    exit_code = __main__.main()

    assert exit_code == 0
    assert captured["target"] == str(project_dir)
    assert captured["pretty"] is True
    assert captured["describe_relationship"] is True
    assert isinstance(captured["creation_metadata"], CreationMetadata)
    creation = captured["creation_metadata"]
    assert creation.creation_datetime == "2026-04-01T00:00:00Z"
    assert creation.creation_comment == "configured in pyproject"


def test_generate_mode_default_file_headers_and_content_type_are_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No --extract-file-header/--content-type/--content-type-method
    flags: all three must reach generate() as None, deferring to
    [tool.pitloom] extract-file-header / [tool.pitloom.content-type]."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate(target: object, **kwargs: object) -> str:
        _ = target
        captured["extract_file_header"] = kwargs.get("extract_file_header")
        captured["content_type"] = kwargs.get("content_type")
        captured["content_type_method"] = kwargs.get("content_type_method")
        return "{}"

    monkeypatch.setattr(mod_generate, "generate", _fake_generate)
    monkeypatch.setattr(sys, "argv", ["loom", "generate", str(project_dir)])

    assert __main__.main() == 0
    assert captured["extract_file_header"] is None
    assert captured["content_type"] is None
    assert captured["content_type_method"] is None


@pytest.mark.parametrize(
    ("flag", "kwarg", "expected"),
    [
        ("--extract-file-header", "extract_file_header", True),
        ("--no-extract-file-header", "extract_file_header", False),
        ("--content-type", "content_type", True),
        ("--no-content-type", "content_type", False),
    ],
)
def test_generate_mode_file_headers_content_type_flags_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    flag: str,
    kwarg: str,
    expected: bool,
) -> None:
    """--extract-file-header/--no-extract-file-header and
    --content-type/--no-content-type must each override generate()'s
    corresponding param independently."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate(target: object, **kwargs: object) -> str:
        _ = target
        captured["extract_file_header"] = kwargs.get("extract_file_header")
        captured["content_type"] = kwargs.get("content_type")
        return "{}"

    monkeypatch.setattr(mod_generate, "generate", _fake_generate)
    monkeypatch.setattr(sys, "argv", ["loom", "generate", str(project_dir), flag])

    assert __main__.main() == 0
    assert captured[kwarg] is expected


def test_generate_mode_content_type_method_flag_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--content-type-method must reach generate() verbatim."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate(target: object, **kwargs: object) -> str:
        _ = target
        captured["content_type_method"] = kwargs.get("content_type_method")
        return "{}"

    monkeypatch.setattr(mod_generate, "generate", _fake_generate)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "generate", str(project_dir), "--content-type-method", "magika"],
    )

    assert __main__.main() == 0
    assert captured["content_type_method"] == "magika"


def test_deployed_dispatches_to_generate_env_sbom(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom env` must dispatch to generate_env_sbom()."""
    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate_env_sbom(
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object = None,
        offline: bool = False,
    ) -> str:
        _ = (creation_metadata, pretty, describe_relationship, registry, offline)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(mod_env, "generate_env_sbom", _fake_generate_env_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "env"])

    assert __main__.main() == 0
    assert captured["output_path"] == tmp_path / "deployed-environment.spdx3.json"


def test_ids_generate_cli_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom ids generate` smoke test through main(): real filesystem, no
    monkeypatching of IdRegistry itself since it is fast and local."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "ids", "generate"])

    assert __main__.main() == 0

    registry_path = tmp_path / "loom-ids.json"
    assert registry_path.exists()
    registry = IdRegistry.load(registry_path)
    assert "src/mod.py" in registry.files
