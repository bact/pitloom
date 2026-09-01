# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.spdx3.document.build_deployed(): the
pipdeptree-style env_tree walk's dependency-relationship passes -- second
pass (parent->child dependsOn), third pass (environment-root->top-level
dependsOn) and their edge cases (a package entry missing a "key", a
package that is both a dependency and depended upon), plus the
simpleLicensing profileConformance branch.

See also: tests/core/generator/test_generator_model.py, which
covers build_deployed() registry-based id reuse -- basic AI-model
assembly and usage-file lifecycle scoping live there too.
tests/core/generator/test_generator_model_enrichment.py for
license handling on regular (non-deployed) assembler paths.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from pitloom.assemble.spdx3.document import build_deployed
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata


def _relationships(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in graph if e.get("type") == "Relationship"]


def _packages(graph: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {e["name"]: e for e in graph if e.get("type") == "software_Package"}


def test_build_deployed_links_transitive_dependency_chain() -> None:
    """A multi-level dependency tree (app -> lib-a -> lib-c, app -> lib-b)
    exercises the second pass's inner dependency loop in full (lines
    180-194) and the third pass's "skip, already has a parent" branch
    (lines 199->197) for every non-root package."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree: list[dict[str, Any]] = [
        {
            "package": {
                "key": "app",
                "package_name": "app",
                "installed_version": "1.0",
            },
            "dependencies": [{"key": "lib-a"}, {"key": "lib-b"}],
        },
        {
            "package": {
                "key": "lib-a",
                "package_name": "lib-a",
                "installed_version": "2.0",
            },
            "dependencies": [{"key": "lib-c"}],
        },
        {
            "package": {
                "key": "lib-b",
                "package_name": "lib-b",
                "installed_version": "3.0",
            }
        },
        {
            "package": {
                "key": "lib-c",
                "package_name": "lib-c",
                "installed_version": "4.0",
            }
        },
    ]

    exporter = build_deployed(doc, env_tree, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    pkgs = _packages(graph)
    rels = _relationships(graph)
    dep_rels = [r for r in rels if r.get("relationshipType") == "dependsOn"]

    def _has(from_name: str, to_name: str) -> bool:
        from_id = pkgs[from_name]["spdxId"]
        to_id = pkgs[to_name]["spdxId"]
        return any(r["from"] == from_id and to_id in r["to"] for r in dep_rels)

    # Second pass: parent -> child edges for every declared dependency.
    assert _has("app", "lib-a")
    assert _has("app", "lib-b")
    assert _has("lib-a", "lib-c")

    # Third pass: only "app" has no parent, so only it gets linked to the
    # synthetic environment-root main package; lib-a/lib-b/lib-c must not.
    main_pkg = next(
        e
        for e in graph
        if e.get("type") == "software_Package" and e["name"] == "deployed-environment"
    )
    root_edges = [r for r in dep_rels if r["from"] == main_pkg["spdxId"]]
    assert len(root_edges) == 1
    assert root_edges[0]["to"] == [pkgs["app"]["spdxId"]]


def test_build_deployed_package_without_key_is_skipped_in_relationship_passes() -> None:
    """A pipdeptree node whose "package" dict has no "key" (only
    "package_name") still gets a software_Package element in the first
    pass, but is silently excluded from both the second pass (line 178:
    no parent_spdx_id to look up) and the third pass (line 201->197: no
    child_spdx_id to look up either) -- it ends up with no relationship
    at all rather than crashing."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree: list[dict[str, Any]] = [
        {
            "package": {
                "package_name": "orphan",
                "installed_version": "9.9",
            }
        }
    ]

    exporter = build_deployed(doc, env_tree, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    pkgs = _packages(graph)
    assert "orphan" in pkgs

    # Every package (even "orphan") gets a NOASSERTION license
    # relationship, which is unrelated to the dependency-tree passes under
    # test here -- restrict to "dependsOn" to check those specifically.
    dep_rels = [
        r for r in _relationships(graph) if r.get("relationshipType") == "dependsOn"
    ]
    orphan_id = pkgs["orphan"]["spdxId"]
    assert not any(
        r["from"] == orphan_id or orphan_id in r.get("to", []) for r in dep_rels
    )


def test_build_deployed_adds_simple_licensing_profile_when_license_found() -> None:
    """When a dependency's locally-installed metadata resolves a real
    license (offline path via importlib.metadata, not the network), a
    simplelicensing_SimpleLicensingText element is created and the
    document's profileConformance gains the simpleLicensing profile
    (lines 232-238). "pytest" is used as the dependency name because it
    is installed in this test environment with a known License-Expression
    of "MIT"."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree = [
        {
            "package": {
                "key": "pytest",
                "package_name": "pytest",
                "installed_version": "unknown",
            }
        }
    ]

    exporter = build_deployed(doc, env_tree, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    licenses = [
        e for e in graph if e.get("type") == "simplelicensing_SimpleLicensingText"
    ]
    assert licenses, "expected a SimpleLicensingText element from pytest's metadata"

    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")
    assert "simpleLicensing" in spdx_doc["profileConformance"]


def test_build_deployed_no_simple_licensing_profile_for_empty_environment() -> None:
    """Baseline: with no installed packages at all, no
    simplelicensing_SimpleLicensingText element is ever created (not even
    a NOASSERTION one, since that path only runs per-dependency), so the
    simpleLicensing profile must not be added -- the false side of the
    line 232-238 branch."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build_deployed(doc, [], offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    licenses = [
        e for e in graph if e.get("type") == "simplelicensing_SimpleLicensingText"
    ]
    assert not licenses

    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")
    assert "simpleLicensing" not in spdx_doc["profileConformance"]


def test_build_deployed_dependency_entry_without_key_is_skipped() -> None:
    """A "dependencies" entry with no "key" at all (not even present in the
    dict, unlike the "package without key" case above) must be silently
    skipped in the second pass -- it is neither recorded in
    dep_keys_with_parents (child_key falsy) nor looked up in
    package_spdx_ids (child_spdx_id falsy), rather than crashing."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree: list[dict[str, Any]] = [
        {
            "package": {
                "key": "app",
                "package_name": "app",
                "installed_version": "1.0",
            },
            "dependencies": [{}],
        },
    ]

    exporter = build_deployed(doc, env_tree, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    dep_rels = [
        r
        for r in graph
        if r.get("type") == "Relationship" and r.get("relationshipType") == "dependsOn"
    ]
    pkgs = _packages(graph)
    app_id = pkgs["app"]["spdxId"]
    # "app" still gets linked from the synthetic environment root (third
    # pass), but the keyless dependency entry contributes no edge at all.
    assert all(r["to"] == [app_id] or r["from"] != app_id for r in dep_rels)


def test_build_deployed_no_relationships_when_build_relationship_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When build_relationship() returns None, both the second pass
    (parent -> child dependsOn) and the third pass (environment-root ->
    top-level dependsOn) must skip adding a Relationship element rather
    than crashing."""
    monkeypatch.setattr(
        "pitloom.assemble.spdx3._document_deployed.build_relationship",
        lambda *args, **kwargs: None,
    )
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree: list[dict[str, Any]] = [
        {
            "package": {
                "key": "app",
                "package_name": "app",
                "installed_version": "1.0",
            },
            "dependencies": [{"key": "lib-a"}],
        },
        {
            "package": {
                "key": "lib-a",
                "package_name": "lib-a",
                "installed_version": "2.0",
            },
        },
    ]

    exporter = build_deployed(doc, env_tree, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    dep_rels = [
        r
        for r in graph
        if r.get("type") == "Relationship" and r.get("relationshipType") == "dependsOn"
    ]
    assert dep_rels == []
