# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The licence messages through the real readers: a value refused as an
expression (``license-expression-malformed`` or ``-invalid``, by
LicenseID's category, never by which helper says it), LicenseID's reading
(``license-expression-invalid/resolved`` at ``INFO:``, a change of form at
``DEBUG:`` with no code), several classifiers (``license-ambiguous``) and a
lone surrogate in a value (``text-malformed``). Each value is said once,
whichever helper comes first.

See also: tests/messages/test_licence_surfaces.py (the entry points and the
database lines), tests/extract/test_license_spdx_only_fields.py and
tests/assemble/test_license_database_missing.py (the policies).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract._core_metadata import license_cascade, license_from_classifiers
from pitloom.extract._license import classify_license, warn_unless_expression
from pitloom.logging_config import CODE_ATTR
from tests._code_records import coded

_MALFORMED = "license-expression-malformed"
_INVALID = "license-expression-invalid"
_RESOLVED = "license-expression-invalid/resolved"

#: A value that looks like an expression, and the code of its refusal.
_REFUSED = [
    ("MIT OR", _MALFORMED),  # an operator with no operand
    ("(MIT", _MALFORMED),  # a parenthesis without its match
    ("MIT AND (Apache-2.0", _MALFORMED),
    ("MIT OR Foo", _INVALID),  # an operand LicenseID names nothing for
    ("Apache-2.0 WITH Bar", _INVALID),  # an exception not on the List
    ("MIT; Apache-2.0", _INVALID),  # no operator: nothing to parse
]


@pytest.mark.parametrize(("value", "code"), _REFUSED, ids=[v for v, _ in _REFUSED])
@pytest.mark.parametrize("field", [None, "License-Expression"], ids=["text", "field"])
def test_a_refusal_is_coded_by_licenseids_category(
    value: str, code: str, field: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """The split is LicenseID's: a broken-expression warning and a field
    holding an expression only say the same code for one value."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        if field is None:
            classify_license(value)
        else:
            warn_unless_expression(value, field)
    said = coded(caplog)
    if value == "MIT; Apache-2.0" and field is None:
        assert not said  # no operator: no broken expression to warn about
        return
    ((got, message),) = said
    assert got == code
    assert message.startswith(f"FIELD={field} " if field else "LICENSE=")
    assert message.endswith("; recorded as licence text")


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("Foo OR", _MALFORMED),  # LicenseID: category unresolved, reason parse failed
        ("Acme OR", _MALFORMED),
        ("(Foo", _MALFORMED),
        ("OR OR", _MALFORMED),
        ("MIT WITH", _INVALID),  # a WITH with no exception is read as a name
    ],
    ids=["foo-or", "acme-or", "paren", "or-or", "with-none"],
)
def test_a_parse_failure_is_malformed_whatever_the_category(
    value: str, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    """LicenseID reports some syntax errors under ``unresolved`` with a
    ``parse failed:`` reason: they are as malformed as ``MIT OR``."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_unless_expression(value, "License-Expression")
    ((got, _),) = coded(caplog)
    assert got == code


def test_a_url_credential_in_the_reason_is_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reason repeats the operand LicenseID could not resolve."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        classify_license("MIT OR https://u:hunter2@h.example/x")
    ((_, message),) = coded(caplog)
    assert "hunter2" not in message
    assert message.count("***:***@h.example") == 2  # the value and the reason


def test_an_empty_field_name_is_no_field(caplog: pytest.LogCaptureFixture) -> None:
    """``say_resolved`` and the refusal line take a field only when it has a
    name: an empty one is the line without ``FIELD=``, not an error."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_unless_expression("MIT OR Foo", "")
    ((_, message),) = coded(caplog)
    assert message.startswith("LICENSE=")


@pytest.mark.parametrize("helper_first", [True, False], ids=["field", "text"])
def test_a_refused_value_is_said_once_through_both_helpers(
    helper_first: bool, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        if helper_first:
            warn_unless_expression("MIT OR Foo", "project.license")
        classify_license("MIT OR Foo")
        warn_unless_expression("MIT OR Foo", "project.license")
        classify_license("MIT OR Foo")
    levels = [(r.levelno, getattr(r, CODE_ATTR, None)) for r in caplog.records]
    assert levels[0] == (logging.WARNING, _INVALID)
    assert all(level == logging.DEBUG for level, _ in levels[1:])


@pytest.mark.parametrize(
    ("value", "level", "code"),
    [
        ("Apache2", logging.INFO, _RESOLVED),  # a re-spelling: decided
        ("MIT License", logging.INFO, _RESOLVED),  # a listed name
        ("mit", logging.DEBUG, None),  # case only: form
        ("GPL-2.0+", logging.DEBUG, None),  # a "+": form
    ],
    ids=["respelt", "name", "case", "plus"],
)
def test_a_reading_is_info_when_decided_else_debug(
    value: str, level: int, code: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """The level is the reading's, the text the same either way; only the
    ``INFO:`` line carries a code."""
    with caplog.at_level(logging.DEBUG, logger="pitloom.extract._license_resolve"):
        classify_license(value)
        classify_license(value)
    first, *again = caplog.records
    assert (first.levelno, getattr(first, CODE_ATTR, None)) == (level, code)
    assert first.getMessage().startswith(f"LICENSE={value!r}: read as ")
    assert [r.levelno for r in again] == [logging.DEBUG]


def test_a_reading_is_said_once_through_both_helpers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``MIT License`` read alone, then as one of several classifiers (its
    ``FIELD=classifiers`` line), shares one key: one ``INFO:``."""
    classifiers = [
        "License :: OSI Approved :: MIT License",
        "License :: OSI Approved :: Apache Software License",
    ]
    with caplog.at_level(logging.INFO, logger="pitloom.extract._license_resolve"):
        classify_license("MIT License")
        license_from_classifiers(classifiers)
    assert coded(caplog) == [
        (_RESOLVED, "LICENSE='MIT License': read as MIT (listed_name)")
    ]


def test_several_classifiers_are_ambiguous_once_per_set(
    caplog: pytest.LogCaptureFixture,
) -> None:
    classifiers = [
        "License :: OSI Approved :: MIT License",
        "License :: OSI Approved :: BSD License",
    ]
    with caplog.at_level(logging.WARNING, logger="pitloom.extract._core_metadata"):
        _, licence = license_cascade([None], classifiers)
        license_cascade([None], classifiers)
        license_cascade([None], classifiers[:1])  # one licence: no choice
    ((code, message),) = coded(caplog)
    assert code == "license-ambiguous"
    assert message.startswith(
        "CLASSIFIERS='License :: OSI Approved :: BSD License', "
        "'License :: OSI Approved :: MIT License': several licence classifiers"
    )
    assert f"recorded as {licence}, assuming AND" in message


@pytest.mark.parametrize("warn", [True, False], ids=["warn", "quiet"])
def test_a_lone_surrogate_is_replaced_and_said_once(
    warn: bool, caplog: pytest.LogCaptureFixture
) -> None:
    raw = "MIT\udc80 License"
    with caplog.at_level(logging.WARNING, logger="pitloom.extract._license_classify"):
        got = classify_license(raw, warn=warn)
        classify_license(raw, warn=warn)
    assert got is not None and "\ufffd" in got.value
    expected = [("text-malformed", "LICENSE='MIT\\udc80 License': lone surrogates")]
    said = [(code, text[: len(expected[0][1])]) for code, text in coded(caplog)]
    assert said == (expected if warn else [])


def test_each_value_with_a_lone_surrogate_is_said(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The key is the value as read: two values that read the same once
    replaced are two lines."""
    with caplog.at_level(logging.WARNING, logger="pitloom.extract._license_classify"):
        for raw in ("MIT\udc80 Licence", "MIT\udc81 Licence"):
            classify_license(raw)
    assert [code for code, _ in coded(caplog)] == ["text-malformed"] * 2


def test_two_classifiers_naming_one_licence_are_not_ambiguous(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two classifiers, one licence name: no choice to assume AND over."""
    classifiers = ["License :: OSI Approved :: MIT License", "License :: MIT License"]
    with caplog.at_level(logging.WARNING, logger="pitloom.extract._core_metadata"):
        license_cascade([None], classifiers)
    assert not coded(caplog)
