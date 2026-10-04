# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract._license.classify_license`."""

from __future__ import annotations

import logging
import time

import pytest

from pitloom.extract import _license
from pitloom.extract._license import ClassifiedLicense, classify_license

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
    ("UNKNOWN", None, "", False),
    ("unknown", None, "", False),
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
    # grammar gaps: kept as written, operators upper-cased
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
    # `+` only follows a listed licence id
    ("LicenseRef-foo+", "text", "LicenseRef-foo+", False),
    ("DocumentRef-x:LicenseRef-y+", "text", "DocumentRef-x:LicenseRef-y+", False),
    ("MIT WITH AdditionRef-x+", "text", "MIT WITH AdditionRef-x+", True),
    ("GPL-2.0++", "text", "GPL-2.0++", False),
    ("LGPL-2.1++", "text", "LGPL-2.1++", False),
    ("GPL-2.0-only+", "text", "GPL-2.0-only+", False),
    ("GPL-2.0-or-later+", "text", "GPL-2.0-or-later+", False),
    ("licenseref-foo", "text", "licenseref-foo", False),
    # looks like an expression, is not: text and one WARNING
    ("GPL-2.0+ OR Foo", "text", "GPL-2.0+ OR Foo", True),
    ("(GPL-2.0+", "text", "(GPL-2.0+", True),
    ("GPL-2.0+ AND", "text", "GPL-2.0+ AND", True),
    ("mit or", "text", "mit or", True),
    ("MIT with attribution", "text", "MIT with attribution", True),
    ("MIT OR", "text", "MIT OR", True),
    ("(MIT", "text", "(MIT", True),
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


def test_long_text_is_not_parsed() -> None:
    """A 48 KB body is classified without running the expression parser."""
    body = "MIT and Apache-2.0 " * 2500
    start = time.monotonic()
    got = classify_license(body)
    assert time.monotonic() - start < 1.0
    assert got is not None
    assert got.kind == "text"


def test_a_parser_crash_makes_the_value_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parser can raise other than ``ParseError`` on odd input."""

    def crash(_expression: str) -> None:
        raise IndexError("boom")

    monkeypatch.setattr(_license, "parse_spdx_expression", crash)
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
        _license,
        "get_spdx_license",
        lambda i: (
            {"licenseId": i, "isDeprecatedLicenseId": listed[i]}
            if i in listed
            else None
        ),
    )
    # pylint: disable-next=protected-access
    assert _license._successor_id("Foo+") == expected
