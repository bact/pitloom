# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pitloom.core.evidence``: the one writer of the ``Evidence:`` and
``Reason:`` provenance segment."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import re

import pytest

from pitloom.core.evidence import (
    DECLARED,
    EVIDENCE_KEY,
    LOWER_BOUND,
    MEASURED_READ,
    MEASURED_STAT,
    NOT_MEASURED,
    REASON_CODES,
    REASON_KEY,
    evidence_segment,
)
from pitloom.core.provenance import parse_provenance_value


@pytest.mark.parametrize(
    ("level", "reason", "segment", "parsed"),
    [
        (MEASURED_STAT, None, "Evidence: measured_stat", {"evidence": "measured_stat"}),
        (MEASURED_READ, None, "Evidence: measured_read", {"evidence": "measured_read"}),
        (DECLARED, None, "Evidence: declared", {"evidence": "declared"}),
        (LOWER_BOUND, None, "Evidence: lower_bound", {"evidence": "lower_bound"}),
        (
            NOT_MEASURED,
            "over-cap",
            "Evidence: not_measured | Reason: over-cap",
            {"evidence": "not_measured", "reason": "over-cap"},
        ),
    ],
    ids=["stat", "read", "declared", "lower-bound", "not-measured"],
)
def test_segment_is_written_and_parses_back(
    level: str, reason: str | None, segment: str, parsed: dict[str, str]
) -> None:
    assert evidence_segment(level, reason) == segment
    assert parse_provenance_value(segment) == parsed
    assert set(parsed) <= {EVIDENCE_KEY, REASON_KEY}


@pytest.mark.parametrize(
    ("level", "reason"),
    [
        ("measured", None),
        ("", None),
        (NOT_MEASURED, None),
        (NOT_MEASURED, "disk full"),
        (NOT_MEASURED, "over-cap | Source: x"),
        (NOT_MEASURED, ""),
        (DECLARED, "over-cap"),
        (MEASURED_STAT, "timeout"),
    ],
    ids=[
        "unknown-level",
        "empty-level",
        "no-reason",
        "free-text",
        "injected-segment",
        "empty-reason",
        "reason-on-declared",
        "reason-on-stat",
    ],
)
def test_segment_rejects_an_invalid_pair(level: str, reason: str | None) -> None:
    with pytest.raises(ValueError):
        evidence_segment(level, reason)


@pytest.mark.parametrize("code", sorted(REASON_CODES))
def test_reason_codes_are_catalogue_style(code: str) -> None:
    assert re.fullmatch(r"[a-z][a-z0-9-]*", code)
    assert evidence_segment(NOT_MEASURED, code).endswith(f"Reason: {code}")


def test_reason_codes_are_the_starting_set() -> None:
    assert REASON_CODES == {
        "over-cap",
        "timeout",
        "network-failed",
        "lfs-pointer",
        "unreadable-file",
        "unlistable-dir",
    }
