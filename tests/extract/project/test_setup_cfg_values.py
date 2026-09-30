# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every boolean and integer ``setup.cfg`` ``[tool:pitloom]`` key reads as its
``pyproject.toml`` counterpart does.

See also:
- :mod:`tests.extract.project.test_setuptools_cfg_config` for the rest of
  the ``[tool:pitloom]`` read.
- :mod:`tests.assemble.test_setup_cfg_typed_keys` for the same keys on
  every surface.
"""

from __future__ import annotations

import dataclasses

import pytest

from pitloom.core.config import (
    BOOL_KEYS,
    INT_KEYS,
    PitloomConfig,
    parse_pitloom_config,
)
from pitloom.extract._toml_io import load_toml_bytes
from pitloom.extract.project.setuptools_cfg import setup_cfg_pitloom_config

#: ``PitloomConfig`` field -> (sub-table, key) it is read from. ``tools`` is
#: the one non-bool field a boolean key (``no-creation-tool``) decides.
_FIELD_KEYS: dict[str, tuple[str, str]] = {
    "pretty": ("", "pretty"),
    "describe_relationship": ("", "describe-relationship"),
    "update_id_registry": ("", "update-id-registry"),
    "provenance_max_source_metadata_bytes": (
        "provenance",
        "max-source-metadata-bytes",
    ),
    "enrich_local": ("", "enrich"),
    "extract_file_header": ("", "extract-file-header"),
    "scan_model_usage": ("", "scan-model-usage"),
    "max_model_extract_bytes": ("", "max-model-extract-bytes"),
    "content_type_enabled": ("content-type", "enabled"),
    "offline": ("", "offline"),
    "use_lockfile": ("", "use-lockfile"),
    "tools": ("creation", "no-creation-tool"),
}

#: INI spelling -> the TOML literal it must read as.
_BOOL_VALUES = {
    "true": "true",
    "false": "false",
    "yes": "true",
    "no": "false",
    "1": "true",
    "0": "false",
    "TRUE": "true",
    "False": "false",
}
_INT_VALUES = ("0", "100", "4096", "+100")
_INVALID_BOOL = ("maybe", "2", "on")
_INVALID_INT = ("12x", "1.5", "true", "0x10", "\u0e54\u0e50\u0e59\u0e56", "\uff14")


def _is_typed(annotation: object) -> bool:
    """Whether a field annotation is a bool or int, optional or not."""
    parts = {p.strip() for p in str(annotation).split("|")} - {"None"}
    return bool(parts) and parts <= {"bool", "int"}


def _declared() -> list[tuple[str, str, bool]]:
    """(sub-table, key, is_int) for every declared key and spelling."""
    return sorted(
        [(t, k, False) for t, keys in BOOL_KEYS.items() for k in keys]
        + [(t, k, True) for t, keys in INT_KEYS.items() for k in keys]
    )


def _field_of(table: str, key: str) -> str:
    canonical = (table, key.replace("_", "-"))
    return next(f for f, tk in _FIELD_KEYS.items() if tk == canonical)


def _header(table: str, sep: str) -> str:
    return f"[tool{sep}pitloom{sep + table if table else ''}]"


def _from_cfg(table: str, body: str) -> PitloomConfig:
    return setup_cfg_pitloom_config(
        f"[metadata]\nname = demo\n{_header(table, ':')}\n{body}\n"
    )


def _from_toml(table: str, body: str) -> PitloomConfig:
    text = f"{_header(table, '.')}\n{body}\n"
    return parse_pitloom_config(load_toml_bytes(text.encode()))


def test_every_typed_field_is_mapped_and_declared() -> None:
    """A new boolean/integer ``PitloomConfig`` field fails here until it is
    mapped above and declared in ``BOOL_KEYS``/``INT_KEYS``."""
    typed = {f.name for f in dataclasses.fields(PitloomConfig) if _is_typed(f.type)}
    assert typed | {"tools"} == set(_FIELD_KEYS)
    declared = {(t, k.replace("_", "-")) for t, k, _ in _declared()}
    assert declared == set(_FIELD_KEYS.values())


@pytest.mark.parametrize(
    ("annotation", "typed"),
    [
        ("bool", True),
        ("int", True),
        ("bool | None", True),
        ("int | None", True),
        ("None | int", True),
        ("bool | int", True),
        ("str | None", False),
        ("int | str", False),
        ("list[int]", False),
        ("tuple[int, ...]", False),
        ("None", False),
    ],
)
def test_is_typed_classifies_optional_fields(annotation: str, typed: bool) -> None:
    """The guard above must not miss an optional (``int | None``) field."""
    assert _is_typed(annotation) is typed


def _outcome(config: str, field: str, table: str, body: str) -> tuple[str, object]:
    """The field's value, or the one-line error a rejected value raises."""
    read = _from_cfg if config == "cfg" else _from_toml
    try:
        return "value", getattr(read(table, body), field)
    except ValueError as exc:
        return "error", str(exc)


@pytest.mark.parametrize(("table", "key", "is_int"), _declared())
def test_setup_cfg_value_reads_as_pyproject(table: str, key: str, is_int: bool) -> None:
    """Value or error alike: a key that rejects some spelling (a ceiling
    rejects ``0``) must reject it from ``setup.cfg`` too."""
    field = _field_of(table, key)
    pairs = [(v, v) for v in _INT_VALUES] if is_int else list(_BOOL_VALUES.items())
    default = getattr(PitloomConfig(), field)
    results = []
    for ini, toml in pairs:
        got = _outcome("cfg", field, table, f"{key} = {ini}")
        assert got == _outcome("toml", field, table, f"{key} = {toml}"), ini
        results.append(got)
    # not vacuous: the key took effect, not just the default on both sides
    assert any(kind == "value" and v != default for kind, v in results)


@pytest.mark.parametrize(
    ("table", "key", "value"),
    [
        (t, k, v)
        for t, k, is_int in _declared()
        for v in (_INVALID_INT if is_int else _INVALID_BOOL) + ("",)
    ],
)
def test_invalid_or_empty_value_is_one_error(table: str, key: str, value: str) -> None:
    """An unparsable or empty (declared-but-valueless) value fails with the
    ``pyproject.toml`` error shape, never falls back to the default."""
    kind = "an integer" if key in INT_KEYS.get(table, ()) else "a boolean"
    with pytest.raises(ValueError, match=f"must be {kind}") as exc:
        _from_cfg(table, f"{key} = {value}")
    assert "\n" not in str(exc.value)


@pytest.mark.parametrize(("table", "key", "_is_int"), _declared())
def test_absent_key_is_the_default(table: str, key: str, _is_int: bool) -> None:
    field = _field_of(table, key)
    config = _from_cfg(table, "")  # section declared, key absent
    assert getattr(config, field) == getattr(PitloomConfig(), field)


@pytest.mark.parametrize("top", ["no-creation-tool", "no_creation_tool"])
@pytest.mark.parametrize("own", ["no-creation-tool", "no_creation_tool"])
def test_top_level_no_creation_tool_yields_to_creation_section(
    top: str, own: str
) -> None:
    """``[tool:pitloom:creation]``'s own value wins in either spelling."""
    body = f"{top} = yes\n[tool:pitloom:creation]\n{own} = no"
    assert _from_cfg("", body).tools is None
    assert _from_cfg("", f"{top} = yes").tools == []


def test_untyped_key_stays_a_string() -> None:
    config = _from_cfg("", "sbom-basename =  demo.spdx3.json ")
    assert config.sbom_basename == "demo.spdx3.json"
