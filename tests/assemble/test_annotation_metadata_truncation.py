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

from pitloom.assemble.spdx3.document import build_model
from pitloom.assemble.spdx3.provenance import (
    KeysLeftOut,
    build_source_metadata_annotation,
)
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.models import _clear_doc_counters
from pitloom.core.provenance import ProvenanceConfig
from pitloom.messages import code_of
from tests._author_routes import CREATED

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
    assert [r.getMessage() for r in caplog.records] == [
        "FORMAT=gguf FILE=urn:doc#ai_AIPackage-1: all 3 metadata key(s) left "
        "out to fit the 230-byte max-source-metadata-bytes cap"
    ]
    assert [getattr(r, "pitloom_code", None) for r in caplog.records] == ["over-cap"]


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
    assert [r.getMessage() for r in caplog.records] == [
        "FORMAT=gguf FILE=urn:doc#ai_AIPackage-1: its metadata does not fit "
        "the 8-byte max-source-metadata-bytes cap even with no key; "
        "artifact-metadata annotation left out"
    ]
    assert [getattr(r, "pitloom_code", None) for r in caplog.records] == ["over-cap"]


def test_the_budget_line_names_the_file_a_caller_passes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``where`` names the model file in the line; without it, the subject."""
    with caplog.at_level(logging.WARNING):
        build_source_metadata_annotation(
            "urn:doc#ai_AIPackage-1",
            "gguf",
            _small_metadata(),
            _make_ci(),
            _DOC_NAME,
            _DOC_UUID,
            max_metadata_bytes=8,
            where="models/m.gguf",
        )
    assert caplog.records[0].getMessage().startswith("FORMAT=gguf FILE=models/m.gguf: ")
    assert getattr(caplog.records[0], "pitloom_code", None) == "over-cap"


@pytest.mark.parametrize("fmt", ["My-Format", ""], ids=["upper-hyphen", "empty"])
def test_a_format_of_no_model_names_the_file_only(
    caplog: pytest.LogCaptureFixture, fmt: str
) -> None:
    """A library caller's own ``source_format`` is no ``FORMAT=``: a budget
    that drops nothing never fails over it, and one that drops everything
    names the file only."""
    args = ("urn:doc#ai_AIPackage-1", fmt, _small_metadata(), _make_ci())
    big = build_source_metadata_annotation(
        *args, _DOC_NAME, _DOC_UUID, max_metadata_bytes=100_000
    )
    assert big is not None
    with caplog.at_level(logging.WARNING):
        none = build_source_metadata_annotation(
            *args, _DOC_NAME, _DOC_UUID, max_metadata_bytes=8
        )
    assert none is None
    assert caplog.records[0].getMessage().startswith("FILE=urn:doc#ai_AIPackage-1: ")
    assert getattr(caplog.records[0], "pitloom_code", None) == "over-cap"


def test_a_model_route_names_the_model_file_in_the_budget_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The model's file, not the package's SPDX id, is the ``FILE=`` value."""
    model = AiModelMetadata(
        name="m",
        raw_metadata=_small_metadata(),
        format_info=AiModelFormatInfo(
            file_name="m.gguf",
            physical_path="models/m.gguf",
            model_format=AiModelFormat.GGUF,
        ),
    )
    config = ProvenanceConfig(max_source_metadata_bytes=8)
    with caplog.at_level(logging.WARNING):
        build_model(model, CREATED, provenance=config)
    budget = [
        r for r in caplog.records if getattr(r, "pitloom_code", None) == "over-cap"
    ]
    assert [r.getMessage() for r in budget] == [
        "FORMAT=gguf FILE=models/m.gguf: its metadata does not fit the 8-byte "
        "max-source-metadata-bytes cap even with no key; artifact-metadata "
        "annotation left out"
    ]


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
        left_out=KeysLeftOut(capped),
    )
    assert ann is not None
    assert ann.statement is not None
    assert len(ann.statement.encode("utf-8")) <= budget


def test_negative_max_bytes_rejected() -> None:
    with pytest.raises(ValueError, match="of at least 8, got an integer -5") as exc:
        build_source_metadata_annotation(
            "urn:doc#ai_AIPackage-1",
            "gguf",
            _small_metadata(),
            _make_ci(),
            _DOC_NAME,
            _DOC_UUID,
            max_metadata_bytes=-5,
        )
    assert code_of(exc.value) == "option-invalid"  # a library parameter


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
    ("budget", "left_out", "markers"),
    [
        (0, KeysLeftOut(), {}),
        (
            0,
            KeysLeftOut(7),
            {"truncated": True, "truncatedKeyCount": 7, "maxEntries": 1000},
        ),
        # Unread keys (a read in part) are no entry cap: no maxEntries
        (0, KeysLeftOut(0, 3), {"truncated": True, "truncatedKeyCount": 3}),
        (
            0,
            KeysLeftOut(7, 3),
            {"truncated": True, "truncatedKeyCount": 10, "maxEntries": 1000},
        ),
        (
            500,
            KeysLeftOut(7),
            {
                "truncated": True,
                "truncatedKeyCount": 8,
                "truncatedKeys": ["tokenizer.ggml.tokens"],
                "maxMetadataBytes": 500,
                "maxEntries": 1000,
            },
        ),
    ],
    ids=["none", "entry-cap", "unread", "entry-cap-and-unread", "entry-cap-and-budget"],
)
def test_entry_cap_markers_merge_with_the_byte_budget(
    budget: int, left_out: KeysLeftOut, markers: dict[str, object]
) -> None:
    """Keys over the entry cap or unread are counted, never named; a byte
    budget's dropped keys are named and counted with them."""
    ann = build_source_metadata_annotation(
        "urn:doc#ai_AIPackage-1",
        "gguf",
        _metadata_with_one_huge_key(),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
        max_metadata_bytes=budget,
        left_out=left_out,
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
        left_out=KeysLeftOut(capped),
    )
    assert (ann is not None) == emitted
