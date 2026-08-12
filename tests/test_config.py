# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for [tool.pitloom] config parsing: extract-file-header,
[tool.pitloom.content-type], ids-file, enrich, [tool.pitloom.fragment]."""

import pytest

from pitloom.core.config import (
    _read_content_type_settings,
    _read_enrich_settings,
    _read_extract_file_header,
    _read_fragments,
    _read_ids_file,
)
from pitloom.core.content_type_config import ContentTypeOverride

# ---------------------------------------------------------------------------
# _read_extract_file_header
# ---------------------------------------------------------------------------


def test_read_extract_file_header_defaults_true_when_absent() -> None:
    """No 'extract-file-header' key: defaults to True."""
    assert _read_extract_file_header({}) is True


def test_read_extract_file_header_explicit_false() -> None:
    assert _read_extract_file_header({"extract-file-header": False}) is False


def test_read_extract_file_header_non_bool_raises() -> None:
    with pytest.raises(ValueError, match="'extract-file-header' must be a boolean"):
        _read_extract_file_header({"extract-file-header": "yes"})


# ---------------------------------------------------------------------------
# _read_content_type_settings
# ---------------------------------------------------------------------------


def test_read_content_type_settings_defaults_when_section_absent() -> None:
    """No [tool.pitloom.content-type] section: enabled defaults False,
    method defaults 'auto', overrides defaults to an empty tuple."""
    assert _read_content_type_settings({}) == (False, "auto", ())


def test_read_content_type_settings_explicit_enabled() -> None:
    pitloom_data = {"content-type": {"enabled": True}}
    assert _read_content_type_settings(pitloom_data) == (True, "auto", ())


@pytest.mark.parametrize("method", ["auto", "magika", "extension"])
def test_read_content_type_settings_valid_methods(method: str) -> None:
    pitloom_data = {"content-type": {"method": method}}
    _, resolved_method, _ = _read_content_type_settings(pitloom_data)
    assert resolved_method == method


def test_read_content_type_settings_invalid_method_raises() -> None:
    pitloom_data = {"content-type": {"method": "mimetypes"}}
    with pytest.raises(ValueError, match="'method' must be one of"):
        _read_content_type_settings(pitloom_data)


def test_read_content_type_settings_non_table_raises() -> None:
    """[tool.pitloom.content-type] must be a table."""
    with pytest.raises(ValueError, match="must be a table"):
        _read_content_type_settings({"content-type": "not-a-table"})


def test_read_content_type_settings_non_bool_enabled_raises() -> None:
    with pytest.raises(ValueError, match="'enabled' must be a boolean"):
        _read_content_type_settings({"content-type": {"enabled": "yes"}})


# ---------------------------------------------------------------------------
# [[tool.pitloom.content-type.override]]
# ---------------------------------------------------------------------------


def test_read_content_type_settings_override_valid() -> None:
    """Valid entries parse to ContentTypeOverride tuples, in declaration order."""
    pitloom_data = {
        "content-type": {
            "override": [
                {"pattern": "*.woff2", "content-type": "font/woff2"},
                {"pattern": "vendor/*", "content-type": "application/octet-stream"},
            ]
        }
    }
    _, _, overrides = _read_content_type_settings(pitloom_data)
    assert overrides == (
        ContentTypeOverride(pattern="*.woff2", content_type="font/woff2"),
        ContentTypeOverride(
            pattern="vendor/*", content_type="application/octet-stream"
        ),
    )


def test_read_content_type_settings_override_absent_defaults_empty() -> None:
    pitloom_data = {"content-type": {"enabled": True}}
    _, _, overrides = _read_content_type_settings(pitloom_data)
    assert not overrides


def test_read_content_type_settings_override_non_list_raises() -> None:
    """'override' must be an array (of tables)."""
    pitloom_data = {"content-type": {"override": "not-a-list"}}
    with pytest.raises(ValueError, match="must be an array of tables"):
        _read_content_type_settings(pitloom_data)


def test_read_content_type_settings_override_entry_non_table_raises() -> None:
    pitloom_data = {"content-type": {"override": ["not-a-table"]}}
    with pytest.raises(ValueError, match="entries must be tables"):
        _read_content_type_settings(pitloom_data)


def test_read_content_type_settings_override_missing_pattern() -> None:
    pitloom_data = {
        "content-type": {"override": [{"content-type": "image/png"}]},
    }
    with pytest.raises(ValueError, match="'pattern' must be a non-empty string"):
        _read_content_type_settings(pitloom_data)


def test_read_content_type_settings_override_empty_pattern() -> None:
    """An empty-string 'pattern' raises -- non-empty is required."""
    pitloom_data = {
        "content-type": {"override": [{"pattern": "", "content-type": "image/png"}]},
    }
    with pytest.raises(ValueError, match="'pattern' must be a non-empty string"):
        _read_content_type_settings(pitloom_data)


def test_read_content_type_settings_override_missing_content_type() -> None:
    pitloom_data = {
        "content-type": {"override": [{"pattern": "*.png"}]},
    }
    with pytest.raises(ValueError, match="'content-type' must be a MIME type"):
        _read_content_type_settings(pitloom_data)


def test_read_content_type_settings_override_malformed_content_type() -> None:
    """A 'content-type' value not shaped like 'type/subtype' raises."""
    pitloom_data = {
        "content-type": {"override": [{"pattern": "*.png", "content-type": "PNG"}]},
    }
    with pytest.raises(ValueError, match="'content-type' must be a MIME type"):
        _read_content_type_settings(pitloom_data)


# ---------------------------------------------------------------------------
# _read_ids_file
# ---------------------------------------------------------------------------


def test_read_ids_file_defaults_none_when_absent() -> None:
    assert _read_ids_file({}) is None


def test_read_ids_file_explicit_string() -> None:
    assert _read_ids_file({"ids-file": "loom-ids.json"}) == "loom-ids.json"


def test_read_ids_file_non_string_raises() -> None:
    with pytest.raises(ValueError, match="'ids-file' must be a string"):
        _read_ids_file({"ids-file": 123})


# ---------------------------------------------------------------------------
# _read_enrich_settings
# ---------------------------------------------------------------------------


def test_read_enrich_settings_defaults_false_when_absent() -> None:
    assert _read_enrich_settings({}) is False


def test_read_enrich_settings_explicit_true() -> None:
    assert _read_enrich_settings({"enrich": True}) is True


def test_read_enrich_settings_non_bool_raises() -> None:
    with pytest.raises(ValueError, match="'enrich' must be a boolean"):
        _read_enrich_settings({"enrich": "yes"})


# ---------------------------------------------------------------------------
# _read_fragments
# ---------------------------------------------------------------------------


def test_read_fragments_defaults_empty_when_absent() -> None:
    assert _read_fragments({}) == []


def test_read_fragments_reads_singular_table() -> None:
    pitloom_data = {"fragment": {"files": ["a.json", "b.json"]}}
    assert _read_fragments(pitloom_data) == ["a.json", "b.json"]
