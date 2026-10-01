# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Both halves of the configuration cascade.

:func:`~pitloom.core.config_cascade.apply_overrides` is where "the flag
wins, the config is the fallback" is decided once for every surface, so
these guard its two easy-to-break properties: an override of ``False``/``0``
is an explicit choice rather than an absence, and the *resulting* config is
what gets validated, not just the override.

:func:`~pitloom.core.config_cascade.load_config_file` reads a config the
user named explicitly (``--config``); unlike a target's own config, every
failure of that read is fatal, since the user asked for that file.

See also:
- :mod:`tests.assemble.test_embed_build_seam` for the resolved values
  reaching the assembler on each surface.
- :mod:`tests.assemble.test_embed_overrides` for what ``embed-wheel`` does
  with a merged config.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import (
    ConfigOverrides,
    apply_overrides,
    load_config_file,
    resolve_standalone_config,
)
from pitloom.core.provenance import ProvenanceConfig


def test_apply_overrides_full() -> None:
    """Test apply_overrides applies all CLI override parameters."""
    cfg = PitloomConfig()
    prov = ProvenanceConfig(
        format="fields",
        schema="https://example.com/schema",
        detail="full",
        preserve_source_metadata="always",
    )
    overridden = apply_overrides(
        cfg,
        ConfigOverrides(
            provenance=prov,
            enrich=True,
            extract_file_header=False,
            content_type=True,
            content_type_method="extension",
            offline=True,
        ),
    )
    assert overridden.provenance_format == "fields"
    assert overridden.provenance_schema == "https://example.com/schema"
    assert overridden.provenance_detail == "full"
    assert overridden.provenance_preserve_source_metadata == "always"
    assert overridden.enrich_local is True
    assert overridden.extract_file_header is False
    assert overridden.content_type.enabled is True
    assert overridden.content_type.method == "extension"
    assert overridden.offline is True

    with pytest.raises(ValueError, match="content_type_method must be one of"):
        apply_overrides(
            cfg,
            ConfigOverrides(content_type_method="invalid_method"),
        )


# Each boolean override and the PitloomConfig field it lands on. Two fields
# are renamed on the way across, which is itself worth pinning.
_BOOL_OVERRIDE_TO_CONFIG = {
    "enrich": "enrich_local",
    "extract_file_header": "extract_file_header",
    "scan_model_usage": "scan_model_usage",
    "content_type": "content_type_enabled",
    "offline": "offline",
    "pretty": "pretty",
    "describe_relationship": "describe_relationship",
    "update_id_registry": "update_id_registry",
}


def test_every_config_overrides_field_is_accounted_for() -> None:
    """A new override field must join the map above (and so get the
    both-ways test below), rather than silently going uncovered."""
    non_bool = {
        "provenance",
        "content_type_method",
        "max_source_metadata_bytes",
        "build_options",
        "trust_wheel_model",  # no config key, like build_options
    }
    assert set(_BOOL_OVERRIDE_TO_CONFIG) | non_bool == {
        f.name for f in dataclasses.fields(ConfigOverrides)
    }


@pytest.mark.parametrize("override_name", sorted(_BOOL_OVERRIDE_TO_CONFIG))
@pytest.mark.parametrize("value", [True, False])
def test_explicit_bool_override_beats_the_config_both_ways(
    override_name: str, value: bool
) -> None:
    """``False`` is an explicit choice, not an absence.

    Testing only the ``True`` direction cannot tell ``is not None`` apart
    from a truthiness check, and a truthiness check silently discards
    ``--no-offline``/``--no-pretty`` and every other opt-out (AGENTS.md's
    ``None`` vs empty tri-state rule). The config is seeded to the opposite
    value, so the override is the only possible source of the result.
    """
    config_name = _BOOL_OVERRIDE_TO_CONFIG[override_name]
    # Both field names are only known at run time, so the kwargs dicts are
    # typed Any; the assertion below is what pins the behaviour.
    seed: dict[str, Any] = {config_name: not value}
    override: dict[str, Any] = {override_name: value}
    merged = apply_overrides(PitloomConfig(**seed), ConfigOverrides(**override))
    assert getattr(merged, config_name) is value


def test_invalid_method_from_the_config_alone_is_rejected() -> None:
    """``apply_overrides`` validates the effective method, not just the
    override, so a hand-built config cannot smuggle one past a caller that
    overrode nothing. Only the public library API can reach this: the TOML
    reader and the CLI's ``choices=`` both reject it earlier."""
    with pytest.raises(ValueError, match="content_type_method must be one of"):
        apply_overrides(PitloomConfig(content_type_method="bogus"), ConfigOverrides())


def test_load_config_file_reads_every_key(tmp_path: Path) -> None:
    """Policy and identity alike: an explicitly named config applies in
    full, since the user asked for exactly that file."""
    path = tmp_path / "team.toml"
    path.write_text(
        '[tool.pitloom]\npretty = true\ncreation-comment = "from team"\n'
        '[[tool.pitloom.creator]]\nname = "Team"\ntype = "organization"\n',
        encoding="utf-8",
    )
    config = load_config_file(path)
    assert config.pretty is True
    assert config.creation_comment == "from team"
    assert [creator.name for creator in config.creators] == ["Team"]


def test_load_config_file_resolves_id_registry_against_its_own_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative ``id-registry`` means the same file whatever directory
    Pitloom runs from -- the one beside the config, never the cwd's."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    path = config_dir / "pyproject.toml"
    path.write_text('[tool.pitloom]\nid-registry = "ids/loom.json"\n', encoding="utf-8")
    monkeypatch.chdir(elsewhere)

    config = load_config_file(path)

    assert config.id_registry is not None
    assert Path(config.id_registry) == (config_dir / "ids" / "loom.json").resolve()


def test_load_config_file_keeps_an_absolute_id_registry(tmp_path: Path) -> None:
    target = tmp_path / "abs.json"
    path = tmp_path / "pyproject.toml"
    path.write_text(
        f"[tool.pitloom]\nid-registry = {json.dumps(str(target))}\n", encoding="utf-8"
    )
    assert load_config_file(path).id_registry == str(target)


@pytest.mark.parametrize("shape", ["missing", "directory"])
def test_load_config_file_fails_for_a_non_file(tmp_path: Path, shape: str) -> None:
    """A named config that is absent or a directory is a failed explicit
    source: raise, never degrade to defaults."""
    path = tmp_path / "pyproject.toml"
    if shape == "directory":
        path.mkdir()
    with pytest.raises(FileNotFoundError):
        load_config_file(path)


def test_load_config_file_fails_for_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.pitloom\ninvalid", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config_file(path)


@pytest.mark.parametrize(
    "payload",
    [
        b"[tool.pitloom\ninvalid",
        b"\xff\xfe[tool.pitloom]\n",
        b'[tool.pitloom]\npretty = "yes"\n',
        b"[tool.pitloom]\nfragment = []\n",
        b"tool = 3\n",
        b"[tool]\npitloom = 3\n",
    ],
    ids=[
        "invalid-toml",
        "not-utf8",
        "bad-value",
        "fragment-list",
        "tool-int",
        "pitloom-int",
    ],
)
def test_load_config_file_error_names_the_file(tmp_path: Path, payload: bytes) -> None:
    """Undecodable bytes or a wrong table shape are a ValueError too, never
    a bare UnicodeDecodeError/AttributeError traceback, and the message says
    which file."""
    path = tmp_path / "team.toml"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="team.toml"):
        load_config_file(path)


@pytest.mark.parametrize(
    ("content", "warns"),
    [
        ('[project]\nname = "x"\n', True),
        ("[tool.other]\nkey = 1\n", True),
        ("[tool.pitloom]\n", False),
    ],
    ids=["no-tool", "other-tool", "empty-pitloom"],
)
def test_load_config_file_warns_without_a_pitloom_table(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, content: str, warns: bool
) -> None:
    """A named file with no [tool.pitloom] table gives the defaults and one
    warning (a wrong path must not pass unnoticed); an empty table is a
    real, empty config and stays quiet."""
    path = tmp_path / "team.toml"
    path.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert load_config_file(path) == PitloomConfig()
    named = [r for r in caplog.records if "[tool.pitloom]" in r.getMessage()]
    assert len(named) == int(warns)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
def test_load_config_file_id_registry_follows_the_link_not_its_target(
    tmp_path: Path,
) -> None:
    """A relative id-registry resolves beside the path the user named."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "team.toml").write_text(
        '[tool.pitloom]\nid-registry = "loom.json"\n', encoding="utf-8"
    )
    link_dir = tmp_path / "link"
    link_dir.mkdir()
    (link_dir / "team.toml").symlink_to(real / "team.toml")

    config = load_config_file(link_dir / "team.toml")

    assert config.id_registry == str(link_dir / "loom.json")


def test_resolve_standalone_config_uses_only_explicit_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No config named: the built-in defaults, even with a cwd config that
    sets everything differently."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pitloom]\npretty = true\noffline = true\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert resolve_standalone_config(None, ConfigOverrides()) == PitloomConfig()
    named = PitloomConfig(pretty=True)
    assert resolve_standalone_config(named, ConfigOverrides()).pretty is True
    assert (
        resolve_standalone_config(named, ConfigOverrides(pretty=False)).pretty is False
    )


def test_max_source_metadata_bytes_override_keeps_sibling_provenance() -> None:
    """The byte-cap override replaces that one field only; every other
    provenance setting the config carried survives. Replacing the whole
    provenance object instead would silently reset ``detail`` here."""
    config = PitloomConfig(
        provenance_detail="full", provenance_max_source_metadata_bytes=7000
    )
    merged = apply_overrides(config, ConfigOverrides(max_source_metadata_bytes=5000))
    assert merged.provenance_detail == "full"
    assert merged.provenance_max_source_metadata_bytes == 5000
    assert config.provenance_detail != PitloomConfig().provenance_detail


def test_max_source_metadata_bytes_override_wins_over_provenance_object() -> None:
    merged = apply_overrides(
        PitloomConfig(),
        ConfigOverrides(
            provenance=ProvenanceConfig(max_source_metadata_bytes=9000),
            max_source_metadata_bytes=5000,
        ),
    )
    assert merged.provenance_max_source_metadata_bytes == 5000


def test_max_source_metadata_bytes_zero_clears_the_config_cap() -> None:
    """``0`` is an explicit "unbounded", not an absence."""
    merged = apply_overrides(
        PitloomConfig(provenance_max_source_metadata_bytes=7000),
        ConfigOverrides(max_source_metadata_bytes=0),
    )
    assert merged.provenance_max_source_metadata_bytes == 0


def test_max_source_metadata_bytes_too_small_warns_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        merged = apply_overrides(
            PitloomConfig(), ConfigOverrides(max_source_metadata_bytes=-1)
        )
    assert merged.provenance_max_source_metadata_bytes == 0
    assert caplog.text.count("too small") == 1


def _serialisation_signals(sbom_json: str) -> tuple[bool, bool]:
    """(pretty-printed, relationships described) for one SBOM."""
    relationships = [
        node
        for node in json.loads(sbom_json)["@graph"]
        if node.get("type") == "Relationship"
    ]
    assert relationships, "fixture must produce relationships to describe"
    return "\n  " in sbom_json, any("description" in r for r in relationships)


@pytest.mark.parametrize(
    ("setting", "via"),
    [
        pytest.param(setting, via, id=f"{setting}-via-{via}")
        for setting in ("pretty", "describe_relationship")
        for via in ("override", "config")
    ],
)
def test_project_serialisation_settings_reach_the_output(
    setting: str, via: str, tmp_path: Path
) -> None:
    """``pretty``/``describe_relationship`` only act at serialisation, the
    last step of ``generate_project_sbom``, so a value the cascade resolved
    correctly can still be dropped on the way out. Each is turned on from
    exactly one source and must show up in the output -- and only that
    one, which is what makes the other's absence a real check.
    """
    toml_key = setting.replace("_", "-")
    config = f"\n[tool.pitloom]\n{toml_key} = true\n" if via == "config" else ""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "cascade-pkg"\nversion = "1.0.0"\n'
        'dependencies = ["somedep"]\n' + config,
        encoding="utf-8",
    )
    overrides: dict[str, Any] = {setting: True} if via == "override" else {}

    pretty, described = _serialisation_signals(
        generate_project_sbom(tmp_path, offline=True, **overrides)
    )

    assert (pretty, described) == (setting == "pretty", setting != "pretty")


def test_project_serialisation_settings_default_off(tmp_path: Path) -> None:
    """The baseline both cases above differ from: with neither given,
    neither signal appears, so their presence is never incidental."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "cascade-pkg"\nversion = "1.0.0"\n'
        'dependencies = ["somedep"]\n',
        encoding="utf-8",
    )
    assert _serialisation_signals(generate_project_sbom(tmp_path, offline=True)) == (
        False,
        False,
    )


def test_load_config_file_fragments_resolve_beside_it(tmp_path: Path) -> None:
    """A fragment path keeps its written form (it is recorded in the SBOM)
    and gains the config file's directory as its base."""
    path = tmp_path / "ci" / "c.toml"
    path.parent.mkdir()
    path.write_text(
        '[tool.pitloom.fragment]\nfiles = ["frag.spdx3.json"]\n', encoding="utf-8"
    )
    (fragment,) = load_config_file(path).fragments
    assert fragment.path == "frag.spdx3.json"
    assert fragment.base_dir == str(path.parent)
