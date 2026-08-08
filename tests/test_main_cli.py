# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.core.creation import CreationMetadata
from pitloom.ids import IdRegistry

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


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
    ) -> str:
        _ = registry
        _ = (project_metadata, pitloom_config)
        captured["project_dir"] = project_dir
        captured["output_path"] = output_path
        captured["creation_metadata"] = creation_metadata
        captured["pretty"] = pretty
        captured["describe_relationship"] = describe_relationship
        return "{}"

    monkeypatch.setattr(__main__, "generate_project_sbom", _fake_generate_project_sbom)
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
    ) -> str:
        _ = registry
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

    monkeypatch.setattr(__main__, "generate_project_sbom", _fake_generate_project_sbom)
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
    ) -> str:
        _ = registry
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
    monkeypatch.setattr(__main__, "generate_project_sbom", _fake_generate_project_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(target_dir)])

    exit_code = __main__.main()

    assert exit_code == 0
    assert captured["pretty"] is False
    assert isinstance(captured["creation_metadata"], CreationMetadata)
    creation = captured["creation_metadata"]
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

    def _fake_generate_project_sbom(
        project_dir: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool | None = None,
        describe_relationship: bool | None = None,
        project_metadata: object | None = None,
        pitloom_config: object | None = None,
        registry: object | None = None,
    ) -> str:
        _ = registry
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
    monkeypatch.setattr(__main__, "generate_project_sbom", _fake_generate_project_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(target_dir), "-v"])

    exit_code = __main__.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert str(target_pyproject) in captured.out
    assert "Config file" in captured.out
    assert "creation_datetime     : None" in captured.out
    assert "creation_comment      : 'Generated via Pitloom CLI'" in captured.out


def test_project_mode_malformed_pitloom_config_surfaces_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed [tool.pitloom] section must be a hard error, not a silent
    fallback to default config.

    ``creator-name`` directly under ``[tool.pitloom]`` is the old/invalid
    single-valued form (creators now live under
    ``[[tool.pitloom.creator]]``), so ``read_pyproject`` raises ``ValueError``.
    ``_run_project_mode`` reads the project once via ``read_project()``; that
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

    monkeypatch.setattr(__main__, "generate_project_sbom", _fake_generate_project_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(project_dir)])

    exit_code = __main__.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Error generating SBOM" in captured.err
    assert not (project_dir / "x.spdx3.json").exists()
    assert not (tmp_path / "sbom.spdx3.json").exists()


# ---------------------------------------------------------------------------
# analyze: model-mode tests
# ---------------------------------------------------------------------------


def test_model_mode_no_project_dir_required(
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(SAFETENSORS_FIXTURE)])

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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(
        sys, "argv", ["loom", "model", str(ONNX_FIXTURE), "-o", str(explicit_out)]
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(SAFETENSORS_FIXTURE)])

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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(ONNX_FIXTURE), "--pretty"])

    assert __main__.main() == 0
    assert captured["pretty"] is True


def test_model_mode_passes_creation_info(
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", str(SAFETENSORS_FIXTURE), "--creator-name", "TestBot"],
    )

    assert __main__.main() == 0
    ci = captured["creation_metadata"]
    assert isinstance(ci, CreationMetadata)
    assert [c.name for c in ci.creators] == ["TestBot"]


def test_model_mode_nonexistent_file_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["loom", "model", str(tmp_path / "no-such-model.safetensors")]
    )
    assert __main__.main() == 1


def test_project_mode_default_creation_comment(
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


def test_project_mode_creator_type_organization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--creator-name with --creator-type organization emits an Organization."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname = "org-cli-app"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    out = tmp_path / "org-cli-app.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            str(project_dir),
            "-o",
            str(out),
            "--creator-name",
            "Acme Corp",
            "--creator-type",
            "organization",
        ],
    )

    assert __main__.main() == 0

    graph = json.loads(out.read_text())["@graph"]
    orgs = [e.get("name") for e in graph if e.get("type") == "Organization"]
    assert orgs == ["Acme Corp"]
    assert not [e for e in graph if e.get("type") == "Person"]


@pytest.mark.parametrize(
    ("creator_type", "expected_element_type"),
    [
        ("software-agent", "SoftwareAgent"),
        ("agent", "Agent"),
    ],
)
def test_project_mode_creator_type_software_agent_and_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    creator_type: str,
    expected_element_type: str,
) -> None:
    """--creator-type also accepts software-agent and the generic agent."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname = "bot-cli-app"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    out = tmp_path / "bot-cli-app.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            str(project_dir),
            "-o",
            str(out),
            "--creator-name",
            "CI Bot",
            "--creator-type",
            creator_type,
        ],
    )

    assert __main__.main() == 0

    graph = json.loads(out.read_text())["@graph"]
    matches = [e.get("name") for e in graph if e.get("type") == expected_element_type]
    assert "CI Bot" in matches


def test_project_mode_multiple_interleaved_creators(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Repeated --creator-name interleaved with --creator-type/--creator-email
    starts a new creator each time; --creator-type/--creator-email bind to
    the most recently named creator."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname = "multi-cli-app"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    out = tmp_path / "multi-cli-app.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            str(project_dir),
            "-o",
            str(out),
            "--creator-name",
            "Acme Corp",
            "--creator-type",
            "organization",
            "--creator-name",
            "Alice",
            "--creator-email",
            "alice@example.com",
        ],
    )

    assert __main__.main() == 0

    graph = json.loads(out.read_text())["@graph"]
    orgs = [e for e in graph if e.get("type") == "Organization"]
    persons = [e for e in graph if e.get("type") == "Person"]
    assert [o["name"] for o in orgs] == ["Acme Corp"]
    assert [p["name"] for p in persons] == ["Alice"]
    assert persons[0]["externalIdentifier"]


def test_project_mode_three_creators_type_and_email_bind_to_most_recent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """With three creators, each --creator-type/--creator-email must bind to
    the creator most recently named, not the first or a stale index -- a
    regression check for the switch from in-place mutation
    (``creators[-1].type = values``) to reconstructing the last ``Creator``
    (``creators[-1] = Creator(...)``) in ``_CreatorTypeAction``/
    ``_CreatorEmailAction``."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname = "three-cli-app"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    out = tmp_path / "three-cli-app.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            str(project_dir),
            "-o",
            str(out),
            "--creator-name",
            "Acme Corp",
            "--creator-type",
            "organization",
            "--creator-name",
            "Alice",
            "--creator-type",
            "person",
            "--creator-email",
            "alice@example.com",
            "--creator-name",
            "CI Bot",
            "--creator-type",
            "software-agent",
        ],
    )

    assert __main__.main() == 0

    graph = json.loads(out.read_text())["@graph"]
    orgs = {e["name"] for e in graph if e.get("type") == "Organization"}
    persons = {e.get("name"): e for e in graph if e.get("type") == "Person"}
    agents = {e["name"] for e in graph if e.get("type") == "SoftwareAgent"}

    assert orgs == {"Acme Corp"}
    assert set(persons) == {"Alice"}
    assert agents == {"CI Bot"}
    # The email must land on Alice, not on Acme Corp or CI Bot.
    assert persons["Alice"]["externalIdentifier"]


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


def test_project_mode_repeated_creation_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Repeated --creation-tool records more than one Tool in createdUsing."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname = "multi-tool-cli-app"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    out = tmp_path / "multi-tool-cli-app.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            str(project_dir),
            "-o",
            str(out),
            "--creation-tool",
            "Pitloom",
            "--creation-tool",
            "MyWrapper",
        ],
    )

    assert __main__.main() == 0

    graph = json.loads(out.read_text())["@graph"]
    tools = [e for e in graph if e.get("type") == "Tool"]
    assert sorted(t["name"] for t in tools) == ["MyWrapper", "Pitloom"]


def test_no_args_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["loom"])
    with pytest.raises(SystemExit) as excinfo:
        __main__.main()
    assert excinfo.value.code == 2
    assert "the following arguments are required: command" in capsys.readouterr().err


def test_model_mode_verbose_shows_model_path(
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(ONNX_FIXTURE), "-v"])

    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert str(ONNX_FIXTURE.resolve()) in out
    assert "Pitloom version" in out


# ---------------------------------------------------------------------------
# analyze: integration tests with real model fixtures
# ---------------------------------------------------------------------------


def test_model_mode_safetensors_produces_ai_package(
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


def test_model_mode_onnx_produces_ai_package(
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


def test_model_mode_safetensors_no_software_package(
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


def test_model_mode_onnx_sbom_root_is_ai_package(
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


# ---------------------------------------------------------------------------
# analyze: Hugging Face URL / model-ID mode tests (mocked)
# ---------------------------------------------------------------------------


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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_hf_sbom)
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", "Qwen/Qwen3-235B-A22B"])

    assert __main__.main() == 0
    assert captured["model_source"] == "Qwen/Qwen3-235B-A22B"


def test_hf_mode_default_output_uses_model_name(
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_hf_sbom)
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


def test_hf_mode_explicit_output_path(
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_hf_sbom)
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


def test_hf_mode_passes_creation_info(
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_hf_sbom)
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


def test_hf_mode_passes_pretty_flag(
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_hf_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "model", "mistralai/Mistral-7B-v0.1", "--pretty"],
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_hf_sbom)
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

    monkeypatch.setattr(__main__, "generate_model_sbom", _fake_generate_hf_sbom)
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


# ---------------------------------------------------------------------------
# `loom wheel` / `loom env` / `loom ids` dispatch
# ---------------------------------------------------------------------------


def _make_wheel(tmp_path: Path, name: str, version: str) -> Path:
    """Build a minimal .whl containing just a METADATA file."""
    wheel_path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    metadata_body = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(f"{name}-{version}.dist-info/METADATA", metadata_body)
    return wheel_path


def test_analyze_wheel_dispatches_to_wheel_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom wheel foo.whl` must dispatch to generate_wheel_sbom(),
    not the AI-model or Hugging Face paths."""
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_wheel(tmp_path, "pkg", "1.0.0")
    captured: dict[str, object] = {}

    def _fake_generate_analyzed_sbom(
        wheel_path_arg: Path,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object = None,
    ) -> str:
        _ = (creation_metadata, pretty, describe_relationship, registry)
        captured["wheel_path"] = wheel_path_arg
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(__main__, "generate_wheel_sbom", _fake_generate_analyzed_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", str(wheel_path)])

    assert __main__.main() == 0
    assert captured["wheel_path"] == wheel_path.resolve()


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
    ) -> str:
        _ = (creation_metadata, pretty, describe_relationship, registry)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(__main__, "generate_env_sbom", _fake_generate_env_sbom)
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


def test_ids_import_cli_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom ids import` smoke test through main(): harvests ids from a real
    SBOM produced by `loom project`."""
    pyproject_content = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "importable-pkg"
version = "1.0.0"
"""
    (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    sbom_path = tmp_path / "importable-pkg-1.0.0.spdx3.json"
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(tmp_path)])
    assert __main__.main() == 0
    assert sbom_path.exists()

    monkeypatch.setattr(sys, "argv", ["loom", "ids", "import", str(sbom_path)])
    assert __main__.main() == 0

    registry_path = tmp_path / "loom-ids.json"
    assert registry_path.exists()
    registry = IdRegistry.load(registry_path)
    assert "importable-pkg" in registry.entities
