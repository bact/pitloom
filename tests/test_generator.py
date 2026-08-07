# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for SBOM generation."""

import json
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__about__ import __version__
from pitloom.assemble import (
    generate_analyzed_sbom,
    generate_deployed_sbom,
    generate_sbom,
)
from pitloom.assemble.spdx3.document import build, build_deployed, build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata, Creator, Tool
from pitloom.core.document import DocumentModel
from pitloom.core.models import generate_spdx_id
from pitloom.core.project import PhantomDependency, ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract.ai_model import read_ai_model
from pitloom.ids import IdRegistry


def test_generate_sbom_basic() -> None:
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

        sbom_json = generate_sbom(
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


def test_generate_sbom_basic_main_package_purl() -> None:
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

        sbom_json = generate_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        main_package = next(p for p in packages if p["name"] == "test-package")
        assert main_package["software_packageUrl"] == "pkg:pypi/test-package@1.0.0"


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


def test_build_package_files_have_sha256_verified_using() -> None:
    """Every file (not directory) software_File must carry a SHA-256
    verifiedUsing hash matching the corresponding ProjectFile.digest_sha256."""
    files = [
        ProjectFile(
            physical_path="src/pkg/__init__.py",
            distribution_path="pkg/__init__.py",
            digest_sha256="a" * 64,
        ),
        ProjectFile(
            physical_path="src/pkg/module.py",
            distribution_path="pkg/module.py",
            digest_sha256="b" * 64,
        ),
    ]
    project = ProjectMetadata(name="file-hash-project", version="1.0.0", files=files)
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    file_elements = [e for e in graph if e.get("type") == "software_File"]
    by_name = {e["name"]: e for e in file_elements}

    # Directory node: no verifiedUsing hash.
    assert "verifiedUsing" not in by_name["pkg"]

    # File nodes: exactly one SHA-256 Hash matching the source digest.
    for pf in files:
        file_elem = by_name[pf.distribution_path]
        assert file_elem["software_fileKind"] == "file"
        (hash_obj,) = file_elem["verifiedUsing"]
        assert hash_obj["algorithm"] == "sha256"
        assert hash_obj["hashValue"] == pf.digest_sha256


def test_generate_sbom_to_output_path() -> None:
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
        generate_sbom(tmppath, output_path=output_path)

        assert output_path.exists()

        # Validate the file content
        sbom_data = json.loads(output_path.read_text())
        assert "@context" in sbom_data
        assert "@graph" in sbom_data


def test_generate_sbom_creation_comment_and_no_tool() -> None:
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

        sbom_json = generate_sbom(
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


def test_generate_sbom_tool_summary_default_and_no_comment() -> None:
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

        sbom_json = generate_sbom(tmppath)
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert "comment" not in creation_infos[0]

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert len(tool_elements) == 1
        assert tool_elements[0]["name"] == "Pitloom"
        assert tool_elements[0]["summary"] == f"Pitloom {__version__}"


def test_generate_sbom_tool_summary_omitted_for_custom_tool_name() -> None:
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

        sbom_json = generate_sbom(
            tmppath,
            creation_metadata=CreationMetadata(tools=[Tool("MyWrapper")]),
        )
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert len(tool_elements) == 1
        assert tool_elements[0]["name"] == "MyWrapper"
        assert "summary" not in tool_elements[0]


def _creation_agents(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the elements referenced by the single CreationInfo.createdBy."""
    creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
    assert len(creation_infos) == 1
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    return [by_id[ref] for ref in creation_infos[0]["createdBy"]]


def test_generate_sbom_default_creator_is_software_agent() -> None:
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

        graph = json.loads(generate_sbom(tmppath))["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["SoftwareAgent"]
        assert agents[0]["name"] == "Pitloom"
        assert not [e for e in graph if e["type"] == "Person"]

        packages = [e for e in graph if e["type"] == "software_Package"]
        assert packages and all("suppliedBy" not in p for p in packages)


def test_generate_sbom_named_creator_is_person_with_supplied_by() -> None:
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
            generate_sbom(
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


def test_generate_sbom_organization_creator() -> None:
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
            generate_sbom(
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
def test_generate_sbom_all_valid_creator_types(
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
            generate_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Bot", type=creator_type)]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == [expected_element_type]
        assert agents[0]["name"] == "Bot"


def test_generate_sbom_invalid_creator_type_raises() -> None:
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
            generate_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Bot", type="robot")]
                ),
            )


def test_generate_sbom_creation_datetime_normalized_on_export() -> None:
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

        sbom_json = generate_sbom(
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


def test_generate_sbom_multiple_creators_and_supplied_by_first() -> None:
    """Multiple creators each become their own Agent in createdBy, of the
    correct subclass; suppliedBy on the main package is the *first* named
    creator."""
    pyproject_content = """
[project]
name = "multi-creator-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_sbom(
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


def test_generate_sbom_multiple_creators_same_type_distinct_agents() -> None:
    """Two creators of the *same* type each become their own Agent, with
    distinct spdxIds, and both are present in createdBy -- same-type
    creators must not collapse into a single Agent."""
    pyproject_content = """
[project]
name = "multi-person-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_sbom(
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


def test_generate_sbom_multiple_tools() -> None:
    """Multiple tools each become their own Tool in createdUsing."""
    pyproject_content = """
[project]
name = "multi-tool-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_sbom(
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


def test_generate_sbom_sentimentdemo_structure() -> None:
    """Test SBOM generation with sentimentdemo-like structure."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sentimentdemo"
dynamic = ["version"]
description = "A simple sentiment analysis application"
readme = "README.md"
requires-python = ">=3.10"
license = "CC0-1.0"
keywords = ["sbom", "spdx", "ai", "nlp"]
authors = [{ name = "Test Author", email = "test@example.com" }]
dependencies = [
    "fasttext==0.9.3",
    "newmm-tokenizer==0.2.2",
    "numpy==1.26.4",
]

[project.urls]
Source = "https://github.com/bact/sentimentdemo"
"""

    about_content = '__version__ = "0.1.0"'

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Create version file
        src_dir = tmppath / "src" / "sentimentdemo"
        src_dir.mkdir(parents=True)
        about_path = src_dir / "__about__.py"
        about_path.write_text(about_content)

        sbom_json = generate_sbom(tmppath)
        sbom_data = json.loads(sbom_json)

        # Verify structure
        graph = sbom_data["@graph"]
        packages = [elem for elem in graph if elem["type"] == "software_Package"]

        # Check main package
        main_package = [p for p in packages if p["name"] == "sentimentdemo"][0]
        assert main_package["software_packageVersion"] == "0.1.0"

        # Check dependencies
        dep_names = {p["name"] for p in packages if p["name"] != "sentimentdemo"}
        assert "fasttext" in dep_names
        assert "newmm-tokenizer" in dep_names
        assert "numpy" in dep_names

        # Check relationships
        relationships = [elem for elem in graph if elem["type"] == "Relationship"]
        assert len(relationships) >= 3  # At least 3 dependencies


def test_generate_sbom_with_fragments() -> None:
    """Test SBOM generation with external generic SBOM fragments."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "fragment-app"
version = "1.0.0"
description = "App with fragments"

[tool.pitloom.fragments]
files = ["fragment1.json", "fragment2.json"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Create dummy fragment 1 with an AI Package
        doc_uuid_1 = "aaaa-bbbb"
        ci1 = spdx3.CreationInfo(
            specVersion="3.0.1", created=datetime.now(timezone.utc)
        )
        person1 = spdx3.Person(
            spdxId=generate_spdx_id("Person", "author1", doc_uuid_1),
            name="Author 1",
            creationInfo=ci1,
        )
        ci1.createdBy = [require_spdx_id(person1)]
        ai_pkg = spdx3.ai_AIPackage(
            spdxId=generate_spdx_id("AIPackage", "test-ai-model", doc_uuid_1),
            name="cool-ai-model",
            creationInfo=ci1,
        )
        exporter1 = Spdx3JsonExporter()
        exporter1.add_person(person1)
        exporter1.add_package(ai_pkg)
        (tmppath / "fragment1.json").write_text(exporter1.to_json())

        # Create dummy fragment 2 with a Dataset Package
        doc_uuid_2 = "cccc-dddd"
        ci2 = spdx3.CreationInfo(
            specVersion="3.0.1", created=datetime.now(timezone.utc)
        )
        person2 = spdx3.Person(
            spdxId=generate_spdx_id("Person", "author2", doc_uuid_2),
            name="Author 2",
            creationInfo=ci2,
        )
        ci2.createdBy = [require_spdx_id(person2)]
        dataset_pkg = spdx3.dataset_DatasetPackage(
            spdxId=generate_spdx_id("DatasetPackage", "test-dataset", doc_uuid_2),
            name="cool-dataset",
            creationInfo=ci2,
        )
        dataset_pkg.dataset_datasetType = [spdx3.dataset_DatasetType.text]
        exporter2 = Spdx3JsonExporter()
        exporter2.add_person(person2)
        exporter2.add_package(dataset_pkg)
        (tmppath / "fragment2.json").write_text(exporter2.to_json())

        sbom_json = generate_sbom(tmppath)
        sbom_data = json.loads(sbom_json)

        # Validate that elements from fragments are included in the graph
        graph = sbom_data["@graph"]
        element_types = {elem["type"] for elem in graph}

        assert "ai_AIPackage" in element_types
        assert "dataset_DatasetPackage" in element_types
        assert "software_Package" in element_types

        # Verify names
        ai_packages = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert ai_packages[0]["name"] == "cool-ai-model"

        dataset_packages = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert dataset_packages[0]["name"] == "cool-dataset"


def test_generate_sbom_setup_cfg_only_project() -> None:
    """generate_sbom() must support projects with no pyproject.toml at all,
    falling back to setup.cfg via the shared read_project() helper.

    Regression test: generate_sbom() previously hardcoded a pyproject.toml
    read with no setup.cfg/setup.py fallback, so a setup.cfg-only project
    raised FileNotFoundError.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "setup.cfg").write_text(
            "[metadata]\nname = setup-cfg-only-package\nversion = 1.2.3\n"
        )

        sbom_json = generate_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        main_package = next(
            p for p in packages if p["name"] == "setup-cfg-only-package"
        )
        assert main_package["software_packageVersion"] == "1.2.3"


def test_generate_sbom_uses_preparsed_metadata_without_reparsing() -> None:
    """When metadata/pitloom_config are given, generate_sbom() must not
    re-parse project_dir via read_project()."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # No pyproject.toml, setup.cfg, or setup.py -- read_project() would
        # raise FileNotFoundError if generate_sbom() called it.
        metadata = ProjectMetadata(name="preparsed-package", version="9.9.9")
        pitloom_config = PitloomConfig()

        sbom_json = generate_sbom(
            tmppath, project_metadata=metadata, pitloom_config=pitloom_config
        )
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        main_package = next(p for p in packages if p["name"] == "preparsed-package")
        assert main_package["software_packageVersion"] == "9.9.9"


def test_generate_sbom_partial_preparsed_args_reparses_both() -> None:
    """project_metadata and pitloom_config must be given together.

    Passing only one is treated as if neither were given: both are read
    fresh from project_dir, and the one caller-supplied value is ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(
            '[project]\nname = "real-package"\nversion = "1.0.0"\n'
        )
        fake_metadata = ProjectMetadata(name="should-be-discarded")

        sbom_json = generate_sbom(
            tmppath, project_metadata=fake_metadata, pitloom_config=None
        )
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        names = [p["name"] for p in packages]
        assert "real-package" in names
        assert "should-be-discarded" not in names


def test_assembler_ai_model_with_inputs_outputs() -> None:
    """Test that AI model metadata with inputs/outputs is serialized into SPDX 3."""
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.PYTORCH_PT2),
        name="linear-model",
        version="1.0.0",
        type_of_model="linear regression",
        inputs=[{"name": "x"}],
        outputs=[{"name": "linear"}],
        hyperparameters={"trainable": True},
        provenance={"inputs": "Source: model.pt2 | Field: models/model.json"},
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    exporter = build(doc)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    pkg = ai_pkgs[0]
    assert pkg["name"] == "linear-model"
    assert pkg["software_packageVersion"] == "1.0.0"
    assert pkg["ai_typeOfModel"] == ["linear regression"]

    info = json.loads(pkg["ai_informationAboutApplication"])
    assert info["inputs"] == [{"name": "x"}]
    assert info["outputs"] == [{"name": "linear"}]

    hp = pkg["ai_hyperparameter"]
    assert any(e["key"] == "trainable" and e["value"] == "True" for e in hp)

    # profileConformance must include "ai"
    spdx_docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert "ai" in spdx_docs[0]["profileConformance"]

    # contains relationship from main package to AI package
    rels = [e for e in graph if e.get("type") == "Relationship"]
    contains_rels = [r for r in rels if r.get("relationshipType") == "contains"]
    assert len(contains_rels) == 1
    assert any(pkg["spdxId"] in r["to"] for r in contains_rels)

    # no license relationships when ai_model.license is not set
    license_rels = [
        r
        for r in rels
        if r.get("relationshipType") in ("hasDeclaredLicense", "hasConcludedLicense")
    ]
    assert not license_rels


def test_assembler_usage_file_hasdatafile_is_lifecycle_scoped_runtime() -> None:
    """The ``hasDataFile`` relationship from a usage file (e.g. predict.py,
    which loads the model at inference time) to the model file must be a
    ``LifecycleScopedRelationship`` with ``scope: runtime`` -- contrast with
    ``pitloom.loom``'s ``generates`` edges, which are scoped ``build``."""
    project = ProjectMetadata(
        name="ai-project",
        version="0.1.0",
        files=[
            ProjectFile(
                physical_path="src/pkg/model.bin",
                distribution_path="pkg/model.bin",
                digest_sha256="a" * 64,
            ),
            ProjectFile(
                physical_path="src/pkg/predict.py",
                distribution_path="pkg/predict.py",
                digest_sha256="b" * 64,
            ),
        ],
    )
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="model.bin",
            file_path_relative="pkg/model.bin",
            model_format=AiModelFormat.PYTORCH_PT2,
        ),
        name="usage-model",
        usage_files=["pkg/predict.py"],
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    exporter = build(doc)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    has_data_file = [
        e
        for e in graph
        if e.get("type") == "LifecycleScopedRelationship"
        and e.get("relationshipType") == "hasDataFile"
    ]
    assert len(has_data_file) == 1
    assert has_data_file[0]["scope"] == "runtime"

    # Plain "Relationship"-typed elements must not include a hasDataFile
    # edge -- it was reclassified, not duplicated.
    assert not any(
        e.get("type") == "Relationship" and e.get("relationshipType") == "hasDataFile"
        for e in graph
    )


def test_assembler_ai_model_reuses_registry_entity_by_physical_path() -> None:
    """A scan-discovered AI model must reuse a registry entity's spdxId when
    its physical path (project-root-relative, e.g. "src/pkg/model.bin") is
    registered -- the same string a pitloom.loom fragment's
    run.set_model(model_file_path, ...) call would have used, so the two
    become the same element once merged instead of yielding a second,
    duplicate ai_AIPackage."""
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="model.bin",
            physical_path="src/sentimentdemo/model.bin",
            model_format=AiModelFormat.FASTTEXT,
        ),
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    registry = IdRegistry.new("ai-project")
    registered_id = registry.register_entity(
        "src/sentimentdemo/model.bin", "ai_AIPackage"
    )

    exporter = build(doc, registry=registry)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert ai_pkgs[0]["spdxId"] == registered_id


def test_assembler_ai_model_reuses_registry_entity_by_file_stem() -> None:
    """Falls back to the model file's stem (mirroring the lookup
    generate_ai_model_sbom performs for loom model/--registry) when no
    physical_path or name match is registered."""
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="model.bin",
            model_format=AiModelFormat.FASTTEXT,
        ),
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    registry = IdRegistry.new("ai-project")
    registered_id = registry.register_entity("model", "ai_AIPackage")

    exporter = build(doc, registry=registry)
    graph = json.loads(exporter.to_json())["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert ai_pkgs[0]["spdxId"] == registered_id


def test_assembler_ai_model_no_registry_match_mints_fresh_id() -> None:
    """No matching registry entity -> unchanged behaviour: a fresh id is
    minted, and it does not collide with an unrelated registered entity."""
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="model.bin",
            physical_path="src/sentimentdemo/model.bin",
            model_format=AiModelFormat.FASTTEXT,
        ),
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    registry = IdRegistry.new("ai-project")
    unrelated_id = registry.register_entity("some-other-model", "ai_AIPackage")

    exporter = build(doc, registry=registry)
    graph = json.loads(exporter.to_json())["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert ai_pkgs[0]["spdxId"] != unrelated_id


def test_build_deployed_reuses_registry_entity_by_name() -> None:
    """A Deployed SBOM's installed packages must reuse a registered
    ``software_Package`` entity's spdxId (looked up by package name), so
    the same package referenced elsewhere (e.g. a Source or Analyzed SBOM)
    unifies with it once merged, instead of always minting a fresh id."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]

    registry = IdRegistry.new("deployed-environment")
    registered_id = registry.register_entity("requests", "software_Package")

    exporter = build_deployed(doc, env_tree, registry=registry)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    requests_pkg = next(p for p in packages if p["name"] == "requests")
    assert requests_pkg["spdxId"] == registered_id


def test_build_deployed_no_registry_match_mints_fresh_id() -> None:
    """No matching registry entity -> unchanged behaviour: a fresh id is
    minted for the installed package."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]

    registry = IdRegistry.new("deployed-environment")
    unrelated_id = registry.register_entity("some-other-package", "software_Package")

    exporter = build_deployed(doc, env_tree, registry=registry)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    requests_pkg = next(p for p in packages if p["name"] == "requests")
    assert requests_pkg["spdxId"] != unrelated_id


# ---------------------------------------------------------------------------
# Phantom dependency tests (add_phantom_dependencies via build())
# ---------------------------------------------------------------------------


def test_phantom_dependency_creates_package_and_dependency_relationship() -> None:
    """A phantom dependency produces a software_Package (name/version) and a
    dependsOn Relationship from the main package to it."""
    project = ProjectMetadata(name="main-project", version="1.0.0")
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        phantom_dependencies=[
            PhantomDependency(
                name="libfoo",
                file_path="pkg.libs/libfoo.so",
                digest_sha256="c" * 64,
                version="1.2.3",
            )
        ],
    )

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    phantom_pkg = next(p for p in packages if p["name"] == "libfoo")
    assert phantom_pkg["software_packageVersion"] == "1.2.3"

    main_package = next(p for p in packages if p["name"] == "main-project")
    relationships = [e for e in graph if e.get("type") == "Relationship"]
    depends_on = [
        r
        for r in relationships
        if r["relationshipType"] == "dependsOn"
        and r["from"] == main_package["spdxId"]
        and phantom_pkg["spdxId"] in r["to"]
    ]
    assert len(depends_on) == 1


def test_phantom_dependency_without_version_is_unknown() -> None:
    """A phantom dependency with no inferred version gets 'unknown'."""
    project = ProjectMetadata(name="main-project", version="1.0.0")
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        phantom_dependencies=[
            PhantomDependency(
                name="libbar",
                file_path="pkg.libs/libbar.so",
                digest_sha256="d" * 64,
                version=None,
            )
        ],
    )

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    phantom_pkg = next(p for p in packages if p["name"] == "libbar")
    assert phantom_pkg["software_packageVersion"] == "unknown"


def test_phantom_dependency_links_to_matching_file() -> None:
    """When a phantom dependency's file_path matches a registered project
    file, a 'contains' Relationship links the phantom package to that file."""
    files = [
        ProjectFile(
            physical_path="src/pkg.libs/libfoo.so",
            distribution_path="pkg.libs/libfoo.so",
            digest_sha256="c" * 64,
        ),
    ]
    project = ProjectMetadata(name="main-project", version="1.0.0", files=files)
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        phantom_dependencies=[
            PhantomDependency(
                name="libfoo",
                file_path="pkg.libs/libfoo.so",
                digest_sha256="c" * 64,
                version=None,
            )
        ],
    )

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    phantom_pkg = next(p for p in packages if p["name"] == "libfoo")
    files_elems = [e for e in graph if e.get("type") == "software_File"]
    file_elem = next(f for f in files_elems if f["name"] == "pkg.libs/libfoo.so")

    relationships = [e for e in graph if e.get("type") == "Relationship"]
    contains = [
        r
        for r in relationships
        if r["relationshipType"] == "contains"
        and r["from"] == phantom_pkg["spdxId"]
        and file_elem["spdxId"] in r["to"]
    ]
    assert len(contains) == 1


def test_phantom_dependency_no_matching_file_no_link() -> None:
    """When a phantom dependency's file_path has no matching registered
    project file, no 'contains' relationship is created and building does
    not crash."""
    project = ProjectMetadata(name="main-project", version="1.0.0")
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        phantom_dependencies=[
            PhantomDependency(
                name="libfoo",
                file_path="pkg.libs/libfoo.so",
                digest_sha256="c" * 64,
                version=None,
            )
        ],
    )

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    phantom_pkg = next(p for p in packages if p["name"] == "libfoo")

    relationships = [e for e in graph if e.get("type") == "Relationship"]
    contains_from_phantom = [
        r
        for r in relationships
        if r["relationshipType"] == "contains" and r["from"] == phantom_pkg["spdxId"]
    ]
    assert contains_from_phantom == []


# ---------------------------------------------------------------------------
# License relationship tests
# ---------------------------------------------------------------------------
# Each (model_name, license_id, hf_id) triple is taken from the model zoo in
# test_extract_huggingface.py, which records the actual values observed on
# Hugging Face Hub on 2026-05-08.  Using real identifiers ensures the assembly
# layer is exercised with the full range of license strings found in practice:
# standard SPDX IDs, custom Hugging Face identifiers, and OpenRAIL variants.
# ---------------------------------------------------------------------------

_AI_LICENSE_CASES: list[tuple[str, str, str]] = [
    # standard SPDX identifiers
    ("Kokoro-82M", "apache-2.0", "hexgrad/Kokoro-82M"),
    ("DeepSeek-R1", "mit", "deepseek-ai/DeepSeek-R1"),
    ("blip-vqa-base", "bsd-3-clause", "Salesforce/blip-vqa-base"),
    (
        "speaker-diarization-community-1",
        "cc-by-4.0",
        "pyannote/speaker-diarization-community-1",
    ),
    ("seamless-m4t-v2-large", "cc-by-nc-4.0", "facebook/seamless-m4t-v2-large"),
    (
        "wangchanglm-7.5B-sft-enth",
        "cc-by-sa-4.0",
        "pythainlp/wangchanglm-7.5B-sft-enth",
    ),
    # non-standard / custom Hugging Face license identifiers
    ("starcoder2-3b", "bigcode-openrail-m", "bigcode/starcoder2-3b"),
    ("Llama-3.2-1B", "llama3.2", "meta-llama/Llama-3.2-1B"),
    ("Hermes-3-Llama-3.2-3B", "llama3", "NousResearch/Hermes-3-Llama-3.2-3B"),
    ("Gemma-SEA-LION-v4-27B-IT", "gemma", "aisingapore/Gemma-SEA-LION-v4-27B-IT"),
    (
        "Deberta_Human_Value_Detector",
        "openrail++",
        "tum-nlp/Deberta_Human_Value_Detector",
    ),
    ("DepthPro-hf", "apple-amlr", "apple/DepthPro-hf"),
]


def _check_license_relationships(
    graph: list[dict[str, Any]], ai_pkg_id: str, license_id: str
) -> None:
    """Assert hasDeclaredLicense or hasConcludedLicense relationship exists."""
    rels = [e for e in graph if e.get("type") == "Relationship"]
    declared = [
        r
        for r in rels
        if r.get("relationshipType") == "hasDeclaredLicense"
        and r.get("from") == ai_pkg_id
    ]
    concluded = [
        r
        for r in rels
        if r.get("relationshipType") == "hasConcludedLicense"
        and r.get("from") == ai_pkg_id
    ]

    assert len(declared) + len(concluded) == 1, (
        f"expected exactly one license relationship, got {len(declared)} declared "
        f"and {len(concluded)} concluded"
    )

    license_rel = declared[0] if declared else concluded[0]
    license_spdx_id = license_rel["to"][0]
    license_elems = [
        e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
        and e.get("spdxId") == license_spdx_id
    ]
    assert len(license_elems) == 1
    assert license_elems[0]["simplelicensing_licenseText"] == license_id

    spdx_docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert "simpleLicensing" in spdx_docs[0]["profileConformance"]


@pytest.mark.parametrize(
    "model_name,license_id,hf_id",
    _AI_LICENSE_CASES,
    ids=[f"{n}-{lic}" for n, lic, _ in _AI_LICENSE_CASES],
)
def test_assembler_ai_model_with_license(
    model_name: str, license_id: str, hf_id: str
) -> None:
    """AI model with a license must produce hasDeclaredLicense and
    hasConcludedLicense relationships, and simpleLicensing in profileConformance.

    Model/license pairs are taken from real Hugging Face Hub data recorded in
    the model zoo (test_extract_huggingface.py, 2026-05-08).
    """
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS),
        name=model_name,
        license=license_id,
        provenance={
            "license": (f"Source: Hugging Face Hub ({hf_id}) | Field: cardData.license")
        },
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    exporter = build(doc)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    _check_license_relationships(graph, ai_pkgs[0]["spdxId"], license_id)


# Standalone build_model() cases: real GGUF and safetensors models.
# aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF uses a custom "gemma" license;
# deepseek-ai/DeepSeek-R1 uses the standard SPDX "mit" identifier.
_BUILD_MODEL_LICENSE_CASES: list[tuple[str, str, AiModelFormat, str]] = [
    (
        "Gemma-SEA-LION-v4-4B-VL-GGUF",
        "gemma",
        AiModelFormat.GGUF,
        "aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF",
    ),
    (
        "DeepSeek-R1",
        "mit",
        AiModelFormat.SAFETENSORS,
        "deepseek-ai/DeepSeek-R1",
    ),
]


@pytest.mark.parametrize(
    "model_name,license_id,fmt,hf_id",
    _BUILD_MODEL_LICENSE_CASES,
    ids=[f"{n}-{lic}" for n, lic, _, _ in _BUILD_MODEL_LICENSE_CASES],
)
def test_build_model_with_license(
    model_name: str, license_id: str, fmt: AiModelFormat, hf_id: str
) -> None:
    """build_model() for a standalone AI model must emit license relationships
    and include simpleLicensing in profileConformance.

    Model/license pairs are taken from real Hugging Face Hub data recorded in
    the model zoo (test_extract_huggingface.py, 2026-05-08).
    """
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=fmt),
        name=model_name,
        license=license_id,
        provenance={
            "license": (f"Source: Hugging Face Hub ({hf_id}) | Field: cardData.license")
        },
    )

    exporter = build_model(model, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    _check_license_relationships(graph, ai_pkgs[0]["spdxId"], license_id)


def test_build_model_without_license() -> None:
    """build_model() for a model with no license produces no license
    relationships and no simpleLicensing in profileConformance.

    microsoft/resnet-18 is a real Hugging Face model that does not declare a
    license in its model card, making it a realistic no-license test case.
    """
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
        name="resnet-18",
    )

    exporter = build_model(model, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    rels = [e for e in graph if e.get("type") == "Relationship"]
    license_rels = [
        r
        for r in rels
        if r.get("relationshipType") in ("hasDeclaredLicense", "hasConcludedLicense")
    ]
    assert not license_rels

    spdx_docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert "simpleLicensing" not in spdx_docs[0]["profileConformance"]


# ---------------------------------------------------------------------------
# Fixture-based end-to-end license export tests
# ---------------------------------------------------------------------------
# These tests extract real metadata from local model files in
# tests/fixtures/aimodels/,
# then assemble a standalone SPDX 3 document and verify the license
# relationships are present in the output.
#
# Many fixture files do not embed license metadata in their format (e.g. most
# Safetensors files only store {"format": "pt"} in __metadata__, and the GGUF
# extractor does not map general.license to ai_model.license).  Those fixtures
# are skipped at runtime via pytest.skip() rather than excluded from the
# parametrize list, so that newly enhanced extractors will be picked up
# automatically without any change to this test.
# ---------------------------------------------------------------------------

_FIXTURE_ROOT = Path(__file__).parent / "fixtures"
_AI_MODEL_ROOT = _FIXTURE_ROOT / "aimodels"
_AI_MODEL_DIRS = [
    "fasttext",
    "gguf",
    "hdf5",
    "keras",
    "numpy",
    "onnx",
    "pytorch",
    "pytorch_pt2",
    "safetensors",
]
_AI_MODEL_FIXTURES: list[Path] = [
    p
    for d in _AI_MODEL_DIRS
    for p in sorted((_AI_MODEL_ROOT / d).glob("*"))
    if p.is_file() and p.suffix != ""
]


@pytest.mark.parametrize(
    "fixture_path",
    _AI_MODEL_FIXTURES,
    ids=[f"{p.parent.name}/{p.name}" for p in _AI_MODEL_FIXTURES],
)
def test_fixture_license_export(fixture_path: Path) -> None:
    """Extract metadata from a fixture file and verify SPDX 3 license output.

    Skips when:
    - The fixture file is absent from the repository clone.
    - The required optional library is not installed.
    - The model format does not embed a license (``meta.license is None``).

    When a license is present, asserts that the assembled ``build_model()``
    output contains both ``hasDeclaredLicense`` and ``hasConcludedLicense``
    relationships pointing to a ``simplelicensing_SimpleLicensingText`` element
    whose ``simplelicensing_licenseText`` matches the extracted license string.
    """
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {fixture_path}")

    try:
        meta = read_ai_model(fixture_path)
    except ImportError as exc:
        pytest.skip(str(exc))

    if meta.license is None:
        pytest.skip(f"No license metadata embedded in {fixture_path.name}")

    exporter = build_model(meta, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert meta.license is not None  # type: ignore[comparison-overlap]
    _check_license_relationships(graph, ai_pkgs[0]["spdxId"], meta.license)


# ---------------------------------------------------------------------------
# assemble-layer wiring: generate_analyzed_sbom() / generate_deployed_sbom()
# ---------------------------------------------------------------------------


def _make_wheel(tmp_path: Path, name: str, version: str) -> Path:
    """Build a minimal .whl with just a METADATA file."""
    wheel_path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    metadata_body = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(f"{name}-{version}.dist-info/METADATA", metadata_body)
        zf.writestr(f"{name}/__init__.py", "")
    return wheel_path


def test_generate_analyzed_sbom_from_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_analyzed_sbom() wires read_wheel()'s extracted metadata into
    a valid SPDX 3 JSON-LD document with the expected package name/version."""
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_wheel(tmp_path, "analyzed-pkg", "2.3.4")

    sbom_json = generate_analyzed_sbom(wheel_path)
    data = json.loads(sbom_json)

    assert "@graph" in data
    graph = data["@graph"]
    packages = [e for e in graph if e.get("type") == "software_Package"]
    main_package = next(p for p in packages if p["name"] == "analyzed-pkg")
    assert main_package["software_packageVersion"] == "2.3.4"


def test_generate_deployed_sbom_mocked_pipdeptree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_deployed_sbom() wires read_environment()'s pipdeptree tree
    into a valid SPDX 3 JSON-LD document containing the installed package."""
    monkeypatch.chdir(tmp_path)
    tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]
    fake_result = subprocess.CompletedProcess(
        args=["pipdeptree", "--json-tree", "--all"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )

    with patch("subprocess.run", return_value=fake_result):
        sbom_json = generate_deployed_sbom()

    data = json.loads(sbom_json)

    assert "@graph" in data
    graph = data["@graph"]
    packages = [e for e in graph if e.get("type") == "software_Package"]
    requests_pkg = next(p for p in packages if p["name"] == "requests")
    assert requests_pkg["software_packageVersion"] == "2.31.0"
