# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.dataset.values`: the checks every
dataset reader's field values go through.

See also: tests/extract/dataset/test_croissant.py and test_card.py (the
readers using them).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.core.canonical_json import MAX_SAFE_INTEGER
from pitloom.extract.dataset.values import (
    MAX_VERSION_DIGITS,
    stated_count,
    stated_name,
    stated_text,
    stated_texts,
    stated_total,
    stated_version,
)

_SRC = "src.json"


def _warned(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    ("value", "expected", "warns"),
    [
        (None, None, False),
        ("  ", None, False),
        ([], None, False),
        ([None], None, False),
        ([""], None, False),
        (" x ", "x", False),
        (["x"], "x", False),
        ({"@value": "x", "@language": "en"}, "x", False),
        ([{"@value": "x"}], "x", False),
        ({"@id": "https://x.org"}, "https://x.org", False),
        (["a", "b"], None, True),
        ({"name": "x"}, None, True),
        (5, None, True),
        (True, None, True),
    ],
    ids=repr,
)
def test_stated_text(
    caplog: pytest.LogCaptureFixture, value: object, expected: object, warns: bool
) -> None:
    assert stated_text(value, _SRC, "f") == expected
    assert bool(_warned(caplog)) is warns


@pytest.mark.parametrize(
    ("value", "expected", "warns"),
    [
        (None, [], False),
        ("a, b", ["a", "b"], False),
        ("a; b, c", ["a; b, c"], False),
        (["a", " ", None, {"@value": "b"}], ["a", "b"], False),
        (["a", 3, {"x": 1}], ["a"], True),
        (7, [], True),
        ([["nested"], "a"], ["a"], True),
    ],
    ids=repr,
)
def test_stated_texts(
    caplog: pytest.LogCaptureFixture, value: object, expected: object, warns: bool
) -> None:
    assert stated_texts(value, _SRC, "f") == expected
    assert len(_warned(caplog)) == int(warns)


@pytest.mark.parametrize(
    ("value", "expected", "warns"),
    [
        (None, None, False),
        ({"name": "  "}, None, False),
        ({"@type": "Person"}, None, False),
        ([{"name": "A"}, {"name": "B"}], "A", False),
        ({"sc:name": "A"}, "A", False),
        ("A", "A", False),
        ([None, " ", "Alice"], "Alice", False),
        (["unknown", "N/A", "Real"], "Real", False),  # a placeholder states nothing
        (["unknown"], None, False),
        (7, None, True),
        ({"name": 7}, None, True),
    ],
    ids=repr,
)
def test_stated_name(
    caplog: pytest.LogCaptureFixture, value: object, expected: object, warns: bool
) -> None:
    assert stated_name(value, _SRC, "creator") == expected
    assert bool(_warned(caplog)) is warns


_HUGE = 10**MAX_VERSION_DIGITS


@pytest.mark.parametrize(
    ("value", "numbers", "expected", "warns"),
    [
        (None, False, None, False),
        ("1.10", False, "1.10", False),
        (["2"], False, "2", False),
        (2, True, "2", False),
        (_HUGE - 1, True, str(_HUGE - 1), False),
        (2, False, None, True),
        (3661, False, None, True),
        (1.1, True, None, True),
        (1.1, False, None, True),
        (True, True, None, True),
        (_HUGE, True, None, True),
        (-_HUGE, True, None, True),
        (int("f" * 5000, 16), True, None, True),
    ],
    ids=[
        "none", "text", "one-item", "json-int", "longest", "yaml-int", "base-60",
        "json-float", "yaml-float", "bool", "huge", "-huge", "hex",
    ],
)  # fmt: skip
def test_stated_version(
    caplog: pytest.LogCaptureFixture,
    value: object,
    numbers: bool,
    expected: object,
    warns: bool,
) -> None:
    """JSON integers are unambiguous decimals; a YAML number is not text the
    author wrote (``1:1:1`` loads as ``3661``): quote it."""
    assert stated_version(value, _SRC, numbers=numbers) == expected
    messages = _warned(caplog)
    assert len(messages) == int(warns)
    if warns and not numbers:
        assert "quote it to keep it as written" in messages[0]


@pytest.mark.parametrize(
    ("value", "expected", "warns"),
    [
        (None, None, False),
        (0, 0, False),
        (12, 12, False),
        (3.0, 3, False),
        (" 7 ", 7, False),
        (MAX_SAFE_INTEGER, MAX_SAFE_INTEGER, False),
        (str(MAX_SAFE_INTEGER), MAX_SAFE_INTEGER, False),
        (MAX_SAFE_INTEGER + 1, None, True),
        (float(2**53), None, True),
        (10**20, None, True),
        (str(MAX_SAFE_INTEGER + 1), None, True),
        ("9" * 5000, None, True),
        (-5, None, True),
        (True, None, True),
        (False, None, True),
        (1.9, None, True),
        (float("inf"), None, True),
        (float("nan"), None, True),
        ("1e3", None, True),
        ("\u00b2", None, True),
        ([3], None, True),
    ],
    ids=lambda v: repr(v)[:40],
)
def test_stated_count(
    caplog: pytest.LogCaptureFixture, value: object, expected: object, warns: bool
) -> None:
    """A count is at most the largest integer canonical JSON can write."""
    assert stated_count(value, _SRC, "size") == expected
    assert len(_warned(caplog)) == int(warns)


@pytest.mark.parametrize(
    ("values", "expected", "warnings"),
    [
        ([], None, 0),
        ([2, 3], 5, 0),
        ([10, None, None], None, 0),
        ([10, "abc"], None, 1),
        ([-5, "x", 2], None, 1),
        ([10**63] * 20, None, 1),
        ([MAX_SAFE_INTEGER, 1], None, 1),
        ([-5, MAX_SAFE_INTEGER, 1], None, 1),
    ],
    ids=[
        "none",
        "sum",
        "partly-absent",
        "partly-bad",
        "refused-items",
        "items-over-cap",
        "sum-over-cap",
        "bad-and-over-cap",
    ],
)
def test_stated_total(
    caplog: pytest.LogCaptureFixture,
    values: list[object],
    expected: int | None,
    warnings: int,
) -> None:
    """A total only when every item states a count: one ``WARNING:`` for
    the items stating a bad one, however many, one for a sum canonical JSON
    cannot write, and none for an item stating nothing."""
    assert stated_total(values, _SRC, "size") == expected
    assert len(_warned(caplog)) == warnings
