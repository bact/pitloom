# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 compliance validation."""

import json
import tempfile
from pathlib import Path
from typing import Any

from spdx_python_model import v3_0_1 as spdx3

from pitloom.assemble import generate_sbom

_VALID_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    iri.split("/")[-1] for iri in spdx3.RelationshipType.NAMED_INDIVIDUALS.values()
)


def test_spdx3_json_structure() -> None:
    """Test that generated SBOM has valid SPDX 3 JSON-LD structure."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-compliance"
version = "1.0.0"
description = "Testing SPDX 3.0 compliance"
dependencies = ["requests>=2.28.0"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        output_path = tmppath / "sbom.spdx3.json"
        generate_sbom(tmppath, output_path=output_path)

        # Load and validate structure
        sbom_data = json.loads(output_path.read_text())

        # Check JSON-LD context
        assert "@context" in sbom_data
        assert sbom_data["@context"] == "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"

        # Check graph structure
        assert "@graph" in sbom_data
        graph = sbom_data["@graph"]
        assert isinstance(graph, list)
        assert len(graph) > 0

        # Validate each element has required fields
        for element in graph:
            assert "type" in element, "Every element must have a type"

            # CreationInfo itself does not have a creationInfo field
            if element["type"] != "CreationInfo":
                assert "creationInfo" in element, (
                    f"{element['type']} must have creationInfo"
                )

            # Element-specific validations
            if element["type"] == "CreationInfo":
                assert "@id" in element
                assert element["@id"].startswith("_:CreationInfo")
                assert "specVersion" in element
                assert "created" in element
                assert "createdBy" in element

            elif element["type"] == "Person":
                assert "spdxId" in element
                assert "name" in element
                assert element["spdxId"].startswith("https://spdx.org/spdxdocs/")

            elif element["type"] == "SpdxDocument":
                assert "spdxId" in element
                assert "rootElement" in element
                assert "profileConformance" in element
                assert isinstance(element["rootElement"], list)
                assert isinstance(element["profileConformance"], list)

            elif element["type"] == "software_Sbom":
                assert "spdxId" in element
                assert "rootElement" in element
                assert "software_sbomType" in element
                assert isinstance(element["rootElement"], list)
                assert isinstance(element["software_sbomType"], list)

            elif element["type"] == "software_Package":
                assert "spdxId" in element
                assert "name" in element
                assert element["spdxId"].startswith("https://spdx.org/spdxdocs/")

            elif element["type"] == "Relationship":
                assert "spdxId" in element
                assert "from" in element
                assert "to" in element
                assert "relationshipType" in element
                assert isinstance(element["to"], list)


def test_spdx3_required_elements() -> None:
    """Test that all required SPDX 3.0 elements are present."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "required-elements-test"
version = "2.0.0"
description = "Test for required elements"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        output_path = tmppath / "sbom.spdx3.json"
        generate_sbom(tmppath, output_path=output_path)

        sbom_data = json.loads(output_path.read_text())
        graph = sbom_data["@graph"]

        # Check for required element types
        element_types = {elem["type"] for elem in graph}

        required_types = {
            "CreationInfo",
            "SpdxDocument",
            "software_Sbom",  # Since we produce a software SBOM
            "software_Package",  # At least the project itself
        }

        for req_type in required_types:
            assert req_type in element_types, f"Required type {req_type} not found"


def test_spdx3_profile_conformance() -> None:
    """Test that profile conformance is declared correctly."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "profile-test"
version = "1.0.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        output_path = tmppath / "sbom.spdx3.json"
        generate_sbom(tmppath, output_path=output_path)

        sbom_data = json.loads(output_path.read_text())
        graph = sbom_data["@graph"]

        # Find SpdxDocument
        docs = [elem for elem in graph if elem["type"] == "SpdxDocument"]
        assert len(docs) == 1

        doc = docs[0]
        assert "profileConformance" in doc
        profiles = doc["profileConformance"]

        # Check that core and software profiles are declared
        assert "core" in profiles
        assert "software" in profiles


def test_spdx3_relationships_valid() -> None:
    """Test that relationships reference valid elements."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "relationship-test"
version = "1.0.0"
dependencies = ["numpy==1.24.0"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        output_path = tmppath / "sbom.spdx3.json"
        generate_sbom(tmppath, output_path=output_path)

        sbom_data = json.loads(output_path.read_text())
        graph = sbom_data["@graph"]

        # Collect all valid spdxIds
        valid_ids = {elem.get("spdxId") for elem in graph if "spdxId" in elem}

        # Check all relationships
        relationships = [elem for elem in graph if elem["type"] == "Relationship"]

        for rel in relationships:
            # From element must be valid
            assert rel["from"] in valid_ids, f"Invalid 'from' reference: {rel['from']}"

            # To elements must be valid
            for to_id in rel["to"]:
                assert to_id in valid_ids, f"Invalid 'to' reference: {to_id}"

            # Relationship type should be valid
            assert rel["relationshipType"] in _VALID_RELATIONSHIP_TYPES


# ---------------------------------------------------------------------------
# SPDX 3.0 SHACL shape constraints (structural equivalent)
# ---------------------------------------------------------------------------

# SPDX 3.0 SHACL: sh:class spdx:Agent; sh:path spdx:createdBy
# Agent subclasses per the SPDX 3.0 OWL ontology
_AGENT_TYPES: frozenset[str] = frozenset({"Person", "Organization"})


def _build_spdx_id_type_map(graph: list[dict[str, Any]]) -> dict[str, str]:
    """Return a mapping of spdxId → JSON-LD type for all elements."""
    return {elem["spdxId"]: elem["type"] for elem in graph if "spdxId" in elem}


def test_spdx3_shacl_creation_info_created_by_are_agents() -> None:
    """createdBy must reference only Agent elements (Person or Organization).

    Replicates the SPDX 3.0 SHACL shape::

        [] sh:class spdx:Agent ;
           sh:minCount 1 ;
           sh:path spdx:createdBy .

    Tool is NOT an Agent subclass; placing a Tool in createdBy causes a SHACL
    violation.  Tools must appear in createdUsing instead.
    """
    pyproject_content = """
[project]
name = "shacl-agent-test"
version = "1.0.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_sbom(tmppath)
        graph: list[dict[str, Any]] = json.loads(sbom_json)["@graph"]

        id_to_type = _build_spdx_id_type_map(graph)
        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]

        assert creation_infos, "SBOM must contain at least one CreationInfo"

        for ci in creation_infos:
            created_by = ci.get("createdBy", [])
            assert created_by, "CreationInfo.createdBy must have at least one entry"

            for ref_id in created_by:
                elem_type = id_to_type.get(ref_id)
                assert elem_type in _AGENT_TYPES, (
                    f"createdBy references '{ref_id}' of type {elem_type!r}. "
                    "Only Person and Organization (Agent subclasses) are allowed. "
                    "Tool must go in createdUsing."
                )


def test_spdx3_shacl_creation_info_created_using_are_tools() -> None:
    """createdUsing must reference only Tool elements.

    Replicates the SPDX 3.0.1 SHACL shape for the optional createdUsing path::

        [] sh:class spdx:Tool ;
           sh:path spdx:createdUsing .
    """
    pyproject_content = """
[project]
name = "shacl-tool-test"
version = "1.0.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_sbom(tmppath)
        graph: list[dict[str, Any]] = json.loads(sbom_json)["@graph"]

        id_to_type = _build_spdx_id_type_map(graph)
        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]

        for ci in creation_infos:
            for ref_id in ci.get("createdUsing", []):
                elem_type = id_to_type.get(ref_id)
                assert elem_type == "Tool", (
                    f"createdUsing references '{ref_id}' of type {elem_type!r}. "
                    "Only Tool elements are allowed in createdUsing."
                )


def test_spdx3_shacl_creation_info_has_tool() -> None:
    """Generated SBOM must include a Tool element declared via createdUsing.

    This is not a SPDX 3.0 requirement but every SBOM generated by Pitloom
    should include a Tool element.
    """
    pyproject_content = """
[project]
name = "shacl-has-tool-test"
version = "1.0.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_sbom(tmppath)
        graph: list[dict[str, Any]] = json.loads(sbom_json)["@graph"]

        element_types = {e["type"] for e in graph}
        assert "Tool" in element_types, (
            "SBOM must contain a Tool element representing the generation tool"
        )

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        for ci in creation_infos:
            assert ci.get("createdUsing"), (
                "CreationInfo must reference the generation tool via createdUsing"
            )
