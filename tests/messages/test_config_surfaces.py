# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The configuration lines through the real readers: one case per
``expected`` id (``pyproject.toml`` and the ``setup.cfg`` spelling), the table
a ``_pick_str`` key came from, an entry's index, what is found (masked,
escaped, one line), an unknown key said once and a Windows path.

See also: tests/messages/test_config.py (the mechanism),
tests/messages/test_config_drift.py (the tables against the readers),
tests/messages/test_config_moved.py (moved keys),
tests/messages/test_config_hook.py (the Hatchling hook's lines) and
tests/test_config_key_surfaces.py (the CLI, library and sdist routes).
"""

from __future__ import annotations

import logging
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

from pitloom._toml_io import load_toml_bytes
from pitloom.core.config import parse_pitloom_config, read_pitloom_config
from pitloom.extract.project.setuptools_cfg import (
    read_setup_cfg,
    setup_cfg_pitloom_config,
)
from pitloom.messages import code_of, trusted_message
from pitloom.messages.config import (
    CONFIG_INVALID,
    CONFIG_MOVED,
    EXPECTED,
)
from tests._code_records import coded

pytestmark = pytest.mark.platform

_SECRET = "ghp_secretvalue"
_CFG_BASE = "[metadata]\nname = demo\nversion = 1\n"

#: Each id of :data:`~pitloom.messages.config.EXPECTED` -> (the
#: ``pyproject.toml`` that refuses a value, the key's place). A secret value
#: is never said (``got a string``).
_CASES = {
    "boolean": ('[tool.pitloom]\npretty = "maybe"', "[tool.pitloom] pretty"),
    "integer": (
        '[tool.pitloom]\nmax-download-bytes = "maybe"',
        "[tool.pitloom] max-download-bytes",
    ),
    "positive": (
        "[tool.pitloom]\nmax-model-extract-bytes = 0",
        "[tool.pitloom] max-model-extract-bytes",
    ),
    "budget": (
        "[tool.pitloom.provenance]\nmax-source-metadata-bytes = 3",
        "[tool.pitloom.provenance] max-source-metadata-bytes",
    ),
    "string": ("[tool.pitloom]\nid-registry = 5", "[tool.pitloom] id-registry"),
    "non-empty": (
        '[[tool.pitloom.creator]]\nname = ""',
        "[[tool.pitloom.creator]] entry 0 name",
    ),
    "string-or-table": (
        "[tool.pitloom.fragment]\nfiles = [42]",
        "[tool.pitloom.fragment] files entry 0",
    ),
    "table": ('[tool.pitloom]\nprovenance = "maybe"', "[tool.pitloom.provenance]"),
    "array": (
        '[tool.pitloom.fragment]\nfiles = "maybe"',
        "[tool.pitloom.fragment] files",
    ),
    "array-of-tables": (
        '[tool.pitloom.creator]\nname = "x"',
        "[[tool.pitloom.creator]]",
    ),
    "one-of-format": (
        '[tool.pitloom.provenance]\nformat = "maybe"',
        "[tool.pitloom.provenance] format",
    ),
    "one-of-detail": (
        '[tool.pitloom.provenance]\ndetail = "maybe"',
        "[tool.pitloom.provenance] detail",
    ),
    "one-of-schema": (
        '[tool.pitloom.provenance]\nschema = "maybe"',
        "[tool.pitloom.provenance] schema",
    ),
    "one-of-preserve": (
        '[tool.pitloom.provenance]\npreserve-source-metadata = "maybe"',
        "[tool.pitloom.provenance] preserve-source-metadata",
    ),
    "one-of-method": (
        '[tool.pitloom.content-type]\nmethod = "maybe"',
        "[tool.pitloom.content-type] method",
    ),
    "creator-type": (
        '[[tool.pitloom.creator]]\nname = "A"\ntype = "maybe"',
        "[[tool.pitloom.creator]] entry 0 type",
    ),
    "media-type": (
        '[[tool.pitloom.content-type.override]]\npattern = "*.png"\n'
        'content-type = "maybe"',
        "[[tool.pitloom.content-type.override]] entry 0 content-type",
    ),
    "file-name": (
        '[tool.pitloom]\nsbom-basename = "a/b"',
        "[tool.pitloom] sbom-basename",
    ),
    "bare-file-name": (
        '[tool.pitloom]\nsbom-basename = ".spdx3.json"',
        "[tool.pitloom] sbom-basename",
    ),
    "datetime": (
        '[tool.pitloom.creation]\ncreation-datetime = "maybe"',
        "[tool.pitloom.creation] creation-datetime",
    ),
    "fingerprint": (
        f'[tool.pitloom]\naccept-url-credentials = ["{_SECRET}"]',
        "[tool.pitloom] accept-url-credentials entry 0",
    ),
    "fingerprints": (
        f'[tool.pitloom]\naccept-url-credentials = "{_SECRET}"',
        "[tool.pitloom] accept-url-credentials",
    ),
    "url-credentials-mode": (
        f'[tool.pitloom]\nurl-credentials = "{_SECRET}"',
        "[tool.pitloom] url-credentials",
    ),
    "sha-256": (
        '[tool.pitloom.fragment]\nfiles = [{path = "f.json", sha256 = "maybe"}]',
        "[tool.pitloom.fragment] files entry 0 sha256",
    ),
}
#: What each case's value is said as (the same value from ``setup.cfg``).
_FOUND = {
    "boolean": "a string 'maybe'",
    "integer": "a string 'maybe'",
    "positive": "an integer 0",
    "budget": "an integer 3",
    "string": "an integer 5",
    "non-empty": "a string ''",
    "string-or-table": "an integer 42",
    "table": "a string 'maybe'",
    "array": "a string 'maybe'",
    "array-of-tables": "a table",
    "one-of-format": "a string 'maybe'",
    "one-of-detail": "a string 'maybe'",
    "one-of-schema": "a string 'maybe'",
    "one-of-preserve": "a string 'maybe'",
    "one-of-method": "a string 'maybe'",
    "creator-type": "a string 'maybe'",
    "media-type": "a string 'maybe'",
    "file-name": "a string 'a/b'",
    "bare-file-name": "a string '.spdx3.json'",
    "datetime": "a string 'maybe'",
    "fingerprint": "a string",
    "fingerprints": "a string",
    "url-credentials-mode": "a string",
    "sha-256": "a string 'maybe'",
}
#: The same, from ``setup.cfg`` (a subset: INI has no arrays of tables).
_CFG_CASES = {
    "boolean": ("[tool:pitloom]\npretty = maybe", "[tool:pitloom] pretty"),
    "integer": (
        "[tool:pitloom]\nmax-download-bytes = maybe",
        "[tool:pitloom] max-download-bytes",
    ),
    "positive": (
        "[tool:pitloom]\nmax-model-extract-bytes = 0",
        "[tool:pitloom] max-model-extract-bytes",
    ),
    "budget": (
        "[tool:pitloom:provenance]\nmax-source-metadata-bytes = 3",
        "[tool:pitloom:provenance] max-source-metadata-bytes",
    ),
    "one-of-format": (
        "[tool:pitloom:provenance]\nformat = maybe",
        "[tool:pitloom:provenance] format",
    ),
    "one-of-method": (
        "[tool:pitloom:content-type]\nmethod = maybe",
        "[tool:pitloom:content-type] method",
    ),
    "creator-type": (
        "[tool:pitloom:creation]\ncreator-name = A\ncreator-type = maybe",
        "[tool:pitloom:creator] entry 0 type",
    ),
    "media-type": (
        "[tool:pitloom:content-type]\nenabled = true\n"
        "[tool:pitloom:content-type:override]\n*.png = maybe",
        "[tool:pitloom:content-type:override] entry 0 content-type",
    ),
    "file-name": (
        "[tool:pitloom]\nsbom-basename = a/b",
        "[tool:pitloom] sbom-basename",
    ),
    "datetime": (
        "[tool:pitloom:creation]\ndatetime = maybe",
        "[tool:pitloom:creation] datetime",
    ),
    "fingerprint": (
        f"[tool:pitloom]\naccept-url-credentials = {_SECRET}",
        "[tool:pitloom] accept-url-credentials entry 0",
    ),
    "url-credentials-mode": (
        f"[tool:pitloom]\nurl-credentials = {_SECRET}",
        "[tool:pitloom] url-credentials",
    ),
}


def _line(file: str, place: str, expected: str) -> str:
    """The line a refused value is said as."""
    return f"FILE={file}: {place}: must be {EXPECTED[expected]}, got {_FOUND[expected]}"


def _toml(text: str) -> dict[str, Any]:
    return load_toml_bytes(text.encode())


def _chain(exc: BaseException | None) -> list[str]:
    """Everything an exception and its chain would show: ``str``, ``args``,
    the attributes."""
    shown: list[str] = []
    while exc is not None:
        shown += [str(exc), repr(exc.args), repr(vars(exc))]
        exc = exc.__cause__ or exc.__context__
    return shown


def test_every_expected_id_has_a_case() -> None:
    """A new id of the table fails here until a real reader says it."""
    # A parameter's type or value, no file says it.
    library_only = {"config-source", "sbom-content"}
    # Said by the project metadata readers (metadata-invalid), not config.
    metadata_only = {"array-of-strings", "string-or-array"}
    not_config = library_only | metadata_only
    assert set(_CASES) == set(EXPECTED) - not_config == set(_FOUND)
    assert set(_CFG_CASES) <= set(EXPECTED)


@pytest.mark.parametrize("expected", _CASES)
def test_each_expected_id_is_said_by_the_real_reader(
    tmp_path: Path, expected: str
) -> None:
    """From a parsed dict (the file as the caller names it) and from a file
    (``str(path)``): the id picks the text, the place names the key, the code
    is ``config-invalid`` and a secret is never shown."""
    text, place = _CASES[expected]
    with pytest.raises(ValueError) as from_dict:
        parse_pitloom_config(_toml(text), source="pyproject.toml")
    path = tmp_path / "pyproject.toml"
    path.write_bytes(text.encode())
    with pytest.raises(ValueError) as from_file:
        read_pitloom_config(path)
    assert str(from_dict.value) == _line("pyproject.toml", place, expected)
    assert str(from_file.value) == _line(str(path), place, expected)
    for caught in (from_dict, from_file):
        assert code_of(caught.value) == "config-invalid"
        assert _SECRET not in "".join(_chain(caught.value))


@pytest.mark.parametrize("expected", _CFG_CASES)
def test_the_setup_cfg_spelling_names_its_own_tables(
    tmp_path: Path, expected: str
) -> None:
    """``[tool:pitloom:x]``, an array in single brackets, the file as given:
    the one writer spells it (never ``[tool.pitloom]``)."""
    text, place = _CFG_CASES[expected]
    with pytest.raises(ValueError) as from_text:
        setup_cfg_pitloom_config(f"{_CFG_BASE}{text}\n", "setup.cfg")
    (tmp_path / "setup.cfg").write_bytes(f"{_CFG_BASE}{text}\n".encode())
    with pytest.raises(ValueError) as from_dir:
        read_setup_cfg(tmp_path)
    assert str(from_text.value) == _line("setup.cfg", place, expected)
    assert str(from_dir.value) == _line(str(tmp_path / "setup.cfg"), place, expected)
    for caught in (from_text, from_dir):
        assert code_of(caught.value) == "config-invalid"
        assert "[tool.pitloom" not in str(caught.value)
        assert _SECRET not in "".join(_chain(caught.value))


@pytest.mark.parametrize(
    ("toml", "line"),
    [
        pytest.param(
            '[[tool.pitloom.creator]]\nname = "A"\n[[tool.pitloom.creator]]\n'
            'name = "B"\ntype = "x"',
            "[[tool.pitloom.creator]] entry 1 type: must be one of",
            id="creator",
        ),
        pytest.param(
            '[[tool.pitloom.creation-tool]]\nname = "A"\n'
            '[[tool.pitloom.creation-tool]]\nname = ""',
            "[[tool.pitloom.creation-tool]] entry 1 name: must be a non-empty "
            "string, got a string ''",
            id="creation-tool",
        ),
        pytest.param(
            '[tool.pitloom]\ncreation_tool = [{name = "A"}, {}]',
            "[[tool.pitloom.creation_tool]] entry 1 name: must be a non-empty "
            "string, got nothing",
            id="creation-tool-underscore",
        ),
        pytest.param(
            '[tool.pitloom.fragment]\nfiles = ["a.json", ""]',
            "[tool.pitloom.fragment] files entry 1: must be a non-empty string",
            id="fragment-string",
        ),
        pytest.param(
            '[tool.pitloom.fragment]\nfiles = ["a.json", {path = "b", role = 1}]',
            "[tool.pitloom.fragment] files entry 1 role: must be a string",
            id="fragment-table",
        ),
        pytest.param(
            '[[tool.pitloom.content-type.override]]\npattern = "*.a"\n'
            'content-type = "a/b"\n[[tool.pitloom.content-type.override]]\n'
            'pattern = ""',
            "[[tool.pitloom.content-type.override]] entry 1 pattern: must be a "
            "non-empty string",
            id="override",
        ),
    ],
)
def test_an_entry_is_named_by_its_index_from_zero(toml: str, line: str) -> None:
    """The second bad entry is entry 1, whichever array holds it."""
    with pytest.raises(ValueError) as caught:
        parse_pitloom_config(_toml(toml), source="p.toml")
    assert str(caught.value).startswith(f"FILE=p.toml: {line}")


@pytest.mark.parametrize(
    ("toml", "place"),
    [
        ("[tool.pitloom.creation]\ndatetime = 5", "[tool.pitloom.creation] datetime"),
        (
            "[tool.pitloom.creation]\ncreation_datetime = 5",
            "[tool.pitloom.creation] creation_datetime",
        ),
        (
            "[tool.pitloom.creation]\ncomment = 5",
            "[tool.pitloom.creation] comment",
        ),
        (
            "[tool.pitloom.creation]\ncreation-comment = 5",
            "[tool.pitloom.creation] creation-comment",
        ),
        ("[tool.pitloom]\ncreation-datetime = 5", "[tool.pitloom] creation-datetime"),
        ("[tool.pitloom]\ncreation_comment = 5", "[tool.pitloom] creation_comment"),
        ("[tool.pitloom]\nsbom-basename = 5", "[tool.pitloom] sbom-basename"),
    ],
    ids=[
        "creation-datetime-short",
        "creation-datetime-underscore",
        "creation-comment-short",
        "creation-comment",
        "top-datetime",
        "top-comment",
        "basename",
    ],
)
def test_a_string_key_names_the_table_it_was_read_from(toml: str, place: str) -> None:
    """``_pick_str`` reads the same key from two tables: the line names the
    table and the spelling the value sat in, not ``[tool.pitloom]``."""
    with pytest.raises(ValueError) as caught:
        parse_pitloom_config(_toml(toml), source="p.toml")
    assert str(caught.value) == (
        f"FILE=p.toml: {place}: must be a string, got an integer 5"
    )


@pytest.mark.parametrize(
    ("pitloom", "raises"),
    [
        pytest.param({}, False, id="absent"),
        pytest.param({"creation-datetime": ""}, False, id="empty"),
        pytest.param({"creation": {"datetime": ""}}, False, id="empty-in-creation"),
        pytest.param({"creation-datetime": "2026-01-01T00:00:00Z"}, False, id="valid"),
        pytest.param({"creation-datetime": "2026-01-01"}, False, id="date-only"),
        pytest.param({"creation-datetime": "garbage"}, True, id="garbage"),
        pytest.param({"creation-datetime": "  "}, True, id="blank"),
        pytest.param({"creation": {"datetime": "x"}}, True, id="garbage-in-creation"),
    ],
)
def test_an_empty_creation_datetime_is_unset_and_a_bad_one_is_refused(
    pitloom: dict[str, Any], raises: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Empty is no claim (silently unset); present and not a date is an error."""
    data = {"tool": {"pitloom": pitloom}}
    with caplog.at_level(logging.INFO):
        if raises:
            with pytest.raises(ValueError, match="an ISO 8601 date and time"):
                parse_pitloom_config(data)
        else:
            config = parse_pitloom_config(data)
            assert not config.creation_datetime or config.creation_datetime[0] == "2"
    assert not caplog.records


def test_a_url_with_credentials_is_masked_and_leaves_no_trace() -> None:
    """``got`` masks ``user:pass@`` in the line, in ``args`` and in the chain
    (the exception is raised ``from None``)."""
    data = {"tool": {"pitloom": {"creation-datetime": "https://u:secretpw@h/x"}}}
    with pytest.raises(ValueError) as caught:
        parse_pitloom_config(data, source="p.toml")
    assert str(caught.value).endswith("got a string 'https://***:***@h/x'")
    assert "secretpw" not in "".join(_chain(caught.value))
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("a\nb", r"'a\nb'"),
        ("\x1b[31mred", r"'\x1b[31mred'"),
        ("\udc80x", r"'\udc80x'"),
    ],
    ids=["newline", "escape", "surrogate"],
)
def test_a_value_is_escaped_on_one_line_and_so_is_an_unknown_key(
    value: str, shown: str, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(ValueError) as caught:
        parse_pitloom_config({"tool": {"pitloom": {"pretty": value}}}, source="p.toml")
    assert str(caught.value).endswith(f"got a string {shown}")
    assert caught.value.args == (str(caught.value),)
    with caplog.at_level(logging.WARNING):
        parse_pitloom_config({"tool": {"pitloom": {value: 1}}}, source="p.toml")
    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning == f"FILE=p.toml: [tool.pitloom]: unknown key {shown}"


def test_an_unknown_key_in_a_file_read_twice_is_said_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The CLI reads ``pyproject.toml`` more than once; a path with a space
    is shown as it is."""
    project = tmp_path / "my project"
    project.mkdir()
    path = project / "pyproject.toml"
    path.write_text("[tool.pitloom]\nofline = true\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            read_pitloom_config(path)
    assert coded(caplog) == [
        (
            "config-unknown-key",
            f"FILE={path}: [tool.pitloom]: unknown key ofline; did you mean offline?",
        )
    ]


def test_file_is_built_with_str_path_and_a_windows_path_reads_back() -> None:
    """A drive colon before the ``: `` separator: the line is still one entry
    of the catalogue."""
    path = PureWindowsPath(r"C:\p\pyproject.toml")
    data = {"tool": {"pitloom": {"pretty": "maybe"}}}
    with pytest.raises(ValueError) as caught:
        parse_pitloom_config(data, source=str(path))
    text = str(caught.value)
    assert text.startswith(r"FILE=C:\p\pyproject.toml: [tool.pitloom] pretty: ")
    assert trusted_message(f"ERROR: {text} [config-invalid]") is CONFIG_INVALID
    moved = {"tool": {"pitloom": {"ids-file": "x"}}}
    with pytest.raises(ValueError) as caught:
        parse_pitloom_config(moved, source=str(path))
    assert trusted_message(f"ERROR: {caught.value} [config-moved]") is CONFIG_MOVED
