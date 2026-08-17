# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour.

See also: tests/cli/test_cli_project_creators.py for creator-metadata and
enrich-command flag passthrough tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import model as mod_model
from pitloom.cli.commands import project as mod_project
from pitloom.core.creation import CreationMetadata
from tests.cli.shared import SAFETENSORS_FIXTURE, _make_simple_project


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
        _ = (project_metadata, pitloom_config)
        captured["project_dir"] = project_dir
        captured["output_path"] = output_path
        captured["creation_metadata"] = creation_metadata
        captured["pretty"] = pretty
        captured["describe_relationship"] = describe_relationship
        return "{}"

    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "project", str(project_dir), "-o", str(output_path)],
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
            pretty,
            describe_relationship,
            project_metadata,
            pitloom_config,
        )
        captured["creation_metadata"] = creation_metadata
        return "{}"

    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(project_dir)])

    exit_code = __main__.main()

    assert exit_code == 0
    assert isinstance(captured["creation_metadata"], CreationMetadata)
    creation = captured["creation_metadata"]
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
            describe_relationship,
            project_metadata,
            pitloom_config,
        )
        captured["creation_metadata"] = creation_metadata
        captured["pretty"] = pretty
        return "{}"

    monkeypatch.chdir(current_dir)
    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(target_dir)])

    exit_code = __main__.main()

    assert exit_code == 0
    assert captured["pretty"] is False
    assert isinstance(captured["creation_metadata"], CreationMetadata)
    creation = captured["creation_metadata"]
    assert creation.creation_datetime == "2030-01-02T03:04:05Z"


def test_project_command_malformed_pitloom_config_surfaces_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed [tool.pitloom] section must be a hard error, not a silent
    fallback to default config.

    ``creator-name`` directly under ``[tool.pitloom]`` is the old/invalid
    single-valued form (creators now live under
    ``[[tool.pitloom.creator]]``), so ``read_pyproject`` raises ``ValueError``.
    ``_run_project_command`` reads the project once via ``read_project()``; that
    error must propagate rather than being silently discarded: exit code 1,
    no SBOM written.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        """
[project]
name = "x"

[tool.pitloom]
creator-name = 123
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def _fake_generate_project_sbom(*args: object, **kwargs: object) -> str:
        raise AssertionError(
            "generate_project_sbom must not run when [tool.pitloom] config is malformed"
        )

    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(project_dir)])

    exit_code = __main__.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "ERROR: SBOM generation failed" in captured.err
    assert not (project_dir / "x.spdx3.json").exists()
    assert not (tmp_path / "sbom.spdx3.json").exists()


def test_model_command_no_project_dir_required(
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
        _ = (creation_metadata, pretty, describe_relationship)
        captured["model_path"] = model_path
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(SAFETENSORS_FIXTURE)])

    assert __main__.main() == 0
    assert captured["model_path"] == SAFETENSORS_FIXTURE.resolve()


def test_project_command_default_file_headers_and_content_type_are_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No --extract-file-header/--content-type/--content-type-method
    flags: all three must reach generate_project_sbom() as None,
    deferring to [tool.pitloom] extract-file-header /
    [tool.pitloom.content-type] rather than forcing any state."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate_project_sbom(project_dir: Path, **kwargs: object) -> str:
        _ = project_dir
        captured["extract_file_header"] = kwargs.get("extract_file_header")
        captured["content_type"] = kwargs.get("content_type")
        captured["content_type_method"] = kwargs.get("content_type_method")
        return "{}"

    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(project_dir)])

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
def test_project_command_file_headers_content_type_flags_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    flag: str,
    kwarg: str,
    expected: bool,
) -> None:
    """--extract-file-header/--no-extract-file-header and
    --content-type/--no-content-type must each override
    generate_project_sbom()'s corresponding param independently, not
    just be silently dropped."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate_project_sbom(project_dir: Path, **kwargs: object) -> str:
        _ = project_dir
        captured["extract_file_header"] = kwargs.get("extract_file_header")
        captured["content_type"] = kwargs.get("content_type")
        return "{}"

    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(project_dir), flag])

    assert __main__.main() == 0
    assert captured[kwarg] is expected


@pytest.mark.parametrize("method", ["auto", "magika", "extension"])
def test_project_command_content_type_method_flag_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
) -> None:
    """--content-type-method must reach generate_project_sbom() verbatim,
    for each of its three valid choices."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate_project_sbom(project_dir: Path, **kwargs: object) -> str:
        _ = project_dir
        captured["content_type_method"] = kwargs.get("content_type_method")
        return "{}"

    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "project", str(project_dir), "--content-type-method", method],
    )

    assert __main__.main() == 0
    assert captured["content_type_method"] == method


def test_project_command_default_creation_comment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A CLI-generated SBOM must carry the CLI's default creation comment."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname = "cli-app"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    out = tmp_path / "cli-app.spdx3.json"
    monkeypatch.setattr(
        sys, "argv", ["loom", "project", str(project_dir), "-o", str(out)]
    )

    assert __main__.main() == 0

    doc = json.loads(out.read_text())
    creation_infos = [n for n in doc["@graph"] if n["type"] == "CreationInfo"]
    assert len(creation_infos) == 1
    assert creation_infos[0]["comment"] == "Generated via Pitloom CLI"
