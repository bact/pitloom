# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.untrusted_text`.

See also: :mod:`tests.assemble.test_display_text_escape` (the escape in the
SBOM, on every surface), :mod:`tests.assemble.test_display_text_related` (a
Hugging Face model's base model, datasets and references).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

import pytest
import rfc8785

from pitloom.core.canonical_json import canonical_json
from pitloom.core.file_names import escape_file_name_part
from pitloom.core.iri import iri_segment
from pitloom.core.untrusted_text import (
    DISPLAY_CONTROLS,
    escape_display_controls,
    escape_display_controls_in_iri,
    escape_display_controls_in_json,
    escape_lone_surrogates,
    escape_lone_surrogates_in,
)
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.logging_config import loggable

_ESCAPED = [
    *range(0x00, 0x09),
    0x0B,
    0x0C,
    *range(0x0E, 0x20),
    *range(0x7F, 0xA0),
    0x00AD,
    0x034F,
    0x061C,
    0x180E,
    *range(0x200B, 0x2010),
    0x2028,
    0x2029,
    *range(0x202A, 0x202F),
    *range(0x2060, 0x2065),
    *range(0x2066, 0x2070),
    0xFEFF,
    *range(0xFFF9, 0xFFFC),
    *range(0xE0000, 0xE0080),
]
# The neighbours of each range, and other format characters, stay as they are.
_KEPT = [
    *(0x09, 0x0A, 0x0D, 0x20, 0x7E, 0xA0, 0xAC, 0xAE, 0x034E, 0x0350),
    *(0x061B, 0x061D, 0x180D, 0x180F, 0x200A, 0x2010, 0x2027, 0x202F, 0x205F),
    *(0x2065, 0x2070, 0xFEFE, 0xFF00, 0xFFF8, 0xFFFC, 0x0E01, 0xE0080),
    0x1F600,
]


def test_the_set_is_the_documented_one() -> None:
    assert DISPLAY_CONTROLS == frozenset(map(chr, _ESCAPED))
    assert len(DISPLAY_CONTROLS) == 225


@pytest.mark.parametrize("code_point", _ESCAPED, ids=lambda c: f"U+{c:04X}")
def test_each_control_is_written_as_its_escape(code_point: int) -> None:
    shown = escape_display_controls(f"a{chr(code_point)}b")
    if code_point <= 0xFFFF:
        assert shown == f"a\\u{code_point:04x}b"
    else:  # as JSON spells it: decoding the escape gives the code point back
        assert json.loads(f'"{shown}"') == f"a{chr(code_point)}b"
        assert len(shown) == 14 and shown.startswith("a\\udb40\\udc")


@pytest.mark.parametrize("code_point", _KEPT, ids=lambda c: f"U+{c:04X}")
def test_a_neighbour_is_kept(code_point: int) -> None:
    text = f"a{chr(code_point)}b"
    assert escape_display_controls(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("evil\u202etxt.exe", "evil\\u202etxt.exe"),  # in the middle
        ("\ufeffname", "\\ufeffname"),  # a BOM at the start
        ("\u2067\u2067", "\\u2067\\u2067"),  # every one, not the first only
        ("a\\u202eb", "a\\u202eb"),  # already the text of an escape: kept
        ("C:\\models\\x", "C:\\models\\x"),  # a backslash is not escaped
        ("", ""),
    ],
    ids=["middle", "bom-start", "repeated", "literal-escape", "backslash", "empty"],
)
def test_adversarial_text(text: str, expected: str) -> None:
    shown = escape_display_controls(text)
    assert shown == expected
    assert escape_display_controls(shown) == shown  # stable on its own output
    assert not DISPLAY_CONTROLS & set(shown)


def test_the_json_form_decodes_to_the_escaped_strings() -> None:
    data = {"k\u202e": ["v\u2066", 1, {"\ufeff": "a\\u202eb", "c": "\x1b[31m"}]}
    text = escape_display_controls_in_json(canonical_json(data))
    assert json.loads(text) == {
        "k\\u202e": ["v\\u2066", 1, {"\\ufeff": "a\\u202eb", "c": "\\u001b[31m"}]
    }
    assert not DISPLAY_CONTROLS & set(text)


@pytest.mark.parametrize(
    "text",
    ['{"b": 1, "a": "x"}', "not json \u202e", "not json"],
    ids=["json-without-a-control", "text-with-one", "text-without-one"],
)
def test_the_json_form_keeps_text_without_a_control(text: str) -> None:
    """JSON with nothing to escape is kept as written, not re-serialised;
    text that is not JSON is escaped as text."""
    expected = escape_display_controls(text)
    assert escape_display_controls_in_json(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://h/o/a\u202eb", "https://h/o/a%E2%80%AEb"),
        ("https://h/\u061c\ufeff", "https://h/%D8%9C%EF%BB%BF"),
        ("https://h/o/a%20b?q=1#f", "https://h/o/a%20b?q=1#f"),  # kept as is
    ],
    ids=["rlo", "two-and-three-bytes", "plain"],
)
def test_an_iri_is_percent_encoded(text: str, expected: str) -> None:
    assert escape_display_controls_in_iri(text) == expected


def test_jcs_writes_the_controls_raw_and_the_escape_backslash_escaped() -> None:
    """The layering the module docstring states, against the real library:
    JCS escapes only C0 controls, ``"`` and ``\\``, in lowercase hex."""
    controls = "".join(sorted(c for c in DISPLAY_CONTROLS if c >= "\x20"))
    assert rfc8785.dumps(controls) == f'"{controls}"'.encode()
    assert rfc8785.dumps("\x1f\x7f\U0001f600") == '"\\u001f\x7f\U0001f600"'.encode()
    shown = escape_display_controls("a\u202eb\x1f")
    assert rfc8785.dumps(shown) == b'"a\\\\u202eb\\\\u001f"'


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\ud800b", "a\\ud800b"),
        ("\udfff\udc00", "\\udfff\\udc00"),
        ("\U0001f600 a\\ud800", "\U0001f600 a\\ud800"),  # a pair, a literal
    ],
    ids=["high", "low-twice", "kept"],
)
def test_a_lone_surrogate_is_written_as_text(text: str, expected: str) -> None:
    shown = escape_lone_surrogates(text)
    assert shown == expected
    shown.encode("utf-8")  # encodable now


@dataclass(frozen=True)
class _Frozen:
    name: str
    tags: tuple[str, ...]


class _Pair(NamedTuple):
    key: str
    value: int


def test_lone_surrogates_are_escaped_through_every_container() -> None:
    mapping = {"k\udc00": ["v\ud800", _Pair("p\ud801", 1)], "plain": 1}
    frozen = _Frozen("n\udfff", ("t\ud802", "x"))
    holder = {"a": mapping, "b": frozen}
    result, changed = escape_lone_surrogates_in(holder)
    assert changed and result is holder and holder["a"] is mapping
    assert mapping == {"k\\udc00": ["v\\ud800", _Pair("p\\ud801", 1)], "plain": 1}
    assert list(mapping) == ["k\\udc00", "plain"]  # order kept
    assert holder["b"] is frozen and frozen == _Frozen("n\\udfff", ("t\\ud802", "x"))
    clean = {"a": [1, "b"], "c": _Pair("d", 2)}
    assert escape_lone_surrogates_in(clean) == (clean, False)
    assert escape_lone_surrogates_in(object)[1] is False


# Every helper that claims to neutralise the invisible and bidi controls, and
# whether it touches only that set (the rest of a name kept, but for the code
# points its own rule changes too) or more (None).
_IRI_OWN = frozenset({0x09, 0x0A, 0x0D, 0x20, 0xFFF8, 0xFFFC, 0xE0080})  # no ipchar
_HELPERS: dict[str, tuple[Callable[[str], str], frozenset[int] | None]] = {
    "escape_display_controls": (escape_display_controls, frozenset()),
    "escape_display_controls_in_iri": (escape_display_controls_in_iri, frozenset()),
    "sanitize_provenance_text": (sanitize_provenance_text, frozenset()),
    "iri_segment": (iri_segment, _IRI_OWN),
    "loggable": (loggable, None),
    "escape_file_name_part": (escape_file_name_part, None),
}


@pytest.mark.parametrize("helper", _HELPERS)
def test_every_bidi_helper_covers_the_one_set(helper: str) -> None:
    """Drift guard: a control added to (or dropped from) the set reaches
    every helper, and the exact ones touch nothing else."""
    function, own = _HELPERS[helper]
    for char in DISPLAY_CONTROLS:
        assert char not in function(f"a{char}b"), f"U+{ord(char):04X}"
    if own is not None:
        for code_point in set(_KEPT) - own:
            assert function(f"a{chr(code_point)}b") == f"a{chr(code_point)}b"
