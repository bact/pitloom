# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract._license_classify.classify_license`: the
early exits (no licence, ``NOASSERTION``, ``NONE``), an expression as
``licenseid`` reads it, text, a lone surrogate.

See also: tests/extract/test_license_classify_parsing.py (expressions and
the broken-expression warning), tests/extract/license_classify_cases.py (the
table).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract._license_classify import ClassifiedLicense, classify_license
from tests.extract.license_classify_cases import CASES


@pytest.mark.parametrize(
    ("raw", "kind", "value", "warns"),
    [pytest.param(*c, id=repr(c[0])[:40]) for c in CASES],
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


@pytest.mark.parametrize("raw", [")", ")(", "A)", ")A", "))", "((unbalanced"])
def test_malformed_input_never_raises(raw: str) -> None:
    """Unbalanced brackets (found by ``fuzz/fuzz_license_expression.py``,
    where an earlier parser raised ``IndexError``): the value is text."""
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
