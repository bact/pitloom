# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A moved key names where it went (every key of the moved-key tables,
through the reader, from ``pyproject.toml`` and ``setup.cfg``), and a
``--config`` file's own refusals name the file once.

See also: tests/messages/test_config_surfaces.py (the other lines from the
readers) and tests/messages/test_config_drift.py (the destinations against
the table).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pitloom.core._config_legacy import (
    _MOVED_CREATION_KEYS,
    _MOVED_FLAT_KEYS,
    _MOVED_TOP_LEVEL_TABLES,
)
from pitloom.core.config import parse_pitloom_config
from pitloom.core.config_cascade import load_config_file
from pitloom.extract.project.setuptools_cfg import setup_cfg_pitloom_config
from pitloom.messages import CodedValueError, code_of
from pitloom.messages.config import CONFIG_INVALID, CONFIG_MALFORMED, CONFIG_MOVED

pytestmark = pytest.mark.platform

_CFG_BASE = "[metadata]\nname = demo\nversion = 1\n"


def _moved_cases() -> list[Any]:
    cases = [
        pytest.param(
            {"creation": {key: "x"}}, f"[tool.pitloom.creation] {key}", dest, id=key
        )
        for key, dest in _MOVED_CREATION_KEYS.items()
    ]
    cases += [
        pytest.param({key: "x"}, f"[tool.pitloom] {key}", dest, id=f"top-{key}")
        for key, dest in _MOVED_CREATION_KEYS.items()
        if key not in ("creation-tool", "creation_tool")
    ]
    cases += [
        pytest.param({key: {"a": 1}}, f"[tool.pitloom] {key}", dest, id=f"table-{key}")
        for key, dest in _MOVED_TOP_LEVEL_TABLES.items()
    ]
    cases += [
        pytest.param({key: "x"}, f"[tool.pitloom] {key}", dest, id=f"flat-{key}")
        for key, dest in _MOVED_FLAT_KEYS.items()
    ]
    return cases


@pytest.mark.parametrize(("pitloom", "place", "destination"), _moved_cases())
def test_a_moved_key_names_where_it_went(
    pitloom: dict[str, Any], place: str, destination: str
) -> None:
    """Every key of the moved-key tables, through the reader, both sources:
    the destination is TOML's spelling whichever file the key sat in."""
    data = {"tool": {"pitloom": pitloom}}
    with pytest.raises(ValueError) as from_toml:
        parse_pitloom_config(data, source="pyproject.toml")
    assert str(from_toml.value) == (
        f"FILE=pyproject.toml: {place}: moved to {destination}"
    )
    assert code_of(from_toml.value) == CONFIG_MOVED.code
    with pytest.raises(ValueError) as from_ini:
        parse_pitloom_config(data, is_setup_cfg=True, source="setup.cfg")
    ini_place = place.replace("[tool.pitloom", "[tool:pitloom").replace(
        "pitloom.creation]", "pitloom:creation]"
    )
    assert str(from_ini.value) == (
        f"FILE=setup.cfg: {ini_place}: moved to {destination}"
    )


@pytest.mark.parametrize(
    ("body", "place", "destination"),
    [
        ("ids-file = x", "[tool:pitloom] ids-file", "[tool.pitloom] id-registry"),
        (
            "update-registry = true",
            "[tool:pitloom] update-registry",
            "[tool.pitloom] update-id-registry",
        ),
    ],
    ids=["ids-file", "update-registry"],
)
def test_setup_cfg_moved_keys_name_the_toml_destination(
    body: str, place: str, destination: str
) -> None:
    """A real ``setup.cfg``: the key is in the ``[tool:pitloom]`` table, the
    destination is in the table's TOML spelling."""
    with pytest.raises(ValueError) as caught:
        setup_cfg_pitloom_config(f"{_CFG_BASE}[tool:pitloom]\n{body}\n", "setup.cfg")
    assert str(caught.value) == f"FILE=setup.cfg: {place}: moved to {destination}"
    assert code_of(caught.value) == "config-moved"


def test_a_toml_error_in_a_crlf_file_names_its_line_once(tmp_path: Path) -> None:
    """``--config``: line 3 of a CRLF file, one ``FILE=`` and no prefix before
    it (the caller wrapped a coded error before)."""
    path = tmp_path / "c.toml"
    path.write_bytes(b"[tool.pitloom]\r\npretty = true\r\nbroken = = 1\r\n")
    with pytest.raises(CodedValueError) as caught:
        load_config_file(path)
    text = str(caught.value)
    assert text.startswith(f"FILE={path}: not valid TOML; ")
    assert "(at line 3," in text and text.count("FILE=") == 1
    assert code_of(caught.value) == CONFIG_MALFORMED.code


def test_a_config_file_with_a_bad_value_names_the_file_once(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    path.write_text('[tool.pitloom]\npretty = "maybe"\n', encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        load_config_file(path)
    assert str(caught.value) == (
        f"FILE={path}: [tool.pitloom] pretty: must be true or false, "
        "got a string 'maybe'"
    )
    assert code_of(caught.value) == CONFIG_INVALID.code


# Every old spelling is written out (the tests above iterate the tables
# themselves, so a key dropped from one loses its case and the old key
# becomes a mere unknown-key WARNING).
_OLD_CREATION = [
    f"{word}{sep}{part}"
    for word, part in (
        ("creator", "name"),
        ("creator", "email"),
        ("creator", "type"),
        ("creation", "tool"),
    )
    for sep in "-_"
]


@pytest.mark.parametrize(
    "pitloom",
    [{"creation": {key: "x"}} for key in _OLD_CREATION]
    + [{key: "x"} for key in _OLD_CREATION]
    + [{key: {}} for key in ("ids", "fragments", "file-headers", "file_headers")]
    + [
        {f"{k}{s}{w}": "x"}
        for k, w in (("ids", "file"), ("update", "registry"))
        for s in "-_"
    ],
)
def test_each_old_spelling_is_still_refused_as_moved(pitloom: dict[str, Any]) -> None:
    with pytest.raises(ValueError) as caught:
        parse_pitloom_config({"tool": {"pitloom": pitloom}}, source="pyproject.toml")
    assert code_of(caught.value) == "config-moved"
