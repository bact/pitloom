# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""End-to-end integration test for native SPDX 3 constructs.

Exercises fragment origin / ExternalMap, declared vs. concluded license,
ExternalIdentifier & ExternalRef, descendantOf base-model lineage, and dataset
creator Agent + publishedBy together on a single representative input (N1,
N2, N4, N5, N6). N3 (a second CreationInfo for an enrichment-created
element) is exercised separately in
``test_enrichment_creation_info_and_annotation_present`` below, since it
needs its own enrichment-run input rather than fitting the shared
``_build_integrated_model()`` fixture. Verifies that:

- all native constructs appear correctly on the same document;
- provenance Annotations are trimmed to residual signal and do not duplicate
  values now covered natively;
- output is byte-identical across two generation runs with identical inputs;
- the combined document can be round-tripped through the repo's SPDX 3 model.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference


def _build_integrated_model() -> AiModelMetadata:
    """Return metadata exercising native license, identifier, lineage, and
    creator data.
    """
    ds_meta = DatasetMetadata(
        name="ai-training-data",
        creator="Example Research Group",
        dataset_types=["text"],
        dataset_size=100000,
    )
    return AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS),
        name="native-spdx-integrated-model",
        version="1.0.0",
        license="mit",
        # External identifiers
        doi="10.1234/example.doi",
        arxiv_ids=["2301.12345"],
        url="https://huggingface.co/example/native-spdx-integrated-model",
        # Base-model lineage
        base_model="openai-community/gpt2",
        base_model_relation="finetune",
        # Dataset creator attribution
        datasets=[DatasetReference(role="trainedOn", metadata=ds_meta)],
        # Make the license concluded by using a non-transparent source/method.
        provenance={
            "license": (
                "Source: model card scan | Field: cardData.license | "
                "Method: spdx-license-detector"
            )
        },
    )


def _load_graph(model: AiModelMetadata) -> tuple[list[dict[str, Any]], str]:
    """Build a standalone SBOM for *model* and return its @graph plus raw JSON."""
    exporter = build_model(model, CreationMetadata())
    raw_json = exporter.to_json(pretty=True)
    graph = json.loads(raw_json)["@graph"]
    return graph, raw_json


def test_all_native_construct_types_present() -> None:
    """All native constructs appear on the same document."""
    graph, _ = _load_graph(_build_integrated_model())
    types = {e.get("type") for e in graph}

    assert "ai_AIPackage" in types
    assert "dataset_DatasetPackage" in types
    assert "Agent" in types
    assert "Relationship" in types
    assert "simplelicensing_SimpleLicensingText" in types


def test_declared_vs_concluded_license_present() -> None:
    """A license produces a hasConcludedLicense relationship because the
    provenance carries a detection method."""
    graph, _ = _load_graph(_build_integrated_model())
    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 2, "expected derived + base model packages"
    derived_pkg = next(
        p for p in ai_pkgs if p["name"] == "native-spdx-integrated-model"
    )

    rels = [e for e in graph if e.get("type") == "Relationship"]
    concluded = [
        r
        for r in rels
        if r.get("relationshipType") == "hasConcludedLicense"
        and r.get("from") == derived_pkg["spdxId"]
    ]
    assert len(concluded) == 1, "expected one hasConcludedLicense relationship"

    license_id = concluded[0]["to"][0]
    license_elems = [
        e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
        and e.get("spdxId") == license_id
    ]
    assert len(license_elems) == 1
    assert license_elems[0]["simplelicensing_licenseText"] == "mit"

    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")
    assert "simpleLicensing" in spdx_doc["profileConformance"]


def test_external_identifiers_and_refs_present() -> None:
    """DOI ExternalIdentifier and arXiv/URL ExternalRefs are present."""
    graph, _ = _load_graph(_build_integrated_model())
    derived_pkg = next(
        e
        for e in graph
        if e.get("type") == "ai_AIPackage"
        and e.get("name") == "native-spdx-integrated-model"
    )

    ext_ids = derived_pkg.get("externalIdentifier", [])
    doi_ids = [
        i
        for i in ext_ids
        if i.get("externalIdentifierType") == "other"
        and i.get("identifier") == "10.1234/example.doi"
        and i.get("comment") == "DOI"
    ]
    assert len(doi_ids) == 1, "expected one DOI ExternalIdentifier"

    ext_refs = derived_pkg.get("externalRef", [])
    arxiv_refs = [
        r
        for r in ext_refs
        if r.get("externalRefType") == "documentation"
        and "https://arxiv.org/abs/2301.12345" in r.get("locator", [])
        and r.get("comment") == "arXiv:2301.12345"
    ]
    assert len(arxiv_refs) == 1, "expected one arXiv ExternalRef"

    url_refs = [
        r
        for r in ext_refs
        if r.get("externalRefType") == "altWebPage"
        and "https://huggingface.co/example/native-spdx-integrated-model"
        in r.get("locator", [])
        and r.get("comment") == "Model page URL"
    ]
    assert len(url_refs) == 1, "expected one model-page ExternalRef"


def test_base_model_lineage_present() -> None:
    """A base-model stub and descendantOf relationship are present."""
    graph, _ = _load_graph(_build_integrated_model())
    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 2

    derived_pkg = next(
        p for p in ai_pkgs if p["name"] == "native-spdx-integrated-model"
    )
    base_pkg = next(p for p in ai_pkgs if p["name"] == "gpt2")

    base_refs = [
        r
        for r in base_pkg.get("externalRef", [])
        if r.get("externalRefType") == "altWebPage"
        and "https://huggingface.co/openai-community/gpt2" in r.get("locator", [])
    ]
    assert len(base_refs) == 1, "expected base model altWebPage ExternalRef"

    rels = [e for e in graph if e.get("type") == "Relationship"]
    lineage_rels = [
        r
        for r in rels
        if r.get("relationshipType") == "descendantOf"
        and r.get("from") == derived_pkg["spdxId"]
        and base_pkg["spdxId"] in r.get("to", [])
        and r.get("comment") == "base_model_relation:finetune"
    ]
    assert len(lineage_rels) == 1, "expected one descendantOf relationship"


def test_dataset_creator_agent_and_published_by_present() -> None:
    """A dataset creator Agent and publishedBy relationship are present."""
    graph, _ = _load_graph(_build_integrated_model())

    agents = [e for e in graph if e.get("type") == "Agent"]
    creator_agents = [a for a in agents if a.get("name") == "Example Research Group"]
    assert len(creator_agents) == 1, "expected one creator Agent"
    agent_id = creator_agents[0]["spdxId"]

    ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
    assert len(ds_pkgs) == 1
    ds_pkg_id = ds_pkgs[0]["spdxId"]

    rels = [e for e in graph if e.get("type") == "Relationship"]
    published_by = [
        r
        for r in rels
        if r.get("relationshipType") == "publishedBy"
        and r.get("from") == ds_pkg_id
        and agent_id in r.get("to", [])
    ]
    assert len(published_by) == 1, "expected one publishedBy relationship"


def test_enrichment_creation_info_and_annotation_present() -> None:
    """N3 (a second CreationInfo for an enrichment-created element) and
    E1/E2 (an "enrichment"-kind Annotation on the AI package) appear
    together, alongside the AI package's own native CreationInfo -- the
    sixth and final Phase-2 native construct, landing after the other
    five above. Uses the real ReadmeEnricher (not a hand-built
    EnrichmentResult) so this exercises the actual enrichment code path,
    matching the rest of this file's "real extraction/assembly, not
    mocks" style.
    """
    # pylint: disable=import-outside-toplevel
    import tempfile

    from pitloom.enrich.readme import ReadmeEnricher

    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS),
        name="enrichment-integrated-model",
        version="1.0.0",
    )
    with tempfile.TemporaryDirectory() as d:
        model_dir = Path(d)
        (model_dir / "README.md").write_text(
            "---\nlicense: mit\ndatasets:\n  - enrichment-integration-dataset\n---\n"
        )
        result = ReadmeEnricher().enrich(model, model_dir=model_dir)

    exporter = build_model(model, CreationMetadata(), enrichment_results=[result])
    graph = json.loads(exporter.to_json(pretty=True))["@graph"]

    ai_pkg = next(e for e in graph if e.get("type") == "ai_AIPackage")
    ds_pkg = next(e for e in graph if e.get("type") == "dataset_DatasetPackage")
    assert ds_pkg["name"] == "enrichment-integration-dataset"
    assert ds_pkg["creationInfo"] != ai_pkg["creationInfo"]

    creation_infos = {e["@id"]: e for e in graph if e.get("type") == "CreationInfo"}
    tools = {e["spdxId"]: e for e in graph if e.get("type") == "Tool"}
    dataset_tool_id = creation_infos[ds_pkg["creationInfo"]]["createdUsing"][0]
    assert tools[dataset_tool_id]["name"] == "pitloom.enrich.readme"
    # Same createdBy Agent as the main document -- no fictitious second
    # "Pitloom" identity, only a distinct createdUsing Tool + timestamp.
    assert (
        creation_infos[ai_pkg["creationInfo"]]["createdBy"]
        == creation_infos[ds_pkg["creationInfo"]]["createdBy"]
    )

    annotations = [e for e in graph if e.get("type") == "Annotation"]
    enrichment_anns = [
        a
        for a in annotations
        if a.get("subject") == ai_pkg["spdxId"]
        and json.loads(a["statement"]).get("kind") == "enrichment"
    ]
    assert len(enrichment_anns) == 1
    changes = json.loads(enrichment_anns[0]["statement"])["changes"]
    assert {c["field"] for c in changes} == {
        "license",
        "datasets:enrichment-integration-dataset",
    }


def test_fragment_origin_round_trips_when_merged() -> None:
    """A fragment-origin ExternalMap can be added and round-tripped.

    The standalone build_model path does not perform fragment merging, so we
    add an ExternalMap directly to the SpdxDocument and verify the document
    round-trips through spdx-python-model without data loss.
    """
    exporter = build_model(_build_integrated_model(), CreationMetadata())
    graph = json.loads(exporter.to_json(pretty=True))["@graph"]
    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")

    fragment_ns = "https://spdx.org/spdxdocs/example-fragment"
    spdx_doc.setdefault("import", []).append(
        {
            "type": "ExternalMap",
            "externalSpdxId": fragment_ns,
            "locationHint": "fragments/example.spdx3.json",
        }
    )

    # Round-trip through the model to confirm validity.
    object_set = spdx3.SHACLObjectSet()
    spdx3.JSONLDDeserializer().read(
        io.BytesIO(
            json.dumps({"@context": spdx_doc.get("@context"), "@graph": graph}).encode(
                "utf-8"
            )
        ),
        object_set,
    )
    docs = [o for o in object_set.objects if isinstance(o, spdx3.SpdxDocument)]
    assert len(docs) == 1
    imports = list(docs[0].import_ or [])
    assert any(getattr(item, "externalSpdxId", None) == fragment_ns for item in imports)


def test_provenance_annotations_do_not_duplicate_native_values() -> None:
    """Residual provenance Annotations must not re-state values now native."""
    graph, _ = _load_graph(_build_integrated_model())
    annotations = [e for e in graph if e.get("type") == "Annotation"]

    for ann in annotations:
        statement = json.loads(ann["statement"])
        # Fields covered by native SPDX 3 constructs should not appear in
        # provenance statements anymore.
        fields = statement.get("fields", {})
        assert "doi" not in fields, "DOI should be native, not in an Annotation"
        assert "arxiv" not in fields, "arXiv should be native"
        assert "url" not in fields, "model URL should be native"
        assert "creator" not in fields, "dataset creator should be native"

    # The license detection *method* is residual signal, but the license value
    # itself lives in the SimpleLicensingText element.
    schema_url = "https://pitloom.dev/provenance/fields/1"
    license_statements = [
        stmt
        for a in annotations
        if (stmt := json.loads(a["statement"])).get("schema") == schema_url
        and "license" in stmt.get("fields", {})
    ]
    for stmt in license_statements:
        license_field = stmt["fields"]["license"]
        # Method/source evidence is allowed; the raw SPDX id is not duplicated.
        assert "mit" not in str(license_field), (
            "license value 'mit' should not be repeated in Annotation"
        )


def test_combined_output_is_deterministic() -> None:
    """Two generation runs with identical inputs produce byte-identical JSON."""
    model = _build_integrated_model()
    fixed_ci = CreationMetadata(creation_datetime="2026-08-08T00:00:00+00:00")

    run1 = build_model(model, fixed_ci).to_json(pretty=False)
    run2 = build_model(model, fixed_ci).to_json(pretty=False)

    assert run1 == run2, "combined SBOM output must be byte-identical"


def test_combined_document_round_trips_through_spdx_model() -> None:
    """The combined SBOM is accepted by spdx-python-model deserialization."""
    exporter = build_model(_build_integrated_model(), CreationMetadata())
    raw_json = exporter.to_json(pretty=False)

    object_set = spdx3.SHACLObjectSet()
    spdx3.JSONLDDeserializer().read(io.BytesIO(raw_json.encode("utf-8")), object_set)

    element_types = {type(o).__name__ for o in object_set.objects}
    assert "ai_AIPackage" in element_types
    assert "dataset_DatasetPackage" in element_types
    assert "Agent" in element_types
    assert "Relationship" in element_types
    assert "SpdxDocument" in element_types
    assert "software_Sbom" in element_types


def test_fragment_fixture_files_available() -> None:
    """The pre-existing fragment fixtures used by integration tests exist."""
    fragment_dir = Path(__file__).parent.parent / "fixtures" / "fragments"
    for name in (
        "ai-model-fragment.spdx3.json",
        "dataset-fragment.spdx3.json",
        "training-run-fragment.spdx3.json",
    ):
        assert (fragment_dir / name).is_file(), f"missing fixture {name}"
