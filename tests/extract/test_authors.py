# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.authors`: when a split is warned about,
and the one summary line for a document's dependencies.

See also: tests/extract/test_core_metadata_authors.py (the reading itself)
and tests/test_author_split_surfaces.py (the same reading on every surface).
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable

import pytest

from pitloom.extract.authors import (
    AUTHOR_FIELD_MAX_CHARS,
    AuthorSplit,
    _outside_addresses,
    _outside_quotes,
    dependency_author_pairs,
    dependency_author_splits,
    read_author_fields,
)
from tests._bounded import run_bounded_in_child

_SPLIT = [{"name": "Ann"}, {"name": "Bob"}]


@pytest.mark.parametrize(
    ("deferred", "quiet", "warned"),
    [(False, False, True), (False, True, False), (True, False, False)],
    ids=["warns", "quiet", "deferred"],
)
def test_read_author_fields_warning(
    caplog: pytest.LogCaptureFixture, deferred: bool, quiet: bool, warned: bool
) -> None:
    """One ``WARNING:`` ending with the hint; none when quiet; with *splits*
    given, the split string goes to it for the caller to warn about."""
    splits: list[AuthorSplit] | None = [] if deferred else None
    with caplog.at_level(logging.WARNING):
        authors = read_author_fields(
            "Ann and Bob", None, quiet=quiet, splits=splits, hint=" -- HINT"
        )
    assert authors == _SPLIT
    assert splits == ([AuthorSplit("Ann and Bob", 2)] if deferred else None)
    assert caplog.messages == (
        [
            "AUTHOR='Ann and Bob': split into 2 names on ',' / 'and'; a free-text"
            " author field cannot tell a list from one name containing a comma"
            " -- HINT"
        ]
        if warned
        else []
    )


def test_dependency_splits_one_summary_per_document(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every split in the block gives one line: the first, and how many
    dependencies were split; a dependency read twice counts once."""
    with caplog.at_level(logging.WARNING), dependency_author_splits():
        assert dependency_author_pairs("a", "Ann, Bob", None) == [
            ("Ann", None),
            ("Bob", None),
        ]
        dependency_author_pairs("b", "Cee and Dan and Eve", None)
        dependency_author_pairs("b", "Cee and Dan and Eve", None)
        dependency_author_pairs("c", "Fay", None)
        assert caplog.messages == []
    (line,) = caplog.messages
    assert line.startswith("AUTHOR='Ann, Bob': split into 2 names on ',' / 'and'")
    assert "(PACKAGE=a; 2 dependencies split in all)" in line


@pytest.mark.parametrize("inside", [False, True], ids=["outside-block", "raised"])
def test_dependency_split_outside_block_or_on_error(
    caplog: pytest.LogCaptureFixture, inside: bool
) -> None:
    """Outside a block a split warns at once; a block ended by an error
    does not warn (the document was not built)."""
    with caplog.at_level(logging.WARNING):
        if inside:
            with pytest.raises(RuntimeError), dependency_author_splits():
                dependency_author_pairs("a", "Ann, Bob", None)
                raise RuntimeError("stop")
        else:
            dependency_author_pairs("a", "Ann, Bob", None)
    assert len(caplog.messages) == (0 if inside else 1)


# Pins an open design choice: see extras-parity.md open questions
def test_dependency_address_problem_is_quiet(caplog: pytest.LogCaptureFixture) -> None:
    """Another project's unusable address is left out without a line."""
    with caplog.at_level(logging.WARNING), dependency_author_splits():
        pairs = dependency_author_pairs("a", "Ann", "ann at example dot com")
    assert pairs == [("Ann", None)]
    assert caplog.messages == []


#: The one-regex splits the one-pass splitters replace: the oracle.
_OLD_NAME_SEPARATOR = re.compile(r"(?:,|\band\b)(?![^<>]*>)")
_OLD_ENTRY_SEPARATOR = re.compile(r"""[,;](?=(?:[^"]*"[^"]*")*[^"]*$)""")
_NAME_SEPARATOR = re.compile(r",|\band\b")


def test_one_pass_splitters_match_the_regex_splits() -> None:
    """Drift guard: on every short string of the significant ASCII
    characters (unbalanced ``<``/``>``/``"`` too), the one-pass splits equal
    the lookahead regex splits they replace."""
    alphabet = ["a", "and", " ", ",", ";", '"', "<", ">", "x"]
    rng = random.Random(20261011)
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 9)))
        names = _outside_addresses(text, _NAME_SEPARATOR)
        assert names == _OLD_NAME_SEPARATOR.split(text), text
        assert _outside_quotes(text) == _OLD_ENTRY_SEPARATOR.split(text), text


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
    assert _outside_quotes(text) == entries


def _fastest(call: Callable[[], object]) -> float:
    """The fastest of three runs of *call*, in seconds."""
    times = []
    for _ in range(3):
        start = time.perf_counter()
        call()
        times.append(time.perf_counter() - start)
    return min(times)


def _split_names(text: str) -> list[str]:
    return _outside_addresses(text, _NAME_SEPARATOR)


@pytest.mark.parametrize(
    ("split", "unit"),
    [
        ("_split_names", "a,"),
        ("_split_names", "a and "),
        ("_outside_quotes", '"x",'),
    ],
    ids=["commas", "ands", "quotes"],
)
def test_the_splitters_run_in_linear_time(split: str, unit: str) -> None:
    """Regression: the lookahead splits rescanned the rest of the text at
    each separator (``'a,' * 80000`` took 46 s). Uncapped: four times the
    text takes about four times as long (under eight, past a floor for
    timer noise), and ~160,000 characters split at once."""
    small = unit * (10000 // len(unit))
    large = small * 4
    call = globals()[split]
    floor = max(_fastest(lambda: call(small)), 0.005)
    assert _fastest(lambda: call(large)) < 8 * floor
    huge = unit * (160000 // len(unit))  # one separator per unit
    parts = run_bounded_in_child(f"{__name__}:{split}", huge)
    assert len(parts) == len(huge) // len(unit) + 1


_CHARS = f"{AUTHOR_FIELD_MAX_CHARS}-character"
_NAME_LIST = ", ".join(f"n{i}" for i in range(1001))
_ADDRESS_LIST = ", ".join(f"a{i}@x.org" for i in range(1001))


@pytest.mark.parametrize(
    ("names", "addresses", "first", "kept", "line"),
    [
        (
            _NAME_LIST,
            None,
            {"name": "n0"},
            1000,
            "1000-name author-field cap; only the first 1000 names read of 'n0,",
        ),
        (
            "Ann, " + "y" * 70000,
            None,
            {"name": "Ann"},
            1,
            f"{_CHARS} author-field cap; only the first 1 name read of 'Ann, yy",
        ),
        (
            "y" * 70000 + ", Bob",
            None,
            None,
            0,
            f"{_CHARS} author-field cap; only the first 0 names read of 'yy",
        ),
        (
            "\x1b[1m, " + "y" * 70000,
            None,
            {"name": "\x1b[1m"},
            1,
            f"{_CHARS} author-field cap; only the first 1 name read of '\\x1b[1m, yy",
        ),
        (
            None,
            _ADDRESS_LIST,
            {"email": "a0@x.org"},
            1000,
            "1000-entry author-field cap; only the first 1000 entries read of 'a0@",
        ),
    ],
    ids=["names", "chars", "chars-one-name", "escaped-once", "entries"],
)
def test_an_author_field_over_the_cap_warns_once(
    caplog: pytest.LogCaptureFixture,
    names: str | None,
    addresses: str | None,
    first: dict[str, str] | None,
    kept: int,
    line: str,
) -> None:
    """Past a cap the rest is not read, a name cut by the character cap
    neither; one ``WARNING:`` per field and process saying what was read,
    with a bounded excerpt escaped once; a quiet (discarded) read says
    nothing."""
    with caplog.at_level(logging.WARNING):
        authors = read_author_fields(names, addresses, quiet=True)
        assert caplog.messages == []
        for _ in range(2):
            assert read_author_fields(names, addresses, splits=[]) == authors
    assert len(authors) == kept
    assert authors[:1] == ([] if first is None else [first])
    (cap,) = caplog.messages
    key = "AUTHOR" if names else "AUTHOR_EMAIL"
    assert cap.startswith(f"FIELD={key}: larger than the {line}")
    assert len(cap) < 400


def test_fields_sharing_the_shown_excerpt_warn_each(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The once-per-field key is the whole field, not the excerpt shown;
    a dependency's field is used, so it warns too."""
    with caplog.at_level(logging.WARNING), dependency_author_splits():
        read_author_fields("z" * 70000 + ", Ann", None)
        read_author_fields("z" * 70000 + ", Bob", None)
        dependency_author_pairs("a", "z" * 70000 + ", Cee", None)
    assert [m.startswith("FIELD=AUTHOR: ") for m in caplog.messages] == [True] * 3
