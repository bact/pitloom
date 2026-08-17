# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``add_datasets_for_model``'s relationship-type mapping, and an
integration test that dataset-profile conformance is declared correctly
during full document assembly.

See also: test_spdx3_dataset_fields.py -- this module's sibling, split
from the original test_spdx3_dataset.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json

from pitloom.assemble.spdx3.dataset import add_datasets_for_model
from pitloom.assemble.spdx3.document import build as build_doc
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.document import DocumentModel
from pitloom.core.models import _clear_doc_counters, generate_spdx_id
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci, _make_meta


def _make_exporter() -> Spdx3JsonExporter:
    return Spdx3JsonExporter()


# ---------------------------------------------------------------------------
# add_datasets_for_model -- relationship types
# ---------------------------------------------------------------------------


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
    creation = CreationMetadata(creators=[Creator(name="Test")])
    model = AiModelMetadata(
        name="MyModel",
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
        datasets=[
            DatasetReference(role="trainedOn", metadata=DatasetMetadata(name="Wiki"))
        ],
    )
    doc = DocumentModel(project=project, creation_metadata=creation, ai_models=[model])

    exporter = build_doc(doc)
    data = json.loads(exporter.to_json())
    graph = data["@graph"]
    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")
    conformance = spdx_doc.get("profileConformance", [])
    assert any("dataset" in str(c) for c in conformance)
    assert any("ai" in str(c) for c in conformance)


def test_document_no_dataset_profile_when_no_datasets() -> None:
    project = ProjectMetadata(name="myproject2", version="1.0")
    creation = CreationMetadata(creators=[Creator(name="Test")])
    model = AiModelMetadata(
        name="MyModel",
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
    )
    doc = DocumentModel(project=project, creation_metadata=creation, ai_models=[model])

    exporter = build_doc(doc)
    data = json.loads(exporter.to_json())
    graph = data["@graph"]
    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")
    conformance = spdx_doc.get("profileConformance", [])
    assert not any("dataset" in str(c) for c in conformance)
