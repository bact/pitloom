# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI creator-metadata handling and enrich-command
flag passthrough.

See also: tests/cli/test_cli_project.py for main() config/pyproject
behaviour and project-command flag passthrough.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import enrich as mod_enrich
from tests.cli.shared import SAFETENSORS_FIXTURE


def test_project_command_creator_type_organization(
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
def test_project_command_creator_type_software_agent_and_agent(
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


def test_project_command_multiple_interleaved_creators(
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


def test_project_command_three_creators_type_and_email_bind_to_most_recent(
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


def test_project_command_repeated_creation_tool(
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


def test_enrich_command_project_dir_flag_passed_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--project-dir must reach enrich_model()'s project_target parameter
    so the fragment references the project-level ai_AIPackage id, not the
    single-model one -- the fix for the project-level merge bug."""
    captured: dict[str, object] = {}
    project_dir = tmp_path / "some-project"

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
            str(project_dir),
        ],
    )

    assert __main__.main() == 0
    assert captured["project_target"] == project_dir
