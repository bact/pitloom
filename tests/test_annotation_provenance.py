# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 Core/Annotation-based metadata provenance."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import (
    ARTIFACT_METADATA_SCHEMA_URL,
    DEFAULT_SCHEMA_ID,
    UNIFICATION_SCHEMA_URL,
    PitloomV1Encoder,
    ProvenanceEncoder,
    build_provenance_annotation,
    build_provenance_comment,
    build_source_metadata_annotation,
    build_unification_annotation,
    emit_provenance,
    filter_high_signal,
    parse_provenance_value,
    resolve_encoder,
)
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

_DOC_NAME = "testproject"
_DOC_UUID = compute_doc_uuid("testproject", "1.0", [])


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
# parse_provenance_value
# ---------------------------------------------------------------------------


def test_parse_provenance_value_source_and_field() -> None:
    parsed = parse_provenance_value("Source: pyproject.toml | Field: project.name")
    assert parsed == {"source": "pyproject.toml", "location": "project.name"}


def test_parse_provenance_value_extra_field_path() -> None:
    parsed = parse_provenance_value("Source: model.pt2 | Field: extra/name")
    assert parsed == {"source": "model.pt2", "location": "extra/name"}


def test_parse_provenance_value_with_method() -> None:
    parsed = parse_provenance_value(
        "Source: src/pkg/__about__.py | Method: dynamic_extraction"
    )
    assert parsed == {"source": "src/pkg/__about__.py", "method": "dynamic_extraction"}


def test_parse_provenance_value_note_only() -> None:
    parsed = parse_provenance_value(
        "Phantom dependency bundled in distribution artifact"
    )
    assert parsed == {"note": "Phantom dependency bundled in distribution artifact"}


def test_parse_provenance_value_empty_string() -> None:
    assert not parse_provenance_value("")


def test_parse_provenance_value_unknown_key_passthrough() -> None:
    parsed = parse_provenance_value("Package: requests")
    assert parsed == {"package": "requests"}


# ---------------------------------------------------------------------------
# PitloomV1Encoder
# ---------------------------------------------------------------------------


def test_pitloom_v1_encoder_is_deterministic() -> None:
    encoder = PitloomV1Encoder()
    provenance = {
        "name": "Source: pyproject.toml | Field: project.name",
        "license": "Source: pyproject.toml | Field: project.license",
    }
    first = encoder.encode(provenance)
    second = encoder.encode(provenance)
    assert first == second


def test_pitloom_v1_encoder_produces_valid_json_with_schema_marker() -> None:
    encoder = PitloomV1Encoder()
    body = encoder.encode({"name": "Source: pyproject.toml | Field: project.name"})
    parsed = json.loads(body)
    assert parsed["schema"] == "https://pitloom.dev/provenance/1"
    assert parsed["fields"]["name"] == {
        "source": "pyproject.toml",
        "location": "project.name",
    }


def test_pitloom_v1_encoder_content_type() -> None:
    assert PitloomV1Encoder.content_type == "application/json"
    assert PitloomV1Encoder.schema_id == "pitloom/1"


# ---------------------------------------------------------------------------
# resolve_encoder
# ---------------------------------------------------------------------------


def test_resolve_encoder_default() -> None:
    encoder = resolve_encoder()
    assert encoder.schema_id == DEFAULT_SCHEMA_ID


def test_resolve_encoder_explicit_known_id() -> None:
    encoder = resolve_encoder("pitloom/1")
    assert isinstance(encoder, PitloomV1Encoder)


def test_resolve_encoder_unknown_id_raises_with_known_list() -> None:
    with pytest.raises(ValueError, match="pitloom/1"):
        resolve_encoder("not-a-real-schema")


def test_resolve_encoder_empty_string_raises_rather_than_defaulting() -> None:
    """An explicit empty schema id is an invalid id, not "use the default" --
    only omitting the argument (None) should select DEFAULT_SCHEMA_ID."""
    with pytest.raises(ValueError, match="pitloom/1"):
        resolve_encoder("")


# ---------------------------------------------------------------------------
# build_provenance_annotation
# ---------------------------------------------------------------------------


def test_build_provenance_annotation_returns_none_for_empty_provenance() -> None:
    ci = _make_ci()
    ann = build_provenance_annotation(
        subject_spdx_id="urn:example#Package-1",
        provenance={},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
    )
    assert ann is None


def test_build_provenance_annotation_fields() -> None:
    _clear_doc_counters(_DOC_UUID)
    ci = _make_ci()
    ann = build_provenance_annotation(
        subject_spdx_id="urn:example#Package-1",
        provenance={"name": "Source: pyproject.toml | Field: project.name"},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
    )
    assert ann is not None
    assert ann.annotationType == spdx3.AnnotationType.other
    assert ann.contentType == "application/json"
    assert ann.subject == "urn:example#Package-1"
    assert ann.spdxId is not None
    assert ann.creationInfo is ci
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["fields"]["name"]["source"] == "pyproject.toml"


def test_build_provenance_annotation_uses_given_encoder() -> None:
    """A caller-supplied encoder overrides the registered default -- this is
    the seam a future external schema (e.g. PROV-O) plugs into without any
    change to build_provenance_annotation or its callers."""

    # pylint: disable=too-few-public-methods
    class _StubEncoder:
        schema_id = "stub/1"
        content_type = "text/plain"

        def encode(self, provenance: dict[str, str]) -> str:
            return "|".join(f"{k}={v}" for k, v in sorted(provenance.items()))

    _clear_doc_counters(_DOC_UUID)
    ci = _make_ci()
    ann = build_provenance_annotation(
        subject_spdx_id="urn:example#Package-1",
        provenance={"name": "x", "license": "y"},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        encoder=_StubEncoder(),
    )
    assert ann is not None
    assert ann.contentType == "text/plain"
    assert ann.statement == "license=y|name=x"


# ---------------------------------------------------------------------------
# build_provenance_comment
# ---------------------------------------------------------------------------


def test_build_provenance_comment_matches_legacy_format() -> None:
    comment = build_provenance_comment(
        {"name": "Source: pyproject.toml | Field: project.name"}
    )
    assert (
        comment
        == "Metadata provenance: name: Source: pyproject.toml | Field: project.name"
    )


def test_build_provenance_comment_none_for_empty() -> None:
    assert build_provenance_comment({}) is None


# ---------------------------------------------------------------------------
# emit_provenance
# ---------------------------------------------------------------------------


def _make_subject(
    exporter: Spdx3JsonExporter, ci: spdx3.CreationInfo
) -> spdx3.software_Package:
    pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID),
        name="dep",
        creationInfo=ci,
    )
    exporter.add_package(pkg)
    return pkg


def test_emit_provenance_unknown_format_raises() -> None:
    """An unrecognized provenance_format must fail loudly, not silently drop
    the provenance (neither branch in emit_provenance would otherwise fire)."""
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    with pytest.raises(ValueError, match="bogus-value"):
        emit_provenance(
            subject=pkg,
            provenance={"name": "Source: pyproject.toml | Field: project.name"},
            creation_info=ci,
            doc_name=_DOC_NAME,
            doc_uuid=_DOC_UUID,
            exporter=exporter,
            provenance_format="bogus-value",
        )
    # Nothing partially applied.
    assert pkg.comment is None
    assert not any(isinstance(o, spdx3.Annotation) for o in exporter.object_set.objects)


def test_emit_provenance_unknown_detail_raises() -> None:
    """An unrecognized provenance_detail must fail loudly, not silently behave
    as 'full'."""
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    with pytest.raises(ValueError, match="verbose"):
        emit_provenance(
            subject=pkg,
            provenance={"name": "Source: pyproject.toml | Field: project.name"},
            creation_info=ci,
            doc_name=_DOC_NAME,
            doc_uuid=_DOC_UUID,
            exporter=exporter,
            provenance_detail="verbose",
        )
    assert pkg.comment is None
    assert not any(isinstance(o, spdx3.Annotation) for o in exporter.object_set.objects)


def test_emit_provenance_both_sets_comment_and_annotation() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    emit_provenance(
        subject=pkg,
        provenance={"name": "Source: pyproject.toml | Field: project.name"},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        exporter=exporter,
        provenance_format="both",
        provenance_detail="full",
    )

    assert pkg.comment is not None
    assert "Metadata provenance" in pkg.comment
    annotations = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Annotation)
    ]
    assert len(annotations) == 1
    assert annotations[0].subject == require_spdx_id(pkg)


def test_emit_provenance_annotation_only_leaves_comment_unset() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    emit_provenance(
        subject=pkg,
        provenance={"name": "Source: pyproject.toml | Field: project.name"},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        exporter=exporter,
        provenance_format="annotation",
        provenance_detail="full",
    )

    assert pkg.comment is None
    annotations = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Annotation)
    ]
    assert len(annotations) == 1


def test_emit_provenance_comment_only_creates_no_annotation() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    emit_provenance(
        subject=pkg,
        provenance={"name": "Source: pyproject.toml | Field: project.name"},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        exporter=exporter,
        provenance_format="comment",
        provenance_detail="full",
    )

    assert pkg.comment is not None
    annotations = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Annotation)
    ]
    assert len(annotations) == 0


def test_emit_provenance_empty_provenance_is_a_noop() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    emit_provenance(
        subject=pkg,
        provenance={},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        exporter=exporter,
        provenance_format="both",
    )

    assert pkg.comment is None
    annotations = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Annotation)
    ]
    assert len(annotations) == 0


def test_emit_provenance_appends_to_existing_comment() -> None:
    """A subject that already carries a comment (e.g. an ai_AIPackage with
    known_biases) keeps that text, with the provenance line appended."""
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)
    pkg.comment = "Known biases: overrepresents English text"

    emit_provenance(
        subject=pkg,
        provenance={"name": "Source: pyproject.toml | Field: project.name"},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        exporter=exporter,
        provenance_format="comment",
        provenance_detail="full",
    )

    assert pkg.comment
    assert pkg.comment.startswith("Known biases: overrepresents English text\n")
    assert "Metadata provenance" in pkg.comment


# ---------------------------------------------------------------------------
# Pluggability: swapping the encoder changes contentType/statement without
# touching Annotation wiring (acceptance criterion, see
# working-docs/implementation/annotation-provenance.md §9).
# ---------------------------------------------------------------------------


def test_swapping_encoder_changes_output_without_changing_wiring() -> None:
    # pylint: disable=too-few-public-methods
    class _FutureSchemaEncoder:
        schema_id = "future-schema/1"
        content_type = "application/ld+json"

        def encode(self, provenance: dict[str, str]) -> str:
            return json.dumps({"@context": "future", "data": provenance})

    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)
    provenance = {"name": "Source: pyproject.toml | Field: project.name"}

    default_encoder: ProvenanceEncoder = resolve_encoder()
    default_ann = build_provenance_annotation(
        subject_spdx_id=require_spdx_id(pkg),
        provenance=provenance,
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        encoder=default_encoder,
    )

    _clear_doc_counters(_DOC_UUID + "-b")
    future_ann = build_provenance_annotation(
        subject_spdx_id=require_spdx_id(pkg),
        provenance=provenance,
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID + "-b",
        encoder=_FutureSchemaEncoder(),
    )

    assert default_ann is not None
    assert future_ann is not None
    assert default_ann.contentType == "application/json"
    assert future_ann.contentType == "application/ld+json"
    assert default_ann.statement != future_ann.statement
    # Same subject/annotationType/creationInfo wiring regardless of encoder.
    assert default_ann.subject == future_ann.subject == require_spdx_id(pkg)
    assert (
        default_ann.annotationType
        == future_ann.annotationType
        == spdx3.AnnotationType.other
    )
    assert default_ann.creationInfo is future_ann.creationInfo is ci


# ---------------------------------------------------------------------------
# High-signal filter (minimal detail boundary)
# ---------------------------------------------------------------------------


def test_filter_high_signal_drops_transparent_manifest_reads() -> None:
    prov = {
        "name": "Source: pyproject.toml | Field: project.name",
        "version": "Source: pyproject.toml | Field: project.version",
        "description": "Source: Hugging Face Hub | Field: model card",
    }
    assert filter_high_signal(prov) == {}


def test_filter_high_signal_keeps_inferred_and_detected() -> None:
    prov = {
        "name": "Source: pyproject.toml | Field: project.name",
        "copyright_text": "Source: Pitloom generator | Method: inferred_from_authors",
        "license": "Source: LICENSE | Method: licenseid_detection",
    }
    kept = filter_high_signal(prov)
    assert set(kept) == {"copyright_text", "license"}


def test_filter_high_signal_keeps_nonmanifest_sources() -> None:
    prov = {
        "declared_constraint": "requests>=2.28.0",
        "architecture": "Source: model.safetensors | Field: __metadata__",
        "package": "Source: pipdeptree (deployed environment)",
        "note": "Phantom dependency bundled in distribution artifact",
    }
    assert filter_high_signal(prov) == prov


# ---------------------------------------------------------------------------
# emit_provenance -- minimal vs full detail
# ---------------------------------------------------------------------------


def test_emit_provenance_minimal_filters_trivial_fields() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    emit_provenance(
        subject=pkg,
        provenance={
            "name": "Source: pyproject.toml | Field: project.name",
            "copyright_text": (
                "Source: Pitloom generator | Method: inferred_from_authors"
            ),
        },
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        exporter=exporter,
        provenance_format="annotation",
        provenance_detail="minimal",
    )
    annotations = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Annotation)
    ]
    assert len(annotations) == 1
    assert annotations[0].statement is not None
    statement = json.loads(annotations[0].statement)
    assert set(statement["fields"]) == {"copyright_text"}


def test_emit_provenance_minimal_all_trivial_emits_nothing() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    emit_provenance(
        subject=pkg,
        provenance={"name": "Source: pyproject.toml | Field: project.name"},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        exporter=exporter,
        provenance_format="both",
        provenance_detail="minimal",
    )
    assert pkg.comment is None
    assert not any(isinstance(o, spdx3.Annotation) for o in exporter.object_set.objects)


def test_emit_provenance_full_keeps_all_fields() -> None:
    _clear_doc_counters(_DOC_UUID)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    pkg = _make_subject(exporter, ci)

    emit_provenance(
        subject=pkg,
        provenance={
            "name": "Source: pyproject.toml | Field: project.name",
            "version": "Source: pyproject.toml | Field: project.version",
        },
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
        exporter=exporter,
        provenance_format="annotation",
        provenance_detail="full",
    )
    annotations = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Annotation)
    ]
    assert annotations[0].statement is not None
    statement = json.loads(annotations[0].statement)
    assert set(statement["fields"]) == {"name", "version"}


# ---------------------------------------------------------------------------
# build_unification_annotation (A1)
# ---------------------------------------------------------------------------


def test_build_unification_annotation_shape_and_determinism() -> None:
    ci = _make_ci()
    ann = build_unification_annotation(
        subject_spdx_id="urn:doc#File-1",
        criterion="sha256",
        unified_ids=["urn:doc#File-9", "urn:doc#File-4"],
        fragments=["b/frag.json", "a/frag.json"],
        creation_info=ci,
        annotation_spdx_id="urn:doc#Annotation-unification-1",
    )
    assert ann.spdxId == "urn:doc#Annotation-unification-1"
    assert ann.contentType == "application/json"
    assert ann.annotationType == spdx3.AnnotationType.other
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["schema"] == UNIFICATION_SCHEMA_URL
    assert statement["event"] == "unification"
    assert statement["criterion"] == "sha256"
    # Lists are sorted for byte-stability.
    assert statement["unified"] == ["urn:doc#File-4", "urn:doc#File-9"]
    assert statement["fragments"] == ["a/frag.json", "b/frag.json"]


# ---------------------------------------------------------------------------
# build_source_metadata_annotation (P1)
# ---------------------------------------------------------------------------


def test_build_source_metadata_annotation_embeds_verbatim() -> None:
    _clear_doc_counters(_DOC_UUID)
    ci = _make_ci()
    ann = build_source_metadata_annotation(
        subject_spdx_id="urn:doc#ai_AIPackage-1",
        source_format="gguf",
        metadata={"general.architecture": "llama", "block_count": 32, "raw": b"\x00"},
        creation_info=ci,
        doc_name=_DOC_NAME,
        doc_uuid=_DOC_UUID,
    )
    assert ann is not None
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["schema"] == ARTIFACT_METADATA_SCHEMA_URL
    assert statement["format"] == "gguf"
    # native value types preserved; bytes base64-encoded.
    assert statement["metadata"]["block_count"] == 32
    assert statement["metadata"]["general.architecture"] == "llama"
    assert statement["metadata"]["raw"] == "AA=="


def test_build_source_metadata_annotation_empty_returns_none() -> None:
    ci = _make_ci()
    assert (
        build_source_metadata_annotation(
            "urn:doc#ai_AIPackage-1", "gguf", {}, ci, _DOC_NAME, _DOC_UUID
        )
        is None
    )


def test_build_source_metadata_annotation_nan_and_infinity_are_valid_json() -> None:
    """A malformed/adversarial binary model can produce NaN/Infinity float
    metadata. Plain ``json.dumps`` serializes those as the non-standard
    ``NaN``/``Infinity``/``-Infinity`` tokens (RFC 8259 forbids them) --
    ``default=`` is never consulted since floats are natively serializable.
    The statement must instead be valid, strict JSON."""
    ci = _make_ci()
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        {"nan": float("nan"), "pos_inf": float("inf"), "neg_inf": float("-inf")},
        ci,
        _DOC_NAME,
        _DOC_UUID,
    )
    assert ann is not None
    assert ann.statement is not None
    assert "NaN" not in ann.statement.replace('"NaN"', "")
    assert "Infinity" not in ann.statement.replace('"Infinity"', "").replace(
        '"-Infinity"', ""
    )
    statement = json.loads(ann.statement)  # must not raise
    assert statement["metadata"] == {
        "nan": "NaN",
        "pos_inf": "Infinity",
        "neg_inf": "-Infinity",
    }


def test_build_source_metadata_annotation_set_is_deterministic() -> None:
    """A ``set`` has no stable iteration order across processes
    (``PYTHONHASHSEED`` randomization) -- it must be normalized to a sorted
    list, not left to a generic ``str()`` fallback, to preserve the
    byte-stable-SBOM guarantee."""
    ci = _make_ci()
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        {"tags": {"zebra", "alpha", "gamma"}},
        ci,
        _DOC_NAME,
        _DOC_UUID,
    )
    assert ann is not None
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["metadata"]["tags"] == ["alpha", "gamma", "zebra"]


def test_sanitize_for_json_orders_unsortable_elements_deterministically() -> None:
    """``sorted()`` on raw set elements can silently "succeed" without
    raising ``TypeError`` yet still be non-deterministic -- e.g. `frozenset`
    ordering (`<` means "is a proper subset of", not a total order) depends
    on the input set's own iteration order, which is itself
    ``PYTHONHASHSEED``-dependent. Ordering by canonical JSON form instead of
    Python's native `<` must stay stable regardless of insertion order."""
    # pylint: disable=import-outside-toplevel
    from pitloom.assemble.spdx3.provenance import _sanitize_for_json

    set_a = {frozenset({1, 2}), frozenset({3, 4}), frozenset({5})}
    set_b = {frozenset({5}), frozenset({3, 4}), frozenset({1, 2})}
    assert _sanitize_for_json(set_a) == _sanitize_for_json(set_b)
