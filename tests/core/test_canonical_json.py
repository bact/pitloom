# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.canonical_json`.

See also: tests/assemble/test_source_metadata_annotation.py (every
embedded JSON text of every fixture model's SBOM is canonical).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys
from decimal import Decimal
from fractions import Fraction

import pytest

from pitloom.core.canonical_json import (
    MAX_SAFE_INTEGER,
    canonical_json,
    canonical_json_bytes,
    canonical_json_indented,
    indent_canonical,
    json_safe,
)
from tests.json_text_helpers import without_token_whitespace


# pylint: disable-next=too-few-public-methods
class _Unrecognised:
    def __str__(self) -> str:
        return "unrecognised-value"


@pytest.mark.parametrize(
    ("value", "safe"),
    [
        (float("nan"), "NaN"),
        (float("inf"), "INF"),
        (float("-inf"), "-INF"),
        (3.14, 3.14),
        (Fraction(1, 2), 0.5),
        (MAX_SAFE_INTEGER, MAX_SAFE_INTEGER),
        (-MAX_SAFE_INTEGER, -MAX_SAFE_INTEGER),
        (MAX_SAFE_INTEGER + 1, "9007199254740992"),
        (-MAX_SAFE_INTEGER - 1, "-9007199254740992"),
        (True, True),
        (None, None),
        ("s", "s"),
        (b"\x00\xff", "AP8="),
        (Decimal("1.5"), "1.5"),
        (_Unrecognised(), "unrecognised-value"),
        ((1, "a"), [1, "a"]),
        ({1: (2,)}, {"1": [2]}),
    ],
    ids=[
        "nan",
        "inf",
        "-inf",
        "float",
        "real",
        "max-int",
        "min-int",
        "over-max-int",
        "under-min-int",
        "bool",
        "none",
        "str",
        "bytes",
        "decimal",
        "other",
        "tuple",
        "mapping",
    ],
)
def test_json_safe(value: object, safe: object) -> None:
    assert json_safe(value) == safe
    assert type(json_safe(value)) is type(safe)  # True is no 1, "1" no 1
    canonical_json(value)  # never raises


def test_numpy_scalars_are_json_values() -> None:
    np = pytest.importorskip("numpy")
    value = [np.bool_(True), np.int64(7), np.uint64(2**63), np.float32(np.inf)]
    assert canonical_json(value) == '[true,7,"9223372036854775808","INF"]'


def test_set_order_does_not_depend_on_insertion_order() -> None:
    """A frozenset's ``<`` is a subset test, no total order: the canonical
    form decides."""
    set_a = {frozenset({1, 2}), frozenset({3, 4}), frozenset({5})}
    set_b = {frozenset({5}), frozenset({3, 4}), frozenset({1, 2})}
    assert canonical_json(set_a) == canonical_json(set_b) == "[[1,2],[3,4],[5]]"


def test_canonical_json_is_rfc8785() -> None:
    """Compact, raw UTF-8, keys in UTF-16 code-unit order (U+1F600 is
    D83D DE00, before U+FFFD, unlike code-point order)."""
    value = {"�": 1, "\U0001f600": 2, "b": [1e-7, 100.0, "é"], "a": None}
    text = '{"a":null,"b":[1e-7,100,"é"],"\U0001f600":2,"�":1}'
    assert canonical_json(value) == text
    assert canonical_json_bytes(value) == text.encode("utf-8")


def test_deep_nesting_takes_one_frame_per_level() -> None:
    """A nesting over half the recursion limit, which a parser takes,
    serialises."""
    depth = sys.getrecursionlimit() * 3 // 5
    value: object = 1
    for _ in range(depth):
        value = [value]
    assert canonical_json(value) == "[" * depth + "1" + "]" * depth


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, "{}"),
        ([], "[]"),
        ("s", '"s"'),
        ([[]], "[\n  []\n]"),
        ({"b": [1, {}], "a": 2}, '{\n  "a": 2,\n  "b": [\n    1,\n    {}\n  ]\n}'),
        # structural characters, quotes and backslashes inside strings
        ({"k": 'a, b: {c} [d] "e" \\'}, '{\n  "k": "a, b: {c} [d] \\"e\\" \\\\"\n}'),
        # RFC 8785 order is UTF-16 code units: U+10000 sorts before U+E000
        (
            {"\ue000": 1, "\U00010000": 2},
            '{\n  "\U00010000": 2,\n  "\ue000": 1\n}',
        ),
    ],
    ids=["object", "array", "scalar", "nested-empty", "keys", "strings", "utf16-order"],
)
def test_indented_canonical_json(value: object, expected: str) -> None:
    assert canonical_json_indented(value) == expected
    # only whitespace between tokens was added
    assert without_token_whitespace(canonical_json_indented(value)) == (
        canonical_json(value)
    )


def test_indent_width_is_a_parameter() -> None:
    assert (
        indent_canonical('{"a":[1]}', indent=4) == '{\n    "a": [\n        1\n    ]\n}'
    )
