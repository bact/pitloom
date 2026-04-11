# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 compliance validation."""

import json
import tempfile
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.export.spdx3_json import (
    _deduplicate_creation_infos,
    _deduplicate_named_elements,
    _graph_sort_key,
)

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


def test_graph_element_ordering() -> None:
    """@graph elements must follow the canonical priority order.

    Required order:
      0. CreationInfo   — blank node referenced by every element
      1. SpdxDocument   — document envelope / profileConformance
      2. software_Sbom  — root element pointer / sbomType
      3+ everything else, sorted by spdxId/@id

    This test also verifies that repeated calls produce identical output
    (i.e., ordering is deterministic across runs).
    """
    pyproject_content = """
[project]
name = "ordering-test"
version = "1.0.0"
dependencies = ["requests>=2.28.0"]
"""
    # Fixed timestamp so two calls with identical inputs produce identical output.
    # Without this, datetime.now() is called on each invocation and the
    # CreationInfo.created field would differ between runs.
    fixed_ci = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json_1 = generate_sbom(tmppath, creation_info=fixed_ci)
        sbom_json_2 = generate_sbom(tmppath, creation_info=fixed_ci)

        # Determinism: two calls with identical inputs must produce identical output
        assert sbom_json_1 == sbom_json_2, (
            "@graph order is not deterministic across runs"
        )

        graph: list[dict[str, Any]] = json.loads(sbom_json_1)["@graph"]
        types = [e["type"] for e in graph]

        # Priority elements must appear before everything else
        assert "CreationInfo" in types
        assert "SpdxDocument" in types
        assert "software_Sbom" in types

        ci_idx = types.index("CreationInfo")
        doc_idx = types.index("SpdxDocument")
        sbom_idx = types.index("software_Sbom")

        assert ci_idx < doc_idx, "CreationInfo must precede SpdxDocument"
        assert doc_idx < sbom_idx, "SpdxDocument must precede software_Sbom"

        # If a core Bom element is present it must sit between SpdxDocument
        # and software_Sbom (priority 2, between 1 and 3).
        if "Bom" in types:
            bom_idx = types.index("Bom")
            assert doc_idx < bom_idx < sbom_idx, (
                "Bom must appear after SpdxDocument and before software_Sbom"
            )

        # All priority elements must appear before the general population
        priority_types = {"CreationInfo", "SpdxDocument", "Bom", "software_Sbom"}
        first_other = next(
            (i for i, e in enumerate(graph) if e["type"] not in priority_types),
            len(graph),
        )
        assert sbom_idx < first_other, (
            "All priority elements must precede non-priority elements"
        )


def test_creation_info_deduplication() -> None:
    """Identical CreationInfo blank nodes must be collapsed to one canonical node."""
    ci_shared = {
        "type": "CreationInfo",
        "@id": "_:CreationInfo0",
        "specVersion": "3.0.1",
        "created": "2026-01-01T00:00:00Z",
        "createdBy": ["https://example.org/Person-1"],
        "createdUsing": ["https://example.org/Tool-1"],
    }
    ci_duplicate = {**ci_shared, "@id": "_:CreationInfo1"}
    pkg = {
        "type": "software_Package",
        "spdxId": "https://example.org/Package-1",
        "creationInfo": "_:CreationInfo1",
        "name": "example",
    }
    graph: list[dict[str, Any]] = [ci_shared, ci_duplicate, pkg]

    result = _deduplicate_creation_infos(graph)

    ci_nodes = [e for e in result if e["type"] == "CreationInfo"]
    assert len(ci_nodes) == 1, "Duplicate CreationInfo must be removed"
    canonical_id = ci_nodes[0]["@id"]

    pkg_result = next(e for e in result if e["type"] == "software_Package")
    assert pkg_result["creationInfo"] == canonical_id, (
        "Reference to removed CreationInfo must be redirected to canonical node"
    )


def test_creation_info_deduplication_distinct_kept() -> None:
    """CreationInfo nodes with different content must both be retained."""
    ci_a = {
        "type": "CreationInfo",
        "@id": "_:CreationInfo0",
        "specVersion": "3.0.1",
        "created": "2026-01-01T00:00:00Z",
        "createdBy": ["https://example.org/Person-1"],
        "createdUsing": [],
    }
    ci_b = {
        "type": "CreationInfo",
        "@id": "_:CreationInfo1",
        "specVersion": "3.0.1",
        "created": "2026-06-01T00:00:00Z",  # different timestamp
        "createdBy": ["https://example.org/Person-1"],
        "createdUsing": [],
    }
    graph = [ci_a, ci_b]

    result = _deduplicate_creation_infos(graph)
    assert len(result) == 2, "Distinct CreationInfo nodes must not be merged"


def test_named_element_deduplication_identical() -> None:
    """Exact-duplicate named elements (same spdxId, same content) collapse to one."""
    pkg = {
        "type": "software_Package",
        "spdxId": "https://example.org/Package-1",
        "name": "example",
        "creationInfo": "_:CreationInfo0",
    }
    graph: list[dict[str, Any]] = [dict(pkg), dict(pkg)]

    result = _deduplicate_named_elements(graph)
    assert len(result) == 1, "Identical named elements must be deduplicated"
    assert result[0]["spdxId"] == pkg["spdxId"]


def test_named_element_deduplication_conflict_retained() -> None:
    """Named elements with the same spdxId but different content must all be kept."""
    pkg_a = {
        "type": "software_Package",
        "spdxId": "https://example.org/Package-1",
        "name": "example",
        "software_packageVersion": "1.0.0",
    }
    pkg_b = {**pkg_a, "software_packageVersion": "1.0.1"}  # version differs
    graph: list[dict[str, Any]] = [pkg_a, pkg_b]

    result = _deduplicate_named_elements(graph)
    assert len(result) == 2, "Conflicting named elements must all be retained"


def test_named_element_deduplication_no_spdx_id_passthrough() -> None:
    """Elements without spdxId (blank nodes) must pass through untouched."""
    ci = {
        "type": "CreationInfo",
        "@id": "_:CreationInfo0",
        "specVersion": "3.0.1",
        "created": "2026-01-01T00:00:00Z",
    }
    graph: list[dict[str, Any]] = [ci]

    result = _deduplicate_named_elements(graph)
    assert result == graph


def test_graph_sort_key_priority_order() -> None:
    """_graph_sort_key must assign lower values to higher-priority types."""
    elements = [
        {"type": "software_Sbom", "spdxId": "https://example.org/Sbom-1"},
        {"type": "Bom", "spdxId": "https://example.org/Bom-1"},
        {"type": "SpdxDocument", "spdxId": "https://example.org/Doc-1"},
        {"type": "CreationInfo", "@id": "_:CreationInfo0"},
        {"type": "software_Package", "spdxId": "https://example.org/Package-1"},
    ]
    sorted_elements = sorted(elements, key=_graph_sort_key)
    sorted_types = [e["type"] for e in sorted_elements]

    assert sorted_types[0] == "CreationInfo"
    assert sorted_types[1] == "SpdxDocument"
    assert sorted_types[2] == "Bom"
    assert sorted_types[3] == "software_Sbom"
    assert sorted_types[4] == "software_Package"
