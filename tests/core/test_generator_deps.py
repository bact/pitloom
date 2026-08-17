# ruff: noqa: F403, F405
from __future__ import annotations

import json

from pitloom.assemble.spdx3.document import (
    build,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import PhantomDependency, ProjectFile, ProjectMetadata

from .conftest import *


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

    # Same completeness policy as regular dependencies (add_dependencies):
    # NOASSERTION for copyright/license rather than a silently absent
    # field, and the bundled binary's own hash -- already computed
    # locally -- as its integrity hash.
    assert phantom_pkg["software_copyrightText"] == "NOASSERTION"
    assert phantom_pkg["verifiedUsing"] == [
        {"type": "Hash", "algorithm": "sha256", "hashValue": "c" * 64}
    ]
    license_rels = [
        r
        for r in relationships
        if r["relationshipType"] == "hasDeclaredLicense"
        and r["from"] == phantom_pkg["spdxId"]
    ]
    assert len(license_rels) == 1
    licenses = {
        e["spdxId"]: e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
    }
    assert (
        licenses[license_rels[0]["to"][0]]["simplelicensing_licenseText"]
        == "NOASSERTION"
    )


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
