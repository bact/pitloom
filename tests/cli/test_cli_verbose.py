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
from pitloom.cli.commands import project as mod_project

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


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

    def _fake_generate_project_sbom(
        project_dir: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool | None = None,
        describe_relationship: bool | None = None,
        project_metadata: object | None = None,
        pitloom_config: object | None = None,
        registry: object | None = None,
        **kwargs: object,
    ) -> str:
        _ = (registry, kwargs)
        _ = (
            project_dir,
            output_path,
            creation_metadata,
            pretty,
            describe_relationship,
            project_metadata,
            pitloom_config,
        )
        return "{}"

    monkeypatch.chdir(current_dir)
    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(target_dir), "-v"])

    exit_code = __main__.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert str(target_pyproject) in captured.out
    assert "Config file" in captured.out
    assert "creation_datetime     : None" in captured.out
    assert "creation_comment      : 'Generated via Pitloom CLI'" in captured.out


def test_build_creation_option_rows_full() -> None:
    from pitloom.cli.options import (
        _ResolvedCreationMetadata,
        _ResolvedCreators,
        _ResolvedTools,
        _ResolvedValue,
    )
    from pitloom.cli.verbose import _build_creation_option_rows
    from pitloom.core.creation import Creator, Tool

    creation = _ResolvedCreationMetadata(
        creators=_ResolvedCreators(
            value=[Creator(name="Alice", type="person", email="alice@example.com")],
            source="cli",
        ),
        tools=_ResolvedTools(value=[], source="default"),
        creation_datetime=_ResolvedValue(value="2026-08-17T00:00:00Z", source="cli"),
        creation_comment=_ResolvedValue(value="Test comment", source="cli"),
    )

    rows = _build_creation_option_rows(
        creation,
        eff_pretty=True,
        pretty_src="cli",
        eff_desc=False,
        desc_src="cli",
    )

    keys = [r[0] for r in rows]
    assert "creator[1]" in keys
    assert "tools" in keys
    assert "creation_datetime" in keys
    assert "creation_comment" in keys

    # Test None tools
    creation_none_tools = _ResolvedCreationMetadata(
        creators=_ResolvedCreators(value=[], source="default"),
        tools=_ResolvedTools(value=None, source="default"),
        creation_datetime=_ResolvedValue(value=None, source="default"),
        creation_comment=_ResolvedValue(value=None, source="default"),
    )
    rows_none = _build_creation_option_rows(
        creation_none_tools,
        eff_pretty=True,
        pretty_src="cli",
        eff_desc=False,
        desc_src="cli",
    )
    assert any(r[1].startswith("None") for r in rows_none if r[0] == "tools")
    assert any(r[1].startswith("[]") for r in rows_none if r[0] == "creators")

    # Test tools list
    creation_tools_list = _ResolvedCreationMetadata(
        creators=_ResolvedCreators(value=[], source="default"),
        tools=_ResolvedTools(value=[Tool(name="MyTool")], source="default"),
        creation_datetime=_ResolvedValue(value=None, source="default"),
        creation_comment=_ResolvedValue(value=None, source="default"),
    )
    rows_list = _build_creation_option_rows(
        creation_tools_list,
        eff_pretty=True,
        pretty_src="cli",
        eff_desc=False,
        desc_src="cli",
    )
    assert any(r[0] == "tool[1]" for r in rows_list)
