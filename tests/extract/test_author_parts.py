# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract._author_parts`: the one-pass splitter
of a free-text author field against an independent regex oracle, quoted
display names, and linear time.

See also: tests/extract/test_authors.py (the warnings) and
tests/extract/test_authors_name_field.py (where a name field is cut).
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable

import pytest

from pitloom.extract._author_parts import field_parts, outside_entries
from tests._bounded import run_bounded_in_child

#: The lookahead regex split the one-pass splitter replaces: the oracle. A
#: ``,`` or ``;`` counts outside an ``<...>`` (no ``>`` before the next
#: ``<``) and outside ``"`` quotes (an even number follow); captured, so
#: the name-field oracle can join segments again.
_ORACLE = re.compile(r"""([,;])(?![^<>]*>)(?=(?:[^"]*"[^"]*")*[^"]*$)""")
#: A segment less one trailing ``(comment)``: the lazy text before it.
_LESS_COMMENT = re.compile(r"(?s)(.*?)(?:\([^()]*\)\s*)?")
#: A segment that ends a mailbox: an ``<...>`` last, or one bare address.
_MAILBOX_END = re.compile(r"(?s)\s*(?:.*<.*>|[^@\s]+@[^@\s]+)\s*")
#: A segment that is one bare address.
_BARE_ADDRESS = re.compile(r"(?s)\s*[^@\s]+@[^@\s]+\s*")
#: An angle bracket outside ``"`` quotes (an even number follow).
_OUTSIDE_ANGLE = re.compile(r"""[<>](?=(?:[^"]*"[^"]*")*[^"]*$)""")
#: An ``and`` or ``&`` leading the entry after a cut between mailboxes.
_LEADING_AND = re.compile(r"(?i)\A\s*(?:&|and(?=\s|$))")


def _less_comment_matches(pattern: re.Pattern[str], segment: str) -> bool:
    less = _LESS_COMMENT.fullmatch(segment)
    return bool(less and pattern.fullmatch(less.group(1)))


def _oracle_between_mailboxes(piece: str) -> list[str]:
    """*piece* cut after each ``>`` (outside quotes) right after a ``<``
    with one bare address between, but the last such; a leading
    ``and``/``&`` dropped after a cut."""
    angles = list(_OUTSIDE_ANGLE.finditer(piece))
    ends = [
        close.end()
        for open_, close in zip(angles, angles[1:], strict=False)
        if open_.group() == "<"
        and close.group() == ">"
        and _BARE_ADDRESS.fullmatch(piece[open_.end() : close.start()])
    ][:-1]
    bounds = [0, *ends, len(piece)]
    entries = [piece[start:end] for start, end in zip(bounds, bounds[1:], strict=False)]
    return [entries[0], *(_LEADING_AND.sub("", e, count=1) for e in entries[1:])]


def _oracle_pieces(text: str, named: bool) -> list[str]:
    """*text* split by :data:`_ORACLE`; *named*, a separator is a cut only
    after a segment ending a mailbox (:data:`_MAILBOX_END`, less a
    comment), a blank segment right after a cut, or before a bare address
    (:data:`_BARE_ADDRESS`); each piece then cut between mailboxes
    (:func:`_oracle_between_mailboxes`)."""
    split = _ORACLE.split(text)
    segments, separators = split[0::2], split[1::2]
    if not named:
        return segments
    pieces, fresh = [segments[0]], True
    for segment, separator, following in zip(
        segments, separators, segments[1:], strict=False
    ):
        ends = _less_comment_matches(_MAILBOX_END, segment)
        bare = _less_comment_matches(_BARE_ADDRESS, following)
        fresh = ends or (fresh and not segment.strip()) or bare
        if fresh:
            pieces.append(following)
        else:
            pieces[-1] += separator + following
    return [entry for piece in pieces for entry in _oracle_between_mailboxes(piece)]


@pytest.mark.parametrize("named", [False, True], ids=["address-field", "name-field"])
def test_one_pass_splitter_matches_the_regex_splits(named: bool) -> None:
    """Drift guard: on every short string of the significant ASCII
    characters (unbalanced ``<``/``>``/``"``/``(`` too), the one-pass split
    on ``,``/``;`` equals the lookahead regex split -- a name field's cut
    only next to an address -- and a field's stripped parts are its
    stripped, non-blank pieces (never split on ``and`` between names)."""
    alphabet = [
        *("a", "and", " ", ",", ";", '"', "<", ">", "x", "@", "a@x", "(", ")"),
        *("&", "\n", "<a@x>"),
    ]
    rng = random.Random(20261011)
    for _ in range(8000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 9)))
        oracle = _oracle_pieces(text, named)
        assert outside_entries(text, named) == oracle, text
        parts = [p.strip() for p in oracle if p.strip()]
        assert field_parts(text, named)[0] == parts, text


@pytest.mark.parametrize(
    ("text", "entries"),
    [
        ("\u201cDoe, Jane\u201d <j@x>, Bo", ["\u201cDoe, Jane\u201d <j@x>", " Bo"]),
        ("\u2018Doe; Jane\u2019, Bo", ["\u2018Doe; Jane\u2019", " Bo"]),
        ("O\u2019Brien, Bo", ["O\u2019Brien", " Bo"]),
        ("\u201cDoe, Jane", ["\u201cDoe", " Jane"]),
        ("\u201dDoe, Jane\u201c", ["\u201dDoe", " Jane\u201c"]),
        ("\u201cA\u201d, \u201cB, C\u201d", ["\u201cA\u201d", " \u201cB, C\u201d"]),
        (
            "\u201cA, \u2018B\u2019, C\u201d, D",
            ["\u201cA, \u2018B\u2019, C\u201d", " D"],
        ),
    ],
    ids=["double", "single", "apostrophe", "unclosed", "reversed", "two", "nested"],
)
def test_typographic_quotes_hold_an_entry_together(
    text: str, entries: list[str]
) -> None:
    """A typographic opening quote holds ``,``/``;`` until its closing
    quote; a closing quote alone (an apostrophe) holds nothing."""
    assert outside_entries(text) == entries


def _fastest(call: Callable[[], object]) -> float:
    """The fastest of three runs of *call*, in seconds."""
    times = []
    for _ in range(3):
        start = time.perf_counter()
        call()
        times.append(time.perf_counter() - start)
    return min(times)


@pytest.mark.parametrize(
    ("unit", "named", "extra"),
    [
        ("a,", False, 1),
        ('"x",', False, 1),
        ("\u201cx\u201d,", False, 1),
        ("a,", True, None),
        ("a ,", True, None),
        ("a@x,", True, 1),
        ("<a@x>(c),", True, 1),
        ("<a@x> and ", True, 0),
    ],
    ids=[
        "commas",
        "quotes",
        "typographic",
        "name-commas",
        "names",
        "addresses",
        "mailboxes",
        "joined-mailboxes",
    ],
)
def test_the_splitter_runs_in_linear_time(
    unit: str, named: bool, extra: int | None
) -> None:
    """Regression: the lookahead split rescanned the rest of the text at
    each separator (``'a,' * 80000`` took 46 s); a name field held
    together must not rescan its growing entry either. Uncapped: four
    times the text takes about four times as long (under eight, past a
    floor for timer noise), and ~160,000 characters split at once, into
    one piece per unit and *extra* (``None``: not split)."""
    small = unit * (10000 // len(unit))
    large = small * 4
    floor = max(_fastest(lambda: outside_entries(small, named)), 0.005)
    assert _fastest(lambda: outside_entries(large, named)) < 8 * floor
    huge = unit * (160000 // len(unit))  # one cut per unit
    parts = run_bounded_in_child(f"{__name__}:outside_entries", huge, named)
    assert len(parts) == (1 if extra is None else len(huge) // len(unit) + extra)
