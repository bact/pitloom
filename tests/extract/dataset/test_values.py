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

from pitloom.extract.dataset.values import (
    MAX_NUMBER_DIGITS,
    stated_count,
    stated_name,
    stated_text,
    stated_texts,
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


_HUGE = 10**MAX_NUMBER_DIGITS


@pytest.mark.parametrize(
    ("value", "expected", "warns"),
    [
        (None, None, False),
        ("1.10", "1.10", False),
        (2, "2", False),
        (_HUGE - 1, str(_HUGE - 1), False),
        (1.1, None, True),
        (True, None, True),
        (_HUGE, None, True),
        (-_HUGE, None, True),
        (int("f" * 5000, 16), None, True),
    ],
    ids=["none", "text", "int", "longest", "float", "bool", "huge", "-huge", "hex"],
)
def test_stated_version(
    caplog: pytest.LogCaptureFixture, value: object, expected: object, warns: bool
) -> None:
    assert stated_version(value, _SRC) == expected
    assert bool(_warned(caplog)) is warns


@pytest.mark.parametrize(
    ("value", "expected", "warns"),
    [
        (None, None, False),
        (0, 0, False),
        (12, 12, False),
        (3.0, 3, False),
        (" 7 ", 7, False),
        (-5, None, True),
        (True, None, True),
        (False, None, True),
        (1.9, None, True),
        (float("inf"), None, True),
        (float("nan"), None, True),
        ("1e3", None, True),
        ("²", None, True),
        ("9" * (MAX_NUMBER_DIGITS + 1), None, True),
        ("9" * 5000, None, True),
        (_HUGE, None, True),
        ([3], None, True),
    ],
    ids=lambda v: repr(v)[:40],
)
def test_stated_count(
    caplog: pytest.LogCaptureFixture, value: object, expected: object, warns: bool
) -> None:
    assert stated_count(value, _SRC, "size") == expected
    assert len(_warned(caplog)) == int(warns)
