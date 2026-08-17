# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_creator_type_invalid_choice_rejected_by_argparse(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--creator-type bogus`` is rejected by argparse's ``choices=``
    before Pitloom even sees it -- CLI validation stays uniform with the
    eager ``Creator.__post_init__`` validation used by config/library
    callers."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            ".",
            "--creator-name",
            "Bot",
            "--creator-type",
            "bogus",
        ],
    )
    with pytest.raises(SystemExit):
        __main__.main()
    assert "invalid choice" in capsys.readouterr().err


def test_creator_type_before_creator_name_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--creator-type before any --creator-name is a clear argparse error."""
    monkeypatch.setattr(
        sys, "argv", ["loom", "project", ".", "--creator-type", "organization"]
    )
    with pytest.raises(SystemExit):
        __main__.main()
    assert "--creator-type must come after a --creator-name" in capsys.readouterr().err


def test_creator_email_before_creator_name_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--creator-email before any --creator-name is a clear argparse error."""
    monkeypatch.setattr(
        sys, "argv", ["loom", "project", ".", "--creator-email", "a@example.com"]
    )
    with pytest.raises(SystemExit):
        __main__.main()
    assert "--creator-email must come after a --creator-name" in capsys.readouterr().err


def test_resolve_project_paths_not_found(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    nonexistent = tmp_path / "does_not_exist"
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(nonexistent)])
    result = __main__.main()
    assert result == 1
    assert "ERROR: project directory not found" in capsys.readouterr().err


def test_resolve_project_paths_is_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sdist_file = tmp_path / "my_project-1.0.tar.gz"
    sdist_file.write_text("dummy content")

    from pitloom.cli.commands import project

    def fake_read_project(*args: Any, **kwargs: Any) -> Any:
        class MockMeta:
            name = "foo"
            version = "1.0"

        from pitloom.core.config import PitloomConfig

        return MockMeta(), PitloomConfig(), None

    monkeypatch.setattr(project, "read_project", fake_read_project)

    def fake_generate(*args: Any, **kwargs: Any) -> Any:
        pass

    monkeypatch.setattr(project, "generate_project_sbom", fake_generate)

    monkeypatch.setattr(sys, "argv", ["loom", "project", str(sdist_file), "-o", "-"])
    result = __main__.main()
    assert result == 0


def test_resolve_project_paths_no_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(empty_dir)])
    result = __main__.main()
    assert result == 1
    assert "ERROR: no project configuration found" in capsys.readouterr().err


def test_explicit_creation_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pitloom.cli.commands import project

    def fake_read_project(*args: Any, **kwargs: Any) -> Any:
        class MockMeta:
            name = "foo"
            version = "1.0"

        from pitloom.core.config import PitloomConfig

        return MockMeta(), PitloomConfig(), None

    monkeypatch.setattr(project, "read_project", fake_read_project)

    def fake_generate(*args: Any, **kwargs: Any) -> Any:
        pass

    monkeypatch.setattr(project, "generate_project_sbom", fake_generate)

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "pyproject.toml").write_text('[project]\nname="foo"\nversion="1.0"\n')

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            str(proj_dir),
            "-o",
            "-",
            "--creator-name",
            "TestUser",
            "--creator-type",
            "person",
            "--creation-datetime",
            "2026-08-17T00:00:00Z",
            "--creation-comment",
            "CLI Comment",
            "--creation-tool",
            "MyCustomTool",
        ],
    )
    result = __main__.main()
    assert result == 0


def test_no_creation_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pitloom.cli.commands import project

    def fake_read_project(*args: Any, **kwargs: Any) -> Any:
        class MockMeta:
            name = "foo"
            version = "1.0"

        from pitloom.core.config import PitloomConfig

        return MockMeta(), PitloomConfig(), None

    monkeypatch.setattr(project, "read_project", fake_read_project)

    def fake_generate(*args: Any, **kwargs: Any) -> Any:
        pass

    monkeypatch.setattr(project, "generate_project_sbom", fake_generate)

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "pyproject.toml").write_text('[project]\nname="foo"\nversion="1.0"\n')

    monkeypatch.setattr(
        sys, "argv", ["loom", "project", str(proj_dir), "-o", "-", "--no-creation-tool"]
    )
    result = __main__.main()
    assert result == 0
