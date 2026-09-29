# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for [tool.pitloom] config parsing: extract-file-header,
[tool.pitloom.content-type], id-registry, enrich, [tool.pitloom.fragment].

See also: test_config_moved_keys.py (moved-key guards, PitloomConfig
helper properties, provenance, sbom-basename -- split out of this file,
see AGENTS.md's file-size rule).
"""

import pytest

from pitloom.core.config import (
    FragmentConfig,
    _read_content_type_settings,
    _read_enrich_settings,
    _read_extract_file_header,
    _read_fragments,
    _read_id_registry,
    _read_use_lockfile_setting,
    parse_pitloom_config,
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
# _read_id_registry
# ---------------------------------------------------------------------------


def test_read_id_registry_defaults_none_when_absent() -> None:
    assert _read_id_registry({}) is None


def test_read_id_registry_explicit_string() -> None:
    assert (
        _read_id_registry({"id-registry": "loom-id-registry.json"})
        == "loom-id-registry.json"
    )


def test_read_id_registry_non_string_raises() -> None:
    with pytest.raises(ValueError, match="'id-registry' must be a string"):
        _read_id_registry({"id-registry": 123})


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
# _read_use_lockfile_setting
# ---------------------------------------------------------------------------


def test_read_use_lockfile_setting_defaults_true_when_absent() -> None:
    """Unlike ``offline``/``enrich``, this is opt-out: on by default."""
    assert _read_use_lockfile_setting({}) is True


def test_read_use_lockfile_setting_explicit_false() -> None:
    assert _read_use_lockfile_setting({"use-lockfile": False}) is False


def test_read_use_lockfile_setting_non_bool_raises() -> None:
    with pytest.raises(ValueError, match="'use-lockfile' must be a boolean"):
        _read_use_lockfile_setting({"use-lockfile": "yes"})


def test_parse_pitloom_config_use_lockfile_default_true() -> None:
    assert parse_pitloom_config({}).use_lockfile is True


def test_parse_pitloom_config_use_lockfile_false() -> None:
    config = parse_pitloom_config({"tool": {"pitloom": {"use-lockfile": False}}})
    assert config.use_lockfile is False


# ---------------------------------------------------------------------------
# _read_fragments
# ---------------------------------------------------------------------------


def test_read_fragments_defaults_empty_when_absent() -> None:
    assert _read_fragments({}) == []


def test_read_fragments_reads_singular_table() -> None:
    pitloom_data = {"fragment": {"files": ["a.json", "b.json"]}}
    assert _read_fragments(pitloom_data) == [
        FragmentConfig(path="a.json"),
        FragmentConfig(path="b.json"),
    ]


def test_read_fragments_table_entry_with_all_fields() -> None:
    """An inline table entry with every field set must land on the
    FragmentConfig unchanged."""
    pitloom_data = {
        "fragment": {
            "files": [
                {
                    "path": "model.spdx3.json",
                    "role": "ai_model",
                    "description": "fine-tune training provenance",
                    "required": True,
                    "sha256": "a3f1",
                    "link-to-main": "trainedOn",
                }
            ]
        }
    }
    assert _read_fragments(pitloom_data) == [
        FragmentConfig(
            path="model.spdx3.json",
            role="ai_model",
            description="fine-tune training provenance",
            required=True,
            sha256="a3f1",
            link_to_main="trainedOn",
        )
    ]


def test_read_fragments_unrecognised_role_value_still_parses() -> None:
    """role is genuinely unvalidated -- any string is accepted."""
    pitloom_data = {"fragment": {"files": [{"path": "a.json", "role": "widget"}]}}
    assert _read_fragments(pitloom_data) == [
        FragmentConfig(path="a.json", role="widget")
    ]


def test_read_fragments_mixes_plain_string_and_table_entries() -> None:
    """A files array may mix a plain string and an inline table -- the
    backward-compatible case the FragmentConfig roadmap item is about."""
    pitloom_data = {
        "fragment": {
            "files": [
                "plain.spdx3.json",
                {"path": "table.spdx3.json", "role": "dataset"},
            ]
        }
    }
    assert _read_fragments(pitloom_data) == [
        FragmentConfig(path="plain.spdx3.json"),
        FragmentConfig(path="table.spdx3.json", role="dataset"),
    ]


def test_read_fragments_table_entry_missing_path_raises() -> None:
    pitloom_data = {"fragment": {"files": [{"role": "ai_model"}]}}
    with pytest.raises(ValueError, match="valid 'path'"):
        _read_fragments(pitloom_data)


def test_read_fragments_plain_string_empty_path_raises() -> None:
    """An empty-string plain entry must be rejected the same way an
    empty/missing 'path' is rejected for the table-entry form -- the same
    field, validated the same way regardless of which TOML shape it's
    written in."""
    pitloom_data = {"fragment": {"files": [""]}}
    with pytest.raises(ValueError, match="must not be an empty string"):
        _read_fragments(pitloom_data)


def test_read_fragments_table_entry_non_bool_required_raises() -> None:
    pitloom_data = {"fragment": {"files": [{"path": "a.json", "required": "yes"}]}}
    with pytest.raises(ValueError, match="'required' must be a boolean"):
        _read_fragments(pitloom_data)


def test_read_fragments_entry_neither_string_nor_table_raises() -> None:
    pitloom_data = {"fragment": {"files": [42]}}
    with pytest.raises(ValueError, match="must each be a string or table"):
        _read_fragments(pitloom_data)


@pytest.mark.parametrize("files", ["a.json", {"path": "a.json"}, 3])
def test_read_fragments_files_not_a_list_raises(files: object) -> None:
    """A malformed 'files' is the user's opinion delivered wrongly, not an
    absent setting: it raises, as a wrong-shaped [tool.pitloom.provenance]
    or [tool.pitloom.content-type] does, instead of dropping every fragment
    (a ``required`` one included) without a word."""
    with pytest.raises(ValueError, match="'files' must be an array"):
        _read_fragments({"fragment": {"files": files}})


def test_read_fragments_fragment_not_a_table_raises() -> None:
    with pytest.raises(ValueError, match=r"\[tool.pitloom.fragment\] must be a table"):
        _read_fragments({"fragment": 3})


def test_read_fragments_table_entry_non_str_role_raises() -> None:
    pitloom_data = {"fragment": {"files": [{"path": "a.json", "role": 1}]}}
    with pytest.raises(ValueError, match="'role' must be a string"):
        _read_fragments(pitloom_data)


def test_read_fragments_table_entry_non_str_description_raises() -> None:
    pitloom_data = {"fragment": {"files": [{"path": "a.json", "description": ["x"]}]}}
    with pytest.raises(ValueError, match="'description' must be a string"):
        _read_fragments(pitloom_data)


def test_read_fragments_table_entry_non_str_sha256_raises() -> None:
    pitloom_data = {"fragment": {"files": [{"path": "a.json", "sha256": 123}]}}
    with pytest.raises(ValueError, match="'sha256' must be a string"):
        _read_fragments(pitloom_data)


def test_read_fragments_table_entry_non_str_link_to_main_raises() -> None:
    pitloom_data = {"fragment": {"files": [{"path": "a.json", "link-to-main": False}]}}
    with pytest.raises(ValueError, match="'link-to-main' must be a string"):
        _read_fragments(pitloom_data)
