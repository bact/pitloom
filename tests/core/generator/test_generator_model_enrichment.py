# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for build_model()/generate_model_sbom(): AI-model license
handling, external identifiers, dataset-creator attribution, and README
enrichment variants.

See also: tests/core/generator/test_generator_model.py for
registry-based id reuse in the assembler/build_deployed().
tests/core/generator/test_generator_model_fragments.py for
enrich_model() fragment tests, id-consistency, and base-model lineage.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.assemble.spdx3.document import build, build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata

from ..conftest import (
    _AI_LICENSE_CASES,
    _AI_MODEL_ROOT,
    _BUILD_MODEL_LICENSE_CASES,
    _check_license_relationships,
)


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


def test_build_model_external_identifiers() -> None:
    """build_model() must emit ExternalIdentifier for DOI and ExternalRef for
    arXiv paper IDs and model page URLs (external identifiers).
    """
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS),
        name="test-external-ids",
        doi="10.1234/test.doi",
        arxiv_ids=["2301.12345"],
        url="https://huggingface.co/org/test-external-ids",
    )

    exporter = build_model(model, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    ai_pkg = ai_pkgs[0]

    # Verify DOI externalIdentifier
    ext_ids = ai_pkg.get("externalIdentifier", [])
    doi_ids = [
        i
        for i in ext_ids
        if i.get("externalIdentifierType") == "other"
        and i.get("identifier") == "10.1234/test.doi"
    ]
    assert len(doi_ids) == 1
    assert doi_ids[0].get("comment") == "DOI"

    # Verify arXiv and URL externalRef entries
    ext_refs = ai_pkg.get("externalRef", [])
    arxiv_refs = [
        r
        for r in ext_refs
        if r.get("externalRefType") == "documentation"
        and "https://arxiv.org/abs/2301.12345" in r.get("locator", [])
    ]
    assert len(arxiv_refs) == 1
    assert arxiv_refs[0].get("comment") == "arXiv:2301.12345"

    url_refs = [
        r
        for r in ext_refs
        if r.get("externalRefType") == "altWebPage"
        and "https://huggingface.co/org/test-external-ids" in r.get("locator", [])
    ]
    assert len(url_refs) == 1
    assert url_refs[0].get("comment") == "Model page URL"


def test_build_model_with_dataset_creator() -> None:
    """build_model() for a model linked to a dataset with creator metadata
    must emit an Agent element and a publishedBy Relationship
    (dataset creator attribution).
    """
    ds_meta = DatasetMetadata(name="squad", creator="Stanford NLP")
    ds_ref = DatasetReference(role="trainedOn", metadata=ds_meta)
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS),
        name="test-ds-creator",
        datasets=[ds_ref],
    )

    exporter = build_model(model, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    agents = [e for e in graph if e.get("type") == "Agent"]
    creator_agents = [a for a in agents if a.get("name") == "Stanford NLP"]
    assert len(creator_agents) == 1
    agent_spdx_id = creator_agents[0]["spdxId"]

    ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
    assert len(ds_pkgs) == 1
    ds_pkg_id = ds_pkgs[0]["spdxId"]

    rels = [e for e in graph if e.get("type") == "Relationship"]
    pub_rels = [
        r
        for r in rels
        if r.get("relationshipType") == "publishedBy"
        and r.get("from") == ds_pkg_id
        and agent_spdx_id in r.get("to", [])
    ]
    assert len(pub_rels) == 1


def test_generate_model_sbom_readme_enrichment_end_to_end() -> None:
    """A local model file with an adjacent README.md whose YAML frontmatter
    names a dataset absent from the model's own metadata: the enrichment
    run must add a new dataset_DatasetPackage + trainedOn relationship
    with a *distinct* CreationInfo (different createdUsing Tool) from the
    AI package's own, plus an "enrichment"-kind Annotation on the AI
    package recording the change."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )
        (tmppath / "pyproject.toml").write_text("[tool.pitloom]\nenrich = true\n")

        sbom_json = generate_model_sbom(model_path)

        graph = json.loads(sbom_json)["@graph"]
        ai_pkg = next(e for e in graph if e.get("type") == "ai_AIPackage")
        ai_creation_info = ai_pkg["creationInfo"]

        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"
        dataset_creation_info = ds_pkgs[0]["creationInfo"]
        assert dataset_creation_info != ai_creation_info

        rels = [e for e in graph if e.get("type") == "Relationship"]
        trained_on = [
            r
            for r in rels
            if r.get("relationshipType") == "trainedOn"
            and r.get("from") == ai_pkg["spdxId"]
            and ds_pkgs[0]["spdxId"] in r.get("to", [])
        ]
        assert len(trained_on) == 1
        assert trained_on[0]["creationInfo"] == dataset_creation_info

        tools = {e["spdxId"]: e for e in graph if e.get("type") == "Tool"}
        creation_infos = {e["@id"]: e for e in graph if e.get("type") == "CreationInfo"}
        ai_tool_id = creation_infos[ai_creation_info]["createdUsing"][0]
        dataset_tool_id = creation_infos[dataset_creation_info]["createdUsing"][0]
        assert tools[ai_tool_id]["name"] == "Pitloom"
        assert tools[dataset_tool_id]["name"] == "pitloom.enrich.readme"
        # Same createdBy Agent on both -- enrichment doesn't invent a second
        # "Pitloom" identity, only a distinct createdUsing Tool + timestamp.
        assert (
            creation_infos[ai_creation_info]["createdBy"]
            == creation_infos[dataset_creation_info]["createdBy"]
        )

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("subject") == ai_pkg["spdxId"]
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1
        statement = json.loads(enrichment_anns[0]["statement"])
        changed_fields = {c["field"] for c in statement["changes"]}
        assert changed_fields == {"license", "datasets:tiny-imagenet"}

        # The Annotation itself must carry the enrichment tool/timestamp
        # (who/when this specific fact was asserted), not the main
        # document's generic CreationInfo -- otherwise the *only* record
        # of "which enricher filled the license field in place" (N3
        # doesn't cover in-place field-fills, only new elements) is lost.
        assert enrichment_anns[0]["creationInfo"] == dataset_creation_info
        assert enrichment_anns[0]["creationInfo"] != ai_creation_info
        assert all(c["role"] == "detected" for c in statement["changes"])


def test_generate_model_sbom_field_only_enrichment_has_own_creation_info() -> None:
    """When enrichment fills only an existing element's field (no new
    dataset element -- N3 doesn't apply, there's no dataset CreationInfo
    to compare against), the E1/E2 Annotation must still carry its own
    enrichment CreationInfo (the readme enricher's tool/timestamp), not
    silently fall back to the AI package's main document CreationInfo --
    the Annotation is the *only* place this in-place field-fill's
    provenance can live."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text("---\nlicense: apache-2.0\n---\n")
        (tmppath / "pyproject.toml").write_text("[tool.pitloom]\nenrich = true\n")

        graph = json.loads(generate_model_sbom(model_path))["@graph"]

        ai_pkg = next(e for e in graph if e.get("type") == "ai_AIPackage")
        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("subject") == ai_pkg["spdxId"]
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1

        tools = {e["spdxId"]: e for e in graph if e.get("type") == "Tool"}
        creation_infos = {e["@id"]: e for e in graph if e.get("type") == "CreationInfo"}
        ann_ci_id = enrichment_anns[0]["creationInfo"]
        assert ann_ci_id != ai_pkg["creationInfo"]
        ann_tool_id = creation_infos[ann_ci_id]["createdUsing"][0]
        assert tools[ann_tool_id]["name"] == "pitloom.enrich.readme"


def test_generate_model_sbom_no_readme_no_enrichment_artifacts() -> None:
    """No adjacent README: generation succeeds with zero enrichment
    side-effects -- no extra CreationInfo, no enrichment Annotation."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())

        sbom_json = generate_model_sbom(model_path)

        graph = json.loads(sbom_json)["@graph"]
        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert not any(
            json.loads(e["statement"]).get("kind") == "enrichment"
            for e in graph
            if e.get("type") == "Annotation"
        )


def test_generate_model_sbom_default_off_even_with_readme() -> None:
    """No `[tool.pitloom] enrich` config at all: enrichment stays off by
    default, even when an adjacent README has frontmatter to gap-fill from
    -- `enrich` must be explicitly opted into, it's not implicit."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")

        sbom_json = generate_model_sbom(model_path)

        graph = json.loads(sbom_json)["@graph"]
        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]


def test_generate_model_sbom_enrich_local_false_disables_readme_enrichment() -> None:
    """`[tool.pitloom] enrich = false` in a pyproject.toml next to
    the model file turns off README enrichment explicitly (same outcome as
    the default, but exercised independently in case the default changes
    again)."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")
        (tmppath / "pyproject.toml").write_text("[tool.pitloom]\nenrich = false\n")

        sbom_json = generate_model_sbom(model_path)

        graph = json.loads(sbom_json)["@graph"]
        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
