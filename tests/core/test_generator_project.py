# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.generate_project_sbom / build(): basic
generation, main-package PURL, output path, creation comment/tool
summary, and createdBy creator-type handling.

See also: tests/core/test_generator_project_structure.py for
creator/tool multiplicity, sentimentdemo structure, dependency-name
parsing, fragments, setup.cfg, and preparsed-metadata tests.
tests/core/test_generator_project_enrichment.py for project-level
enrichment and license-conflict-detection tests.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pitloom.__about__ import __version__
from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.document import _magika_version, build
from pitloom.core.creation import CreationMetadata, Creator, Tool
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata

from .conftest import _creation_agents


def test_generate_project_sbom_basic() -> None:
    """Test basic SBOM generation from a simple project."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-package"
version = "1.0.0"
description = "A test package"
dependencies = ["requests>=2.28.0", "numpy==1.24.0"]

[project.urls]
Homepage = "https://example.com"
Source = "https://github.com/test/test-package"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(
                creators=[Creator(name="Test Creator", email="test@example.com")],
            ),
        )

        # Parse and validate JSON
        sbom_data = json.loads(sbom_json)

        # Check basic structure
        assert "@context" in sbom_data
        assert "@graph" in sbom_data
        assert sbom_data["@context"] == "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"

        graph = sbom_data["@graph"]
        assert len(graph) > 0

        # Check for required elements
        element_types = {elem["type"] for elem in graph}
        assert "CreationInfo" in element_types
        assert "Person" in element_types
        assert "software_Package" in element_types
        assert "software_Sbom" in element_types
        assert "SpdxDocument" in element_types

        # Check package details
        packages = [elem for elem in graph if elem["type"] == "software_Package"]
        main_package = [p for p in packages if p["name"] == "test-package"][0]
        assert main_package["software_packageVersion"] == "1.0.0"

        # Check dependencies
        dep_packages = [p for p in packages if p["name"] in ["requests", "numpy"]]
        assert len(dep_packages) >= 2


def test_generate_project_sbom_basic_main_package_purl() -> None:
    """The main package must carry a pkg:pypi PURL when a real version is known."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-package"
version = "1.0.0"
description = "A test package"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_project_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        main_package = next(p for p in packages if p["name"] == "test-package")
        assert main_package["software_packageUrl"] == "pkg:pypi/test-package@1.0.0"


def test_generate_project_sbom_invalid_content_type_method_raises() -> None:
    """An explicit content_type_method outside auto/magika/extension must
    raise immediately, matching the TOML/CLI paths' own validation --
    not silently fall through to guess_content_type's "auto" behavior."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-package"
version = "1.0.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        with pytest.raises(ValueError, match="content_type_method must be one of"):
            generate_project_sbom(tmppath, content_type_method="mimetypes")


def test_build_main_package_no_purl_without_real_version() -> None:
    """No PURL is set when the version is unknown."""
    project = ProjectMetadata(name="no-version-project")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    main_package = next(p for p in packages if p["name"] == "no-version-project")
    assert "software_packageUrl" not in main_package


def test_build_main_package_purl_normalizes_name() -> None:
    """PURL name is lowercased with underscores replaced by hyphens."""
    project = ProjectMetadata(name="My_Package", version="2.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    main_package = next(p for p in packages if p["name"] == "My_Package")
    assert main_package["software_packageUrl"] == "pkg:pypi/my-package@2.0.0"


def test_magika_version_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """_magika_version() must only hit importlib.metadata once per process,
    not once per magika-detected file -- real disk I/O otherwise repeated
    for a value that can't change mid-process."""
    _magika_version.cache_clear()
    call_count = 0

    # pylint: disable=unused-argument

    def _fake_pkg_version(name: str) -> str:
        nonlocal call_count
        call_count += 1
        return "1.2.3"

    monkeypatch.setattr(
        "pitloom.assemble.spdx3.document._pkg_version", _fake_pkg_version
    )

    assert _magika_version() == "1.2.3"
    assert _magika_version() == "1.2.3"
    assert _magika_version() == "1.2.3"
    assert call_count == 1
    _magika_version.cache_clear()


def test_generate_project_sbom_to_output_path() -> None:
    """Test SBOM generation written to an output file."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "simple-app"
version = "0.5.0"
description = "A simple application"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        output_path = tmppath / "sbom.spdx3.json"
        generate_project_sbom(tmppath, output_path=output_path)

        assert output_path.exists()

        # Validate the file content
        sbom_data = json.loads(output_path.read_text())
        assert "@context" in sbom_data
        assert "@graph" in sbom_data


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
