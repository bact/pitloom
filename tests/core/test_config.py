# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for [tool.pitloom] config parsing: extract-file-header,
[tool.pitloom.content-type], id-registry, enrich, [tool.pitloom.fragment]."""

import pytest

from pitloom._embed_wheel import _validate_sbom_filename
from pitloom.core.config import (
    VALID_CONTENT_TYPE_METHODS,
    FragmentConfig,
    PitloomConfig,
    _read_content_type_settings,
    _read_enrich_settings,
    _read_extract_file_header,
    _read_fragments,
    _read_id_registry,
    _read_use_lockfile_setting,
    parse_pitloom_config,
)
from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.creation import Creator, Tool
from pitloom.core.file_names import is_plain_file_name

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


# ---------------------------------------------------------------------------
# Old-shaped keys raise instead of being silently ignored (moved-keys guard)
# ---------------------------------------------------------------------------


def test_old_ids_table_raises_instead_of_silently_ignored() -> None:
    """A leftover [tool.pitloom.ids] table must error, not silently
    revert id-registry to auto-discovery."""
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
                "id-registry": "loom-id-registry.json",
                "fragment": {"files": ["a.json"]},
                "extract-file-header": False,
                "enrich": True,
                "content-type": {"enabled": True},
            }
        }
    }
    config = parse_pitloom_config(data)
    assert config.id_registry == "loom-id-registry.json"
    assert config.fragments == [FragmentConfig(path="a.json")]
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
        provenance_max_source_metadata_bytes=5000,
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
    assert prov.max_source_metadata_bytes == 5000

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


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"tool": 3}, r"\[tool\] must be a table"),
        ({"tool": {"pitloom": 3}}, r"\[tool.pitloom\] must be a table"),
        (
            {"tool": {"pitloom": {"creation": "not-a-table"}}},
            r"\[tool.pitloom.creation\] must be a table",
        ),
        (
            {"tool": {"pitloom": {"creation": {"creation-datetime": 3}}}},
            "'creation-datetime' must be a string",
        ),
        (
            {"tool": {"pitloom": {"sbom-basename": 3}}},
            "'sbom-basename' must be a string",
        ),
    ],
    ids=["tool", "pitloom", "creation", "creation-datetime", "sbom-basename"],
)
def test_parse_pitloom_config_wrong_shape_raises(
    data: dict[str, object], match: str
) -> None:
    """A present value of the wrong type raises a ValueError naming the key,
    never degrades to the default (it would silently drop the user's
    setting) nor crashes later with an AttributeError."""
    with pytest.raises(ValueError, match=match):
        parse_pitloom_config(data)


def test_parse_pitloom_config_absent_tables_are_defaults() -> None:
    """Absent is not wrong: no [tool], no [tool.pitloom], an empty
    ``sbom-basename`` all give the defaults."""
    assert parse_pitloom_config({}) == parse_pitloom_config({"tool": {}})
    config = parse_pitloom_config({"tool": {"pitloom": {"sbom-basename": ""}}})
    assert config.sbom_basename is None


def test_parse_pitloom_config_describe_relationship_non_bool_raises() -> None:
    data = {"tool": {"pitloom": {"describe-relationship": "yes"}}}
    with pytest.raises(ValueError, match="describe-relationship must be a boolean"):
        parse_pitloom_config(data)


def test_read_provenance_invalid_detail_raises() -> None:
    data = {"tool": {"pitloom": {"provenance": {"detail": "invalid"}}}}
    with pytest.raises(ValueError, match="must be one of"):
        parse_pitloom_config(data)


@pytest.mark.parametrize(
    "value",
    ["../escaped", "sub/name", "a\\b", "/abs", "C:name", ".", "..", "a\x00b", "  "],
)
def test_sbom_basename_must_be_a_file_name(value: str) -> None:
    """A config -- possibly a third-party sdist's -- must not choose where
    the SBOM is written."""
    with pytest.raises(ValueError, match="'sbom-basename' must be a file name"):
        parse_pitloom_config({"tool": {"pitloom": {"sbom-basename": value}}})


def test_sbom_basename_plain_name_is_kept() -> None:
    data = {"tool": {"pitloom": {"sbom-basename": "demo-1.0..sbom"}}}
    assert parse_pitloom_config(data).sbom_basename == "demo-1.0..sbom"


def test_config_and_embed_flag_share_one_file_name_rule() -> None:
    """Drift guard: the ``sbom-basename`` key and the embedded name agree."""
    for name in ("ok", "a:b", "a/b", "..", "a\x00b", "  ", "x.spdx3.json"):
        data = {"tool": {"pitloom": {"sbom-basename": name}}}
        try:
            parse_pitloom_config(data)
            key_ok = True
        except ValueError:
            key_ok = False
        try:
            _validate_sbom_filename(name)
            flag_ok = True
        except ValueError:
            flag_ok = False
        assert key_ok == flag_ok == is_plain_file_name(name), name
