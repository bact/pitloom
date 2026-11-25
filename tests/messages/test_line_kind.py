# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reading a printed line's kind back (:func:`pitloom.messages.line_kind`):
each kind, the order the kinds are tried in, a Windows line end, the
length cap, and the patterns compiled once.

See also: tests/messages/test_record_kinds.py (the kind a record carries),
tests/messages/test_messages_trust.py (trusting a code).
"""

from __future__ import annotations

import pytest

from pitloom.log_masking import UNSHOWN_MESSAGE
from pitloom.messages import LINE_KINDS, LONGEST_LINE, line_kind, trusted_message
from pitloom.messages import _line_kind as kinds

_LFS = (
    "WARNING: FILE=a: Git LFS pointer, content not read (2 files); clone "
    "with git lfs, then run on the directory [lfs-pointer]"
)
# pylint: disable-next=protected-access
_SUMMARY_RE = kinds._summary_re
# pylint: disable-next=protected-access
_RELAY_RE = kinds._relay_re
#: A coded ``INFO`` line that starts ``KEY=``, as a detail does.
_CODED_KEY = "INFO: FILE=x: one of several AI model files [model-ambiguous]"

#: (line, kind), each tried with and without a trailing ``\r``.
_CASES = [
    ("DEBUG: anything", "debug"),
    ("DEBUG: FILE=x: one of several AI model files [model-ambiguous]", "debug"),
    ("", "untagged"),
    ("usage: loom [-h] {generate,project} ...", "untagged"),
    ("  File 'x.py', line 1, in <module>", "untagged"),
    ("WARNING:no space after the tag", "untagged"),
    ("warning: lower case", "untagged"),
    (" INFO: indented", "untagged"),
    (_LFS, "coded"),
    (_CODED_KEY, "coded"),
    # A code nobody may trust: a summary's text with a code after it, a
    # detail with a code that is not its line's.
    ("INFO: merge: merged 3 fragment(s) [model-ambiguous]", "uncoded"),
    ("WARNING: FILE=a: own words [lfs-pointer]", "uncoded"),
    ("INFO: merge: merged 3 fragment(s)", "summary"),
    ("INFO: Git source: $ git fetch origin", "summary"),
    ("INFO: merge: merged three fragment(s)", "uncoded"),  # not a number
    ("WARNING: merge: merged 3 fragment(s)", "uncoded"),  # not INFO
    ("INFO: merge: merged 3 fragment(s) and more", "uncoded"),  # not whole
    ("INFO: PITLOOM_VERSION=0.25.0", "detail"),
    ("INFO: OPTION=x SOURCE=cli VALUE=a b", "detail"),
    ("INFO: key=lower case", "uncoded"),
    ("INFO: =VALUE", "uncoded"),
    ("WARNING: PITLOOM_VERSION=0.25.0", "uncoded"),  # not INFO
    ("WARNING: fickling: its own words", "relay"),
    ("INFO: licenseid: variant not stated", "relay"),
    ("WARNING: setuptools stderr: error: x", "relay"),
    ("ERROR: spdx3-validate: a finding", "relay"),
    ("ERROR: loom generate: spdx3-validate: a finding", "relay"),
    ("WARNING: FORMAT=pytorch FILE=m.pt: fickling: its own words", "relay"),
    # A frame of another level, two frames, or the prefix not at the start.
    ("INFO: Git source: licenseid: x", "relay"),  # a frame of INFO
    ("INFO: AI model scan: licenseid: x", "uncoded"),  # a WARNING-only frame
    ("WARNING: AI model scan: FORMAT=pytorch FILE=m.pt: fickling: x", "uncoded"),
    ("ERROR: loom generate: loom: spdx3-validate: x", "uncoded"),
    ("WARNING: own words, then fickling: x", "uncoded"),
    ("WARNING: fickling:x", "uncoded"),
    ("ERROR: loom generate: boom", "uncoded"),
    (f"ERROR: loom generate: {UNSHOWN_MESSAGE}", "uncoded"),
]


@pytest.mark.parametrize("end", ["", "\r"], ids=["lf", "crlf"])
@pytest.mark.parametrize(
    ("line", "kind"), _CASES, ids=[f"{n}-{k}" for n, (_, k) in enumerate(_CASES)]
)
def test_each_kind_and_its_boundaries(line: str, kind: str, end: str) -> None:
    assert line_kind(line + end) == kind
    assert kind in LINE_KINDS


def test_the_coded_cases_are_trusted_and_the_forged_are_not() -> None:
    """The fixture's premise: a ``coded`` case is one
    :func:`~pitloom.messages.trusted_message` trusts, a forged one not."""
    assert trusted_message(_LFS) is not None
    assert trusted_message(_CODED_KEY) is not None
    assert (
        trusted_message("INFO: merge: merged 3 fragment(s) [model-ambiguous]") is None
    )


def test_only_one_line_end_is_dropped() -> None:
    assert line_kind(_LFS + "\r\r") == "uncoded"
    assert line_kind(_LFS + "\n") == "uncoded"


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("INFO: PITLOOM_VERSION=", "detail"),
        ("WARNING: fickling: ", "relay"),
        ("WARNING: own ", "uncoded"),
        ("no tag ", "untagged"),
    ],
    ids=["detail", "relay", "uncoded", "untagged"],
)
def test_a_line_over_the_cap_is_overlong_and_one_at_it_is_read(
    line: str, kind: str
) -> None:
    """Over :data:`~pitloom.messages.LONGEST_LINE` a tagged line is not read
    further; at it, it is; an untagged one stays untagged; a ``\\r`` dropped
    first does not count."""
    at_cap = line + "x" * (LONGEST_LINE - len(line))
    assert len(at_cap) == LONGEST_LINE
    assert line_kind(at_cap) == kind
    assert line_kind(at_cap + "\r") == kind
    over = at_cap + "x"
    assert line_kind(over) == ("untagged" if kind == "untagged" else "overlong")


def test_a_coded_line_over_the_cap_is_overlong() -> None:
    over = _LFS.replace("FILE=a", "FILE=" + "a" * LONGEST_LINE)
    assert trusted_message(over) is None
    assert line_kind(over) == "overlong"


def test_the_patterns_are_compiled_once() -> None:
    _SUMMARY_RE.cache_clear()
    _RELAY_RE.cache_clear()
    for _ in range(3):
        line_kind("INFO: merge: merged 3 fragment(s)")
        line_kind("INFO: own words")
        line_kind("WARNING: fickling: x")
    assert _SUMMARY_RE.cache_info().misses == 1
    assert _RELAY_RE.cache_info().misses == 2  # INFO and WARNING
