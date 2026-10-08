# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for build_source_metadata_annotation()'s max_metadata_bytes cap
(P1 artifact-metadata size truncation).

See also: test_annotation_provenance_annotations.py, which covers the
rest of build_source_metadata_annotation()'s shape/determinism.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging

import pytest

from pitloom.assemble.spdx3.provenance import build_source_metadata_annotation
from pitloom.core.models import _clear_doc_counters

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci


def _small_metadata() -> dict[str, object]:
    return {"general.architecture": "llama", "block_count": 32}


def _metadata_with_one_huge_key() -> dict[str, object]:
    metadata = _small_metadata()
    metadata["tokenizer.ggml.tokens"] = [f"token_{i}" for i in range(2000)]
    return metadata


def test_default_max_bytes_zero_is_unbounded_no_op() -> None:
    ci = _make_ci()
    metadata = _metadata_with_one_huge_key()
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1", "gguf", metadata, ci, _DOC_NAME, _DOC_UUID
    )
    assert ann is not None
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert "truncated" not in statement
    assert len(statement["metadata"]["tokenizer.ggml.tokens"]) == 2000


def test_budget_above_real_size_no_marker_keys() -> None:
    ci = _make_ci()
    metadata = _small_metadata()
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        metadata,
        ci,
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=100_000,
    )
    assert ann is not None
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert "truncated" not in statement
    assert "truncatedKeys" not in statement
    assert "maxMetadataBytes" not in statement
    assert statement["metadata"] == metadata


def test_budget_drops_the_huge_key_keeps_small_ones() -> None:
    ci = _make_ci()
    metadata = _metadata_with_one_huge_key()
    # Big enough for the two small keys plus envelope overhead, far too
    # small for the 2000-entry token list.
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        metadata,
        ci,
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=500,
    )
    assert ann is not None
    assert ann.statement is not None
    assert len(ann.statement.encode("utf-8")) <= 500
    statement = json.loads(ann.statement)
    assert statement["truncated"] is True
    assert statement["truncatedKeys"] == ["tokenizer.ggml.tokens"]
    assert statement["truncatedKeyCount"] == 1
    assert statement["maxMetadataBytes"] == 500
    assert statement["metadata"] == {
        "general.architecture": "llama",
        "block_count": 32,
    }


def test_budget_drops_every_key_but_envelope_still_fits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ci = _make_ci()
    # Each key is large enough that keeping any of them exceeds the budget,
    # but an empty metadata dict plus the truncatedKeys marker still fits.
    metadata = {"k1": "x" * 40, "k2": "y" * 40, "k3": "z" * 40}
    with caplog.at_level(logging.WARNING):
        ann = build_source_metadata_annotation(
            "urn:doc#ai_AIPackage-1",
            "gguf",
            metadata,
            ci,
            _DOC_NAME,
            _DOC_UUID,
            max_metadata_bytes=230,
        )
    assert ann is not None
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["metadata"] == {}
    assert sorted(statement["truncatedKeys"]) == sorted(metadata)
    assert statement["truncatedKeyCount"] == len(metadata)
    assert "all" in caplog.text and "dropped" in caplog.text


def test_budget_too_small_for_empty_envelope_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ci = _make_ci()
    with caplog.at_level(logging.WARNING):
        ann = build_source_metadata_annotation(
            "urn:doc#ai_AIPackage-1",
            "gguf",
            _small_metadata(),
            ci,
            _DOC_NAME,
            _DOC_UUID,
            max_metadata_bytes=8,
        )
    assert ann is None
    assert "dropped entirely" in caplog.text


def test_truncated_keys_sorted_alphabetically_regardless_of_drop_order() -> None:
    ci = _make_ci()
    # zzz_huge is larger than aaa_huge, so it's dropped *first* (largest
    # first) -- the raw drop order is [zzz_huge, aaa_huge], the opposite of
    # alphabetical, so this actually exercises the sort rather than
    # coinciding with it.
    metadata = {
        "zzz_huge": "x" * 3000,
        "aaa_huge": "y" * 2500,
        "mmm_small": 5,
    }
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        metadata,
        ci,
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=300,
    )
    assert ann is not None
    assert ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement["truncatedKeys"] == ["aaa_huge", "zzz_huge"]
    assert statement["metadata"] == {"mmm_small": 5}


def test_truncation_is_deterministic_regardless_of_dict_insertion_order() -> None:
    ci = _make_ci()
    metadata_a = _metadata_with_one_huge_key()
    metadata_b = {k: metadata_a[k] for k in reversed(list(metadata_a))}

    _clear_doc_counters(_DOC_UUID)
    ann_a = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        metadata_a,
        ci,
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=500,
    )
    ann_b = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        metadata_b,
        ci,
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=500,
    )
    assert ann_a is not None and ann_b is not None
    assert ann_a.statement == ann_b.statement


@pytest.mark.parametrize("capped", [0, 7])
@pytest.mark.parametrize("budget", [500, 1000, 5000, 50_000])
def test_respects_the_real_byte_budget(budget: int, capped: int) -> None:
    ci = _make_ci()
    metadata = _metadata_with_one_huge_key()
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        metadata,
        ci,
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=budget,
        capped_key_count=capped,
    )
    assert ann is not None
    assert ann.statement is not None
    assert len(ann.statement.encode("utf-8")) <= budget


def test_negative_max_bytes_rejected() -> None:
    with pytest.raises(ValueError, match="at least 8 bytes"):
        build_source_metadata_annotation(
            "urn:doc#ai_AIPackage-1",
            "gguf",
            _small_metadata(),
            _make_ci(),
            _DOC_NAME,
            _DOC_UUID,
            max_metadata_bytes=-5,
        )


@pytest.mark.parametrize(
    ("budget", "kept_types"),
    [
        (0, {"block_count": "integer", "huge": "integer"}),
        (500, {"block_count": "integer"}),
        (270, None),  # its type tips block_count over: no valueTypes, no {}
    ],
    ids=["unbounded", "huge-dropped", "all-dropped"],
)
def test_value_types_follow_the_kept_keys(
    budget: int, kept_types: dict[str, str] | None
) -> None:
    """A dropped key takes its ``valueTypes`` entry with it, and a type for
    a key the metadata does not hold is never written."""
    metadata = {"general.architecture": "llama", "block_count": "32"}
    metadata["huge"] = "9" * 2000
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        metadata,
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=budget,
        value_types={"block_count": "integer", "huge": "integer", "gone": "float"},
    )
    assert ann is not None and ann.statement is not None
    statement = json.loads(ann.statement)
    assert statement.get("valueTypes") == kept_types
    assert set(statement.get("valueTypes") or {}) <= set(statement["metadata"])
    if budget:
        assert len(ann.statement.encode("utf-8")) <= budget
        assert statement["truncatedKeyCount"] == len(statement["truncatedKeys"])


_ENVELOPE = {"schema", "kind", "format", "metadata", "valueTypes"}


@pytest.mark.parametrize(
    ("budget", "capped", "markers"),
    [
        (0, 0, {}),
        (0, 7, {"truncated": True, "truncatedKeyCount": 7, "maxEntries": 1000}),
        (
            500,
            7,
            {
                "truncated": True,
                "truncatedKeyCount": 8,
                "truncatedKeys": ["tokenizer.ggml.tokens"],
                "maxMetadataBytes": 500,
                "maxEntries": 1000,
            },
        ),
    ],
    ids=["none", "entry-cap", "entry-cap-and-budget"],
)
def test_entry_cap_markers_merge_with_the_byte_budget(
    budget: int, capped: int, markers: dict[str, object]
) -> None:
    """Keys over the entry cap are counted, never named; a byte budget's
    dropped keys are named and counted with them."""
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        _metadata_with_one_huge_key(),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=budget,
        capped_key_count=capped,
    )
    assert ann is not None and ann.statement is not None
    statement = json.loads(ann.statement)
    assert {k: v for k, v in statement.items() if k not in _ENVELOPE} == markers


@pytest.mark.parametrize(("capped", "emitted"), [(0, True), (7, False)])
def test_entry_cap_markers_count_against_the_byte_budget(
    capped: int, emitted: bool
) -> None:
    """A budget that holds the metadata unmarked but not with the entry-cap
    markers (nor an empty envelope with them) gives no annotation."""
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        {"k1": "x" * 40},
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=210,
        capped_key_count=capped,
    )
    assert (ann is not None) == emitted
