# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract._license_classify.classify_license`."""

from __future__ import annotations

import logging
from unittest.mock import create_autospec

import pytest
from py_spdx_license import parse as spdx_parse

from pitloom.extract import _license_classify
from pitloom.extract._license_classify import (
    ClassifiedLicense,
    classify_license,
    is_listed_name,
)

_LONG_BODY = "Permission is granted to use, copy and modify this software, and " * 800


def _padded(length: int) -> str:
    """A valid expression of exactly *length* characters."""
    text = f"MIT{' ' * (length - 9)}OR MIT"
    assert len(text) == length
    return text


#: (raw, kind, value, whether a WARNING is expected); ``None`` kind = no licence.
_CASES = [
    # no licence stated
    (None, None, "", False),
    ("", None, "", False),
    ("  \t ", None, "", False),
    # UNKNOWN: the source does not know, which is NOASSERTION
    ("UNKNOWN", "noassertion", "NOASSERTION", False),
    ("unknown", "noassertion", "NOASSERTION", False),
    (" Unknown ", "noassertion", "NOASSERTION", False),
    # individuals, in any case
    ("NOASSERTION", "noassertion", "NOASSERTION", False),
    (" noassertion ", "noassertion", "NOASSERTION", False),
    ("NONE", "none", "NONE", False),
    ("none", "none", "NONE", False),
    # valid expressions, canonical
    ("MIT", "expression", "MIT", False),
    ("mit", "expression", "MIT", False),
    ("mit and apache-2.0", "expression", "Apache-2.0 AND MIT", False),
    (
        "MIT AND (Apache-2.0 OR GPL-2.0-only)",
        "expression",
        "MIT AND (Apache-2.0 OR GPL-2.0-only)",
        False,
    ),
    (
        "GPL-2.0-only WITH Classpath-exception-2.0",
        "expression",
        "GPL-2.0-only WITH Classpath-exception-2.0",
        False,
    ),
    ("LicenseRef-foo", "expression", "LicenseRef-foo", False),
    # grammar gaps: canonical like any expression
    ("Apache-2.0+", "expression", "Apache-2.0+", False),
    ("apache-2.0+", "expression", "Apache-2.0+", False),
    # a deprecated id with a listed successor is replaced by it
    ("GPL-2.0+", "expression", "GPL-2.0-or-later", False),
    ("lgpl-2.1+", "expression", "LGPL-2.1-or-later", False),
    ("gpl-2.0+ or mit", "expression", "GPL-2.0-or-later OR MIT", False),
    (
        "GPL-2.0+ WITH Classpath-exception-2.0",
        "expression",
        "GPL-2.0-or-later WITH Classpath-exception-2.0",
        False,
    ),
    (
        "Apache-2.0 WITH AdditionRef-x",
        "expression",
        "Apache-2.0 WITH AdditionRef-x",
        False,
    ),
    ("GPL-2.0", "expression", "GPL-2.0", False),
    # an addition after an id that says only/or-later, or a user reference
    (
        "GPL-2.0-only WITH AdditionRef-x",
        "expression",
        "GPL-2.0-only WITH AdditionRef-x",
        False,
    ),
    (
        "LicenseRef-a WITH AdditionRef-x",
        "expression",
        "LicenseRef-a WITH AdditionRef-x",
        False,
    ),
    (
        "DocumentRef-d:LicenseRef-a WITH AdditionRef-x",
        "expression",
        "DocumentRef-d:LicenseRef-a WITH AdditionRef-x",
        False,
    ),
    # a user's own reference spelled like the gap placeholder is kept
    (
        "LicenseRef-pitloom-gap-000 OR Apache-2.0+",
        "expression",
        "LicenseRef-pitloom-gap-000 OR Apache-2.0+",
        False,
    ),
    (
        "LicenseRef-pitloom-gap-0001 OR Apache-2.0+ OR MIT+",
        "expression",
        "LicenseRef-pitloom-gap-0001 OR Apache-2.0+ OR MIT+",
        False,
    ),
    # `+` only follows a listed licence id
    ("LicenseRef-foo+", "text", "LicenseRef-foo+", False),
    ("DocumentRef-x:LicenseRef-y+", "text", "DocumentRef-x:LicenseRef-y+", False),
    ("MIT WITH AdditionRef-x+", "text", "MIT WITH AdditionRef-x+", True),
    ("GPL-2.0++", "text", "GPL-2.0++", False),
    ("LGPL-2.1++", "text", "LGPL-2.1++", False),
    ("GPL-2.0-only+", "text", "GPL-2.0-only+", False),
    ("GPL-2.0-or-later+", "text", "GPL-2.0-or-later+", False),
    ("licenseref-foo", "text", "licenseref-foo", False),
    # an addition needs a licence: a listed id or a well-formed reference
    ("Foo WITH AdditionRef-x", "text", "Foo WITH AdditionRef-x", False),
    ("LicenseRef- WITH AdditionRef-x", "text", "LicenseRef- WITH AdditionRef-x", False),
    (
        "LicenseRef-a+ WITH AdditionRef-x",
        "text",
        "LicenseRef-a+ WITH AdditionRef-x",
        True,
    ),
    # looks like an expression, is not: text and one WARNING
    ("GPL-2.0+ OR Foo", "text", "GPL-2.0+ OR Foo", True),
    ("(GPL-2.0+", "text", "(GPL-2.0+", True),
    ("GPL-2.0+ AND", "text", "GPL-2.0+ AND", True),
    ("mit or", "text", "mit or", True),
    ("MIT with attribution", "text", "MIT with attribution", True),
    ("MIT OR", "text", "MIT OR", True),
    ("(MIT", "text", "(MIT", True),
    ("MIT)", "text", "MIT)", True),
    ("GPL-2.0-only+ OR Foo", "text", "GPL-2.0-only+ OR Foo", True),
    ("MIT AND Foo", "text", "MIT AND Foo", True),
    (
        "Apache-2.0 WITH AdditionRef-x AND Foo",
        "text",
        "Apache-2.0 WITH AdditionRef-x AND Foo",
        True,
    ),
    # text, silent
    ("Apache2", "text", "Apache2", False),
    (" Foo ", "text", "Foo", False),
    ("MIT License", "text", "MIT License", False),
    ("Foo AND Bar", "text", "Foo AND Bar", False),
    ("Classpath-exception-2.0", "text", "Classpath-exception-2.0", False),
    ("MIT\nApache-2.0", "text", "MIT\nApache-2.0", False),
    ("MIT OR\nApache-2.0", "text", "MIT OR\nApache-2.0", False),  # never parsed
    (_LONG_BODY, "text", _LONG_BODY.strip(), False),
    # the length boundary: 200 parses, 201 does not
    (_padded(200), "expression", "MIT", False),
    (_padded(201), "text", _padded(201), False),
]


@pytest.mark.parametrize(
    ("raw", "kind", "value", "warns"),
    [pytest.param(*c, id=repr(c[0])[:40]) for c in _CASES],
)
def test_classify_license(
    raw: str | None,
    kind: str | None,
    value: str,
    warns: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        got = classify_license(raw)
    if kind is None:
        assert got is None
    else:
        assert got is not None
        assert (got.kind, got.value, got.raw) == (kind, value, raw or "")
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
    ("raw", "expected"),
    [
        ("bsd-3-clause", "BSD-3-Clause"),
        ("GPL-2.0-OR-LATER", "GPL-2.0-or-later"),
        ("MIT AND MIT", "MIT"),
        ("(mit and mit)", "MIT"),
        ("(MIT)", "MIT"),
        # operator words glued into an id are not operators
        ("LicenseRef-my-or-license", "LicenseRef-my-or-license"),
        ("LicenseRef-and-tool", "LicenseRef-and-tool"),
    ],
)
def test_expression_values_are_canonical(raw: str, expected: str) -> None:
    assert _value(raw) == expected


def test_equivalent_expressions_share_one_value() -> None:
    assert _value("MIT OR Apache-2.0") == _value("Apache-2.0 OR MIT")
    assert _value("GPL-2.0+") == _value("GPL-2.0-or-later") == _value("gpl-2.0+")
    assert _value("lgpl-2.1+") == _value("LGPL-2.1+")
    # Redundant parentheses change nothing; a precedence-changing one does.
    plain = _value("MIT AND Apache-2.0 OR BSD-3-Clause")
    assert plain == _value("(MIT AND Apache-2.0) OR BSD-3-Clause")
    assert plain != _value("MIT AND (Apache-2.0 OR BSD-3-Clause)")


@pytest.mark.parametrize(
    "raw",
    [
        "MIT OR Apache-2.0",
        "mit and apache-2.0",
        "GPL-2.0+",
        "Apache-2.0+ WITH AdditionRef-x",
    ],
)
def test_classifying_a_recorded_expression_changes_nothing(raw: str) -> None:
    once = _value(raw)
    assert once is not None
    assert _value(once) == once


@pytest.mark.parametrize(
    ("name", "license_id", "expected"),
    [
        ("MIT License", "MIT", True),
        (" mit license ", "mit", True),  # case and padding are spelling
        ("MIT", "MIT", False),  # an id is not a name
        ("Apache Software License", "Apache-2.0", False),  # not the List name
        ("MIT License", "Foo", False),  # not a listed id
    ],
)
def test_is_listed_name(name: str, license_id: str, expected: bool) -> None:
    assert is_listed_name(name, license_id) is expected


@pytest.mark.parametrize("raw", [")", ")(", "A)", ")A", "))", "((unbalanced"])
def test_malformed_input_never_raises(raw: str) -> None:
    """The parser raises ``IndexError`` for some shapes of unbalanced ``)``
    (found by ``fuzz/fuzz_license_expression.py``); the value is text."""
    got = classify_license(raw)
    assert got is not None
    assert got.kind == "text"


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


def test_grammar_gap_expressions_are_canonical_in_any_spelling() -> None:
    values = {_value(raw) for raw in _GAP_FORMS}
    assert len(values) == 1
    (value,) = values
    assert value is not None
    assert "\t" not in value and "  " not in value
    assert _value(value) == value


@pytest.mark.parametrize("operator", ["AND", "OR"])
def test_grammar_gap_terms_sort_whatever_the_input_order(operator: str) -> None:
    forward = _value(f"Apache-2.0+ {operator} BSD-3-Clause+ {operator} MIT")
    assert forward is not None
    assert forward == _value(f"MIT {operator} BSD-3-Clause+ {operator} Apache-2.0+")
    assert forward == _value(f"BSD-3-Clause+ {operator} MIT {operator} Apache-2.0+")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MIT+ OR MIT+", "MIT+"),
        ("Apache-2.0+  WITH  AdditionRef-x", "Apache-2.0+ WITH AdditionRef-x"),
        (
            "Apache-2.0 WITH AdditionRef-x OR MIT",
            "MIT OR Apache-2.0 WITH AdditionRef-x",
        ),
        ("MIT+ OR MIT", "MIT OR MIT+"),  # distinct terms are not merged
        (
            "apache-2.0+ with classpath-exception-2.0",
            "Apache-2.0+ WITH Classpath-exception-2.0",
        ),
    ],
)
def test_grammar_gap_terms_collapse_only_when_identical(
    raw: str, expected: str
) -> None:
    assert _value(raw) == expected


def test_a_lone_surrogate_is_replaced_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Else serialisation fails on it (``CanonicalizationError``)."""
    raw = "Foo\ud800 bar"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        got = classify_license(raw)
        classify_license(raw)
    assert got == ClassifiedLicense("text", "Foo� bar", "Foo� bar")
    assert len(caplog.records) == 1
    assert "\\ud800" in caplog.records[0].getMessage()


@pytest.mark.parametrize(
    "raw",
    ["Apache-2.0+ WITH Not-an-exception", "MIT+ OR \x00Apache-2.0\x00", "Foo+ OR MIT+"],
)
def test_a_grammar_gap_term_that_is_not_valid_spdx_stays_text(raw: str) -> None:
    got = classify_license(raw, warn=False)
    assert got is not None
    assert got.kind == "text"


def test_a_lone_surrogate_is_replaced_silently_when_not_recording(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        got = classify_license("Foo\ud800", warn=False)
    assert got == ClassifiedLicense("text", "Foo\ufffd", "Foo\ufffd")
    assert not caplog.records


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
