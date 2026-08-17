# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for creator and tool handling in the Hatchling build hook.

See also:
- :mod:`tests.extract.test_hatch_hook_hook_basic` for hook lifecycle and staging.
- :mod:`tests.extract.test_hatch_hook_hook_integration` for integration tests.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.__about__ import __version__

from .conftest import (
    make_hook,
    write_pyproject,
    write_pyproject_with_pitloom_config,
)

pytest.importorskip("hatchling", reason="hatchling is required for hook tests")


def test_hook_creator_name_propagated() -> None:
    """[[tool.pitloom.creator]] name must appear in the SBOM graph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            '[[tool.pitloom.creator]]\nname = "Test Creator"\n',
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]
        names = [e.get("name") for e in graph if e.get("type") == "Person"]
        assert "Test Creator" in names

        hook.finalize("standard", build_data, "")


def test_hook_organization_creator_from_config() -> None:
    """[[tool.pitloom.creator]] type = organization emits Organization."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            '[[tool.pitloom.creator]]\nname = "Acme Corp"\ntype = "organization"\n',
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        graph = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))[
            "@graph"
        ]
        orgs = [e.get("name") for e in graph if e.get("type") == "Organization"]
        assert orgs == ["Acme Corp"]
        assert not [e for e in graph if e.get("type") == "Person"]

        hook.finalize("standard", build_data, "")


def test_hook_multiple_creators_appear_in_graph() -> None:
    """Multiple [[tool.pitloom.creator]] tables all appear in the SBOM @graph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            "[[tool.pitloom.creator]]\n"
            'name = "Acme Corp"\n'
            'type = "organization"\n'
            "\n"
            "[[tool.pitloom.creator]]\n"
            'name = "Alice"\n'
            'email = "alice@example.com"\n',
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        graph = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))[
            "@graph"
        ]
        orgs = [e.get("name") for e in graph if e.get("type") == "Organization"]
        persons = [e.get("name") for e in graph if e.get("type") == "Person"]
        assert orgs == ["Acme Corp"]
        assert persons == ["Alice"]

        creation_infos = [e for e in graph if e.get("type") == "CreationInfo"]
        assert len(creation_infos) == 1
        assert len(creation_infos[0]["createdBy"]) == 2

        hook.finalize("standard", build_data, "")


@pytest.mark.parametrize(
    ("creator_type", "expected_element_type"),
    [
        ("software-agent", "SoftwareAgent"),
        ("agent", "Agent"),
    ],
)
def test_hook_software_agent_and_generic_agent_creator_from_config(
    creator_type: str, expected_element_type: str
) -> None:
    """[[tool.pitloom.creator]] type also allows SoftwareAgent or Agent."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            f'[[tool.pitloom.creator]]\nname = "CI Bot"\ntype = "{creator_type}"\n',
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        graph = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))[
            "@graph"
        ]
        matches = [
            e.get("name") for e in graph if e.get("type") == expected_element_type
        ]
        assert "CI Bot" in matches

        hook.finalize("standard", build_data, "")


def test_hook_default_creator_is_software_agent() -> None:
    """With no [[tool.pitloom.creator]], hook records SoftwareAgent 'Pitloom'."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        graph = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))[
            "@graph"
        ]
        agents = [e for e in graph if e.get("type") == "SoftwareAgent"]
        assert [a["name"] for a in agents] == ["Pitloom"]
        assert not [e for e in graph if e.get("type") == "Person"]

        hook.finalize("standard", build_data, "")


def test_hook_creation_comment_and_tool_summary() -> None:
    """Hook must stamp a build-hook comment and a Pitloom-versioned Tool.summary."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["comment"] == (
            "Generated via Pitloom Hatchling build hook (PEP 770)"
        )

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert len(tool_elements) == 1
        assert tool_elements[0]["summary"] == f"Pitloom {__version__}"

        hook.finalize("standard", build_data, "")
