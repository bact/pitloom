# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 compliance validation: basic JSON-LD structure,
required elements, profile conformance, relationship validity, file
hashes, and the main package's PyPI PURL.

See also: test_spdx3_compliance_shacl.py -- this module's sibling, split
from the original test_spdx3_compliance.py.
"""

import json
import re
import tempfile
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_project_sbom

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
        generate_project_sbom(tmppath, output_path=output_path)

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
        generate_project_sbom(tmppath, output_path=output_path)

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
        generate_project_sbom(tmppath, output_path=output_path)

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
        generate_project_sbom(tmppath, output_path=output_path)

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
# File hashes and main-package PURL
# ---------------------------------------------------------------------------

_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def test_spdx3_file_elements_carry_verified_using_sha256() -> None:
    """Every packaged file's software_File must carry a SHA-256 verifiedUsing
    hash; directory nodes must not.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(
            """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "hash-test-package"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = ["src/hash_test_package"]
""",
            encoding="utf-8",
        )
        pkg_dir = tmppath / "src" / "hash_test_package"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

        output_path = tmppath / "sbom.spdx3.json"
        generate_project_sbom(tmppath, output_path=output_path)

        graph = json.loads(output_path.read_text())["@graph"]
        file_elements = [e for e in graph if e.get("type") == "software_File"]
        assert file_elements, "Expected at least one software_File element"

        files = [e for e in file_elements if e.get("software_fileKind") == "file"]
        directories = [
            e for e in file_elements if e.get("software_fileKind") == "directory"
        ]
        assert files, "Expected at least one file-kind software_File"

        for directory in directories:
            assert "verifiedUsing" not in directory

        for file_elem in files:
            verified = file_elem.get("verifiedUsing")
            assert verified, f"{file_elem['name']} is missing verifiedUsing"
            (hash_obj,) = verified
            assert hash_obj["type"] == "Hash"
            assert hash_obj["algorithm"] == "sha256"
            assert _HEX_SHA256_RE.match(hash_obj["hashValue"])


def test_spdx3_main_package_has_pypi_purl() -> None:
    """The main package must carry a pkg:pypi PURL matching name and version."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(
            """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "purl-test-package"
version = "3.1.4"
""",
            encoding="utf-8",
        )

        output_path = tmppath / "sbom.spdx3.json"
        generate_project_sbom(tmppath, output_path=output_path)

        graph = json.loads(output_path.read_text())["@graph"]
        packages = [e for e in graph if e.get("type") == "software_Package"]
        main_package = next(p for p in packages if p["name"] == "purl-test-package")
        assert main_package["software_packageUrl"] == (
            "pkg:pypi/purl-test-package@3.1.4"
        )
