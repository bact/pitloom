# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.export.spdx3_json: require_spdx_id(), sha256_hash(),
_annotate_relationships(), and Spdx3JsonExporter's license indexing and
to_json()/to_file() serialization.

See also: tests/ids_shared.py, which builds a fuller Spdx3JsonExporter
document for pitloom.ids tests; tests/core/conftest.py, which exercises
Spdx3JsonExporter indirectly through the full assembler pipeline.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.spdx3_json import (
    Spdx3JsonExporter,
    _annotate_relationships,
    require_spdx_id,
    sha256_hash,
)


def _creation_info() -> spdx3.CreationInfo:
    """A CreationInfo with a self-referential createdBy, satisfying the
    model's ``min_count`` requirement without needing a separate Agent
    element added to the exporter for every test."""
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    ci.createdBy = ["https://example.org#SoftwareAgent-1"]
    return ci


# --- require_spdx_id ---


def test_require_spdx_id_returns_assigned_id() -> None:
    ci = _creation_info()
    pkg = spdx3.software_Package(
        spdxId="https://example.org#Package-1", name="pkg", creationInfo=ci
    )
    assert require_spdx_id(pkg) == "https://example.org#Package-1"


def test_require_spdx_id_raises_when_unassigned() -> None:
    ci = _creation_info()
    pkg = spdx3.software_Package(name="pkg", creationInfo=ci)
    with pytest.raises(ValueError, match="has no spdxId assigned"):
        require_spdx_id(pkg)


# --- sha256_hash ---


def test_sha256_hash_without_comment() -> None:
    digest = "a" * 64
    result = sha256_hash(digest)
    assert result.algorithm == spdx3.HashAlgorithm.sha256
    assert result.hashValue == digest
    assert result.comment is None


def test_sha256_hash_with_comment() -> None:
    digest = "b" * 64
    result = sha256_hash(digest, comment="from wheel RECORD")
    assert result.comment == "from wheel RECORD"


# --- _annotate_relationships ---


def test_annotate_relationships_uses_name_field() -> None:
    graph: list[dict[str, Any]] = [
        {"spdxId": "urn:x#A", "name": "app"},
        {"spdxId": "urn:x#B", "name": "lib"},
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "dependsOn",
            "from": "urn:x#A",
            "to": ["urn:x#B"],
        },
    ]
    _annotate_relationships(graph)
    rel = graph[2]
    assert rel["description"] == "app dependsOn: lib"


def test_annotate_relationships_multiple_to_ids_are_joined() -> None:
    graph: list[dict[str, Any]] = [
        {"spdxId": "urn:x#A", "name": "app"},
        {"spdxId": "urn:x#B", "name": "lib-b"},
        {"spdxId": "urn:x#C", "name": "lib-c"},
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "dependsOn",
            "from": "urn:x#A",
            "to": ["urn:x#B", "urn:x#C"],
        },
    ]
    _annotate_relationships(graph)
    assert graph[3]["description"] == "app dependsOn: lib-b, lib-c"


def test_annotate_relationships_falls_back_to_license_expression() -> None:
    graph: list[dict[str, Any]] = [
        {"spdxId": "urn:x#A", "name": "app"},
        {
            "spdxId": "urn:x#Lic-1",
            "simplelicensing_licenseExpression": "MIT",
        },
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "hasConcludedLicense",
            "from": "urn:x#A",
            "to": ["urn:x#Lic-1"],
        },
    ]
    _annotate_relationships(graph)
    assert graph[2]["description"] == "app hasConcludedLicense: MIT"


def test_annotate_relationships_falls_back_to_description_field() -> None:
    graph: list[dict[str, Any]] = [
        {"spdxId": "urn:x#A", "name": "app"},
        {"spdxId": "urn:x#B", "description": "a bespoke note"},
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "dependsOn",
            "from": "urn:x#A",
            "to": ["urn:x#B"],
        },
    ]
    _annotate_relationships(graph)
    assert graph[2]["description"] == "app dependsOn: a bespoke note"


def test_annotate_relationships_falls_back_to_id_suffix() -> None:
    """When an element has neither name, license expression, nor
    description, its @id/spdxId suffix is used; and an id referenced by a
    relationship but absent from the graph entirely also falls back to its
    own suffix."""
    graph: list[dict[str, Any]] = [
        {"spdxId": "urn:x#A"},
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "dependsOn",
            "from": "urn:x#A",
            "to": ["urn:x#Unlisted"],
        },
    ]
    _annotate_relationships(graph)
    assert graph[1]["description"] == "A dependsOn: Unlisted"


def test_annotate_relationships_uses_blank_node_id_field() -> None:
    """Elements identified by @id (blank nodes) rather than spdxId are
    still indexed by name."""
    graph: list[dict[str, Any]] = [
        {"@id": "_:CreationInfo0"},
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "dependsOn",
            "from": "_:CreationInfo0",
            "to": ["urn:x#B"],
        },
    ]
    _annotate_relationships(graph)
    # No "#" in the blank-node id, so the id_to_name lookup and the
    # rsplit("#") fallback both resolve to the id unchanged.
    assert graph[1]["description"] == "_:CreationInfo0 dependsOn: B"


def test_annotate_relationships_skips_nodes_without_relationship_type() -> None:
    graph: list[dict[str, Any]] = [
        {"spdxId": "urn:x#A", "name": "app"},
        {"spdxId": "urn:x#B", "name": "lib", "from": "urn:x#A", "to": ["urn:x#B"]},
    ]
    _annotate_relationships(graph)
    assert "description" not in graph[1]


def test_annotate_relationships_skips_when_to_is_not_a_list() -> None:
    """'to' as a bare string (not a list) leaves the node unannotated --
    the isinstance(to_ids, list) guard rejects it."""
    graph: list[dict[str, Any]] = [
        {"spdxId": "urn:x#A", "name": "app"},
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "dependsOn",
            "from": "urn:x#A",
            "to": "urn:x#B",
        },
    ]
    _annotate_relationships(graph)
    assert "description" not in graph[1]


def test_annotate_relationships_skips_element_without_id() -> None:
    """A graph node with neither ``spdxId`` nor ``@id`` (e.g. a bare
    ``CreationInfo`` blank node) is skipped when building the id-to-name
    map, and doesn't prevent later elements' names from being resolved."""
    graph: list[dict[str, Any]] = [
        {"type": "CreationInfo", "specVersion": "3.0.1"},
        {"spdxId": "urn:x#A", "name": "app"},
        {"spdxId": "urn:x#B", "name": "lib"},
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "dependsOn",
            "from": "urn:x#A",
            "to": ["urn:x#B"],
        },
    ]
    _annotate_relationships(graph)
    assert graph[3]["description"] == "app dependsOn: lib"


def test_annotate_relationships_skips_missing_from_or_to() -> None:
    graph: list[dict[str, Any]] = [
        {
            "spdxId": "urn:x#Rel-1",
            "relationshipType": "dependsOn",
            "from": "urn:x#A",
        },
        {
            "spdxId": "urn:x#Rel-2",
            "relationshipType": "dependsOn",
            "to": ["urn:x#B"],
        },
    ]
    _annotate_relationships(graph)
    assert "description" not in graph[0]
    assert "description" not in graph[1]


# --- Spdx3JsonExporter: license indexing ---


def test_add_license_indexes_by_license_text() -> None:
    ci = _creation_info()
    exporter = Spdx3JsonExporter()
    license_text = spdx3.simplelicensing_SimpleLicensingText(
        spdxId="urn:x#Lic-1", creationInfo=ci
    )
    license_text.simplelicensing_licenseText = "MIT"
    exporter.add_license(license_text)
    assert exporter.find_license("MIT") == "urn:x#Lic-1"


def test_add_license_without_license_text_is_not_indexed() -> None:
    """A SimpleLicensingText with no simplelicensing_licenseText value
    (falsy) is added to the object set but never registered in the
    lookup index."""
    ci = _creation_info()
    exporter = Spdx3JsonExporter()
    license_text = spdx3.simplelicensing_SimpleLicensingText(
        spdxId="urn:x#Lic-1", creationInfo=ci
    )
    exporter.add_license(license_text)
    assert exporter.find_license("MIT") is None
    assert license_text in exporter.object_set.objects


# --- Spdx3JsonExporter: to_json()/to_file() ---


def _build_minimal_document(exporter: Spdx3JsonExporter) -> dict[str, str]:
    """Populate *exporter* with the minimum valid SPDX 3 document graph:
    creation info, a main package, a dependency package, a dependsOn
    relationship between them, an SBOM, and the document envelope."""
    namespace = "https://example.org/spdxdocs/sample"
    ci = _creation_info()
    exporter.add_creation_info(ci)

    main_pkg = spdx3.software_Package(
        spdxId=f"{namespace}#Package-1", name="app", creationInfo=ci
    )
    dep_pkg = spdx3.software_Package(
        spdxId=f"{namespace}#Package-2", name="requests", creationInfo=ci
    )
    exporter.add_package(main_pkg)
    exporter.add_package(dep_pkg)

    relationship = spdx3.Relationship(
        spdxId=f"{namespace}#Relationship-1",
        from_=require_spdx_id(main_pkg),
        to=[require_spdx_id(dep_pkg)],
        relationshipType=spdx3.RelationshipType.dependsOn,
        creationInfo=ci,
    )
    exporter.add_relationship(relationship)

    sbom = spdx3.software_Sbom(
        spdxId=f"{namespace}#Sbom-1",
        creationInfo=ci,
        rootElement=[require_spdx_id(main_pkg)],
    )
    exporter.add_sbom(sbom)

    doc = spdx3.SpdxDocument(
        spdxId=namespace, creationInfo=ci, rootElement=[require_spdx_id(sbom)]
    )
    exporter.add_document(doc)

    return {
        "main_id": f"{namespace}#Package-1",
        "dep_id": f"{namespace}#Package-2",
        "relationship_id": f"{namespace}#Relationship-1",
    }


def test_to_json_without_describe_relationship_omits_description() -> None:
    exporter = Spdx3JsonExporter()
    ids = _build_minimal_document(exporter)
    graph = json.loads(exporter.to_json())["@graph"]
    rel = next(e for e in graph if e.get("spdxId") == ids["relationship_id"])
    assert "description" not in rel


def test_to_json_with_describe_relationship_adds_description() -> None:
    exporter = Spdx3JsonExporter()
    ids = _build_minimal_document(exporter)
    graph = json.loads(exporter.to_json(describe_relationship=True))["@graph"]
    rel = next(e for e in graph if e.get("spdxId") == ids["relationship_id"])
    assert rel["description"] == "app dependsOn: requests"


def test_to_file_writes_json_to_path(tmp_path: Path) -> None:
    exporter = Spdx3JsonExporter()
    _build_minimal_document(exporter)
    out_path = tmp_path / "sbom.spdx3.json"

    exporter.to_file(str(out_path))

    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert "@graph" in written
    names = {e.get("name") for e in written["@graph"] if "name" in e}
    assert {"app", "requests"} <= names


def test_to_file_pretty_matches_to_json_pretty(tmp_path: Path) -> None:
    exporter = Spdx3JsonExporter()
    _build_minimal_document(exporter)
    out_path = tmp_path / "sbom-pretty.spdx3.json"

    exporter.to_file(str(out_path), pretty=True)

    assert out_path.read_text(encoding="utf-8") == exporter.to_json(pretty=True)
