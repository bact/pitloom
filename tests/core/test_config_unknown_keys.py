# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An unknown ``[tool.pitloom]`` key is one ``WARNING:``, never silent and
never an error; :data:`~pitloom.core._config_keys.KNOWN_KEYS` matches what the
readers actually look at.

See also: :mod:`tests.test_config_key_surfaces` for every surface.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.core._config_keys import KNOWN_ENTRY_KEYS, KNOWN_KEYS
from pitloom.core._config_legacy import (
    _MOVED_CREATION_KEYS,
    _MOVED_FLAT_KEYS,
    _MOVED_TOP_LEVEL_TABLES,
)
from pitloom.core._config_types import BOOL_KEYS, INT_KEYS
from pitloom.core.config import PitloomConfig, parse_pitloom_config
from pitloom.extract.project.setuptools_cfg import setup_cfg_pitloom_config


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def _parse(
    pitloom: dict[str, Any], *, is_setup_cfg: bool = False, source: str | None = None
) -> PitloomConfig:
    return parse_pitloom_config(
        {"tool": {"pitloom": pitloom}}, is_setup_cfg=is_setup_cfg, source=source
    )


@pytest.mark.parametrize(
    ("pitloom", "expected"),
    [
        pytest.param(
            {"ofline": True},
            ["[tool.pitloom] unknown key 'ofline'; did you mean 'offline'?"],
            id="top-level-close",
        ),
        pytest.param(
            {"zzzzqq": 1}, ["[tool.pitloom] unknown key 'zzzzqq'"], id="no-close"
        ),
        pytest.param(
            {"zeta": 1, "alpha": 2},
            [
                "[tool.pitloom] unknown key 'alpha'",
                "[tool.pitloom] unknown key 'zeta'",
            ],
            id="sorted",
        ),
        pytest.param(
            {"creation": {"comnt": "x"}},
            ["[tool.pitloom.creation] unknown key 'comnt'; did you mean 'comment'?"],
            id="creation",
        ),
        pytest.param(
            {"provenance": {"detial": "full"}},
            ["[tool.pitloom.provenance] unknown key 'detial'; did you mean 'detail'?"],
            id="provenance",
        ),
        pytest.param(
            {"content-type": {"enable": True}},
            [
                "[tool.pitloom.content-type] unknown key 'enable'; "
                "did you mean 'enabled'?"
            ],
            id="content-type",
        ),
        pytest.param(
            {"fragment": {"file": []}},
            ["[tool.pitloom.fragment] unknown key 'file'; did you mean 'files'?"],
            id="fragment",
        ),
        pytest.param(
            {"creator": [{"name": "n", "emial": "e"}]},
            ["[[tool.pitloom.creator]] unknown key 'emial'; did you mean 'email'?"],
            id="creator-entry",
        ),
        pytest.param(
            {
                "content-type": {
                    "override": [{"pattern": "*", "content-type": "a/b", "patern": 1}]
                }
            },
            [
                "[[tool.pitloom.content-type.override]] unknown key 'patern'; "
                "did you mean 'pattern'?"
            ],
            id="override-entry",
        ),
        pytest.param(
            {"fragment": {"files": [{"path": "p", "requried": True}]}},
            [
                "[tool.pitloom.fragment] 'files' entry unknown key 'requried'; "
                "did you mean 'required'?"
            ],
            id="fragment-files-entry",
        ),
    ],
)
def test_unknown_key_warns_once_per_key_in_sorted_order(
    pitloom: dict[str, Any],
    expected: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        _parse(pitloom)
        _parse(pitloom)  # config is parsed more than once per run
    assert _warnings(caplog) == expected


def test_setup_cfg_names_its_own_table(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _parse({"ofline": True, "provenance": {"detial": "x"}}, is_setup_cfg=True)
    assert _warnings(caplog) == [
        "[tool:pitloom] unknown key 'ofline'; did you mean 'offline'?",
        "[tool:pitloom:provenance] unknown key 'detial'; did you mean 'detail'?",
    ]


def test_unknown_key_does_not_change_the_config(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        assert _parse({"ofline": True, "pretty": True}) == _parse({"pretty": True})
    assert _warnings(caplog)  # not vacuous: the typo did warn


@pytest.mark.parametrize(
    ("pitloom", "error", "hint"),
    [
        ({"ofline": True, "pretty": "yes"}, "boolean", "'offline'"),
        ({"creator": [{"nmae": "x"}]}, "'name'", "did you mean 'name'?"),
        (
            {"fragment": {"files": [{"pth": "x"}]}},
            "'path'",
            "did you mean 'path'?",
        ),
    ],
)
def test_the_hint_comes_before_the_error_it_causes(
    pitloom: dict[str, Any], error: str, hint: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Keys are checked before values are read: a misspelt required key shows
    what was meant, then the error about it being missing."""
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match=error):
        _parse(pitloom)
    (warning,) = _warnings(caplog)
    assert hint in warning


@pytest.mark.parametrize(
    ("pitloom", "expected"),
    [
        pytest.param(
            {"max-source-metadata-bytes": 9},
            "[tool.pitloom] unknown key 'max-source-metadata-bytes'; "
            "it belongs in [tool.pitloom.provenance]",
            id="hyphen",
        ),
        pytest.param(
            {"max_source_metadata_bytes": 9},
            "[tool.pitloom] unknown key 'max_source_metadata_bytes'; "
            "it belongs in [tool.pitloom.provenance]",
            id="underscore",
        ),
        pytest.param(
            {"no-creation-tool": True},
            "[tool.pitloom] unknown key 'no-creation-tool'; "
            "it belongs in [tool.pitloom.creation]",
            id="not-the-opposite-key",
        ),
        pytest.param(
            {"creation": {"offline": True}},
            "[tool.pitloom.creation] unknown key 'offline'; "
            "it belongs in [tool.pitloom]",
            id="from-a-sub-table",
        ),
        pytest.param(
            {"no-offline": True},
            "[tool.pitloom] unknown key 'no-offline'",
            id="negation-is-no-hint",
        ),
        pytest.param(
            {"provenance": {"no-schema": 1}},
            "[tool.pitloom.provenance] unknown key 'no-schema'",
            id="negation-in-sub-table",
        ),
    ],
)
def test_hint_names_the_owning_table_and_never_the_opposite_key(
    pitloom: dict[str, Any], expected: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        _parse(pitloom)
    assert expected in _warnings(caplog)


def test_one_file_spelt_two_ways_warns_once(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.WARNING):
        _parse({"ofline": True}, source="pyproject.toml")
        _parse({"ofline": True}, source=str(tmp_path / "pyproject.toml"))
    assert len(_warnings(caplog)) == 1


def test_a_warning_is_per_source(caplog: pytest.LogCaptureFixture) -> None:
    """Two files with one typo each warn; one file parsed twice warns once."""
    with caplog.at_level(logging.WARNING):
        for source in ("/a/pyproject.toml", "/b/pyproject.toml", "/a/pyproject.toml"):
            _parse({"ofline": True}, source=source)
    assert _warnings(caplog) == [
        f"{source} [tool.pitloom] unknown key 'ofline'; did you mean 'offline'?"
        for source in ("/a/pyproject.toml", "/b/pyproject.toml")
    ]


def test_known_keys_in_both_spellings_are_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keys of every table and entry kind, hyphen and underscore spellings
    mixed: nothing to warn. (``test_known_keys_are_exactly...`` covers that
    the table lists every key.)"""
    pitloom: dict[str, Any] = {
        "pretty": True,
        "sbom-basename": "b",
        "describe_relationship": True,
        "creation-datetime": "2026-01-01T00:00:00Z",
        "creation_comment": "c",
        "creator": [{"name": "n", "type": "person", "email": "e"}],
        "creation-tool": [{"name": "t"}],
        "creation": {"no_creation_tool": True, "datetime": "2026-01-01T00:00:00Z"},
        "provenance": {"preserve_source_metadata": "auto", "schema": "pitloom/1"},
        "content-type": {
            "enabled": True,
            "method": "auto",
            "override": [{"pattern": "*", "content-type": "a/b"}],
        },
        "fragment": {
            "files": [
                {"path": "p", "role": "r", "link_to_main": "x", "sha256": "0"},
                "q",
            ]
        },
    }
    with caplog.at_level(logging.WARNING):
        _parse(pitloom)
    assert not _warnings(caplog)


class _Spy(dict[str, Any]):
    """A table that records every key a reader asks it for."""

    def __init__(self, label: str, seen: set[tuple[str, str]], **items: Any) -> None:
        super().__init__(items)
        self._label, self._seen = label, seen

    def get(self, key: str, default: Any = None) -> Any:
        self._seen.add((self._label, key))
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        self._seen.add((self._label, str(key)))
        return super().__contains__(key)


def _read_keys(tool_key: str) -> set[tuple[str, str]]:
    """``(table, key)`` for every key ``parse_pitloom_config`` looked up in a
    config whose tables and entries are all present and minimal; *tool_key* is
    the spelling of ``creation-tool`` to give."""
    seen: set[tuple[str, str]] = set()

    def spy(label: str, **items: Any) -> _Spy:
        return _Spy(label, seen, **items)

    override = spy("content-type.override", pattern="*", **{"content-type": "a/b"})
    top = spy(
        "",
        creation=spy("creation"),
        provenance=spy("provenance"),
        fragment=spy("fragment", files=[spy("fragment.files", path="p")]),
        creator=[spy("creator", name="n")],
        **{
            tool_key: [spy(tool_key, name="t")],
            "content-type": spy("content-type", override=[override]),
        },
    )
    parse_pitloom_config({"tool": {"pitloom": top}})
    return seen


def test_known_keys_are_exactly_the_keys_the_readers_look_at() -> None:
    """The drift guard: a key a reader gains must join the table (else it
    warns as unknown); a key left in the table with no reader is dead."""
    seen = _read_keys("creation-tool") | _read_keys("creation_tool")
    moved = {*_MOVED_CREATION_KEYS, *_MOVED_TOP_LEVEL_TABLES, *_MOVED_FLAT_KEYS}
    tables = {
        **KNOWN_KEYS,
        **{
            ".".join(filter(None, where)): known
            for where, known in KNOWN_ENTRY_KEYS.items()
        },
    }
    for parent, key in KNOWN_ENTRY_KEYS:  # an entry array is a key of its table
        assert key in KNOWN_KEYS[parent]
    for label, known in tables.items():
        read = {key for table, key in seen if table == label}
        assert known <= read, (label, sorted(known - read))
        # the moved-key guards probe their old spellings in these two tables
        extra = read - known - (moved if label in ("", "creation") else set())
        assert not extra, (label, sorted(extra))


@pytest.mark.parametrize("keys", [BOOL_KEYS, INT_KEYS], ids=["bool", "int"])
def test_setup_cfg_typed_keys_are_known_keys(
    keys: dict[str, frozenset[str]],
) -> None:
    for table, names in keys.items():
        assert names <= KNOWN_KEYS[table], (table, sorted(names - KNOWN_KEYS[table]))


def test_setup_cfg_spellings_that_are_read_apart_are_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``tool``, ``creator-*`` and ``fragments`` are ``setup.cfg`` spellings
    folded into other keys before the table is checked; a typo still warns."""
    text = (
        "[metadata]\nname = demo\n[tool:pitloom]\ntool = T\ncreator-name = N\n"
        "fragments = a.json\nofline = yes\n[tool:pitloom:creation]\ntool = U\n"
    )
    with caplog.at_level(logging.WARNING):
        config = setup_cfg_pitloom_config(text, "setup.cfg")
    assert [t.name for t in config.tools or []] == ["U"]  # creation wins
    assert [c.name for c in config.creators] == ["N"]
    assert [f.path for f in config.fragments] == ["a.json"]
    assert _warnings(caplog) == [
        "setup.cfg [tool:pitloom] unknown key 'ofline'; did you mean 'offline'?"
    ]


@pytest.mark.parametrize(
    "section",
    [
        "[tool:pitloom]\ncreation-tool = T\n",
        "[tool:pitloom]\ntool = T\n",
        "[tool:pitloom:creation]\ntool = T\n",
    ],
)
def test_setup_cfg_creation_tool_is_kept(section: str) -> None:
    config = setup_cfg_pitloom_config("[metadata]\nname = demo\n" + section)
    assert config.tools is not None
    assert [t.name for t in config.tools] == ["T"]


def test_setup_cfg_default_section_is_not_a_pitloom_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``[DEFAULT]`` is merged into every section by ``configparser``: its
    own keys are not the user's Pitloom keys, but interpolation and an
    inherited value of a key Pitloom reads still work."""
    text = (
        "[DEFAULT]\nhere = /x\nbase = abc\npretty = true\n"
        "[metadata]\nname = demo\n[tool:pitloom]\ncreation-comment = %(base)s-c\n"
        "ofline = yes\n[tool:pitloom:provenance]\ndetail = full\n"
    )
    with caplog.at_level(logging.WARNING):
        config = setup_cfg_pitloom_config(text)
    assert config.creation_comment == "abc-c"
    assert config.pretty is True  # inherited, as before
    assert config.provenance_detail == "full"
    assert _warnings(caplog) == [
        "[tool:pitloom] unknown key 'ofline'; did you mean 'offline'?"
    ]


@pytest.mark.parametrize(
    ("top", "creation"),
    [
        ("creation-tool = TOP", "tool = CRE"),
        ("tool = TOP", "creation-tool = CRE"),
        ("tool = TOP", "tool = CRE"),
    ],
)
def test_setup_cfg_creation_section_wins_whatever_the_spelling(
    top: str, creation: str
) -> None:
    text = (
        f"[metadata]\nname = d\n[tool:pitloom]\n{top}\ncreator-name = TOPC\n"
        f"[tool:pitloom:creation]\n{creation}\ncreator_name = CREC\n"
    )
    config = setup_cfg_pitloom_config(text)
    assert [t.name for t in config.tools or []] == ["CRE"]
    assert [c.name for c in config.creators] == ["CREC"]


def test_setup_cfg_default_cfg_only_key_reaches_no_other_section(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``[DEFAULT] tool`` is read by the top and creation sections only: it
    does not warn in ``provenance``, nor become a tool through it (nor
    through ``[tool:pitloom]``'s absence)."""
    text = (
        "[DEFAULT]\ntool = D\n[metadata]\nname = d\n"
        "[tool:pitloom:provenance]\ndetail = full\n"
        "[tool:pitloom:content-type]\nenabled = true\n"
    )
    with caplog.at_level(logging.WARNING):
        config = setup_cfg_pitloom_config(text)
    assert not _warnings(caplog)
    assert not config.tools  # no top or creation section to inherit it
    text += "[tool:pitloom:creation]\ncomment = c\n"
    assert [t.name for t in setup_cfg_pitloom_config(text).tools or []] == ["D"]


def test_setup_cfg_default_fragments_stays_in_the_top_section(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``[DEFAULT] fragments`` is read by ``[tool:pitloom]`` only; the
    creation section neither inherits it nor warns about it."""
    text = (
        "[DEFAULT]\nfragments = a.json\n[metadata]\nname = d\n"
        "[tool:pitloom]\noffline = true\n[tool:pitloom:creation]\ncomment = c\n"
    )
    with caplog.at_level(logging.WARNING):
        config = setup_cfg_pitloom_config(text)
    assert not _warnings(caplog)
    assert [f.path for f in config.fragments] == ["a.json"]


def test_setup_cfg_default_key_is_no_content_type_override() -> None:
    """Every key of the override section is a pattern, so a ``[DEFAULT]``
    key (``here`` for ``%(here)s``) must not become one."""
    text = (
        "[DEFAULT]\nhere = /p\n[metadata]\nname = d\n"
        "[tool:pitloom:content-type]\nenabled = true\n"
        "[tool:pitloom:content-type:override]\n*.bin = application/x-foo\n"
    )
    config = setup_cfg_pitloom_config(text)
    assert [o.pattern for o in config.content_type_overrides] == ["*.bin"]
