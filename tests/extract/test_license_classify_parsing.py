# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests of Pitloom's own expression parsing in
:mod:`pitloom.extract._license_classify`: operators, the ``+`` and
``AdditionRef-`` grammar gaps, canonical order, the deprecated-successor rule and
the ``py-spdx-license`` workarounds. They go with that code when Pitloom reads
declared values through ``licenseid`` 0.7.0 (the adoption plan, task T13); the
table is regenerated from the sweep then.

See also: tests/extract/test_license_classify.py (what stays),
tests/extract/license_classify_cases.py (the table),
tests/extract/test_license_parse_drift_guard.py.
"""

from __future__ import annotations

import itertools
import logging
from unittest.mock import create_autospec

import pytest
from py_spdx_license import parse as spdx_parse

from pitloom.extract import _license_classify
from pitloom.extract._license_classify import ClassifiedLicense, classify_license
from tests.extract.license_classify_cases import PARSING


@pytest.mark.parametrize(
    ("raw", "kind", "value", "warns"),
    [pytest.param(*c, id=repr(c[0])[:40]) for c in PARSING],
)
def test_classify_license_by_own_parsing(
    raw: str | None,
    kind: str | None,
    value: str,
    warns: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        got = classify_license(raw)
    assert got is not None
    assert (got.kind, got.value, got.raw) == (kind, value, raw)
    assert len(caplog.records) == int(warns)


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
def test_long_or_multi_line_text_is_not_parsed(
    body: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 48 KB body (seconds in the parser) or a multi-line value is text
    without the expression parser ever being called."""
    parser = create_autospec(spdx_parse)
    monkeypatch.setattr(_license_classify, "parse_spdx_expression", parser)
    got = classify_license(body)
    parser.assert_not_called()
    assert got is not None
    assert got.kind == "text"


def test_a_parser_crash_makes_the_value_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parser can raise other than ``ParseError`` on odd input."""
    crash = create_autospec(spdx_parse, side_effect=IndexError("boom"))
    monkeypatch.setattr(_license_classify, "parse_spdx_expression", crash)
    assert classify_license("MIT") == ClassifiedLicense("text", "MIT", "MIT")


def _value(raw: str) -> str | None:
    got = classify_license(raw)
    return got.value if got else None


@pytest.mark.parametrize(
    ("listed", "expected"),
    [
        ({"Foo+": True, "Foo-or-later": False}, "Foo-or-later"),
        ({"Foo+": True}, None),  # no successor on the list
        ({"Foo+": True, "Foo-or-later": True}, None),  # successor deprecated too
        ({"Foo+": False, "Foo-or-later": False}, None),  # not deprecated
    ],
)
def test_successor_id_needs_a_listed_current_id(
    monkeypatch: pytest.MonkeyPatch, listed: dict[str, bool], expected: str | None
) -> None:
    """The successor comes from the licence list, never from a spelling rule."""
    monkeypatch.setattr(
        _license_classify,
        "get_spdx_license",
        lambda i: (
            {"licenseId": i, "isDeprecatedLicenseId": listed[i]}
            if i in listed
            else None
        ),
    )
    # pylint: disable-next=protected-access
    assert _license_classify._successor_id("Foo+") == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MIT OR ISC OR MIT OR ISC", "ISC OR MIT"),
        ("GPL-2.0-or-later OR MIT OR GPL-2.0-or-later", "GPL-2.0-or-later OR MIT"),
        ("MIT OR LicenseRef-a OR MIT", "MIT OR LicenseRef-a"),
        ("MIT AND ISC AND MIT", "ISC AND MIT"),
        ("MIT OR ISC OR MIT OR ISC OR 0BSD", "0BSD OR ISC OR MIT"),
    ],
)
def test_a_repeated_term_is_one_term_not_a_parser_failure(
    raw: str, expected: str, caplog: pytest.LogCaptureFixture
) -> None:
    """``py-spdx-license`` 0.0.1 raises ``TypeError`` from ``sort()`` on
    these; the value is still a valid expression, with no WARNING."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        got = classify_license(raw)
    assert got is not None
    assert (got.kind, got.value) == ("expression", expected)
    assert not caplog.records


def test_a_shape_the_library_cannot_sort_keeps_the_parsers_spelling() -> None:
    """A mixed, nested chain with a repeat: valid, so never text."""
    got = classify_license("(MIT OR 0BSD AND MIT OR ISC) OR ISC", warn=False)
    assert got is not None
    assert (got.kind, got.value) == ("expression", "MIT OR 0BSD AND MIT OR ISC OR ISC")


_GAP_FORMS = [
    "Apache-2.0+ OR MIT",
    "Apache-2.0+  OR  MIT",
    "Apache-2.0+\tOR\tMIT",
    "MIT OR Apache-2.0+",
    "apache-2.0+ or mit",
    "MIT OR Apache-2.0+ OR MIT",
]


def _orders(operator: str) -> list[str]:
    """Grammar-gap terms joined by *operator*, in every order."""
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
        _GAP_FORMS,
        _orders("AND"),
        _orders("OR"),
        # once recorded, classifying the value again changes nothing
        ["mit and apache-2.0"],
        ["Apache-2.0+ WITH AdditionRef-x"],
    ],
    ids=["or-order", "plus", "lgpl-plus", "parens", "gap", "gap-and", "gap-or",
         "recorded", "gap-with"],
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
    ["Apache-2.0+ WITH Not-an-exception", "MIT+ OR \x00Apache-2.0\x00", "Foo+ OR MIT+"],
)
def test_a_grammar_gap_term_that_is_not_valid_spdx_stays_text(raw: str) -> None:
    got = classify_license(raw, warn=False)
    assert got is not None
    assert got.kind == "text"


@pytest.mark.parametrize("separator", ["\x1c", "\x1d", "\x1e", "\x85", " "])
def test_the_warning_reason_is_not_cut_at_a_unicode_line_break(
    separator: str, caplog: pytest.LogCaptureFixture
) -> None:
    raw = f"MIT AND Foo{separator}bar"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        classify_license(raw)
    (message,) = [r.getMessage() for r in caplog.records]
    assert message.endswith("); recorded as license text")
    assert message.count("'") % 2 == 0
