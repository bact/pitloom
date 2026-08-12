# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for [tool.pitloom.file-headers] config parsing."""

import pytest

from pitloom.core.config import _read_file_headers_settings

# ---------------------------------------------------------------------------
# _read_file_headers_settings
# ---------------------------------------------------------------------------


def test_read_file_headers_settings_defaults_when_section_absent() -> None:
    """No [tool.pitloom.file-headers] section: enabled defaults True,
    detect_content_type defaults False -- different defaults, reflecting
    the different cost profiles."""
    assert _read_file_headers_settings({}) == (True, False)


def test_read_file_headers_settings_explicit_overrides() -> None:
    """Explicit enabled=false and detect-content-type=true each override
    their own default independently."""
    pitloom_data = {"file-headers": {"enabled": False, "detect-content-type": True}}
    assert _read_file_headers_settings(pitloom_data) == (False, True)


def test_read_file_headers_settings_partial_override() -> None:
    """Setting only one key leaves the other at its own default."""
    pitloom_data = {"file-headers": {"detect-content-type": True}}
    assert _read_file_headers_settings(pitloom_data) == (True, True)


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
