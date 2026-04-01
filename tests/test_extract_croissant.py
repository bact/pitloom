# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Croissant JSON-LD dataset metadata extractor."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.extract._croissant import (
    _collect_data_types,
    _extract_creator_name,
    _extract_size,
    _infer_dataset_types,
    _normalize_sensitivity,
    read_croissant,
)
from pitloom.extract._extract_utils import to_str_list as _to_str_list

# Path to the shared fixture directory.
FIXTURES = Path(__file__).parent / "fixtures" / "croissant"


# ---------------------------------------------------------------------------
# _to_str_list
# ---------------------------------------------------------------------------


def test_to_str_list_none() -> None:
    assert _to_str_list(None) == []


def test_to_str_list_single_string() -> None:
    assert _to_str_list("hello") == ["hello"]


def test_to_str_list_csv_string() -> None:
    result = _to_str_list("NLP, text classification, sentiment")
    assert result == ["NLP", "text classification", "sentiment"]


def test_to_str_list_list_input() -> None:
    assert _to_str_list(["a", "b", "c"]) == ["a", "b", "c"]


def test_to_str_list_filters_none_elements() -> None:
    assert _to_str_list([None, "a", None]) == ["a"]


# ---------------------------------------------------------------------------
# _extract_creator_name
# ---------------------------------------------------------------------------


def test_extract_creator_name_none() -> None:
    assert _extract_creator_name(None) is None


def test_extract_creator_name_string() -> None:
    assert _extract_creator_name("Alice") == "Alice"


def test_extract_creator_name_dict() -> None:
    assert _extract_creator_name({"name": "Bob"}) == "Bob"


def test_extract_creator_name_list_of_dicts() -> None:
    assert _extract_creator_name([{"name": "Carol"}, {"name": "Dave"}]) == "Carol"


def test_extract_creator_name_empty_dict() -> None:
    assert _extract_creator_name({}) is None


# ---------------------------------------------------------------------------
# _normalize_sensitivity
# ---------------------------------------------------------------------------


def test_normalize_sensitivity_none() -> None:
    assert _normalize_sensitivity(None) is None


def test_normalize_sensitivity_empty_string() -> None:
    assert _normalize_sensitivity("") is None


def test_normalize_sensitivity_yes_variants() -> None:
    for v in ("yes", "YES", "true", "True", "1"):
        assert _normalize_sensitivity(v) == "yes", f"failed for {v!r}"


def test_normalize_sensitivity_no_variants() -> None:
    for v in ("no", "NO", "false", "False", "0"):
        assert _normalize_sensitivity(v) == "no", f"failed for {v!r}"


def test_normalize_sensitivity_unknown_text() -> None:
    assert _normalize_sensitivity("maybe") == "noAssertion"
    assert _normalize_sensitivity("This dataset contains PII.") == "noAssertion"


# ---------------------------------------------------------------------------
# _collect_data_types / _infer_dataset_types
# ---------------------------------------------------------------------------


def test_collect_data_types_flat() -> None:
    data = {"sc:dataType": "sc:Text"}
    assert _collect_data_types(data) == ["sc:Text"]


def test_collect_data_types_nested() -> None:
    data = {
        "cr:recordSet": [
            {"cr:field": [{"sc:dataType": "sc:Text"}, {"sc:dataType": "sc:Integer"}]}
        ]
    }
    types = _collect_data_types(data)
    assert "sc:Text" in types
    assert "sc:Integer" in types


def test_infer_dataset_types_text_and_numeric() -> None:
    data = {
        "cr:recordSet": [
            {
                "cr:field": [
                    {"sc:dataType": "sc:Text"},
                    {"sc:dataType": "sc:Integer"},
                ]
            }
        ]
    }
    types = _infer_dataset_types(data)
    assert "text" in types
    assert "numeric" in types


def test_infer_dataset_types_deduplicates() -> None:
    data = {
        "cr:recordSet": [
            {
                "cr:field": [
                    {"sc:dataType": "sc:Text"},
                    {"sc:dataType": "sc:Text"},
                ]
            }
        ]
    }
    types = _infer_dataset_types(data)
    assert types.count("text") == 1


def test_infer_dataset_types_unknown_falls_back_to_other() -> None:
    data = {"sc:dataType": "sc:SomeUnknownType"}
    types = _infer_dataset_types(data)
    assert "other" in types


def test_infer_dataset_types_image() -> None:
    data = {"sc:dataType": "sc:ImageObject"}
    assert "image" in _infer_dataset_types(data)


def test_infer_dataset_types_empty() -> None:
    assert not _infer_dataset_types({})


# ---------------------------------------------------------------------------
# _extract_size
# ---------------------------------------------------------------------------


# def test_extract_size_single_record_set() -> None:
#     data = {"cr:recordSet": [{"cr:totalItems": 1000}]}
#     assert _extract_size(data) == 1000


# def test_extract_size_multiple_record_sets_summed() -> None:
#     data = {"cr:recordSet": [{"cr:totalItems": 1000}, {"cr:totalItems": 500}]}
#     assert _extract_size(data) == 1500


# def test_extract_size_string_value() -> None:
#     # totalItems may be a string in some files
#     data = {"cr:recordSet": [{"cr:totalItems": "2500"}]}
#     assert _extract_size(data) == 2500


def test_extract_size_no_record_sets() -> None:
    assert _extract_size({}) is None


# def test_extract_size_missing_total_items() -> None:
#     data: dict[str, object] = {"cr:recordSet": [{"cr:field": []}]}
#     assert _extract_size(data) is None


# ---------------------------------------------------------------------------
# read_croissant — file-based
# ---------------------------------------------------------------------------


def test_read_croissant_minimal() -> None:
    meta = read_croissant(FIXTURES / "minimal.json")
    assert meta.name == "Minimal Dataset"


def test_read_croissant_full_name() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.name == "Sample NLP Dataset"


def test_read_croissant_full_version() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.version == "1.2.0"


def test_read_croissant_full_description() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.description == "A sample dataset for text classification testing."


def test_read_croissant_full_download_url() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.download_url == "https://example.com/datasets/sample-nlp"


def test_read_croissant_full_license() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.license == "Apache-2.0"


def test_read_croissant_full_keywords() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert "NLP" in meta.keywords
    assert "text classification" in meta.keywords


def test_read_croissant_full_creator() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.creator == "Test Author"


def test_read_croissant_full_dataset_types() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert "text" in meta.dataset_types
    assert "numeric" in meta.dataset_types


# def test_read_croissant_full_dataset_size() -> None:
#     meta = read_croissant(FIXTURES / "full.json")
#     assert meta.dataset_size == 5000


def test_read_croissant_full_data_collection() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.data_collection_process == "Data was collected from public web sources."


# def test_read_croissant_full_data_preprocessing() -> None:
#     meta = read_croissant(FIXTURES / "full.json")
#     assert "xxx" in meta.data_preprocessing


# def test_read_croissant_full_known_bias() -> None:
#     meta = read_croissant(FIXTURES / "full.json")
#     assert any("xxx" in bias for bias in meta.known_bias)


def test_read_croissant_full_sensitivity_no() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.has_sensitive_personal_information == "no"


def test_read_croissant_full_provenance_populated() -> None:
    meta = read_croissant(FIXTURES / "full.json")
    assert "name" in meta.provenance
    assert "dataset_types" in meta.provenance
    # assert "dataset_size" in meta.provenance


def test_read_croissant_full_no_croissant_url_for_local_file() -> None:
    # Local file paths must NOT set croissant_url.
    meta = read_croissant(FIXTURES / "full.json")
    assert meta.croissant_url is None


def test_read_croissant_prefixed_keys() -> None:
    meta = read_croissant(FIXTURES / "prefixed.json")
    assert meta.name == "Prefixed Keys Dataset"
    assert meta.version == "2.0"
    assert meta.license == "MIT"
    assert "image" in meta.dataset_types
    assert meta.has_sensitive_personal_information == "yes"


def test_read_croissant_prefixed_creator_string() -> None:
    meta = read_croissant(FIXTURES / "prefixed.json")
    assert meta.creator == "Research Lab"


def test_read_croissant_prefixed_keywords_csv() -> None:
    # "vision, image" is a CSV string; should be split
    meta = read_croissant(FIXTURES / "prefixed.json")
    assert "vision" in meta.keywords


# ---------------------------------------------------------------------------
# read_croissant — error cases
# ---------------------------------------------------------------------------


def test_read_croissant_missing_name_raises(tmp_path: Path) -> None:
    f = tmp_path / "no_name.json"
    f.write_text('{"description": "no name here"}', encoding="utf-8")
    with pytest.raises(ValueError, match="no 'name' field"):
        read_croissant(f)


def test_read_croissant_invalid_json_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        read_croissant(f)


def test_read_croissant_nonexistent_file_raises() -> None:
    with pytest.raises(ValueError, match="Cannot read"):
        read_croissant(Path("/nonexistent/path/dataset.json"))


def test_read_croissant_non_object_json_raises(tmp_path: Path) -> None:
    f = tmp_path / "array.json"
    f.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        read_croissant(f)


# ---------------------------------------------------------------------------
# read_croissant — URL detection
# ---------------------------------------------------------------------------


def test_read_croissant_path_leaves_croissant_url_none() -> None:
    meta = read_croissant(FIXTURES / "minimal.json")
    assert meta.croissant_url is None


def test_read_croissant_url_string_sets_croissant_url() -> None:
    dataset_doc = {"@type": "Dataset", "name": "Remote Dataset"}
    url = "https://example.com/dataset.json"
    mock_resp = io.BytesIO(json.dumps(dataset_doc).encode())
    with patch("urllib.request.urlopen", return_value=mock_resp):
        meta = read_croissant(url)
    assert meta.croissant_url == url
    assert meta.name == "Remote Dataset"
