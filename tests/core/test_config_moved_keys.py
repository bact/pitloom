# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for [tool.pitloom] moved-key guards, PitloomConfig helper
properties, [tool.pitloom.provenance], and sbom-basename validation
(split out of test_config.py -- see AGENTS.md's file-size rule).

See also: test_config.py (extract-file-header, content-type, id-registry,
enrich, fragment settings).
"""

import pytest

from pitloom._embed_wheel import _validate_sbom_filename
from pitloom.core.config import (
    VALID_CONTENT_TYPE_METHODS,
    FragmentConfig,
    PitloomConfig,
    parse_pitloom_config,
)
from pitloom.core.creation import Creator, Tool
from pitloom.core.file_names import is_plain_file_name


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


def test_old_ids_file_key_raises_instead_of_silently_ignored() -> None:
    """A leftover flat ``ids-file`` key (PR A2's rename target) must error
    with the exact moved-key message, not silently be ignored."""
    data = {"tool": {"pitloom": {"ids-file": "custom-ids.json"}}}
    with pytest.raises(
        ValueError,
        match=r"\[tool\.pitloom\] 'ids-file' has moved to 'id-registry'\. "
        r"Update your config\.",
    ):
        parse_pitloom_config(data)


def test_old_update_registry_key_raises_instead_of_silently_ignored() -> None:
    """A leftover flat ``update-registry`` key must error with the exact
    moved-key message, not silently be ignored."""
    data = {"tool": {"pitloom": {"update-registry": True}}}
    with pytest.raises(
        ValueError,
        match=r"\[tool\.pitloom\] 'update-registry' has moved to "
        r"'update-id-registry'\. Update your config\.",
    ):
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
