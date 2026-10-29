# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pitloom.core.evidence``: the one writer of the ``Evidence:`` and
``Reason:`` provenance segment, the :class:`~pitloom.core.evidence.Fact`
value type, a count's bound and the precedence of a recorded fact.

See also: tests/core/test_loom_dataset_size.py (the facts loom records of a
dataset's digest).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import re
from typing import Any

import pytest

from pitloom.core.canonical_json import MAX_SAFE_INTEGER
from pitloom.core.evidence import (
    DECLARED,
    EVIDENCE_KEY,
    LOWER_BOUND,
    MEASURED_READ,
    MEASURED_STAT,
    NOT_MEASURED,
    OVER_CAP,
    REASON_CODES,
    REASON_KEY,
    Fact,
    count_fact,
    evidence_segment,
    record_fact,
    record_stated,
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


_STATED = "Source: card.md"
_UNREAD = "Source: f | Evidence: not_measured | Reason: over-cap"
_STAT = "Source: f | Evidence: measured_stat"


@pytest.mark.parametrize(
    ("fact", "entry", "parsed"),
    [
        (Fact.measured_read(7), None, None),
        (Fact.measured_stat(7, "f"), _STAT, {"evidence": MEASURED_STAT}),
        (
            Fact.declared("x", "f"),
            "Source: f | Evidence: declared",
            {"evidence": DECLARED},
        ),
        (
            Fact.not_measured("f", OVER_CAP),
            _UNREAD,
            {"evidence": NOT_MEASURED, "reason": OVER_CAP},
        ),
    ],
    ids=["read", "stat", "declared", "not-measured"],
)
def test_a_fact_writes_its_entry_and_it_parses_back(
    fact: Fact[Any], entry: str | None, parsed: dict[str, str] | None
) -> None:
    assert fact.provenance() == entry
    if entry is not None:
        assert parse_provenance_value(entry) == {"source": "f", **(parsed or {})}


@pytest.mark.parametrize(
    "args",
    [
        (7, LOWER_BOUND, "f"),
        (7, "measured"),
        (None, MEASURED_READ),
        (7, MEASURED_READ, "f"),
        (7, MEASURED_STAT),
        (None, DECLARED, "f"),
        (7, NOT_MEASURED, "f", OVER_CAP),
        (None, NOT_MEASURED, "f"),
        (None, NOT_MEASURED, "f", "disk full"),
        (None, NOT_MEASURED, None, OVER_CAP),
        (7, DECLARED, "f", OVER_CAP),
    ],
    ids=[
        "lower-bound",
        "unknown-level",
        "read-without-value",
        "read-with-source",
        "stat-without-source",
        "declared-without-value",
        "not-measured-with-value",
        "not-measured-without-reason",
        "free-text-reason",
        "not-measured-without-source",
        "reason-on-declared",
    ],
)
def test_a_fact_refuses_a_misfit(args: tuple[Any, ...]) -> None:
    with pytest.raises(ValueError):
        Fact(*args)


@pytest.mark.parametrize(
    "make",
    [
        lambda s: Fact.measured_stat(1, s),
        lambda s: Fact.declared(1, s),
        lambda s: Fact.not_measured(s, OVER_CAP),
    ],
    ids=["stat", "declared", "not-measured"],
)
def test_an_injected_source_cannot_forge_a_segment(make: Any) -> None:
    """``|`` cannot add a segment; ``;``, a line break and a bidi control
    stay text, the control escaped."""
    fact = make("a|Evidence: measured_read;b\nc\u202e")
    parsed = parse_provenance_value(fact.provenance())
    assert parsed["source"] == "a/Evidence: measured_read;b\nc\\u202e"
    assert parsed["evidence"] == fact.level


@pytest.mark.parametrize(
    ("value", "level", "expected"),
    [
        (0, MEASURED_STAT, Fact(0, MEASURED_STAT, "f")),
        (MAX_SAFE_INTEGER, MEASURED_READ, Fact(MAX_SAFE_INTEGER, MEASURED_READ)),
        (MAX_SAFE_INTEGER + 1, MEASURED_STAT, Fact.not_measured("f", OVER_CAP)),
        (MAX_SAFE_INTEGER + 1, MEASURED_READ, Fact.not_measured("f", OVER_CAP)),
    ],
    ids=["zero", "max-safe", "past-max-stat", "past-max-read"],
)
def test_a_count_within_the_bound_is_kept_and_past_it_not_measured(
    caplog: pytest.LogCaptureFixture, value: int, level: str, expected: Fact[int]
) -> None:
    """Up to 2^53-1 the count; past it ``not_measured`` with the one
    over-cap ``WARNING:`` of every byte size."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert count_fact(value, level, "f", "byte_size") == expected
    warnings = [r.getMessage() for r in caplog.records]
    assert len(warnings) == int(expected.value is None)
    assert all("f byte_size" in w for w in warnings)


@pytest.mark.parametrize(
    ("value", "level"),
    [
        (-1, MEASURED_STAT),
        (True, MEASURED_STAT),
        (1.0, MEASURED_STAT),
        (1, NOT_MEASURED),
    ],
    ids=["negative", "bool", "float", "not-measured"],
)
def test_a_count_refuses_what_is_not_one(value: Any, level: str) -> None:
    with pytest.raises(ValueError):
        count_fact(value, level, "f", "byte_size")


#: (held entry, fact, the entry after, the value set): each pair of levels.
_PRECEDENCE: list[tuple[str | None, Fact[int] | None, str | None, int | None]] = [
    (_STATED, Fact.measured_stat(7, "f"), _STAT, 7),
    (_STATED, Fact.measured_read(7), None, 7),
    (_UNREAD, Fact.declared(7, "p"), "Source: p | Evidence: declared", 7),
    (_UNREAD, Fact.measured_stat(7, "f"), _STAT, 7),
    (_STATED, Fact.not_measured("f", OVER_CAP), _STATED, None),
    (None, Fact.not_measured("f", OVER_CAP), _UNREAD, None),
    (_STATED, Fact.declared(7, "p"), _STATED, None),
    (_STAT, Fact.measured_stat(8, "g"), _STAT, None),
    (_STAT, Fact.declared(7, "p"), _STAT, None),
    (_STATED, None, _STATED, None),
]


@pytest.mark.parametrize(
    ("held", "fact", "after", "value"),
    _PRECEDENCE,
    ids=[
        "measured-stat-over-stated",
        "measured-read-over-stated",
        "declared-over-not-measured",
        "measured-over-not-measured",
        "not-measured-never-replaces-a-value",
        "not-measured-on-an-open-field",
        "first-declared-stays",
        "first-measured-stays",
        "declared-under-measured",
        "no-fact",
    ],
)
def test_record_fact_keeps_the_better_level(
    held: str | None, fact: Fact[int] | None, after: str | None, value: int | None
) -> None:
    """The winner's entry goes last; a measured_read one writes none."""
    provenance = {"package": "Source: s.py"}
    if held is not None:
        provenance["byte_size"] = held
    provenance["version"] = _STATED
    values: list[int] = []
    record_fact(provenance, "byte_size", fact, values.append)
    assert values == ([] if value is None else [value])
    entry = [("byte_size", after)] if after is not None else []
    package, version = ("package", "Source: s.py"), ("version", _STATED)
    if after == held:  # not replaced: in place
        assert list(provenance.items()) == [package, *entry, version]
    else:
        assert list(provenance.items()) == [package, version, *entry]


def test_record_fact_writes_a_given_entry_for_a_winning_fact() -> None:
    """A Git LFS pointer's hash keeps its own form; precedence still holds."""
    pointer = "Source: p | Method: lfs_pointer"
    provenance: dict[str, str] = {}
    record_fact(provenance, "verified_using", Fact.declared("ab", "p"), entry=pointer)
    record_fact(provenance, "verified_using", Fact.not_measured("p", OVER_CAP))
    assert provenance == {"verified_using": pointer}


def test_a_statement_never_replaces_a_recorded_entry() -> None:
    """Risk 7: ``update`` would let a source's entry replace the caller's
    and the hash's evidence; each new field joins in order."""
    provenance = {"package": "Source: s.py", "verified_using": _UNREAD}
    stated = {"verified_using": "Source: x", "package": "Source: y", "version": "v"}
    record_stated(provenance, stated)
    assert list(provenance.items()) == [
        ("package", "Source: s.py"),
        ("verified_using", _UNREAD),
        ("version", "v"),
    ]
