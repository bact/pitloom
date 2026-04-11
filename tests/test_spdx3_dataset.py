# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the SPDX 3 dataset package and relationship assembler."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from datetime import datetime, timezone

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.dataset import (
    _build_dataset_package,
    add_datasets_for_model,
)
from pitloom.assemble.spdx3.document import build as build_doc
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.document import DocumentModel
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter

_DOC_NAME = "testproject"
_DOC_UUID = compute_doc_uuid("testproject", "1.0", [])


def _make_ci() -> spdx3.CreationInfo:
    ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    # createdBy is required for serialisation; use a dummy spdxId.
    person = spdx3.Person(
        spdxId=generate_spdx_id("Person", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID),
        name="Test",
        creationInfo=ci,
    )
    ci.createdBy = [person.spdxId]  # type: ignore[attr-defined, assignment]
    return ci


def _make_meta(**kwargs) -> DatasetMetadata:  # type: ignore[no-untyped-def]
    return DatasetMetadata(name="Test Dataset", **kwargs)


# ---------------------------------------------------------------------------
# _build_dataset_package — core fields
# ---------------------------------------------------------------------------


def test_build_dataset_package_name() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(_make_meta(), _make_ci(), _DOC_NAME, _DOC_UUID)
    assert pkg.name == "Test Dataset"


def test_build_dataset_package_version() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(version="2.0"), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert pkg.software_packageVersion == "2.0"


def test_build_dataset_package_description() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(description="A test dataset."), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert pkg.description == "A test dataset."


def test_build_dataset_package_download_url() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(download_url="https://example.com/data"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.software_downloadLocation == "https://example.com/data"


# ---------------------------------------------------------------------------
# _build_dataset_package — dataset-profile fields
# ---------------------------------------------------------------------------


def test_build_dataset_package_dataset_types() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(dataset_types=["text", "numeric"]), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert len(pkg.dataset_datasetType) == 2


def test_build_dataset_package_unknown_type_skipped() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(dataset_types=["text", "unknownXYZ"]),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    # Only "text" is valid; "unknownXYZ" is silently skipped.
    assert len(pkg.dataset_datasetType) == 1


def test_build_dataset_package_dataset_size() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(dataset_size=10000), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert pkg.dataset_datasetSize == 10000


def test_build_dataset_package_data_collection_process() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(data_collection_process="Web crawl."),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_dataCollectionProcess == "Web crawl."


def test_build_dataset_package_preprocessing() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(data_preprocessing=["tokenization", "lowercasing"]),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert "tokenization" in pkg.dataset_dataPreprocessing
    assert "lowercasing" in pkg.dataset_dataPreprocessing


def test_build_dataset_package_known_bias() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(known_bias=["selection bias"]), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert "selection bias" in pkg.dataset_knownBias


def test_build_dataset_package_intended_use() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(intended_use="Sentiment analysis."),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_intendedUse == "Sentiment analysis."


def test_build_dataset_package_sensitivity_no() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(has_sensitive_personal_information="no"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_hasSensitivePersonalInformation == spdx3.PresenceType.no


def test_build_dataset_package_sensitivity_yes() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(has_sensitive_personal_information="yes"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_hasSensitivePersonalInformation == spdx3.PresenceType.yes


def test_build_dataset_package_sensitivity_no_assertion() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(has_sensitive_personal_information="noAssertion"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_hasSensitivePersonalInformation == spdx3.PresenceType.noAssertion


def test_build_dataset_package_invalid_sensitivity_omitted() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(has_sensitive_personal_information="maybe"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_hasSensitivePersonalInformation is None


def test_build_dataset_package_anonymization() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(anonymization_methods=["k-anonymity"]),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert "k-anonymity" in pkg.dataset_anonymizationMethodUsed


# ---------------------------------------------------------------------------
# _build_dataset_package — Croissant ExternalRef
# ---------------------------------------------------------------------------


def test_build_dataset_package_croissant_url_as_external_ref() -> None:
    _clear_doc_counters(_DOC_UUID)
    url = "https://huggingface.co/datasets/example/croissant.json"
    pkg = _build_dataset_package(
        _make_meta(croissant_url=url), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert len(pkg.externalRef) == 1
    ref = pkg.externalRef[0]
    assert isinstance(ref, spdx3.ExternalRef)
    assert url in ref.locator
    assert ref.externalRefType == spdx3.ExternalRefType.other
    assert ref.comment == "Croissant metadata"


def test_build_dataset_package_no_croissant_url_no_external_ref() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(_make_meta(), _make_ci(), _DOC_NAME, _DOC_UUID)
    assert not pkg.externalRef


# ---------------------------------------------------------------------------
# _build_dataset_package — provenance comment
# ---------------------------------------------------------------------------


def test_build_dataset_package_provenance_in_comment() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(provenance={"name": "Source: test.json | Field: name"}),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.comment is not None
    assert "Metadata provenance" in pkg.comment
    assert "name" in pkg.comment


# ---------------------------------------------------------------------------
# add_datasets_for_model — relationship types
# ---------------------------------------------------------------------------


def _make_exporter() -> Spdx3JsonExporter:
    return Spdx3JsonExporter()


def test_add_datasets_trained_on_relationship() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = _make_exporter()
    ci = _make_ci()
    ai_spdx_id = generate_spdx_id("AIPackage", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID)

    datasets = [DatasetReference(role="trainedOn", metadata=_make_meta())]
    add_datasets_for_model(ai_spdx_id, datasets, ci, _DOC_NAME, _DOC_UUID, exporter)

    # Inspect the exported graph for the relationship
    data = json.loads(exporter.to_json())
    graph = data["@graph"]
    rels = [e for e in graph if e.get("type") == "Relationship"]
    assert any("trainedOn" in str(r.get("relationshipType", "")) for r in rels)


def test_add_datasets_tested_on_relationship() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = _make_exporter()
    ci = _make_ci()
    ai_spdx_id = generate_spdx_id("AIPackage", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID)

    datasets = [DatasetReference(role="testedOn", metadata=_make_meta())]
    add_datasets_for_model(ai_spdx_id, datasets, ci, _DOC_NAME, _DOC_UUID, exporter)

    data = json.loads(exporter.to_json())
    rels = [e for e in data["@graph"] if e.get("type") == "Relationship"]
    assert any("testedOn" in str(r.get("relationshipType", "")) for r in rels)


def test_add_datasets_finetuned_on_falls_back_to_other() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = _make_exporter()
    ci = _make_ci()
    ai_spdx_id = generate_spdx_id("AIPackage", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID)

    datasets = [DatasetReference(role="finetunedOn", metadata=_make_meta())]
    add_datasets_for_model(ai_spdx_id, datasets, ci, _DOC_NAME, _DOC_UUID, exporter)

    data = json.loads(exporter.to_json())
    rels = [e for e in data["@graph"] if e.get("type") == "Relationship"]
    assert any("other" in str(r.get("relationshipType", "")) for r in rels)
    # Comment should explain the fallback
    assert any("finetunedOn" in str(r.get("comment", "")) for r in rels)


def test_add_datasets_unknown_role_falls_back_to_other() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = _make_exporter()
    ci = _make_ci()
    ai_spdx_id = generate_spdx_id("AIPackage", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID)

    datasets = [DatasetReference(role="someNewRole", metadata=_make_meta())]
    add_datasets_for_model(ai_spdx_id, datasets, ci, _DOC_NAME, _DOC_UUID, exporter)

    data = json.loads(exporter.to_json())
    rels = [e for e in data["@graph"] if e.get("type") == "Relationship"]
    assert any("other" in str(r.get("relationshipType", "")) for r in rels)


def test_add_datasets_multiple_datasets() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = _make_exporter()
    ci = _make_ci()
    ai_spdx_id = generate_spdx_id("AIPackage", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID)

    datasets = [
        DatasetReference(role="trainedOn", metadata=DatasetMetadata(name="Train")),
        DatasetReference(role="testedOn", metadata=DatasetMetadata(name="Test")),
    ]
    add_datasets_for_model(ai_spdx_id, datasets, ci, _DOC_NAME, _DOC_UUID, exporter)

    data = json.loads(exporter.to_json())
    graph = data["@graph"]
    rels = [e for e in graph if e.get("type") == "Relationship"]
    assert len(rels) == 2


def test_add_datasets_empty_list_no_elements() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = _make_exporter()
    ci = _make_ci()
    ai_spdx_id = generate_spdx_id("AIPackage", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID)

    add_datasets_for_model(ai_spdx_id, [], ci, _DOC_NAME, _DOC_UUID, exporter)

    data = json.loads(exporter.to_json())
    graph = data.get("@graph", [])
    assert all(e.get("type") != "Relationship" for e in graph)


# ---------------------------------------------------------------------------
# Integration: dataset profile conformance in document assembly
# ---------------------------------------------------------------------------


def test_document_has_dataset_profile_when_model_has_datasets() -> None:
    project = ProjectMetadata(name="myproject", version="1.0")
    creation = CreationMetadata(creator_name="Test")
    model = AiModelMetadata(
        name="MyModel",
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
        datasets=[
            DatasetReference(role="trainedOn", metadata=DatasetMetadata(name="Wiki"))
        ],
    )
    doc = DocumentModel(project=project, creation=creation, ai_models=[model])

    exporter = build_doc(doc)
    data = json.loads(exporter.to_json())
    graph = data["@graph"]
    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")
    conformance = spdx_doc.get("profileConformance", [])
    assert any("dataset" in str(c) for c in conformance)
    assert any("ai" in str(c) for c in conformance)


def test_document_no_dataset_profile_when_no_datasets() -> None:
    project = ProjectMetadata(name="myproject2", version="1.0")
    creation = CreationMetadata(creator_name="Test")
    model = AiModelMetadata(
        name="MyModel",
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
    )
    doc = DocumentModel(project=project, creation=creation, ai_models=[model])

    exporter = build_doc(doc)
    data = json.loads(exporter.to_json())
    graph = data["@graph"]
    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")
    conformance = spdx_doc.get("profileConformance", [])
    assert not any("dataset" in str(c) for c in conformance)
