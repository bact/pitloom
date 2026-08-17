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


def test_resolve_common_options_file_target(tmp_path: Path) -> None:
    import argparse

    from pitloom.cli.options import _resolve_common_options

    f = tmp_path / "target.txt"
    f.write_text("a")
    args = argparse.Namespace(
        no_creation_tool=True,
        creators=[],
        creation_datetime=None,
        creation_comment=None,
    )
    conf, meta, pretty, desc = _resolve_common_options(
        args, target_dir=f, load_project=True
    )
    # The config should gracefully fallback to empty because no pyproject exists in parent
    assert conf.pretty is False


def test_resolve_common_options_not_found(tmp_path: Path) -> None:
    import argparse

    from pitloom.cli.options import _resolve_common_options

    # passing a non-existent dir
    missing = tmp_path / "missing"
    args = argparse.Namespace(
        no_creation_tool=True,
        creators=[],
        creation_datetime=None,
        creation_comment=None,
    )
    conf, meta, pretty, desc = _resolve_common_options(
        args, target_dir=missing, load_project=True
    )
    assert conf.pretty is False


def test_read_pitloom_tool_missing_sections(tmp_path: Path) -> None:
    from pitloom.cli.options import _load_pitloom_tool_section

    # No tool section
    p = tmp_path / "pyproject.toml"
    p.write_text("[project]\nname='a'\n")
    assert _load_pitloom_tool_section(p) == {}

    # No tool.pitloom section
    p.write_text("[tool.other]\nval=1\n")
    assert _load_pitloom_tool_section(p) == {}

    # Malformed toml
    p.write_text("[tool")
    assert _load_pitloom_tool_section(p) == {}


def test_resolve_describe_relationship_and_pretty() -> None:
    import argparse

    from pitloom.cli.options import (
        _resolve_describe_relationship,
        _resolve_pretty,
    )
    from pitloom.core.config import PitloomConfig

    conf = PitloomConfig(pretty=True, describe_relationship=True)
    args = argparse.Namespace(pretty=False, describe_relationship=False)

    # command line overrides all
    v, src = _resolve_pretty(args, conf, {})
    assert v is False
    assert src == "command-line"

    v, src = _resolve_describe_relationship(args, conf, {})
    assert v is False
    assert src == "command-line"

    # fallback to pyproject if no command line
    args = argparse.Namespace(pretty=None, describe_relationship=None)
    v, src = _resolve_pretty(args, conf, {"pretty": False})
    assert v is True  # value comes from conf, source indicates pyproject
    assert src == "pyproject.toml"

    v, src = _resolve_describe_relationship(
        args, conf, {"describe_relationship": False}
    )
    assert v is True
    assert src == "pyproject.toml"


def test_resolve_output_path_combinations() -> None:
    from pitloom.cli.options import _resolve_output_path
    from pitloom.core.config import PitloomConfig
    from pitloom.core.project import ProjectMetadata

    # Explicit path
    assert _resolve_output_path(
        Path("explicit.json"), ProjectMetadata(name="empty"), PitloomConfig()
    ) == Path("explicit.json")

    # basename override
    assert _resolve_output_path(
        None, ProjectMetadata(name="empty"), PitloomConfig(sbom_basename="mybase")
    ) == Path("mybase.spdx3.json")

    # fallback to project name and version
    assert _resolve_output_path(
        None, ProjectMetadata(name="pkg", version="1.0"), PitloomConfig()
    ) == Path("pkg-1.0.spdx3.json")

    # fallback to project name only
    assert _resolve_output_path(
        None, ProjectMetadata(name="pkg", version=""), PitloomConfig()
    ) == Path("pkg.spdx3.json")

    # ultimate fallback
    assert _resolve_output_path(
        None, ProjectMetadata(name="", version=""), PitloomConfig()
    ) == Path("sbom.spdx3.json")


def test_resolve_output_source() -> None:
    import argparse

    from pitloom.cli.options import _resolve_output_source
    from pitloom.core.config import PitloomConfig

    args = argparse.Namespace(output="file.json")
    assert _resolve_output_source(args, PitloomConfig(), None) == "command-line"

    args = argparse.Namespace(output=None)
    assert (
        _resolve_output_source(
            args, PitloomConfig(sbom_basename="out"), Path("pyproject.toml")
        )
        == "pyproject.toml"
    )

    assert (
        _resolve_output_source(args, PitloomConfig(sbom_basename=""), None) == "default"
    )
