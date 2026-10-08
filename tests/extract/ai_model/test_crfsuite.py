# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the CRFsuite adapter (``pitloom.extract.ai_model.crfsuite``).

See also: formats/test_crfsuite.py for the reader's own tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core.ai_metadata import (
    FILE_NAME_STEM_PROVENANCE,
    AiModelFormat,
    AiModelMetadata,
)
from pitloom.extract.ai_model import REGISTRY, crfsuite, read_ai_model
from pitloom.extract.ai_model.formats import Limits
from pitloom.extract.ai_model.formats.crfsuite import CrfsuiteModel, read_crfsuite
from pitloom.extract.ai_model.limits import MAX_MODEL_ENTRIES
from tests.warning_helpers import logged_warnings

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "aimodels" / "crfsuite"
_COMPLETE = _FIXTURES / "complete.crfsuite"
_MINIMAL = _FIXTURES / "minimal.model"
_COMPLETE_LABELS = ["บุคคล", "O", "B-LOC", "I PER/x", "E-X:1"]
# A tagger emits one label per input item: the length is symbolic, as an
# ONNX dim_param is.
_OUTPUTS = [{"name": "label_sequence", "shape": ["sequence_length"]}]


@pytest.fixture(name="complete")
def _complete() -> AiModelMetadata:
    return read_ai_model(_COMPLETE)


def _patched_header(
    monkeypatch: pytest.MonkeyPatch, labels: tuple[str, ...]
) -> mock.MagicMock:
    """Replace the reader with one returning a model of *labels*."""
    fake: mock.MagicMock = mock.create_autospec(
        read_crfsuite,
        return_value=CrfsuiteModel("FOMC", 100, 7, 3, len(labels), labels),
    )
    monkeypatch.setattr(crfsuite, "read_crfsuite_header", fake)
    return fake


def test_complete_fixture_is_read_through_read_ai_model(
    complete: AiModelMetadata,
) -> None:
    assert complete.format_info.model_format is AiModelFormat.CRFSUITE
    assert complete.format_info.framework == "crfsuite"
    assert complete.format_info.format_version == "100"
    assert complete.format_info.file_name == "complete.crfsuite"
    assert complete.type_of_model == "conditional random field"
    assert complete.properties == {
        "labels": '["บุคคล","O","B-LOC","I PER/x","E-X:1"]',
        "model_type": "FOMC",
        "num_attributes": "14",
        "num_features": "24",
        "num_labels": "5",
    }
    assert complete.raw_metadata == {
        "labels": _COMPLETE_LABELS,
        "model_type": "FOMC",
        "num_attributes": "14",
        "num_features": "24",
        "num_labels": "5",
    }
    assert complete.outputs == _OUTPUTS
    assert complete.description == (
        "CRFsuite model with 5 labels: บุคคล, O, B-LOC, I PER/x, E-X:1"
    )
    assert complete.name is None
    assert complete.version is None
    assert complete.license is None


def test_minimal_model_suffix_is_read_by_its_magic() -> None:
    meta = read_ai_model(_MINIMAL)
    assert meta.format_info.model_format is AiModelFormat.CRFSUITE
    assert meta.raw_metadata["labels"] == ["I", "E"]
    assert meta.properties["num_features"] == "4"
    assert meta.description == "CRFsuite model with 2 labels: I, E"


def test_labels_property_is_a_json_array_of_str_values(
    complete: AiModelMetadata,
) -> None:
    assert json.loads(complete.properties["labels"]) == _COMPLETE_LABELS
    assert "บุคคล" in complete.properties["labels"]  # not \u-escaped
    assert all(isinstance(v, str) for v in complete.properties.values())


def test_provenance_cites_where_each_value_came_from(
    complete: AiModelMetadata,
) -> None:
    src = "Source: complete.crfsuite"
    assert complete.provenance == {
        "framework": f"{src} | Field: magic",
        "format_version": f"{src} | Field: version",
        "type_of_model": f"{src} | Field: header.type | Method: crfsuite_model_type",
        "description": f"{src} | Field: labels CQDB | Method: generated_from_labels",
        "outputs": f"{src} | Field: header.type (one label per item)",
        "properties.labels": f"{src} | Field: labels CQDB",
        "properties.model_type": f"{src} | Field: header.type",
        "properties.num_attributes": f"{src} | Field: header.num_attrs",
        # the header's own num_features is always 0
        "properties.num_features": f"{src} | Field: FEAT.num",
        "properties.num_labels": f"{src} | Field: header.num_labels",
    }


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, "CRFsuite model with 1 label: l0"),
        (20, "CRFsuite model with 20 labels: " + ", ".join(f"l{i}" for i in range(20))),
        (
            21,
            "CRFsuite model with 21 labels: "
            + ", ".join(f"l{i}" for i in range(20))
            + ", ... (1 more)",
        ),
        (
            25,
            "CRFsuite model with 25 labels: "
            + ", ".join(f"l{i}" for i in range(20))
            + ", ... (5 more)",
        ),
    ],
    ids=["one", "at-cut", "one-over", "25"],
)
def test_description_names_at_most_twenty_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, count: int, expected: str
) -> None:
    labels = tuple(f"l{i}" for i in range(count))
    fake = _patched_header(monkeypatch, labels)
    path = tmp_path / "m.crfsuite"
    path.write_bytes(b"lCRF")
    meta = crfsuite.read_crfsuite(path)
    fake.assert_called_once()
    assert meta.description == expected
    # only the description is cut
    assert meta.raw_metadata["labels"] == list(labels)
    assert json.loads(meta.properties["labels"]) == list(labels)
    assert meta.outputs == _OUTPUTS


def test_no_labels_means_no_description_and_no_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patched_header(monkeypatch, ())
    path = tmp_path / "m.crfsuite"
    path.write_bytes(b"lCRF")
    meta = crfsuite.read_crfsuite(path)
    assert meta.description is None
    assert not meta.outputs
    assert "description" not in meta.provenance
    assert "outputs" not in meta.provenance
    assert meta.properties["labels"] == "[]"
    assert meta.properties["num_labels"] == "0"
    assert meta.type_of_model == "conditional random field"


def test_awkward_labels_survive_the_json_array(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    labels = ("a,b", 'say "hi"', "line\nbreak", "tab\tctl\x01", "ไทย")
    _patched_header(monkeypatch, labels)
    path = tmp_path / "m.crfsuite"
    path.write_bytes(b"lCRF")
    meta = crfsuite.read_crfsuite(path)
    assert json.loads(meta.properties["labels"]) == list(labels)
    assert meta.raw_metadata["labels"] == list(labels)
    assert "\n" not in meta.properties["labels"]  # escaped by JSON


def test_blank_name_falls_back_to_the_file_stem() -> None:
    meta = read_ai_model(_COMPLETE)
    assert meta.name is None
    name, provenance = meta.resolve_name()
    assert name == "complete"
    assert provenance["name"] == FILE_NAME_STEM_PROVENANCE
    assert "name" not in meta.provenance  # resolve_name copies, never mutates


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows file names cannot hold a pipe"
)
def test_a_provenance_source_name_is_sanitised(tmp_path: Path) -> None:
    path = tmp_path / "a|b.crfsuite"
    path.write_bytes(_COMPLETE.read_bytes())
    source = read_ai_model(path).provenance["framework"].split(" | ")[0]
    assert source.count("|") == 0


def _truncated(tmp: Path) -> Path:
    path = tmp / "t.crfsuite"
    path.write_bytes(_COMPLETE.read_bytes()[:100])
    return path


def _bad_type(tmp: Path) -> Path:
    path = tmp / "t.crfsuite"
    data = bytearray(_COMPLETE.read_bytes())
    data[8:12] = b"XXXX"
    path.write_bytes(bytes(data))
    return path


def _directory(tmp: Path) -> Path:
    path = tmp / "d.crfsuite"
    path.mkdir()
    return path


@pytest.mark.parametrize(
    ("make", "match"),
    [
        (_truncated, "not a readable CRFsuite model: "),
        (_bad_type, "not a readable CRFsuite model: "),
    ],
    ids=["malformed", "unsupported-version"],
)
def test_format_errors_become_value_error(
    tmp_path: Path, make: Callable[[Path], Path], match: str
) -> None:
    with pytest.raises(ValueError, match=match) as info:
        crfsuite.read_crfsuite(make(tmp_path))
    assert str(info.value) != match  # a reason follows
    assert str(tmp_path) not in str(info.value)  # the reason names no path


def test_an_unreadable_file_is_a_value_error_like_the_other_readers(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="Failed to read CRFsuite file"):
        crfsuite.read_crfsuite(_directory(tmp_path))


@pytest.mark.parametrize(
    ("limits", "reason"),
    [
        (Limits(max_crfsuite_labels=4), "more than 4 labels"),
        (Limits(max_crfsuite_labels_chunk_bytes=2072), "labels CQDB over 2072 bytes"),
    ],
    ids=["label-count", "labels-chunk"],
)
def test_a_labels_bound_keeps_the_counts_and_records_no_label(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    limits: Limits,
    reason: str,
) -> None:
    """Same outcome as a label over the length cap: the model is read, its
    counts kept, no label anywhere, one warning; not a stub."""
    monkeypatch.setattr(crfsuite, "_LIMITS", limits)
    meta = read_ai_model(_COMPLETE)
    assert logged_warnings(caplog) == [f"{reason}; no label recorded"]
    assert meta.properties == {
        "model_type": "FOMC",
        "num_attributes": "14",
        "num_features": "24",
        "num_labels": "5",
    }
    assert "labels" not in meta.raw_metadata
    assert meta.description is None
    assert meta.outputs == _OUTPUTS
    assert meta.type_of_model == "conditional random field"
    assert not {"description", "properties.labels"} & set(meta.provenance)


def test_the_label_cap_is_the_model_entry_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _patched_header(monkeypatch, ())
    path = tmp_path / "m.crfsuite"
    path.write_bytes(_COMPLETE.read_bytes())
    read_ai_model(path)
    (_source, limits), _kwargs = fake.call_args
    assert limits.max_crfsuite_labels == MAX_MODEL_ENTRIES


def test_registry_entry_is_the_adapter() -> None:
    (info,) = [i for i in REGISTRY if i.format is AiModelFormat.CRFSUITE]
    assert info.reader is crfsuite.read_crfsuite


@pytest.mark.parametrize(
    ("label", "shown"),
    [
        ("x" * 64, "x" * 64),
        ("x" * 65, "x" * 61 + "..."),
        ("x" * 4096, "x" * 61 + "..."),
    ],
    ids=["at-limit", "over-limit", "at-label-cap"],
)
def test_description_cuts_each_label(
    monkeypatch: pytest.MonkeyPatch, label: str, shown: str
) -> None:
    """One huge label cannot make the description (and the SBOM) huge."""
    _patched_header(monkeypatch, ("O", label))
    meta = read_ai_model(_COMPLETE)
    assert meta.description == f"CRFsuite model with 2 labels: O, {shown}"
    # the labels themselves are kept whole in the properties
    assert json.loads(meta.properties["labels"]) == ["O", label]


def test_a_label_over_the_cap_keeps_the_counts_and_drops_the_labels(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A 4097-byte label: no label anywhere (properties, annotation,
    description), one warning, the counts and output shape still read."""
    _patched_header(monkeypatch, ("O", "x" * 4097))
    meta = read_ai_model(_COMPLETE)
    (message,) = logged_warnings(caplog)
    assert "a label over 4096 bytes; no label recorded" in message
    assert "labels" not in meta.properties
    assert "labels" not in meta.raw_metadata
    assert meta.description is None
    assert meta.properties["num_labels"] == "2"
    assert meta.outputs == _OUTPUTS
    assert "properties.labels" not in meta.provenance
    assert "description" not in meta.provenance
    assert "outputs" in meta.provenance
