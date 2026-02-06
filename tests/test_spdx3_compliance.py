# SPDX-FileCopyrightText: 2024-present Loom Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3.0 compliance validation."""

import json
import tempfile
from pathlib import Path

from loom.generator import generate_sbom_to_file


def test_spdx3_json_structure():
    """Test that generated SBOM has valid SPDX 3.0 JSON-LD structure."""
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
        generate_sbom_to_file(tmppath, output_path)

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
            
            # CreationInfo itself doesn't have a creationInfo field
            if element["type"] != "CreationInfo":
                assert "creationInfo" in element, f"{element['type']} must have creationInfo"

            # Element-specific validations
            if element["type"] == "CreationInfo":
                assert "@id" in element
                assert element["@id"] == "_:creationinfo"
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


def test_spdx3_required_elements():
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
        generate_sbom_to_file(tmppath, output_path)

        sbom_data = json.loads(output_path.read_text())
        graph = sbom_data["@graph"]

        # Check for required element types
        element_types = {elem["type"] for elem in graph}

        required_types = {
            "CreationInfo",
            "Person",
            "SpdxDocument",
            "software_Sbom",
            "software_Package",
        }

        for req_type in required_types:
            assert req_type in element_types, f"Required type {req_type} not found"


def test_spdx3_profile_conformance():
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
        generate_sbom_to_file(tmppath, output_path)

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


def test_spdx3_relationships_valid():
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
        generate_sbom_to_file(tmppath, output_path)

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
            assert rel["relationshipType"] in [
                "dependsOn",
                "contains",
                "describes",
                "hasDistributionPoint",
            ]
