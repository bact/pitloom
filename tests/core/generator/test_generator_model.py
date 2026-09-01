# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.spdx3.document build()/build_deployed():
basic AI-model assembly, usage-file lifecycle scoping, and registry-based
id reuse for the assembler and Deployed SBOMs.

See also: tests/core/generator/test_generator_model_enrichment.py for license
handling, external identifiers, dataset-creator attribution, and
generate_model_sbom() enrichment variants.
tests/core/generator/test_generator_model_fragments.py for enrich_model() fragment
tests, id-consistency, and base-model lineage.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import json

from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.ids import IdRegistry


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

    # no license relationship *from the AI package* when ai_model.license is
    # not set (the main project package gets its own NOASSERTION fallback
    # when it has no declared license either -- see build()'s license block
    # -- which is a separate, expected relationship, not this one).
    ai_pkg_license_rels = [
        r
        for r in rels
        if r.get("relationshipType") in ("hasDeclaredLicense", "hasConcludedLicense")
        and r.get("from") == pkg["spdxId"]
    ]
    assert not ai_pkg_license_rels


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
    generate_model_sbom performs for loom model/--registry) when no
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
