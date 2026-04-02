# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.core.creation import CreationMetadata


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
