# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for [tool.pitloom.file-headers] config parsing."""

import pytest

from pitloom.core.config import _read_file_headers_settings
from pitloom.core.file_headers_config import ContentTypeOverride

# ---------------------------------------------------------------------------
# _read_file_headers_settings
# ---------------------------------------------------------------------------


def test_read_file_headers_settings_defaults_when_section_absent() -> None:
    """No [tool.pitloom.file-headers] section: enabled defaults True,
    detect_content_type defaults False -- different defaults, reflecting
    the different cost profiles -- and content_type_overrides defaults
    to an empty tuple."""
    assert _read_file_headers_settings({}) == (True, False, ())


def test_read_file_headers_settings_explicit_overrides() -> None:
    """Explicit enabled=false and detect-content-type=true each override
    their own default independently."""
    pitloom_data = {"file-headers": {"enabled": False, "detect-content-type": True}}
    assert _read_file_headers_settings(pitloom_data) == (False, True, ())


def test_read_file_headers_settings_partial_override() -> None:
    """Setting only one key leaves the other at its own default."""
    pitloom_data = {"file-headers": {"detect-content-type": True}}
    assert _read_file_headers_settings(pitloom_data) == (True, True, ())


def test_read_file_headers_settings_non_table_raises() -> None:
    """[tool.pitloom.file-headers] must be a table."""
    with pytest.raises(ValueError, match="must be a table"):
        _read_file_headers_settings({"file-headers": "not-a-table"})


def test_read_file_headers_settings_non_bool_enabled_raises() -> None:
    """'enabled' must be a boolean."""
    with pytest.raises(ValueError, match="'enabled' must be a boolean"):
        _read_file_headers_settings({"file-headers": {"enabled": "yes"}})


def test_read_file_headers_settings_non_bool_detect_content_type_raises() -> None:
    """'detect-content-type' must be a boolean."""
    with pytest.raises(ValueError, match="'detect-content-type' must be a boolean"):
        _read_file_headers_settings({"file-headers": {"detect-content-type": "yes"}})


# ---------------------------------------------------------------------------
# content-type-overrides
# ---------------------------------------------------------------------------


def test_read_file_headers_settings_content_type_overrides_valid() -> None:
    """Valid entries parse to ContentTypeOverride tuples, in declaration order."""
    pitloom_data = {
        "file-headers": {
            "content-type-overrides": [
                {"pattern": "*.woff2", "content-type": "font/woff2"},
                {"pattern": "vendor/*", "content-type": "application/octet-stream"},
            ]
        }
    }
    _, _, overrides = _read_file_headers_settings(pitloom_data)
    assert overrides == (
        ContentTypeOverride(pattern="*.woff2", content_type="font/woff2"),
        ContentTypeOverride(
            pattern="vendor/*", content_type="application/octet-stream"
        ),
    )


def test_read_file_headers_settings_content_type_overrides_absent_defaults_empty() -> (
    None
):
    """No content-type-overrides key: defaults to an empty tuple."""
    pitloom_data = {"file-headers": {"enabled": True}}
    _, _, overrides = _read_file_headers_settings(pitloom_data)
    assert not overrides


def test_read_file_headers_settings_content_type_overrides_non_list_raises() -> None:
    """'content-type-overrides' must be an array (of tables)."""
    pitloom_data = {"file-headers": {"content-type-overrides": "not-a-list"}}
    with pytest.raises(ValueError, match="must be an array of tables"):
        _read_file_headers_settings(pitloom_data)


def test_read_file_headers_settings_content_type_overrides_entry_non_table_raises() -> (
    None
):
    """Each content-type-overrides entry must be a table."""
    pitloom_data = {"file-headers": {"content-type-overrides": ["not-a-table"]}}
    with pytest.raises(ValueError, match="entries must be tables"):
        _read_file_headers_settings(pitloom_data)


def test_read_file_headers_settings_content_type_overrides_missing_pattern_raises() -> (
    None
):
    """A missing 'pattern' key raises."""
    pitloom_data = {
        "file-headers": {
            "content-type-overrides": [{"content-type": "image/png"}],
        }
    }
    with pytest.raises(ValueError, match="'pattern' must be a non-empty string"):
        _read_file_headers_settings(pitloom_data)


def test_read_file_headers_settings_content_type_overrides_empty_pattern_raises() -> (
    None
):
    """An empty-string 'pattern' raises -- non-empty is required."""
    pitloom_data = {
        "file-headers": {
            "content-type-overrides": [{"pattern": "", "content-type": "image/png"}],
        }
    }
    with pytest.raises(ValueError, match="'pattern' must be a non-empty string"):
        _read_file_headers_settings(pitloom_data)


def test_read_file_headers_settings_content_type_overrides_missing_content_type() -> (
    None
):
    """A missing 'content-type' key raises."""
    pitloom_data = {
        "file-headers": {
            "content-type-overrides": [{"pattern": "*.png"}],
        }
    }
    with pytest.raises(ValueError, match="'content-type' must be a MIME type"):
        _read_file_headers_settings(pitloom_data)


def test_read_file_headers_settings_content_type_overrides_malformed_content_type() -> (
    None
):
    """A 'content-type' value not shaped like 'type/subtype' raises."""
    pitloom_data = {
        "file-headers": {
            "content-type-overrides": [{"pattern": "*.png", "content-type": "PNG"}],
        }
    }
    with pytest.raises(ValueError, match="'content-type' must be a MIME type"):
        _read_file_headers_settings(pitloom_data)
