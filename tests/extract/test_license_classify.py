# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract._license_classify.classify_license` that
stay when Pitloom hands the expression parsing to ``licenseid``: the early
exits (no licence, ``NOASSERTION``, ``NONE``), a single id, text, a lone
surrogate, a name from the List.

See also: tests/extract/test_license_classify_parsing.py (what goes with
Pitloom's own parsing), tests/extract/license_classify_cases.py (the table).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract._license_classify import (
    ClassifiedLicense,
    classify_license,
    is_listed_name,
)
from tests.extract.license_classify_cases import STAYING


@pytest.mark.parametrize(
    ("raw", "kind", "value", "warns"),
    [pytest.param(*c, id=repr(c[0])[:40]) for c in STAYING],
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
    ("raw", "warn"), [("Foo\ud800 bar", True), ("Foo\ud800", False)]
)
def test_a_lone_surrogate_is_replaced(
    raw: str, warn: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Else serialisation fails on it (``CanonicalizationError``): one
    ``WARNING:`` when recording, none when not."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        got = classify_license(raw, warn=warn)
        classify_license(raw, warn=warn)
    replaced = raw.replace("\ud800", "\ufffd")
    assert got == ClassifiedLicense("text", replaced, replaced)
    assert ["\\ud800" in r.getMessage() for r in caplog.records] == [True] * warn
