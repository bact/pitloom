# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import enrich as mod_enrich
from pitloom.cli.commands import model as mod_model
from pitloom.cli.commands import project as mod_project
from pitloom.core.creation import CreationMetadata

from .shared import _make_simple_project

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
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

    monkeypatch.setattr(mod_model, "generate_model_sbom", _fake_generate_model_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(SAFETENSORS_FIXTURE)])

    assert __main__.main() == 0
    assert captured["model_path"] == SAFETENSORS_FIXTURE.resolve()


def test_project_mode_default_file_headers_and_content_type_are_none(
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
def test_project_mode_file_headers_content_type_flags_passed_through(
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
def test_project_mode_content_type_method_flag_passed_through(
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


def test_enrich_mode_project_dir_flag_passed_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--project-dir must reach enrich_model()'s project_target parameter
    so the fragment references the project-level ai_AIPackage id, not the
    single-model one -- the fix for the project-level merge bug."""
    captured: dict[str, object] = {}

    def _fake_enrich_model(
        source: Path,
        output_path: Path | None = None,
        creation_metadata: object | None = None,
        pretty: bool | None = None,
        **kwargs: object,
    ) -> str:
        _ = (source, output_path, creation_metadata, pretty)
        captured["project_target"] = kwargs.get("project_target")
        return "{}"

    monkeypatch.setattr(mod_enrich, "enrich_model", _fake_enrich_model)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "enrich",
            str(SAFETENSORS_FIXTURE),
            "--project-dir",
            "/tmp/some-project",
        ],
    )

    assert __main__.main() == 0
    assert captured["project_target"] == Path("/tmp/some-project")
