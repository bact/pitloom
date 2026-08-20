# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for pitloom.assemble.spdx3.ai package and lineage building.

See also: :mod:`tests.assemble.test_assemble_ai_metadata`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.ai import (
    _add_base_model_lineage,
    _build_ai_package,
    _LineageContext,
)
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

_DOC_NAME = "testproject"
_DOC_UUID = "00000000-0000-0000-0000-000000000000"


def _make_ci() -> spdx3.CreationInfo:
    ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    person = spdx3.Person(
        spdxId=generate_spdx_id("Person", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID),
        name="Test",
        creationInfo=ci,
    )
    ci.createdBy = [require_spdx_id(person)]
    return ci


def test_build_ai_package_minimal() -> None:
    ci = _make_ci()
    model = AiModelMetadata(name="tiny-model")
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    assert pkg.name == "tiny-model"
    assert pkg.software_packageVersion is None
    assert not pkg.ai_typeOfModel


def test_build_ai_package_name_falls_back_to_format() -> None:
    ci = _make_ci()
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX)
    )
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    assert pkg.name == "onnx"


def test_build_ai_package_entity_spdx_id_override() -> None:
    ci = _make_ci()
    model = AiModelMetadata(name="tiny-model")
    pkg = _build_ai_package(
        model, ci, _DOC_NAME, _DOC_UUID, entity_spdx_id="urn:doc#AIPackage-pinned"
    )
    assert pkg.spdxId == "urn:doc#AIPackage-pinned"


def test_build_ai_package_all_optional_fields() -> None:
    """One comprehensive pass over every optional field _build_ai_package maps."""
    ci = _make_ci()
    model = AiModelMetadata(
        name="full-model",
        version="1.2.3",
        description="A model with everything set.",
        type_of_model="transformer",
        architecture="llama",
        quantization="Q4_K_M",
        hyperparameters={"num_layers": 12, "hidden_size": 768},
        domain=["NLP"],
        inputs=[{"name": "input_ids", "shape": [1, 128]}],
        outputs=[{"name": "logits", "shape": [1, 128, 32000]}],
    )
    model.usage.domains = ["NLP", "text generation"]
    model.usage.limitations = ["English only", "small context window"]
    model.usage.safety_risk_assessment = "medium"
    model.usage.intended_use = ["chatbot"]
    model.usage.unintended_use = ["medical diagnosis"]
    model.usage.known_biases = ["training data skew"]

    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)

    assert pkg.software_packageVersion == "1.2.3"
    assert pkg.description == "A model with everything set."
    assert pkg.ai_typeOfModel == ["transformer", "llama"]
    hyperparameters = [
        entry
        for entry in pkg.ai_hyperparameter
        if isinstance(entry, spdx3.DictionaryEntry)
    ]
    assert len(hyperparameters) == len(pkg.ai_hyperparameter)
    assert hyperparameters[0].key == "quantization"
    assert hyperparameters[0].value == "Q4_K_M"
    hp_keys = {entry.key for entry in hyperparameters}
    assert hp_keys == {"quantization", "num_layers", "hidden_size"}
    assert pkg.ai_domain == ["NLP", "text generation"]
    assert pkg.ai_limitation == "English only; small context window"
    assert pkg.ai_safetyRiskAssessment == spdx3.ai_SafetyRiskAssessmentType.medium
    assert pkg.ai_informationAboutApplication is not None
    assert "chatbot" in pkg.ai_informationAboutApplication
    assert "medical diagnosis" in pkg.ai_informationAboutApplication
    assert pkg.comment == "Known biases: training data skew"


def test_build_ai_package_invalid_safety_risk_ignored() -> None:
    ci = _make_ci()
    model = AiModelMetadata(name="risky-model")
    model.usage.safety_risk_assessment = "not-a-real-risk-level"
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    assert pkg.ai_safetyRiskAssessment is None


def test_build_ai_package_external_identifiers_and_refs() -> None:
    ci = _make_ci()
    model = AiModelMetadata(
        name="cited-model",
        doi="10.1234/example",
        arxiv_ids=["2401.00001"],
        url="https://huggingface.co/org/cited-model",
    )
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    identifier = pkg.externalIdentifier[0]
    assert isinstance(identifier, spdx3.ExternalIdentifier)
    assert identifier.identifier == "10.1234/example"
    ref_0, ref_1 = pkg.externalRef[0], pkg.externalRef[1]
    assert isinstance(ref_0, spdx3.ExternalRef)
    assert isinstance(ref_1, spdx3.ExternalRef)
    assert ref_0.comment == "arXiv:2401.00001"
    assert ref_1.comment == "Model page URL"


def test_add_base_model_lineage_no_base_model_is_noop() -> None:
    ci = _make_ci()
    exporter = Spdx3JsonExporter()
    model = AiModelMetadata(name="standalone")
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    exporter.add_package(pkg)
    ctx = _LineageContext(
        creation_info=ci, doc_name=_DOC_NAME, doc_uuid=_DOC_UUID, exporter=exporter
    )
    _add_base_model_lineage(pkg, model, ctx)
    assert len(exporter.object_set.objects) == 1


def test_add_base_model_lineage_creates_stub_package() -> None:
    ci = _make_ci()
    exporter = Spdx3JsonExporter()
    model = AiModelMetadata(name="finetuned-model", base_model="org/base-model")
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    exporter.add_package(pkg)
    ctx = _LineageContext(
        creation_info=ci, doc_name=_DOC_NAME, doc_uuid=_DOC_UUID, exporter=exporter
    )
    _add_base_model_lineage(pkg, model, ctx)

    relationships = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.Relationship)
    ]
    assert relationships[0].comment is None

    base_packages = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.ai_AIPackage) and obj.name == "base-model"
    ]
    assert len(base_packages) == 1
    base_ref = base_packages[0].externalRef[0]
    assert isinstance(base_ref, spdx3.ExternalRef)
    assert base_ref.locator == ["https://huggingface.co/org/base-model"]
    assert len(relationships) == 1
    assert relationships[0].relationshipType == spdx3.RelationshipType.descendantOf


def test_add_base_model_lineage_reuses_existing_package() -> None:
    ci = _make_ci()
    exporter = Spdx3JsonExporter()

    existing_base = spdx3.ai_AIPackage(
        spdxId=generate_spdx_id(
            "AIPackage-base-model", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID
        ),
        name="base-model",
        creationInfo=ci,
    )
    exporter.add_package(existing_base)

    model = AiModelMetadata(name="finetuned-model", base_model="org/base-model")
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    exporter.add_package(pkg)
    ctx = _LineageContext(
        creation_info=ci, doc_name=_DOC_NAME, doc_uuid=_DOC_UUID, exporter=exporter
    )
    _add_base_model_lineage(pkg, model, ctx)

    base_packages = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.ai_AIPackage) and obj.name == "base-model"
    ]
    assert len(base_packages) == 1
    relationships = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.Relationship)
    ]
    assert relationships[0].to == [require_spdx_id(existing_base)]


def test_add_base_model_lineage_caches_across_calls() -> None:
    ci = _make_ci()
    exporter = Spdx3JsonExporter()
    ctx = _LineageContext(
        creation_info=ci, doc_name=_DOC_NAME, doc_uuid=_DOC_UUID, exporter=exporter
    )

    model_a = AiModelMetadata(name="model-a", base_model="org/shared-base")
    pkg_a = _build_ai_package(model_a, ci, _DOC_NAME, _DOC_UUID)
    exporter.add_package(pkg_a)
    _add_base_model_lineage(pkg_a, model_a, ctx)

    model_b = AiModelMetadata(name="model-b", base_model="org/shared-base")
    pkg_b = _build_ai_package(model_b, ci, _DOC_NAME, _DOC_UUID)
    exporter.add_package(pkg_b)
    _add_base_model_lineage(pkg_b, model_b, ctx)

    base_packages = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.ai_AIPackage) and obj.name == "shared-base"
    ]
    assert len(base_packages) == 1


def test_add_base_model_lineage_relation_comment() -> None:
    ci = _make_ci()
    exporter = Spdx3JsonExporter()
    model = AiModelMetadata(
        name="quantized-model",
        base_model="org/base-model",
        base_model_relation="quantized",
    )
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    exporter.add_package(pkg)
    ctx = _LineageContext(
        creation_info=ci, doc_name=_DOC_NAME, doc_uuid=_DOC_UUID, exporter=exporter
    )
    _add_base_model_lineage(pkg, model, ctx)

    relationships = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.Relationship)
    ]
    assert relationships[0].comment == "base_model_relation:quantized"


def test_add_base_model_lineage_no_relationship_when_build_relationship_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If build_relationship() ever returns None (e.g. from_id somehow
    unset), _add_base_model_lineage() must not add a Relationship element
    -- covers the "skip, no relationship built" exit branch."""
    ci = _make_ci()
    exporter = Spdx3JsonExporter()
    model = AiModelMetadata(name="finetuned-model", base_model="org/base-model")
    pkg = _build_ai_package(model, ci, _DOC_NAME, _DOC_UUID)
    exporter.add_package(pkg)
    ctx = _LineageContext(
        creation_info=ci, doc_name=_DOC_NAME, doc_uuid=_DOC_UUID, exporter=exporter
    )
    monkeypatch.setattr(
        "pitloom.assemble.spdx3._ai_package.build_relationship",
        lambda *args, **kwargs: None,
    )
    _add_base_model_lineage(pkg, model, ctx)

    relationships = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.Relationship)
    ]
    assert relationships == []
