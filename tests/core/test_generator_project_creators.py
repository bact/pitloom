# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.generate_project_sbom creation metadata, tools,
and creators handling.

See also: :mod:`tests.core.test_generator_project`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pitloom.__about__ import __version__
from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata, Creator, Tool

from .conftest import _creation_agents


def test_generate_project_sbom_creation_comment_and_no_tool() -> None:
    """Creation comment must map to CreationInfo.comment and tool is optional."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "comment-app"
version = "0.1.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(
                creators=[Creator(name="Test Creator")],
                tools=[],
                creation_comment="Generated in CI",
            ),
        )
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["comment"] == "Generated in CI"
        assert "createdUsing" not in creation_infos[0]

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert not tool_elements


def test_generate_project_sbom_tool_summary_default_and_no_comment() -> None:
    """Default creation_tool gets a Pitloom-versioned summary; no comment by default."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "summary-app"
version = "0.1.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(tmppath)
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert "comment" not in creation_infos[0]

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert len(tool_elements) == 1
        assert tool_elements[0]["name"] == "Pitloom"
        assert tool_elements[0]["summary"] == f"Pitloom {__version__}"


def test_generate_project_sbom_tool_summary_omitted_for_custom_tool_name() -> None:
    """A user-supplied tool name gets no Pitloom-version summary."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "custom-tool-app"
version = "0.1.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(tools=[Tool("MyWrapper")]),
        )
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert len(tool_elements) == 1
        assert tool_elements[0]["name"] == "MyWrapper"
        assert "summary" not in tool_elements[0]


def test_generate_project_sbom_default_creator_is_software_agent() -> None:
    """With no named creator, createdBy is the SoftwareAgent "Pitloom", not a
    Person, and the package asserts no suppliedBy."""
    pyproject_content = """
[project]
name = "anon-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(generate_project_sbom(tmppath))["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["SoftwareAgent"]
        assert agents[0]["name"] == "Pitloom"
        assert not [e for e in graph if e["type"] == "Person"]

        packages = [e for e in graph if e["type"] == "software_Package"]
        assert packages and all("suppliedBy" not in p for p in packages)


def test_generate_project_sbom_named_creator_is_person_with_supplied_by() -> None:
    """A named creator becomes a Person in createdBy and the main package's
    suppliedBy."""
    pyproject_content = """
[project]
name = "named-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Alice", email="alice@example.com")]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["Person"]
        assert agents[0]["name"] == "Alice"

        main_pkg = next(
            e
            for e in graph
            if e["type"] == "software_Package" and e["name"] == "named-app"
        )
        assert main_pkg["suppliedBy"] == agents[0]["spdxId"]


def test_generate_project_sbom_organization_creator() -> None:
    """type='organization' makes the named creator an Organization."""
    pyproject_content = """
[project]
name = "org-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Acme Corp", type="organization")]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["Organization"]
        assert agents[0]["name"] == "Acme Corp"


@pytest.mark.parametrize(
    ("creator_type", "expected_element_type"),
    [
        ("person", "Person"),
        ("organization", "Organization"),
        ("software-agent", "SoftwareAgent"),
        ("agent", "Agent"),
    ],
)
def test_generate_project_sbom_all_valid_creator_types(
    creator_type: str, expected_element_type: str
) -> None:
    """Every SPDX 3 Agent subclass is a valid createdBy type: Person,
    Organization, SoftwareAgent, and the generic Agent."""
    pyproject_content = """
[project]
name = "creator-type-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Bot", type=creator_type)]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == [expected_element_type]
        assert agents[0]["name"] == "Bot"


def test_generate_project_sbom_invalid_creator_type_raises() -> None:
    """An unrecognised creator type raises ValueError naming the valid set,
    rather than silently falling back to Person."""
    pyproject_content = """
[project]
name = "bad-creator-type-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        with pytest.raises(ValueError, match="Invalid creator type"):
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Bot", type="robot")]
                ),
            )


def test_generate_project_sbom_creation_datetime_normalized_on_export() -> None:
    """Full ISO creation_datetime must be normalised only at SPDX export time."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "datetime-app"
version = "0.1.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(
                creators=[Creator(name="Test Creator")],
                creation_datetime="2026-01-01T12:34:56.789123+02:30",
            ),
        )
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["created"] == "2026-01-01T10:04:56Z"


def test_generate_project_sbom_multiple_creators_and_supplied_by_first() -> None:
    """Multiple creators become Agents in createdBy; suppliedBy is first."""
    pyproject_content = """
[project]
name = "multi-creator-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[
                        Creator(name="Acme Corp", type="organization"),
                        Creator(name="Alice", email="alice@example.com"),
                    ]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["Organization", "Person"]
        assert agents[0]["name"] == "Acme Corp"
        assert agents[1]["name"] == "Alice"

        main_pkg = next(
            e
            for e in graph
            if e["type"] == "software_Package" and e["name"] == "multi-creator-app"
        )
        assert main_pkg["suppliedBy"] == agents[0]["spdxId"]


def test_generate_project_sbom_multiple_creators_same_type_distinct_agents() -> None:
    """Two creators of the same type each become their own Agent."""
    pyproject_content = """
[project]
name = "multi-person-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[
                        Creator(name="Alice", type="person"),
                        Creator(name="Bob", type="person"),
                    ]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["Person", "Person"]
        assert [a["name"] for a in agents] == ["Alice", "Bob"]
        assert agents[0]["spdxId"] != agents[1]["spdxId"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert set(creation_infos[0]["createdBy"]) == {
            agents[0]["spdxId"],
            agents[1]["spdxId"],
        }


def test_generate_project_sbom_multiple_tools() -> None:
    """Multiple tools each become their own Tool in createdUsing."""
    pyproject_content = """
[project]
name = "multi-tool-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(
                tools=[Tool("Pitloom"), Tool("MyWrapper")]
            ),
        )
        graph = json.loads(sbom_json)["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
        tools = [by_id[ref] for ref in creation_infos[0]["createdUsing"]]

        assert [t["name"] for t in tools] == ["Pitloom", "MyWrapper"]
        assert tools[0]["summary"] == f"Pitloom {__version__}"
        assert "summary" not in tools[1]
