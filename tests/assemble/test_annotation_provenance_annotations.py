# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the structured provenance Annotation builders: unification
(A1), conflict (G2), enrichment (E1/E2), and source-metadata (P1).

See also: test_annotation_provenance_core.py,
test_annotation_provenance_emit.py -- this module's siblings, split from
the original test_annotation_provenance.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import (
    ARTIFACT_METADATA_SCHEMA_URL,
    CONFLICT_SCHEMA_URL,
    ENRICHMENT_SCHEMA_URL,
    UNIFICATION_SCHEMA_URL,
    ConflictCandidate,
    EnrichedFieldEntry,
    build_conflict_annotation,
    build_enrichment_annotation,
    build_source_metadata_annotation,
    build_unification_annotation,
)
from pitloom.core.models import _clear_doc_counters

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci

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
    assert statement["kind"] == "unification"
    assert statement["criterion"] == "sha256"
    # Lists are sorted for byte-stability.
    assert statement["unified"] == ["urn:doc#File-4", "urn:doc#File-9"]
    assert statement["fragments"] == ["a/frag.json", "b/frag.json"]


# ---------------------------------------------------------------------------
# build_conflict_annotation (G2)
# ---------------------------------------------------------------------------


def test_build_conflict_annotation_shape_and_determinism() -> None:
    ci = _make_ci()
    candidates: list[ConflictCandidate] = [
        {
            "value": "MIT",
            "role": "declared",
            "source": "Source: pyproject.toml | Field: project.license",
            "ref": "urn:doc#License-1",
        },
        {
            "value": "Apache-2.0",
            "role": "detected",
            "source": (
                "Source: LICENSE | Method: licenseid_detection | Tool: licenseid==0.3.0"
            ),
            "ref": "urn:doc#License-2",
        },
    ]
    ann = build_conflict_annotation(
        subject_spdx_id="urn:doc#Package-1",
        field="license",
        candidates=candidates,
        creation_info=ci,
        annotation_spdx_id="urn:doc#Annotation-conflict-1",
    )
    assert ann.spdxId == "urn:doc#Annotation-conflict-1"
    assert ann.contentType == "application/json"
    assert ann.annotationType == spdx3.AnnotationType.other
    assert ann.subject == "urn:doc#Package-1"
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["schema"] == CONFLICT_SCHEMA_URL
    assert statement["kind"] == "conflict"
    assert statement["field"] == "license"
    assert statement["candidates"] == candidates

    # Byte-stable across two builds with the same input.
    ann2 = build_conflict_annotation(
        subject_spdx_id="urn:doc#Package-1",
        field="license",
        candidates=candidates,
        creation_info=ci,
        annotation_spdx_id="urn:doc#Annotation-conflict-1",
    )
    assert ann.statement == ann2.statement


def test_build_conflict_annotation_generic_field_not_license_specific() -> None:
    """The mechanism is field-agnostic -- license is only the first field
    wired up to it, per the G2 design (any field's multi-source disagreement
    can reuse the same schema)."""
    ci = _make_ci()
    candidates: list[ConflictCandidate] = [
        {"value": "1.0.0", "role": "declared", "source": "Source: pyproject.toml"},
        {"value": "1.0.1", "role": "detected", "source": "Source: build metadata"},
    ]
    ann = build_conflict_annotation(
        subject_spdx_id="urn:doc#Package-1",
        field="version",
        candidates=candidates,
        creation_info=ci,
        annotation_spdx_id="urn:doc#Annotation-conflict-2",
    )
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["field"] == "version"
    # "ref" is optional per candidate -- absent here, not required.
    assert "ref" not in statement["candidates"][0]


# ---------------------------------------------------------------------------
# build_enrichment_annotation (E1/E2, N3's Annotation residual)
# ---------------------------------------------------------------------------


def test_build_enrichment_annotation_shape_and_determinism() -> None:
    ci = _make_ci()
    changes: list[EnrichedFieldEntry] = [
        {
            "field": "license",
            "before": None,
            "after": "MIT",
            "role": "detected",
            "source": "Source: README.md | Method: yaml_frontmatter",
        },
        {
            "field": "datasets:tiny-imagenet",
            "before": None,
            "after": "tiny-imagenet",
            "role": "detected",
            "source": "Source: README.md | Method: yaml_frontmatter",
        },
    ]
    ann = build_enrichment_annotation(
        subject_spdx_id="urn:doc#AIPackage-1",
        changes=changes,
        creation_info=ci,
        annotation_spdx_id="urn:doc#Annotation-enrichment-1",
    )
    assert ann.spdxId == "urn:doc#Annotation-enrichment-1"
    assert ann.contentType == "application/json"
    assert ann.annotationType == spdx3.AnnotationType.other
    assert ann.subject == "urn:doc#AIPackage-1"
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["schema"] == ENRICHMENT_SCHEMA_URL
    assert statement["kind"] == "enrichment"
    assert statement["changes"] == changes

    # Byte-stable across two builds with the same input.
    ann2 = build_enrichment_annotation(
        subject_spdx_id="urn:doc#AIPackage-1",
        changes=changes,
        creation_info=ci,
        annotation_spdx_id="urn:doc#Annotation-enrichment-1",
    )
    assert ann.statement == ann2.statement


def test_build_enrichment_annotation_reuses_g2_role_vocabulary() -> None:
    """E2 deliberately reuses G2's exact role vocabulary rather than
    inventing a separate one -- see annotation-provenance.md."""
    ci = _make_ci()
    changes: list[EnrichedFieldEntry] = [
        {
            "field": "description",
            "before": "old",
            "after": "new",
            "role": "inferred",
            "source": "Source: Claude Code (Anthropic) | Role: inferred",
        }
    ]
    ann = build_enrichment_annotation(
        subject_spdx_id="urn:doc#AIPackage-1",
        changes=changes,
        creation_info=ci,
        annotation_spdx_id="urn:doc#Annotation-enrichment-2",
    )
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["changes"][0]["role"] == "inferred"


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
    assert statement["kind"] == "artifact-metadata"
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
