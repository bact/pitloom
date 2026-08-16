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
