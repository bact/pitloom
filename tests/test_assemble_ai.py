# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for pitloom.assemble.spdx3.ai.

Complements the full-pipeline graph assertions in test_generator.py etc.
with tests that call these functions directly and assert on their
return values, so a regression here fails in this file instead of
surfacing as a generic "wrong graph shape" failure somewhere else.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from datetime import datetime, timezone

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.ai import (
    _add_base_model_lineage,
    _build_ai_package,
    _LineageContext,
    _lookup_ai_model_entity,
    _should_preserve_metadata,
    _source_metadata_blob,
)
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.ids import EntityEntry, IdRegistry

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


# ---------------------------------------------------------------------------
# _should_preserve_metadata
# ---------------------------------------------------------------------------


def test_should_preserve_metadata_always() -> None:
    model = AiModelMetadata()
    assert _should_preserve_metadata(model, {}, "always") is True


def test_should_preserve_metadata_never() -> None:
    model = AiModelMetadata()
    assert _should_preserve_metadata(model, {}, "never") is False


def test_should_preserve_metadata_auto_not_shipped() -> None:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(file_path_relative="model.gguf")
    )
    assert _should_preserve_metadata(model, {}, "auto") is True


def test_should_preserve_metadata_auto_shipped() -> None:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(file_path_relative="model.gguf")
    )
    file_spdx_ids = {"model.gguf": "urn:doc#File-model"}
    assert _should_preserve_metadata(model, file_spdx_ids, "auto") is False


def test_should_preserve_metadata_auto_no_relative_path() -> None:
    model = AiModelMetadata()
    assert _should_preserve_metadata(model, {}, "auto") is True


# ---------------------------------------------------------------------------
# _source_metadata_blob
# ---------------------------------------------------------------------------


def test_source_metadata_blob_prefers_raw_metadata() -> None:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.GGUF),
        raw_metadata={"general.name": "test-model"},
        properties={"ignored": "yes"},
    )
    fmt, blob = _source_metadata_blob(model)
    assert fmt == "gguf"
    assert blob == {"general.name": "test-model"}


def test_source_metadata_blob_falls_back_to_properties_and_extras() -> None:
    model = AiModelMetadata(
        properties={"p": "1"},
        extra_data={"hf.sha": "abc123"},
        extra_lists={"hf.tags": ["a", "b"]},
    )
    fmt, blob = _source_metadata_blob(model)
    assert fmt == "huggingface"
    assert blob == {"p": "1", "hf.sha": "abc123", "hf.tags": ["a", "b"]}


def test_source_metadata_blob_unknown_format_no_extras_stays_unknown() -> None:
    model = AiModelMetadata(properties={"p": "1"})
    fmt, _blob = _source_metadata_blob(model)
    assert fmt == "unknown"


# ---------------------------------------------------------------------------
# _lookup_ai_model_entity
# ---------------------------------------------------------------------------


def test_lookup_ai_model_entity_no_registry_returns_none() -> None:
    model = AiModelMetadata(name="mymodel")
    assert _lookup_ai_model_entity(model, None) is None


def test_lookup_ai_model_entity_not_found_returns_none() -> None:
    registry = IdRegistry(namespace="urn:doc")
    model = AiModelMetadata(name="unregistered")
    assert _lookup_ai_model_entity(model, registry) is None


def test_lookup_ai_model_entity_found_by_name() -> None:
    registry = IdRegistry(
        namespace="urn:doc",
        entities={
            "mymodel": EntityEntry(type="ai_AIPackage", spdx_id="urn:doc#AIPackage-1")
        },
    )
    model = AiModelMetadata(name="mymodel")
    assert _lookup_ai_model_entity(model, registry) == "urn:doc#AIPackage-1"


def test_lookup_ai_model_entity_found_by_physical_path() -> None:
    registry = IdRegistry(
        namespace="urn:doc",
        entities={
            "src/model.gguf": EntityEntry(
                type="ai_AIPackage", spdx_id="urn:doc#AIPackage-2"
            )
        },
    )
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(physical_path="src/model.gguf")
    )
    assert _lookup_ai_model_entity(model, registry) == "urn:doc#AIPackage-2"


def test_lookup_ai_model_entity_found_by_file_stem() -> None:
    registry = IdRegistry(
        namespace="urn:doc",
        entities={
            "model": EntityEntry(type="ai_AIPackage", spdx_id="urn:doc#AIPackage-3")
        },
    )
    model = AiModelMetadata(format_info=AiModelFormatInfo(file_name="model.gguf"))
    assert _lookup_ai_model_entity(model, registry) == "urn:doc#AIPackage-3"


# ---------------------------------------------------------------------------
# _build_ai_package
# ---------------------------------------------------------------------------


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
    """One comprehensive pass over every optional field _build_ai_package
    maps, since the full-pipeline tests only ever exercise a handful of
    these at a time -- this is what actually closes the coverage gap on
    the field-by-field construction logic."""
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
    model.usage.domains = ["NLP", "text generation"]  # overlaps "NLP" -- dedup check
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
    # domain + usage.domains merged and de-duplicated, order preserved.
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


# ---------------------------------------------------------------------------
# _add_base_model_lineage
# ---------------------------------------------------------------------------


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
    assert len(exporter.object_set.objects) == 1  # only pkg itself, no new elements


def test_add_base_model_lineage_creates_stub_package() -> None:
    """Regression test: base_model set without base_model_relation (e.g.
    a model card's frontmatter has base_model but the Hub API's computed
    tags never supplied a relation) used to crash -- the underlying SPDX
    3 binding rejects an explicit `comment=None`, only accepting a
    field left unset entirely. Caught by this direct unit test; no
    full-pipeline test exercised this combination before."""
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

    # An ai_AIPackage for the base model already exists in the document
    # (e.g. it's also a top-level model in this same project scan).
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
    # No second/duplicate base package minted -- the existing one is reused.
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
    # Second call reuses ctx.cache instead of scanning/minting again.
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
