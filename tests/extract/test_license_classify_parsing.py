# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests of how :func:`pitloom.extract._license_classify.classify_license`
reads an expression through ``licenseid``: one canonical value per licence,
what is never read (long and multi-line text), and the warning for a value
that looks like a broken expression.

See also: tests/extract/test_license_classify.py (the table),
tests/extract/test_license_resolve.py (what Pitloom does with an answer),
tests/extract/test_license_readback_guard.py.
"""

from __future__ import annotations

import itertools
import logging
from typing import Any

import pytest
from licenseid import resolve as licenseid_resolve

from pitloom.extract import _license_resolve
from pitloom.extract._license_classify import classify_license


def test_warning_is_one_line_once_per_value_and_escapes_controls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = "MIT OR\x1b[31m"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        classify_license(raw)
        classify_license(raw)
        classify_license("MIT OR GPL-2.0-only AND")
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 2
    assert messages[0].startswith("LICENSE='MIT OR\\x1b[31m': not a valid SPDX")
    assert messages[0].endswith("recorded as license text")
    assert "\n" not in messages[0]
    assert "\x1b" not in messages[0]


@pytest.mark.parametrize(
    "body",
    ["MIT and Apache-2.0 " * 2500, "MIT\nOR Apache-2.0"],
    ids=["48-kb", "multi-line"],
)
def test_long_or_multi_line_text_is_not_read(
    body: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 48 KB body or a multi-line value is text without the resolver ever
    being asked."""
    asked: list[str] = []

    def spy(value: str, **kwargs: Any) -> Any:
        asked.append(value)
        return licenseid_resolve(value, **kwargs)

    monkeypatch.setattr(_license_resolve, "resolve", spy)
    got = classify_license(body)
    assert not asked
    assert got is not None
    assert got.kind == "text"


def _value(raw: str) -> str | None:
    got = classify_license(raw)
    return got.value if got else None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MIT OR ISC OR MIT OR ISC", "ISC OR MIT"),
        ("GPL-2.0-or-later OR MIT OR GPL-2.0-or-later", "GPL-2.0-or-later OR MIT"),
        ("MIT AND ISC AND MIT", "ISC AND MIT"),
        ("MIT OR ISC OR MIT OR ISC OR 0BSD", "0BSD OR ISC OR MIT"),
    ],
)
def test_a_repeated_term_is_one_term(
    raw: str, expected: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        got = classify_license(raw)
    assert got is not None
    assert (got.kind, got.value) == ("expression", expected)
    assert not caplog.records


def _orders(operator: str) -> list[str]:
    """Terms with a ``+`` joined by *operator*, in every order."""
    terms = ["Apache-2.0+", "BSD-3-Clause+", "MIT"]
    return [f" {operator} ".join(order) for order in itertools.permutations(terms)]


@pytest.mark.parametrize(
    "spellings",
    [
        ["MIT OR Apache-2.0", "Apache-2.0 OR MIT"],
        ["GPL-2.0+", "GPL-2.0-or-later", "gpl-2.0+"],
        ["lgpl-2.1+", "LGPL-2.1+"],
        # a redundant parenthesis changes nothing
        ["MIT AND Apache-2.0 OR BSD-3-Clause", "(MIT AND Apache-2.0) OR BSD-3-Clause"],
        ["Apache-2.0+ OR MIT", "Apache-2.0+  OR  MIT", "Apache-2.0+\tOR\tMIT",
         "MIT OR Apache-2.0+", "apache-2.0+ or mit", "MIT OR Apache-2.0+ OR MIT"],
        _orders("AND"),
        _orders("OR"),
        # once recorded, classifying the value again changes nothing
        ["mit and apache-2.0"],
        ["Apache-2.0+ WITH AdditionRef-x"],
    ],
    ids=["or-order", "plus", "lgpl-plus", "parens", "plus-or", "plus-and",
         "plus-orders", "recorded", "plus-with"],
)  # fmt: skip
def test_equivalent_spellings_share_one_canonical_value(spellings: list[str]) -> None:
    (value,) = {_value(raw) for raw in spellings}
    assert value is not None
    assert "\t" not in value and "  " not in value
    assert _value(value) == value


def test_a_precedence_changing_parenthesis_is_another_value() -> None:
    assert _value("MIT AND Apache-2.0 OR BSD-3-Clause") != _value(
        "MIT AND (Apache-2.0 OR BSD-3-Clause)"
    )


@pytest.mark.parametrize(
    "raw",
    ["LicenseRef-pitloom-gap-000 OR Apache-2.0+", "MIT+ OR LicenseRef-x OR MIT+"],
)
def test_a_reference_beside_an_id_is_kept_whatever_the_order(raw: str) -> None:
    """The order of a reference beside an id is ``licenseid``'s to choose;
    each term is kept, and the value reads back as itself."""
    got = classify_license(raw, warn=False)
    assert got is not None and got.kind == "expression"
    assert set(got.value.split(" OR ")) == set(raw.split(" OR "))
    assert _value(got.value) == got.value


@pytest.mark.parametrize(
    "raw",
    ["Apache-2.0+ WITH Not-an-exception", "MIT+ OR \x00Apache-2.0\x00", "Foo+ OR MIT+"],
)
def test_a_term_that_is_not_valid_spdx_stays_text(raw: str) -> None:
    got = classify_license(raw, warn=False)
    assert got is not None
    assert got.kind == "text"


@pytest.mark.parametrize("separator", ["\x1c", "\x1d", "\x1e", "\x85", " "])
def test_the_warning_reason_is_not_cut_at_a_unicode_line_break(
    separator: str, caplog: pytest.LogCaptureFixture
) -> None:
    raw = f"MIT AND Foo{separator}bar"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        classify_license(raw)
    (message,) = [r.getMessage() for r in caplog.records]
    assert message.endswith("); recorded as license text")
    assert message.count("'") % 2 == 0


@pytest.mark.parametrize(
    ("raw", "warns"),
    [
        ("MIT OR Foo", True),  # an id as written
        ("mit or foo", True),  # in any case
        ("GPL-2.0 OR Foo", True),  # a deprecated id as written
        ("GPL-2.0+ OR Foo", True),  # the "+" left out
        ("StandardML-NJ OR Foo", True),  # renamed on the List
        ("GPLv3 OR Foo", False),  # a re-spelling is no id as written
        ("Apache2 OR Foo", False),
        ("MIT License OR Foo", True),  # the id "MIT" beside a word
        ("BSD License OR Foo", False),  # a name, no id
        ("Foo OR Bar", False),
        ("MIT; Foo", False),  # no operator, no bracket
    ],
)
def test_a_broken_expression_warns_when_it_holds_an_id_as_written(
    raw: str, warns: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """The warning keeps its rule: an operator or bracket, and a word that is
    a licence id as written (:func:`~pitloom.extract._license_resolve.\
is_licence_id`)."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        got = classify_license(raw)
    assert got is not None and got.kind == "text"
    assert len(caplog.records) == int(warns)
