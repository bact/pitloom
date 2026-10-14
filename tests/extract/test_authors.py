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

from pitloom.assemble.spdx3.deps_originator import _resolve_author_or_maintainer
from pitloom.assemble.spdx3.deps_pypi import _extract_pypi_originator
from pitloom.extract.authors import (
    AUTHOR_FIELD_MAX_CHARS,
    AuthorSplit,
    _outside_entries,
    _parts,
    dependency_author_splits,
    read_author_fields,
    warn_author_splits,
)
from pitloom.extract.dependency_authors import dependency_author_pairs
from tests._bounded import run_bounded_in_child
from tests.assemble.conftest import _FakeMetadata

_SPLIT = [{"name": "Ann"}, {"name": "Bob"}]
_REASON = (
    " on ',' / ';'; an address field cannot tell a list from one name"
    " containing a comma"
)


@pytest.mark.parametrize(
    ("deferred", "quiet", "warned"),
    [(False, False, True), (False, True, False), (True, False, False)],
    ids=["warns", "quiet", "deferred"],
)
def test_read_author_fields_warning(
    caplog: pytest.LogCaptureFixture, deferred: bool, quiet: bool, warned: bool
) -> None:
    """One ``WARNING:`` for a split address field, ending with the hint;
    none when quiet; with *splits* given, the split string goes to it for
    the caller to warn about."""
    splits: list[AuthorSplit] | None = [] if deferred else None
    with caplog.at_level(logging.WARNING):
        authors = read_author_fields(
            None, "Ann; Bob", quiet=quiet, splits=splits, hint=" -- HINT"
        )
    assert authors == _SPLIT
    assert splits == ([AuthorSplit("Ann; Bob", 2)] if deferred else None)
    assert caplog.messages == (
        [f"AUTHOR_EMAIL='Ann; Bob': split into 2 entries{_REASON} -- HINT"]
        if warned
        else []
    )


def test_dependency_splits_one_summary_per_document(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every split in the block gives one line: the first, and how many
    dependencies were split; a dependency read twice counts once, and an
    ``Author`` holding no address is never split."""
    with caplog.at_level(logging.WARNING), dependency_author_splits():
        assert dependency_author_pairs("a", None, "Ann, Bob") == [
            ("Ann", None),
            ("Bob", None),
        ]
        dependency_author_pairs("b", None, "Cee; Dan; Eve")
        dependency_author_pairs("b", None, "Cee; Dan; Eve")
        assert dependency_author_pairs("c", "Fay, Gus", None) == [("Fay, Gus", None)]
        assert caplog.messages == []
    (line,) = caplog.messages
    assert line.startswith("AUTHOR_EMAIL='Ann, Bob': split into 2 entries on")
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
                dependency_author_pairs("a", None, "Ann, Bob")
                raise RuntimeError("stop")
        else:
            dependency_author_pairs("a", None, "Ann, Bob")
    assert len(caplog.messages) == (0 if inside else 1)


# Pins an open design choice: see extras-parity.md open questions
def test_dependency_address_problem_is_quiet(caplog: pytest.LogCaptureFixture) -> None:
    """Another project's unusable address is left out without a line."""
    with caplog.at_level(logging.WARNING), dependency_author_splits():
        pairs = dependency_author_pairs("a", "Ann", "ann@example dot com")
    assert pairs == [("Ann", None)]
    assert caplog.messages == []


_TWO_MAILBOXES = "Ann <a@x.org>, Bob <b@x.org>"
_NAME_REASON = "; a name field is cut only after an address"
_NOT_ADDRESSES = "; ".join(f"x{i} at y@" for i in range(1000))
_NOT_AN_ADDRESS = ": not an email address; "


def _dependency_split(names: str | None, addresses: str | None) -> None:
    with dependency_author_splits():
        dependency_author_pairs("a", names, addresses)


@pytest.mark.parametrize(
    ("call", "lines"),
    [
        (
            lambda: read_author_fields(None, _NOT_ADDRESSES),
            [
                "AUTHOR_EMAIL=['x0 at y@', 'x1 at y@', 'x2 at y@', ...]"
                f"{_NOT_AN_ADDRESS}1000 entries not recorded"
            ],
        ),
        (
            lambda: read_author_fields("Ann <a b>", "e@ f, Bob <c d>"),
            [
                f"AUTHOR_EMAIL=['e@ f', 'Bob <c d>']{_NOT_AN_ADDRESS}2 entries"
                " not recorded",
                f"AUTHOR='Ann <a b>'{_NOT_AN_ADDRESS}not recorded",
            ],
        ),
        (
            lambda: read_author_fields(None, "y@ " + "y" * 200),
            [f"AUTHOR_EMAIL='y@ {'y' * 117}'...{_NOT_AN_ADDRESS}not recorded"],
        ),
        (
            lambda: read_author_fields(None, "Ann, " + "b" * 200),
            [f"AUTHOR_EMAIL='Ann, {'b' * 115}'...: split into 2 entries"],
        ),
        (
            lambda: warn_author_splits(
                [AuthorSplit(f"{c}, {c}", 2) for c in "ABCD"], hint=""
            ),
            ["AUTHOR_EMAIL=['A, A', 'B, B', 'C, C', ...]: split into 8 entries"],
        ),
        (lambda: _dependency_split("Ann, Bob", None), []),
        (
            lambda: _dependency_split(None, "Doe, Jane <j@x.org>"),
            [
                "AUTHOR_EMAIL='Doe, Jane <j@x.org>': split into 2 entries on"
                " ',' / ';' (PACKAGE=a; 1 dependency split in all)"
            ],
        ),
        (
            lambda: _dependency_split(_TWO_MAILBOXES, None),
            [
                f"AUTHOR={_TWO_MAILBOXES!r}: split into 2 entries on ',' / ';'"
                f" (PACKAGE=a; 1 dependency split in all){_NAME_REASON}"
            ],
        ),
        (
            lambda: read_author_fields(_TWO_MAILBOXES, "Doe, Jane <j@x.org>"),
            [
                f"AUTHOR_EMAIL='Doe, Jane <j@x.org>': split into 2 entries{_REASON}",
                f"AUTHOR={_TWO_MAILBOXES!r}: split into 2 entries on ',' / ';'"
                f"{_NAME_REASON}",
            ],
        ),
    ],
    ids=[
        "flood",
        "per-field",
        "cut",
        "split-cut",
        "splits-cut",
        "dependency-author-unsplit",
        "one-dependency",
        "one-dependency-name-field",
        "line-per-key",
    ],
)
def test_one_bounded_line_per_field(
    caplog: pytest.LogCaptureFixture, call: Callable[[], object], lines: list[str]
) -> None:
    """Regression: one line per entry holding no address (1000 for one
    crafted field), an excerpt cut without ``...``, ``1 dependencies``. Now
    one line per field, at most three entries shown, ``...`` where cut,
    the count in the right number; a dependency's ``Author`` is one author,
    no split line."""
    with caplog.at_level(logging.WARNING):
        call()
    assert len(caplog.messages) == len(lines)
    for message, line in zip(caplog.messages, lines, strict=True):
        assert message.startswith(line)


#: The lookahead regex split the one-pass splitter replaces: the oracle. A
#: ``,`` or ``;`` counts outside an ``<...>`` (no ``>`` before the next
#: ``<``) and outside ``"`` quotes (an even number follow); captured, so
#: the name-field oracle can join segments again.
_ORACLE = re.compile(r"""([,;])(?![^<>]*>)(?=(?:[^"]*"[^"]*")*[^"]*$)""")
#: A segment less one trailing ``(comment)``: the lazy text before it.
_LESS_COMMENT = re.compile(r"(?s)(.*?)(?:\([^()]*\)\s*)?")
#: A segment that ends a mailbox: an ``<...>`` last, or one bare address.
_MAILBOX_END = re.compile(r"(?s)\s*(?:.*<.*>|[^@\s]+@[^@\s]+)\s*")


def _oracle_pieces(text: str, named: bool) -> list[str]:
    """*text* split by :data:`_ORACLE`; *named*, a separator is a cut only
    after a segment ending a mailbox (:data:`_MAILBOX_END`, less a
    comment) or a blank segment right after a cut."""
    split = _ORACLE.split(text)
    segments, separators = split[0::2], split[1::2]
    if not named:
        return segments
    pieces, fresh = [segments[0]], True
    for segment, separator, following in zip(
        segments, separators, segments[1:], strict=False
    ):
        less = _LESS_COMMENT.fullmatch(segment)
        ends = bool(less and _MAILBOX_END.fullmatch(less.group(1)))
        fresh = ends or (fresh and not segment.strip())
        if fresh:
            pieces.append(following)
        else:
            pieces[-1] += separator + following
    return pieces


@pytest.mark.parametrize("named", [False, True], ids=["address-field", "name-field"])
def test_one_pass_splitter_matches_the_regex_splits(named: bool) -> None:
    """Drift guard: on every short string of the significant ASCII
    characters (unbalanced ``<``/``>``/``"``/``(`` too), the one-pass split
    on ``,``/``;`` equals the lookahead regex split -- a name field's cut
    only after a mailbox -- and a field's stripped parts are its stripped,
    non-blank pieces (never split on ``and``)."""
    alphabet = ["a", "and", " ", ",", ";", '"', "<", ">", "x", "@", "a@x", "(", ")"]
    rng = random.Random(20261011)
    for _ in range(6000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 9)))
        oracle = _oracle_pieces(text, named)
        assert _outside_entries(text, named) == oracle, text
        parts = [p.strip() for p in oracle if p.strip()]
        assert _parts(text, named)[0] == parts, text


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
    assert _outside_entries(text) == entries


def _fastest(call: Callable[[], object]) -> float:
    """The fastest of three runs of *call*, in seconds."""
    times = []
    for _ in range(3):
        start = time.perf_counter()
        call()
        times.append(time.perf_counter() - start)
    return min(times)


@pytest.mark.parametrize(
    ("unit", "named", "cuts"),
    [
        ("a,", False, True),
        ('"x",', False, True),
        ("\u201cx\u201d,", False, True),
        ("a,", True, False),
        ("a ,", True, False),
        ("a@x,", True, True),
        ("<a@x>(c),", True, True),
    ],
    ids=[
        "commas",
        "quotes",
        "typographic",
        "name-commas",
        "names",
        "addresses",
        "mailboxes",
    ],
)
def test_the_splitter_runs_in_linear_time(unit: str, named: bool, cuts: bool) -> None:
    """Regression: the lookahead split rescanned the rest of the text at
    each separator (``'a,' * 80000`` took 46 s); a name field held
    together must not rescan its growing entry either. Uncapped: four
    times the text takes about four times as long (under eight, past a
    floor for timer noise), and ~160,000 characters split at once."""
    small = unit * (10000 // len(unit))
    large = small * 4
    floor = max(_fastest(lambda: _outside_entries(small, named)), 0.005)
    assert _fastest(lambda: _outside_entries(large, named)) < 8 * floor
    huge = unit * (160000 // len(unit))  # one separator per unit
    parts = run_bounded_in_child(f"{__name__}:_outside_entries", huge, named)
    assert len(parts) == (len(huge) // len(unit) + 1 if cuts else 1)


_CHARS = f"{AUTHOR_FIELD_MAX_CHARS}-character"
_NAME_LIST = ", ".join(f"n{i}" for i in range(1001))
_ADDRESS_LIST = ", ".join(f"a{i}@x.org" for i in range(1001))
_MAILBOX_LIST = ", ".join(f"n{i} <a{i}@x.org>" for i in range(1001))


@pytest.mark.parametrize(
    ("names", "addresses", "first", "kept", "line"),
    [
        (
            None,
            _NAME_LIST,
            {"name": "n0"},
            1000,
            "1000-entry author-field cap; only the first 1000 entries read of 'n0,",
        ),
        (_NAME_LIST, None, {"name": _NAME_LIST}, 1, None),
        (
            _MAILBOX_LIST,
            None,
            {"name": "n0", "email": "a0@x.org"},
            1000,
            "1000-entry author-field cap; only the first 1000 entries read of 'n0 <",
        ),
        ("Ann, " + "y" * 70000, None, None, 0, f"{_CHARS} author-field cap; 'Ann, y"),
        (
            "Ann <a@x.org>, " + "y" * 70000,
            None,
            {"name": "Ann", "email": "a@x.org"},
            1,
            f"{_CHARS} author-field cap; only the first 1 entry read of 'Ann <a",
        ),
        (
            None,
            "Ann, " + "y" * 70000,
            {"name": "Ann"},
            1,
            f"{_CHARS} author-field cap; only the first 1 entry read of 'Ann, yy",
        ),
        (None, "y" * 70000 + ", Bob", None, 0, f"{_CHARS} author-field cap; 'yy"),
        (
            None,
            "\x1b[1m, " + "y" * 70000,
            {"name": "\x1b[1m"},
            1,
            f"{_CHARS} author-field cap; only the first 1 entry read of '\\x1b[1m, y",
        ),
        (
            None,
            _ADDRESS_LIST,
            {"email": "a0@x.org"},
            1000,
            "1000-entry author-field cap; only the first 1000 entries read of 'a0@",
        ),
    ],
    ids=[
        "names",
        "author-no-name-cap",
        "author-entries",
        "author-chars",
        "author-chars-mailbox",
        "chars",
        "chars-one-name",
        "escaped-once",
        "entries",
    ],
)
def test_an_author_field_over_the_cap_warns_once(
    caplog: pytest.LogCaptureFixture,
    names: str | None,
    addresses: str | None,
    first: dict[str, str] | None,
    kept: int,
    line: str | None,
) -> None:
    """Past a cap the rest is not read, an entry cut by the character cap
    neither (an ``Author`` holding no address, one entry, not at all); one
    ``WARNING:`` per field and process saying what was read, with a bounded
    excerpt escaped once; a quiet (discarded) read says nothing. An
    ``Author`` holding no address is one entry, never over the entry cap;
    one holding mailboxes is cut and capped as an address field is."""
    with caplog.at_level(logging.WARNING):
        authors = read_author_fields(names, addresses, quiet=True)
        assert caplog.messages == []
        for _ in range(2):
            assert read_author_fields(names, addresses, splits=[]) == authors
    assert len(authors) == kept
    assert authors[:1] == ([] if first is None else [first])
    if line is None:
        assert caplog.messages == []
        return
    (cap,) = caplog.messages
    key = "AUTHOR" if names else "AUTHOR_EMAIL"
    assert cap.startswith(f"FIELD={key}: larger than the {line}")
    assert len(cap) < 400
    assert cap.endswith("... not read") is (kept == 0)


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


#: A dependency's originator from its fields (core-metadata names), by the
#: installed and the PyPI route (``author_email``-style keys).
_DEPENDENCY_ROUTES: dict[str, Callable[[dict[str, str]], object]] = {
    "installed": lambda fields: _resolve_author_or_maintainer(
        _FakeMetadata(fields), "p"
    ),
    "pypi": lambda fields: _extract_pypi_originator(
        {k.lower().replace("-", "_"): v for k, v in fields.items()}, "p"
    ),
}
_DOE = "Doe, Jane <j@x.org>"


@pytest.mark.parametrize("route", sorted(_DEPENDENCY_ROUTES))
@pytest.mark.parametrize(
    ("fields", "expected", "line"),
    [
        (
            {"Maintainer-email": _DOE},
            [("Doe", None), ("Jane", "j@x.org")],
            f"MAINTAINER_EMAIL={_DOE!r}: split into 2 entries",
        ),
        ({"Maintainer": "z" * 70000}, [], "FIELD=MAINTAINER: larger than the"),
        ({"Author": "Ann <a@x.org, Bob <b@x.org>", "Maintainer": "Zed"}, [], ""),
        (
            {"Author": "Ann <a@x.org>, Bob <b@x.org>", "Maintainer": "Zed"},
            [("Ann", "a@x.org"), ("Bob", "b@x.org")],
            "AUTHOR='Ann <a@x.org>, Bob <b@x.org>': split into 2 entries",
        ),
        ({"Author-email": "a@b c", "Maintainer": "Zed"}, [], ""),
        ({"Author": "UNKNOWN", "Maintainer": "Zed"}, [("Zed", None)], ""),
        ({"Author": " ", "Maintainer": "Zed"}, [("Zed", None)], ""),
    ],
    ids=[
        "maintainer-split-key",
        "maintainer-cap-key",
        "unread-author-no-fallback",
        "two-mailbox-author-no-fallback",
        "unread-address-no-fallback",
        "placeholder-author-falls-back",
        "blank-author-falls-back",
    ],
)
def test_dependency_maintainer_only_for_an_absent_author(
    caplog: pytest.LogCaptureFixture,
    route: str,
    fields: dict[str, str],
    expected: list[tuple[str | None, str | None]],
    line: str,
) -> None:
    """Regression: an ``Author`` stated but read as no one fell back to the
    ``Maintainer``, crediting the package to Zed; a maintainer field's
    warning named ``AUTHOR_EMAIL``. Only an absent author pair (missing,
    blank, ``UNKNOWN``) falls back, and a warning names the field read."""
    with caplog.at_level(logging.WARNING):
        assert _DEPENDENCY_ROUTES[route](fields) == expected
    assert [m[: len(line)] for m in caplog.messages] == ([line] if line else [])
