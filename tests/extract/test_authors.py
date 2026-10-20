# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.authors`: when a split is warned about,
and the one summary line for a document's dependencies.

See also: tests/extract/test_core_metadata_authors.py (the reading itself),
tests/extract/test_author_parts.py (the splitter) and
tests/test_author_split_surfaces.py (the same reading on every surface).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest

from pitloom.assemble.spdx3.deps_originator import _resolve_author_or_maintainer
from pitloom.assemble.spdx3.deps_pypi import _extract_pypi_originator
from pitloom.extract.authors import (
    AUTHOR_FIELD_MAX_CHARS,
    AuthorSplit,
    dependency_author_splits,
    read_author_fields,
    warn_author_splits,
)
from pitloom.extract.dependency_authors import dependency_author_pairs
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
_NAME_REASON = "; a name field is never cut between names"
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
                f"AUTHOR={_TWO_MAILBOXES!r}: split into 2 entries next to an address"
                f" (PACKAGE=a; 1 dependency split in all){_NAME_REASON}"
            ],
        ),
        (
            lambda: read_author_fields(_TWO_MAILBOXES, "Doe, Jane <j@x.org>"),
            [
                f"AUTHOR_EMAIL='Doe, Jane <j@x.org>': split into 2 entries{_REASON}",
                f"AUTHOR={_TWO_MAILBOXES!r}: split into 2 entries next to an address"
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
    """One line per field (not per entry holding no address), at most three
    entries shown, ``...`` where cut, the count in the right number
    (``1 dependency``); a dependency's ``Author`` is one author, no split
    line."""
    with caplog.at_level(logging.WARNING):
        call()
    assert len(caplog.messages) == len(lines)
    for message, line in zip(caplog.messages, lines, strict=True):
        assert message.startswith(line)


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
    """Only an absent author pair (missing, blank, ``UNKNOWN``) falls back to the
    ``Maintainer``; an ``Author`` stated but read as no one does not, and a
    warning names the field read (not ``AUTHOR_EMAIL`` for a maintainer)."""
    with caplog.at_level(logging.WARNING):
        assert _DEPENDENCY_ROUTES[route](fields) == expected
    assert [m[: len(line)] for m in caplog.messages] == ([line] if line else [])
