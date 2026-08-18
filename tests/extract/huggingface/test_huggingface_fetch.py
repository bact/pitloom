# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for the low-level pitloom.extract._huggingface_fetch
helpers -- the raw HF Hub I/O functions and ``_extract_card_description``.

These bypass the full ``read_huggingface()`` pipeline (exercised by the
sibling ``test_huggingface_*.py`` modules) to reach branches that the
higher-level facade never exercises: a pinned revision short-circuiting the
"no pinned revision" warning, the success paths of the raw fetch helpers,
and the paragraph-collection edge cases in ``_extract_card_description``.

See also: conftest.py and _hf_patches_01.py through _hf_patches_10.py for
the shared mock-HF-API helpers used by the higher-level tests.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.extract._huggingface_fetch import (
    _detect_license_from_hf_files,
    _extract_card_description,
    _list_license_files_in_repo,
    _load_model_card,
    _load_model_info,
    _safe_load_json,
)

_LOGGER_NAME = "pitloom.extract._huggingface_fetch"


class _FakeCardData:
    """Minimal stand-in for huggingface_hub.ModelCardData."""

    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return self._data or {}


class _FakeCard:
    """Minimal stand-in for huggingface_hub.ModelCard."""

    def __init__(self, text: str | None, data: _FakeCardData | None) -> None:
        self.text = text
        self.data = data


class _FakeModelInfo:
    """Minimal stand-in for huggingface_hub.hf_api.ModelInfo -- only the
    attributes _load_model_info() actually reads."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


# ---------------------------------------------------------------------------
# _safe_load_json
# ---------------------------------------------------------------------------


def test_safe_load_json_with_pinned_revision_succeeds_without_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A pinned revision skips the "no pinned revision" warning and the
    download+parse succeeds, returning the parsed JSON dict."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"model_type": "mistral"}), encoding="utf-8")

    with patch("huggingface_hub.hf_hub_download", return_value=str(config_file)):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result = _safe_load_json("org/model", "config.json", revision="deadbeef")

    assert result == {"model_type": "mistral"}
    assert not any("pinned revision" in r.message for r in caplog.records)


def test_safe_load_json_without_revision_warns_and_succeeds(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No revision logs a reproducibility warning but still returns the
    parsed JSON on success."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"a": 1}), encoding="utf-8")

    with patch("huggingface_hub.hf_hub_download", return_value=str(config_file)):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result = _safe_load_json("org/model", "config.json")

    assert result == {"a": 1}
    assert any("pinned revision" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _load_model_card
# ---------------------------------------------------------------------------


def test_load_model_card_success_with_data() -> None:
    fake_card = _FakeCard("Model card body.", _FakeCardData({"license": "mit"}))
    with patch("huggingface_hub.ModelCard.load", return_value=fake_card):
        text, data = _load_model_card("org/model")
    assert text == "Model card body."
    assert data == {"license": "mit"}


def test_load_model_card_success_falsy_data_and_text() -> None:
    # card.data is None and card.text is empty -> data becomes {}, text None.
    fake_card = _FakeCard("", None)
    with patch("huggingface_hub.ModelCard.load", return_value=fake_card):
        text, data = _load_model_card("org/model")
    assert text is None
    assert data == {}


# ---------------------------------------------------------------------------
# _load_model_info
# ---------------------------------------------------------------------------


def test_load_model_info_all_fields_present() -> None:
    info = _FakeModelInfo(
        author="mistralai",
        sha="deadbeef",
        created_at=datetime(2023, 9, 20, 13, 3, 50, tzinfo=timezone.utc),
        last_modified=datetime(2023, 9, 21, 0, 0, 0, tzinfo=timezone.utc),
        downloads=1234,
        tags=["license:apache-2.0", "region:us"],
    )
    with patch("huggingface_hub.model_info", return_value=info):
        result = _load_model_info("org/model")

    assert result == {
        "author": "mistralai",
        "sha": "deadbeef",
        "created_at": "2023-09-20T13:03:50+00:00",
        "last_modified": "2023-09-21T00:00:00+00:00",
        "downloads": 1234,
        "tags": ["license:apache-2.0", "region:us"],
    }


def test_load_model_info_falsy_fields_omitted_but_zero_downloads_kept() -> None:
    # author/created_at/last_modified/tags are falsy -> omitted. downloads
    # uses an "is not None" check (not truthiness), so 0 is still recorded.
    info = _FakeModelInfo(
        author=None,
        sha="abc",
        created_at=None,
        last_modified=None,
        downloads=0,
        tags=[],
    )
    with patch("huggingface_hub.model_info", return_value=info):
        result = _load_model_info("org/model")

    assert result == {"sha": "abc", "downloads": 0}


# ---------------------------------------------------------------------------
# _list_license_files_in_repo
# ---------------------------------------------------------------------------


def test_list_license_files_in_repo_filters_and_orders_by_priority() -> None:
    # _HF_LICENSE_FILENAMES priority: LICENSE, LICENCE, COPYING, NOTICE, ...
    existing = {"COPYING", "LICENSE.txt", "LICENSE", "NOTICE"}
    with patch("huggingface_hub.list_repo_files", return_value=existing):
        result = _list_license_files_in_repo("org/model")

    assert result == ["LICENSE", "COPYING", "NOTICE", "LICENSE.txt"]


# ---------------------------------------------------------------------------
# _detect_license_from_hf_files
# ---------------------------------------------------------------------------


def test_detect_license_from_hf_files_pinned_revision_detects_license(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A pinned revision skips the reproducibility warning, and a matching
    # license file yields the detected SPDX ID plus provenance string.
    license_file = tmp_path / "LICENSE"
    license_file.write_text("MIT License text...", encoding="utf-8")

    with patch(
        "pitloom.extract._huggingface_fetch._list_license_files_in_repo",
        return_value=["LICENSE"],
    ):
        with patch("huggingface_hub.hf_hub_download", return_value=str(license_file)):
            with patch(
                "pitloom.extract._license.detect_license_from_text",
                return_value="MIT",
            ):
                with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                    detected_id, provenance = _detect_license_from_hf_files(
                        "org/model", revision="deadbeef"
                    )

    assert detected_id == "MIT"
    assert provenance == (
        "Source: Hugging Face Hub | File: LICENSE | Method: licenseid_detection"
    )
    assert not any("pinned revision" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _extract_card_description
# ---------------------------------------------------------------------------


def test_extract_card_description_typical_card() -> None:
    card_text = "---\nlicense: mit\n---\n\nA great model for text generation."
    assert _extract_card_description(card_text) == "A great model for text generation."


def test_extract_card_description_no_frontmatter_returns_none() -> None:
    # Without any "---" delimiter, yaml_done never becomes True, so every
    # line is skipped by the "not yaml_done" guard and nothing is collected.
    card_text = "Just plain prose with no YAML frontmatter at all."
    assert _extract_card_description(card_text) is None


def test_extract_card_description_stops_at_blank_line_after_paragraph() -> None:
    # A blank line before any content is swallowed (continue); a blank line
    # once a paragraph has started ends collection (break) -- later
    # paragraphs are never reached.
    card_text = (
        "---\nlicense: mit\n---\n\n"
        "First paragraph line one.\n\n"
        "Second paragraph that must be ignored."
    )
    result = _extract_card_description(card_text)
    assert result == "First paragraph line one."
    assert "Second paragraph" not in (result or "")


def test_extract_card_description_horizontal_rule_mid_paragraph() -> None:
    # A "---" appearing in the body (after frontmatter already closed) is
    # not treated as a new frontmatter delimiter -- it falls straight
    # through to line 254 and gets appended as literal paragraph text.
    card_text = (
        "---\nlicense: mit\n---\n\nFirst line of para.\n---\nSecond continued line."
    )
    result = _extract_card_description(card_text)
    assert result == "First line of para. --- Second continued line."


def test_extract_card_description_truncates_at_500_chars() -> None:
    # A single overlong line (no blank-line break) trips the 500-char
    # length guard and breaks out of collection immediately.
    long_line = "word " * 200  # 1000 chars, single line, no blank line follows
    card_text = f"---\nlicense: mit\n---\n\n{long_line}"

    result = _extract_card_description(card_text)

    assert result is not None
    assert len(result) == 500
