# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 Core/Annotation-based metadata provenance: value
parsing, the pluggable encoder registry, and the low-level
annotation/comment builders.

See also: test_annotation_provenance_emit.py,
test_annotation_provenance_annotations.py -- this module's siblings, split
from the original test_annotation_provenance.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import (
    DEFAULT_SCHEMA_ID,
    PitloomV1Encoder,
    build_provenance_annotation,
    build_provenance_comment,
    parse_provenance_value,
    resolve_encoder,
)
from pitloom.core.models import _clear_doc_counters

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci

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
    assert parsed["schema"] == "https://pitloom.dev/provenance/fields/1"
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


def test_build_provenance_annotation_bad_content_type_names_schema() -> None:
    """A pluggable encoder with a malformed content_type must raise a
    ValueError naming the offending schema_id/content_type, not a bare
    unattributed library error -- otherwise a future external-schema
    plugin's mistake is nearly impossible to trace back to its source."""

    # pylint: disable=too-few-public-methods

    class _BadEncoder:
        schema_id = "bad/1"
        content_type = "not-a-mime-type"

        def encode(self, provenance: dict[str, str]) -> str:
            del provenance
            return "{}"

    _clear_doc_counters(_DOC_UUID)
    ci = _make_ci()
    with pytest.raises(ValueError, match="bad/1") as exc_info:
        build_provenance_annotation(
            subject_spdx_id="urn:example#Package-1",
            provenance={"name": "x"},
            creation_info=ci,
            doc_name=_DOC_NAME,
            doc_uuid=_DOC_UUID,
            encoder=_BadEncoder(),
        )
    assert "not-a-mime-type" in str(exc_info.value)


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
