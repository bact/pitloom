# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pitloom.assemble import (
    enrich_model,
    generate_model_sbom,
    generate_project_sbom,
)
from pitloom.assemble.spdx3.document import (
    build,
    build_deployed,
    build_model,
)
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.ids import IdRegistry

from .conftest import *


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


def test_enrich_model_writes_bare_graph_fragment() -> None:
    """enrich_model() must always run enrichment regardless of
    [tool.pitloom] enrich (calling it is itself the opt-in), and its output
    must be a bare @graph fragment -- no SpdxDocument/software_Sbom/
    ai_AIPackage wrapper -- containing only what the enrichment run added."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        fragment_json = enrich_model(model_path)
        fragment = json.loads(fragment_json)

        assert set(fragment.keys()) == {"@context", "@graph"}
        types = {e.get("type") for e in fragment["@graph"]}
        assert "SpdxDocument" not in types
        assert "software_Sbom" not in types
        assert "ai_AIPackage" not in types

        ds_pkgs = [
            e for e in fragment["@graph"] if e.get("type") == "dataset_DatasetPackage"
        ]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"

        annotations = [e for e in fragment["@graph"] if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("statement")
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1
        changed_fields = {
            c["field"] for c in json.loads(enrichment_anns[0]["statement"])["changes"]
        }
        assert changed_fields == {"license", "datasets:tiny-imagenet"}


def test_enrich_model_no_readme_produces_empty_fragment() -> None:
    """No adjacent README: enrich_model() must not raise -- it writes a
    valid fragment with no enrichment content."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())

        fragment = json.loads(enrich_model(model_path))

        assert not [
            e for e in fragment["@graph"] if e.get("type") == "dataset_DatasetPackage"
        ]
        assert not [e for e in fragment["@graph"] if e.get("type") == "Annotation"]


def test_enrich_model_rejects_huggingface_source() -> None:
    """A Hugging Face source has no local enrichment to run -- HF model
    cards are already parsed natively -- so enrich_model() must reject it
    with a clear error rather than silently doing nothing."""
    with pytest.raises(ValueError, match="Hugging Face"):
        enrich_model("org/model-id")


def test_enrich_model_and_generate_model_sbom_reference_matching_ai_package_id() -> (
    None
):
    """Design invariant: a fragment from enrich_model() run against a local
    file must reference the exact same ai_AIPackage spdxId that
    generate_model_sbom(enrich=True) on the same file would assign -- both
    go through the same identity computation (_ai_model_identity), so the
    fragment's Annotation subject resolves to the base doc's real AI
    package once merged. The fragment's own newly-minted elements
    (CreationInfo, Tool, Annotation, DatasetPackage) deliberately live in a
    separate id namespace from the base doc -- see build_enrichment_fragment's
    docstring -- so only the referenced ai_AIPackage id is expected to
    match, not the fragment's full id set."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        fragment = json.loads(enrich_model(model_path))
        full_doc = json.loads(generate_model_sbom(model_path, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == full_ai_pkg["spdxId"]


def test_enrich_model_project_target_matches_project_level_ai_package_id() -> None:
    """A fragment from enrich_model(project_target=...) must reference the
    same ai_AIPackage id generate_project_sbom() assigns for that model --
    project-level and single-model identity schemes differ (project name/
    version/dependencies/Merkle root vs. the model's own name/version), so
    without project_target the fragment would reference a nonexistent id
    once merged into a project-level base document (the bug this test
    guards against)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment = json.loads(enrich_model(model_path, project_target=tmppath))
        full_doc = json.loads(generate_project_sbom(tmppath, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == full_ai_pkg["spdxId"]


def test_enrich_model_without_project_target_mismatches_project_level_id() -> None:
    """Negative-space guard: *without* project_target, the fragment's
    referenced id must NOT match the project-level ai_AIPackage id -- if
    this test starts failing (i.e. they start matching by coincidence),
    the project_target parameter has become unnecessary and the "why" in
    build_enrichment_fragment's docstring needs re-checking, not this
    test silently loosened."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment = json.loads(enrich_model(model_path))
        full_doc = json.loads(generate_project_sbom(tmppath, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] != full_ai_pkg["spdxId"]


def test_enrich_model_project_target_merges_correctly_end_to_end() -> None:
    """The actual regression test for the bug: a fragment generated with
    project_target, registered under [tool.pitloom.fragment], and merged
    via a real generate_project_sbom() re-run must produce a
    dataset_DatasetPackage and enrichment Annotation genuinely attached to
    the project's real ai_AIPackage -- not just matching id strings in
    isolation (see the two tests above), but surviving an actual
    merge_fragments() pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment_path = tmppath / "model.enrich.spdx3.json"
        enrich_model(model_path, project_target=tmppath, output_path=fragment_path)
        with (tmppath / "pyproject.toml").open("a") as f:
            f.write('\n[tool.pitloom.fragment]\nfiles = ["model.enrich.spdx3.json"]\n')

        merged = json.loads(generate_project_sbom(tmppath))
        graph = merged["@graph"]

        ai_pkg = next(e for e in graph if e.get("type") == "ai_AIPackage")
        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"

        rels = [e for e in graph if e.get("type") == "Relationship"]
        trained_on = [
            r
            for r in rels
            if r.get("relationshipType") == "trainedOn"
            and r.get("from") == ai_pkg["spdxId"]
            and ds_pkgs[0]["spdxId"] in r.get("to", [])
        ]
        assert len(trained_on) == 1

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("subject") == ai_pkg["spdxId"]
            and json.loads(a.get("statement", "{}")).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1


def test_enrich_model_registry_pinned_id_matches_base_doc() -> None:
    """A registry-pinned ai_AIPackage id must be referenced by the
    fragment too, not the freshly computed one -- otherwise a project
    using a stable registry (--registry) gets the same dangling-reference
    bug as the project_target case, even for a single-model base doc."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(
            (
                _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
            ).read_bytes()
        )
        (tmppath / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")

        registry_path = tmppath / "loom-ids.json"
        registry = IdRegistry.new("pinned-demo", path=registry_path)
        pinned_id = registry.register_entity("model", "ai_AIPackage")
        registry.save()

        full_doc = json.loads(
            generate_model_sbom(model_path, enrich=True, registry=registry_path)
        )
        fragment = json.loads(enrich_model(model_path, registry=registry_path))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        assert full_ai_pkg["spdxId"] == pinned_id

        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == pinned_id


def test_build_model_base_model_lineage() -> None:
    """build_model() must emit a stub base model ai_AIPackage and a descendantOf
    Relationship when base_model and base_model_relation are present
    (base-model lineage).
    """
    meta = AiModelMetadata(
        name="my-finetuned-model",
        base_model="Qwen/Qwen2.5-Math-1.5B",
        base_model_relation="finetune",
    )
    exporter = build_model(meta, CreationMetadata())
    graph = json.loads(exporter.to_json(pretty=True)).get("@graph", [])

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 2
    derived_pkg = next(p for p in ai_pkgs if p["name"] == "my-finetuned-model")
    base_pkg = next(p for p in ai_pkgs if p["name"] == "Qwen2.5-Math-1.5B")

    ext_refs = base_pkg.get("externalRef", [])
    assert any(
        r.get("externalRefType") == "altWebPage"
        and "https://huggingface.co/Qwen/Qwen2.5-Math-1.5B" in r.get("locator", [])
        for r in ext_refs
    )

    rels = [e for e in graph if e.get("type") == "Relationship"]
    lineage_rels = [
        r
        for r in rels
        if r.get("relationshipType") == "descendantOf"
        and r.get("from") == derived_pkg["spdxId"]
        and base_pkg["spdxId"] in r.get("to", [])
    ]
    assert len(lineage_rels) == 1
    assert lineage_rels[0].get("comment") == "base_model_relation:finetune"
