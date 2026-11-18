# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The guards of the configuration messages: a writer refuses a value that is
not its field's shape, a raw ``got`` is written masked, an error with no place
cannot be located, and a failure only another reader raises (a file gone
between the check and the read, an INI error of a text with no file) is still
one coded line.

See also: tests/messages/test_config.py (the mechanism) and
tests/core/test_config_load_file.py (``load_config_file``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from pitloom._loom_active_run import loom_config
from pitloom.core import config_cascade
from pitloom.core.config import parse_pitloom_config
from pitloom.core.config_cascade import load_config_file
from pitloom.core.creation import creator_type_problem
from pitloom.core.internal_error import InternalError
from pitloom.extract.project.setuptools_cfg import setup_cfg_pitloom_config
from pitloom.messages import code_of
from pitloom.messages._config_place import expected_text, place_text, tables_text
from pitloom.messages._fields_config import keys_text
from pitloom.messages._templates import template_pattern
from pitloom.messages.config import (
    CONFIG_INVALID,
    CONFIG_MALFORMED,
    INTERPOLATION_LINE,
    UNKNOWN_ELSEWHERE_LINE,
    ConfigError,
    ConfigPlace,
)

pytestmark = pytest.mark.platform

_PRETTY = ConfigPlace("tool.pitloom", "pretty")
_PROV = ConfigPlace("tool.pitloom.provenance")


@pytest.mark.parametrize(
    "call",
    [
        lambda: expected_text("no-such-id"),
        lambda: expected_text(7),
        lambda: place_text("[tool.pitloom] pretty"),
        lambda: tables_text("[tool.pitloom.provenance]"),
        lambda: tables_text([_PRETTY]),  # names a key, not a table
        lambda: tables_text(["[tool.pitloom.provenance]"]),  # not a place
        lambda: tables_text([ConfigPlace("tool.pitloom.creator", entry=0)]),
        lambda: keys_text("pretty"),  # a str is not a collection of keys
        lambda: keys_text(None),
    ],
    ids=[
        "expected-unknown",
        "expected-not-str",
        "place-not-place",
        "tables-not-list",
        "tables-key",
        "tables-not-place",
        "tables-entry",
        "keys-str",
        "keys-none",
    ],
)
def test_a_writer_refuses_a_value_that_is_not_its_fields_shape(call: Any) -> None:
    with pytest.raises(ValueError):
        call()


@pytest.mark.parametrize(
    ("writer", "value"),
    [(expected_text, ["boolean"]), (tables_text, {ConfigPlace("tool.pitloom")})],
    ids=["expected-list", "tables-set"],
)
def test_a_writer_refuses_an_unhashable_or_unordered_value(
    writer: Any, value: object
) -> None:
    with pytest.raises(ValueError):
        writer(value)


@pytest.mark.parametrize(
    ("tables", "matches"),
    [
        ("[tool.pitloom.provenance]", True),
        ("[tool:pitloom] or [tool.pitloom.creation]", True),
        ("nowhere", False),
        ("[tool.pitloom], [tool.pitloom.creation]", False),
    ],
    ids=["one", "two", "junk", "comma"],
)
def test_the_tables_field_reads_back_only_tables(tables: str, matches: bool) -> None:
    line = f"[tool.pitloom]: unknown key x; it belongs in {tables}"
    pattern = template_pattern(UNKNOWN_ELSEWHERE_LINE.template)
    assert (re.fullmatch(pattern, line) is not None) is matches


def test_the_table_and_key_writers_write_what_they_are_given() -> None:
    assert tables_text([_PROV, ConfigPlace("tool.pitloom.fragment")]) == (
        "[tool.pitloom.provenance] or [tool.pitloom.fragment]"
    )
    assert tables_text([]) == ""
    assert keys_text({"b", "a"}) == "a, b"
    assert keys_text(frozenset()) == ""


def test_a_raw_got_is_written_masked_never_as_given() -> None:
    """A caller that hands ``ConfigError`` the value itself (not the ``Found``
    that ``config_invalid`` makes) still gets a credential masked."""
    exc = ConfigError(
        CONFIG_INVALID,
        config_key=_PRETTY,
        expected="boolean",
        got="https://user:hunter2@host.example/x",
    )
    assert str(exc).endswith("got a string 'https://***:***@host.example/x'")


def test_an_error_with_no_place_and_no_file_cannot_be_located() -> None:
    """``located`` needs a ``config_key`` to spell: a programming error."""
    exc = ConfigError(CONFIG_MALFORMED, line=INTERPOLATION_LINE, error="x")
    with pytest.raises(InternalError, match="no config_key"):
        exc.located("setup.cfg", True)


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        (None, None),
        ("Organization", None),
        ("robot", "creator-type"),
        (5, "string"),
        (["person"], "string"),
    ],
    ids=["none-is-person", "case-folded", "unknown-type", "int", "list"],
)
def test_creator_type_problem_names_what_is_wrong(
    value: object, problem: str | None
) -> None:
    assert creator_type_problem(value) == problem


def test_a_config_gone_after_the_check_is_not_found_not_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file exists at the check and is gone at the read."""
    path = tmp_path / "c.toml"
    path.write_bytes(b"[tool.pitloom]\n")

    def _gone(_path: Path) -> dict[str, Any]:
        raise FileNotFoundError

    monkeypatch.setattr(config_cascade, "load_toml_file", _gone)
    with pytest.raises(FileNotFoundError) as exc:
        load_config_file(path)
    assert code_of(exc.value) == "input-not-found"


def test_an_uncoded_value_error_from_the_parser_names_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader that still raises a plain ``ValueError`` is framed, not
    lost; a coded one is forwarded as it is (it names the file already)."""
    path = tmp_path / "c.toml"
    path.write_bytes(b"[tool.pitloom]\n")

    def _plain(_data: object, **_kw: object) -> None:
        raise ValueError("odd")

    monkeypatch.setattr(config_cascade, "parse_pitloom_config", _plain)
    with pytest.raises(ValueError, match=r"^config file .*c\.toml.*: odd$") as exc:
        load_config_file(path)
    assert code_of(exc.value) is None


def test_arrays_nested_past_the_parsers_limit_are_config_malformed(
    tmp_path: Path,
) -> None:
    """The parser raises ``RecursionError``, not a ``TOMLDecodeError``."""
    path = tmp_path / "deep.toml"
    path.write_bytes(b"a = " + b"[" * 5000 + b"]" * 5000)
    with pytest.raises(ValueError) as exc:
        load_config_file(path)
    assert code_of(exc.value) == "config-malformed"
    assert str(exc.value).startswith(f"FILE={path}: ")


@pytest.mark.parametrize("value", [{"pretty": True}, 7, b"c.toml", ["c.toml"]])
def test_a_loom_run_config_of_the_wrong_type_is_option_invalid(value: Any) -> None:
    """Not a bare ``TypeError`` from ``Path()``: a library caller's bad value."""
    with pytest.raises(ValueError, match="^pitloom_config: must be a path") as exc:
        loom_config(value)
    assert code_of(exc.value) == "option-invalid"


def test_an_ini_error_of_a_text_with_no_file_is_one_coded_line() -> None:
    with pytest.raises(ValueError) as exc:
        setup_cfg_pitloom_config("[metadata\nname = x\n")
    assert code_of(exc.value) == "config-malformed"
    assert "FILE=" not in str(exc.value)


def _refusal(pitloom: dict[str, Any]) -> tuple[str | None, str]:
    """The code and text of the error ``[tool.pitloom]`` *pitloom* raises."""
    with pytest.raises(ValueError) as caught:
        parse_pitloom_config({"tool": {"pitloom": pitloom}}, source="pyproject.toml")
    return code_of(caught.value), str(caught.value)


# Each case: a value the reader refuses with config-invalid, at the place given.
@pytest.mark.parametrize(
    ("pitloom", "line"),
    [
        (
            {"creator": [{"name": "  "}]},
            "[[tool.pitloom.creator]] entry 0 name: must be a non-empty string",
        ),
        (
            {"creation-tool": [{"name": " "}]},
            "[[tool.pitloom.creation-tool]] entry 0 name: must be a non-empty",
        ),
        ({"creator": ""}, "[[tool.pitloom.creator]]: must be an array of tables"),
        (
            {"provenance": {"preserve_source_metadata": "x"}},
            "[tool.pitloom.provenance] preserve_source_metadata: must be one of",
        ),
        (
            {"creation": {"no-creation-tool": 1}},
            "[tool.pitloom.creation] no-creation-tool: must be true or false",
        ),
        (
            {"creation": {"creation-comment": False}},
            "[tool.pitloom.creation] creation-comment: must be a string",
        ),
        (
            {"fragment": {"files": [{"path": ""}]}},
            "[tool.pitloom.fragment] files entry 0 path: must be a non-empty",
        ),
        (
            {"fragment": {"files": [{"path": 5}]}},
            "[tool.pitloom.fragment] files entry 0 path: must be a non-empty",
        ),
        (
            {"content-type": {"override": [{"pattern": "*", "content-type": "a/b/c"}]}},
            "[[tool.pitloom.content-type.override]] entry 0 content-type: must be a "
            "media type",
        ),
        ({"pretty": 1}, "[tool.pitloom] pretty: must be true or false"),
        (
            {"content-type": {"method": ["auto"]}},
            "[tool.pitloom.content-type] method: must be one of",
        ),
    ],
    ids=[
        "blank-creator",
        "blank-tool",
        "creator-empty-string",
        "preserve-underscore",
        "no-tool-int",
        "comment-false",
        "path-empty",
        "path-int",
        "media-two-slashes",
        "bool-int",
        "choice-list",
    ],
)
def test_the_reader_refuses_and_names_the_key_as_written(
    pitloom: dict[str, Any], line: str
) -> None:
    code, text = _refusal(pitloom)
    assert code == "config-invalid"
    assert text.startswith(f"FILE=pyproject.toml: {line}")


# With both spellings of the creation-tool array present, the hyphen one is
# read, as for every other two-spelling key.
def test_both_tool_spellings_read_the_hyphen_one() -> None:
    pitloom = {"creation-tool": [{"name": "a"}], "creation_tool": [{"name": "b"}]}
    tools = parse_pitloom_config({"tool": {"pitloom": pitloom}}).tools
    assert [t.name for t in tools or []] == ["a"]
