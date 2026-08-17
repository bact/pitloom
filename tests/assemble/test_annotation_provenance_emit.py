# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``emit_provenance``: format/detail dispatch, encoder
pluggability, and the high-signal filter used at minimal detail.

See also: test_annotation_provenance_core.py,
test_annotation_provenance_annotations.py -- this module's siblings, split
from the original test_annotation_provenance.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    build_provenance_annotation,
    emit_provenance,
    filter_high_signal,
    resolve_encoder,
)
from pitloom.core.models import _clear_doc_counters
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci, _make_subject

# ---------------------------------------------------------------------------
# emit_provenance
# ---------------------------------------------------------------------------


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
            provenance_config=ProvenanceConfig(format="bogus-value"),
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
            provenance_config=ProvenanceConfig(detail="verbose"),
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
        provenance_config=ProvenanceConfig(format="both", detail="full"),
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
        provenance_config=ProvenanceConfig(format="annotation", detail="full"),
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
        provenance_config=ProvenanceConfig(format="comment", detail="full"),
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
        provenance_config=ProvenanceConfig(format="both"),
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
        provenance_config=ProvenanceConfig(format="comment", detail="full"),
    )

    assert pkg.comment
    assert pkg.comment.startswith("Known biases: overrepresents English text\n")
    assert "Metadata provenance: name: " in pkg.comment


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


def test_filter_high_signal_empty_dict_returns_empty_dict() -> None:
    """Boundary case: nothing to filter, nothing raises."""
    assert filter_high_signal({}) == {}


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
        provenance_config=ProvenanceConfig(format="annotation", detail="minimal"),
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
        provenance_config=ProvenanceConfig(format="both", detail="minimal"),
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
        provenance_config=ProvenanceConfig(format="annotation", detail="full"),
    )
    annotations = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Annotation)
    ]
    assert annotations[0].statement is not None
    statement = json.loads(annotations[0].statement)
    assert set(statement["fields"]) == {"name", "version"}
