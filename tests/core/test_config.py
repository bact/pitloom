# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for [tool.pitloom] config parsing: extract-file-header,
[tool.pitloom.content-type], ids-file, enrich, [tool.pitloom.fragment]."""

import pytest

from pitloom.core.config import (
    VALID_CONTENT_TYPE_METHODS,
    PitloomConfig,
    _read_content_type_settings,
    _read_enrich_settings,
    _read_extract_file_header,
    _read_fragments,
    _read_ids_file,
    parse_pitloom_config,
)
from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.creation import Creator, Tool

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
    with pytest.raises(ValueError, match="entry must be a table"):
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


# ---------------------------------------------------------------------------
# Old-shaped keys raise instead of being silently ignored (moved-keys guard)
# ---------------------------------------------------------------------------


def test_old_ids_table_raises_instead_of_silently_ignored() -> None:
    """A leftover [tool.pitloom.ids] table must error, not silently
    revert ids-file to auto-discovery."""
    data = {"tool": {"pitloom": {"ids": {"file": "custom-ids.json"}}}}
    with pytest.raises(ValueError, match=r"\[tool\.pitloom\.ids\] has moved to"):
        parse_pitloom_config(data)


def test_old_fragments_table_raises_instead_of_silently_ignored() -> None:
    """A leftover plural [tool.pitloom.fragments] table must error, not
    silently drop every registered fragment from the SBOM."""
    data = {"tool": {"pitloom": {"fragments": {"files": ["a.json"]}}}}
    with pytest.raises(ValueError, match=r"\[tool\.pitloom\.fragments\] has moved to"):
        parse_pitloom_config(data)


def test_old_file_headers_table_raises_instead_of_silently_ignored() -> None:
    """A leftover [tool.pitloom.file-headers] table must error, not
    silently revert extract-file-header/content-type to their new
    defaults (the opposite of the project's configured intent)."""
    data = {
        "tool": {
            "pitloom": {"file-headers": {"enabled": False, "detect-content-type": True}}
        }
    }
    with pytest.raises(
        ValueError, match=r"\[tool\.pitloom\.file-headers\] has moved to"
    ):
        parse_pitloom_config(data)


def test_old_enrich_table_raises_instead_of_silently_ignored() -> None:
    """A leftover table-shaped [tool.pitloom.enrich] must error with a
    clear message, not the generic 'must be a boolean, got dict' it would
    otherwise surface."""
    data = {"tool": {"pitloom": {"enrich": {"local": True}}}}
    with pytest.raises(ValueError, match=r"\[tool\.pitloom\.enrich\] has moved to"):
        parse_pitloom_config(data)


def test_new_style_config_unaffected_by_moved_keys_guard() -> None:
    """The guard must not false-positive on the current, correct shape."""
    data = {
        "tool": {
            "pitloom": {
                "ids-file": "loom-ids.json",
                "fragment": {"files": ["a.json"]},
                "extract-file-header": False,
                "enrich": True,
                "content-type": {"enabled": True},
            }
        }
    }
    config = parse_pitloom_config(data)
    assert config.ids_file == "loom-ids.json"
    assert config.fragments == ["a.json"]
    assert config.extract_file_header is False
    assert config.enrich_local is True
    assert config.content_type_enabled is True


# ---------------------------------------------------------------------------
# VALID_CONTENT_TYPE_METHODS export (shared by CLI/API, not just config.py)
# ---------------------------------------------------------------------------


def test_valid_content_type_methods_is_public() -> None:
    assert VALID_CONTENT_TYPE_METHODS == frozenset({"auto", "magika", "extension"})


def test_pitloom_config_helper_properties() -> None:
    """Test PitloomConfig properties convert scalar fields to model objects."""
    cfg = PitloomConfig(
        provenance_format="annotation",
        provenance_schema="spdx3",
        provenance_detail="full",
        provenance_preserve_source_metadata="always",
        content_type_enabled=True,
        content_type_method="magika",
        enrich_local=True,
        creators=[Creator(name="Alice", type="person")],
        tools=[Tool(name="Pitloom")],
        creation_datetime="2026-08-14T00:00:00Z",
        creation_comment="Test comment",
    )

    prov = cfg.provenance
    assert prov.format == "annotation"
    assert prov.schema == "spdx3"
    assert prov.detail == "full"
    assert prov.preserve_source_metadata == "always"

    ct = cfg.content_type
    assert ct.enabled is True
    assert ct.method == "magika"

    enrich = cfg.enrich
    assert enrich.local is True

    creation = cfg.creation_metadata
    assert len(creation.creators) == 1
    assert creation.creators[0].name == "Alice"
    assert creation.tools is not None and len(creation.tools) == 1
    assert creation.creation_datetime == "2026-08-14T00:00:00Z"
    assert creation.creation_comment == "Test comment"


def test_read_provenance_non_table_raises() -> None:
    data = {"tool": {"pitloom": {"provenance": "string"}}}
    with pytest.raises(ValueError, match="must be a table"):
        parse_pitloom_config(data)


def test_read_provenance_non_string_key_raises() -> None:
    data = {"tool": {"pitloom": {"provenance": {"format": 123}}}}
    with pytest.raises(ValueError, match="must be a string"):
        parse_pitloom_config(data)


def test_read_provenance_invalid_format_raises() -> None:
    data = {"tool": {"pitloom": {"provenance": {"format": "invalid"}}}}
    with pytest.raises(ValueError, match="must be one of"):
        parse_pitloom_config(data)


def test_parse_pitloom_config_non_table_creation_falls_back_empty() -> None:
    """A ``[tool.pitloom.creation]`` value that isn't a table (e.g. a bare
    string) is treated as absent rather than raising -- other sections of
    ``[tool.pitloom]`` are unaffected."""
    data = {
        "tool": {
            "pitloom": {
                "creation": "not-a-table",
                "ids-file": "loom-ids.json",
            }
        }
    }
    config = parse_pitloom_config(data)
    assert config.ids_file == "loom-ids.json"
    assert config.creation_datetime is None
    assert config.creation_comment is None


def test_parse_pitloom_config_describe_relationship_non_bool_raises() -> None:
    data = {"tool": {"pitloom": {"describe-relationship": "yes"}}}
    with pytest.raises(ValueError, match="describe-relationship must be a boolean"):
        parse_pitloom_config(data)


def test_read_provenance_invalid_detail_raises() -> None:
    data = {"tool": {"pitloom": {"provenance": {"detail": "invalid"}}}}
    with pytest.raises(ValueError, match="must be one of"):
        parse_pitloom_config(data)
