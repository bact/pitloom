# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract._core_metadata.parse_core_metadata_authors --
a package's own authors from ``Author``/``Author-email``, read the same by
the wheel and sdist routes.

See also: :mod:`tests.extract.test_core_metadata` (``Project-URL``) and
:mod:`tests.test_author_surfaces` (the cross-route parity).
"""

from __future__ import annotations

import email
import logging
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract._core_metadata import parse_core_metadata_authors
from pitloom.extract.authors import (
    CORE_METADATA_HINT,
    AuthorSplit,
    warn_author_splits,
)
from pitloom.extract.project.sdist import _parse_pkg_info
from pitloom.extract.wheel import read_wheel

_A = {"name": "Ann", "email": "ann@example.com"}
_B = {"name": "Bob", "email": "bob@example.com"}
_A2 = {"name": "Ann", "email": "a@x.org"}
_B2 = {"name": "Bob", "email": "b@x.org"}
_JE = {"email": "j@x.org"}
_J = {"name": "Jane", **_JE}
#: The separators a split warning names: ``Author``'s, ``Author-email``'s.
_ALL, _COMMAS = "',' / ';' / 'and'", "',' / ';'"
#: The ``Author`` example of the core metadata specification, folded.
_SPEC_AUTHOR = (
    "C. Schultz, Universal Features Syndicate,\n"
    "        Los Angeles, CA <cschultz@peanuts.example.com>"
)


@pytest.mark.parametrize(
    ("author", "author_email", "expected"),
    [
        ("Ann, Bob and Cee", None, [{"name": n} for n in ("Ann", "Bob", "Cee")]),
        (None, "Ann <ann@example.com>, Bob <bob@example.com>", [_A, _B]),
        # hatchling/setuptools: addressed authors, then name-only ones
        ("Cee, Dan", "Ann <ann@example.com>", [_A, {"name": "Cee"}, {"name": "Dan"}]),
        (None, "ann@example.com", [{"email": "ann@example.com"}]),
        ("Ann", "ann@example.com", [_A]),
        (
            "Ann and Bob",
            "team@example.com",
            [{"name": "Ann"}, {"name": "Bob"}, {"email": "team@example.com"}],
        ),
        (None, None, []),
        ("UNKNOWN", "UNKNOWN", []),
        ("  ", "", []),
        ("Ann", "Ann <ann@example.com>, Ann <ann@example.com>", [_A]),
        (
            None,
            '"Doe, Jane" <jane@example.com>',
            [{"name": "Doe, Jane", "email": "jane@example.com"}],
        ),
        (
            "山田",
            "Jörg Müller <j@example.com>",
            [{"name": "Jörg Müller", "email": "j@example.com"}, {"name": "山田"}],
        ),
        (None, "Ann <ann@example.com>, , Bob <bob@example.com>", [_A, _B]),
        (None, "Ann <ann@example.com>,\n Bob <bob@example.com>", [_A, _B]),
        (None, "Unknown <cat@example.org>", [{"email": "cat@example.org"}]),
        (
            None,
            "Unknown <cat@example.org>, Ann <ann@example.com>",
            [{"email": "cat@example.org"}, _A],
        ),
        (None, "Unknown <>", [{"name": "Unknown"}]),
        (
            "Cee",
            "ann@example.com, Bob <bob@example.com>",
            [{"email": "ann@example.com"}, _B, {"name": "Cee"}],
        ),
        ("UNKNOWN  ", None, []),
        (
            "Alexander Sandberg, Sandra Anderson, Roland, andy",
            None,
            [
                {"name": n}
                for n in ("Alexander Sandberg", "Sandra Anderson", "Roland", "andy")
            ],
        ),
        # an address ending a name part is that part's: the comma split
        # cannot tell C. Schultz's affiliation from three more authors
        (
            _SPEC_AUTHOR,
            None,
            [
                {"name": "C. Schultz"},
                {"name": "Universal Features Syndicate"},
                {"name": "Los Angeles"},
                {"name": "CA", "email": "cschultz@peanuts.example.com"},
            ],
        ),
        (
            "Ann <ann@example.org>",
            "Ann <ann@example.com>",
            [_A, {"name": "Ann", "email": "ann@example.org"}],
        ),
        ("Ann <ann@and.example>", None, [{"name": "Ann", "email": "ann@and.example"}]),
        (None, "ann@example.com (Ann)", [_A]),
        (None, "Ann <ann@example.com> ; Bob < bob@example.com > (B)", [_A, _B]),
        (
            "Ann <ann@example.com>",
            "team@example.com",
            [_A, {"email": "team@example.com"}],
        ),
        # a contributor group stays whole, as a [project].authors entry
        ("Jane and others", None, [{"name": "Jane and others"}]),
        (
            "J. Smith et al.",
            "team@example.com",
            [{"name": "J. Smith et al.", "email": "team@example.com"}],
        ),
        # the group test is per comma-separated part: hatchling joins the
        # name-only authors [{name="Doe, Jane"}, {name="Ann and others"}]
        (
            "Doe, Jane, Ann and others",
            None,
            [{"name": n} for n in ("Doe", "Jane", "Ann and others")],
        ),
        (
            "Smith, J. et al.",
            "team@example.com",
            [{"name": "Smith"}, {"name": "J. et al."}, {"email": "team@example.com"}],
        ),
        # an address ends its entry: a group after it is a part of its own
        (
            "Jane Doe <j@x.org> et al.",
            None,
            [{"name": "Jane Doe", "email": "j@x.org"}, {"name": "et al."}],
        ),
        (
            "Jane Doe <j@x.org>, and others",
            None,
            [{"name": "Jane Doe", "email": "j@x.org"}, {"name": "and others"}],
        ),
        (
            "Jane and others <t@x.org>",
            None,
            [{"name": "Jane and others", "email": "t@x.org"}],
        ),
        ("Ann <others@x.org>", None, [{"name": "Ann", "email": "others@x.org"}]),
        (
            "Ann and Bob <others@x.org>",
            None,
            [{"name": "Ann"}, {"name": "Bob", "email": "others@x.org"}],
        ),
        ("<et.al@x.org>", None, [{"email": "et.al@x.org"}]),
        # typographic quotes hold a display name together, as "" do
        (
            None,
            "\u201cDoe, Jane\u201d <j@x.org>, O\u2019Brien <o@x.org>",
            [
                {"name": "Doe, Jane", "email": "j@x.org"},
                {"name": "O\u2019Brien", "email": "o@x.org"},
            ],
        ),
        ("Ann <a@x.org>; Bob <b@x.org>", None, [_A2, _B2]),
        # Author-email is split on , and ; as Author, never on "and": a
        # part with no <, > or @ is a name
        (None, "Doe, Jane <j@x.org>", [{"name": "Doe"}, _J]),
        ("Doe", "Doe, Jane <j@x.org>", [{"name": "Doe"}, _J]),
        (None, "Ann and Bob <b@x.org>", [{"name": "Ann and Bob", "email": "b@x.org"}]),
        (None, "Ann and Bob", [{"name": "Ann and Bob"}]),
        (None, "Jane <j@x.org> and others", [_J, {"name": "and others"}]),
        (None, "Jane and others <j@x.org>", [{"name": "Jane and others", **_JE}]),
        # Author is split as Author-email: quotes, ';', a bare address
        ('"Doe, Jane", Ann', None, [{"name": "Doe, Jane"}, {"name": "Ann"}]),
        ("\u201cDoe, Jane\u201d", None, [{"name": "Doe, Jane"}]),
        ('""', None, []),
        ("Ann; Bob", None, [{"name": "Ann"}, {"name": "Bob"}]),
        ("a@x.org", "b@x.org", [{"email": "a@x.org"}, {"email": "b@x.org"}]),
    ],
    ids=[
        "author-only",
        "email-list",
        "both",
        "bare-address",
        "legacy-pair",
        "legacy-names-shared-address",
        "absent",
        "unknown",
        "blank",
        "duplicate",
        "quoted-comma",
        "non-ascii",
        "empty-entry",
        "folded",
        "placeholder-name",
        "placeholder-name-list",
        "unknown-without-address",
        "bare-address-list",
        "unknown-padded",
        "and-inside-word",
        "spec-example",
        "author-own-address",
        "and-inside-address",
        "comment-name",
        "spaced",
        "author-address-legacy",
        "and-others",
        "et-al-legacy-pair",
        "hatchling-joined-group",
        "comma-before-et-al",
        "address-then-group",
        "address-comma-group",
        "group-with-address",
        "group-word-in-address",
        "group-word-in-address-split",
        "group-word-address-only",
        "typographic-quotes",
        "semicolon-in-author",
        "unquoted-comma-email",
        "unquoted-comma-email-repeat",
        "and-in-email",
        "and-in-email-name",
        "group-after-address-in-email",
        "group-in-email",
        "quoted-name-in-author",
        "typographic-name-in-author",
        "empty-quoted-name",
        "semicolon-names",
        "address-in-author",
    ],
)
def test_parse_core_metadata_authors(
    author: str | None, author_email: str | None, expected: list[dict[str, str]]
) -> None:
    msg = email.message.Message()
    if author is not None:
        msg["Author"] = author
    if author_email is not None:
        msg["Author-email"] = author_email
    assert parse_core_metadata_authors(msg) == expected


@pytest.mark.parametrize("quiet", [False, True], ids=["warns", "quiet"])
@pytest.mark.parametrize(
    ("author", "author_email", "expected", "unreadable"),
    [
        # no <, > or @: a name, as in Author, not an address
        (
            "Jane",
            "john at example dot com",
            [{"name": "john at example dot com"}, {"name": "Jane"}],
            [],
        ),
        (
            None,
            "ann@example.com; Bob <bob@example.com>",
            [{"email": "ann@example.com"}, _B],
            [],
        ),
        (None, "Ann <ann@example.com>; foo@, @bar", [_A], ["foo@", "@bar"]),
        ("Jane", "<<<", [{"name": "Jane"}], ["<<<"]),
        # checked as written, never as email.utils reads it back ("a@bc")
        (None, "a@b c, a@b@c", [], ["a@b c", "a@b@c"]),
        (None, '"a@b', [], ['"a@b']),
        (None, "Ann ann@example.com", [], ["Ann ann@example.com"]),
        # a stated display name is kept; only the address is not recorded
        ("Ann <a@b c>", None, [{"name": "Ann"}], ["Ann <a@b c>"]),
        ("Ann <none>", "Ann <a@b c>", [{"name": "Ann"}], ["Ann <a@b c>", "Ann <none>"]),
        (None, '"Doe, Jane" <x y>', [{"name": "Doe, Jane"}], ['"Doe, Jane" <x y>']),
        ("Jane <j@x, y.org>", None, [{"name": "Jane"}], ["Jane <j@x, y.org>"]),
        # a comma inside <...> ends no entry, in either field
        (None, "Jane <j@x, y.org>", [{"name": "Jane"}], ["Jane <j@x, y.org>"]),
        (
            "Ann <a@b c>",
            "t@x.org",
            [{"name": "Ann"}, {"email": "t@x.org"}],
            ["Ann <a@b c>"],
        ),
        ("Unknown <a b>", None, [], ["Unknown <a b>"]),
    ],
    ids=[
        "words-name",
        "semicolon",
        "partial",
        "unparsable",
        "altered",
        "quote-dropped",
        "no-angle",
        "in-author",
        "both-fields",
        "quoted-name",
        "comma-in-address",
        "comma-in-email-address",
        "not-legacy-pair",
        "unknown-placeholder",
    ],
)
def test_author_email_entry_without_an_address(
    caplog: pytest.LogCaptureFixture,
    author: str | None,
    author_email: str,
    expected: list[dict[str, str]],
    unreadable: list[str],
    quiet: bool,
) -> None:
    """Entries split on ``;`` too; one with no ``local@domain`` address is
    not recorded (no invented address), with one ``WARNING:`` per field,
    tagged with its key, naming the entries and, when several, the count."""
    msg = email.message.Message()
    if author is not None:
        msg["Author"] = author
    msg["Author-email"] = author_email
    with caplog.at_level(logging.WARNING):
        assert parse_core_metadata_authors(msg, quiet=quiet) == expected
    by_key: dict[str, list[str]] = {}
    for e in unreadable:
        key = "AUTHOR" if e in (author or "") else "AUTHOR_EMAIL"
        by_key.setdefault(key, []).append(e)
    assert caplog.messages == (
        []
        if quiet
        else [
            f"{key}={entries[0]!r}: not an email address; not recorded"
            if len(entries) == 1
            else f"{key}={entries!r}: not an email address;"
            f" {len(entries)} entries not recorded"
            for key, entries in by_key.items()
        ]
    )


@pytest.mark.parametrize("quiet", [False, True], ids=["warns", "quiet"])
@pytest.mark.parametrize(
    ("author", "author_email", "warned"),
    [
        ("Ann", None, None),
        ("Ann Lee", "ann@example.com", None),
        (None, '"Doe, Jane" <jane@example.com>', None),
        (None, '"Ann and Bob" <team@example.com>', None),
        (None, "Ann and Bob <team@example.com>", None),
        ("Ann, Bob", None, ("Ann, Bob", 2, _ALL)),
        ("Ann and Bob", None, ("Ann and Bob", 2, _ALL)),
        ("Ann, Bob and Cee", "Dan <dan@example.com>", ("Ann, Bob and Cee", 3, _ALL)),
        ("Ann, Bob", "team@example.com", ("Ann, Bob", 2, _ALL)),
        # shown on one line
        (_SPEC_AUTHOR, None, (" ".join(_SPEC_AUTHOR.split()), 4, _ALL)),
        ("J. Smith et al.", None, None),
        ("Smith, J. et al.", None, ("Smith, J. et al.", 2, _ALL)),
        # a split right after an address is no guess
        ("Ann <a@x.org>, Bob <b@x.org>", None, None),
        ("Jane Doe <j@x.org> et al.", None, None),
        ("Jane Doe <j@x.org>, and others", None, None),
        # Author-email splits on , and ; and warns as Author; one line for
        # both fields, naming every separator used
        (None, "Doe, Jane <j@x.org>", ("Doe, Jane <j@x.org>", 2, _COMMAS)),
        ("Ann", "Doe, Jane <j@x.org>", ("Doe, Jane <j@x.org>", 2, _COMMAS)),
        (None, "a@x.org, b@x.org", None),
        (
            "Ann, Bob",
            "Doe, Jane <j@x.org>",
            (["Doe, Jane <j@x.org>", "Ann, Bob"], 4, _ALL),
        ),
    ],
    ids=[
        "single",
        "legacy-pair",
        "quoted-comma-whole",
        "quoted-and-whole",
        "unquoted-and-whole",
        "comma",
        "and",
        "three-names",
        "legacy-address",
        "spec-example",
        "contributor-group",
        "comma-before-group",
        "addresses",
        "address-then-group",
        "address-comma-group",
        "email-comma",
        "email-comma-author-whole",
        "email-addresses",
        "both-fields",
    ],
)
def test_split_author_warns_once(
    caplog: pytest.LogCaptureFixture,
    author: str | None,
    author_email: str | None,
    warned: tuple[str | list[str], int, str] | None,
    quiet: bool,
) -> None:
    """A split ``Author`` or ``Author-email`` gets one ``WARNING:`` per call
    naming the strings, the count and the separators (``and`` only for
    ``Author``); nothing split, or *quiet*, none -- no other line either."""
    msg = email.message.Message()
    if author is not None:
        msg["Author"] = author
    if author_email is not None:
        msg["Author-email"] = author_email
    with caplog.at_level(logging.WARNING):
        parse_core_metadata_authors(msg, quiet=quiet)
    if warned is None or quiet:
        assert caplog.messages == []
    else:
        (line,) = caplog.messages
        field, count, on = warned
        assert line.startswith(f"AUTHOR={field!r}: split into {count} names on {on};")


def test_warn_splits_several_fields_is_one_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One line; each separator named once, in order."""
    with caplog.at_level(logging.WARNING):
        splits = [
            AuthorSplit("A, B", 2, ("','", "';'")),
            AuthorSplit("C and D and E", 3),
        ]
        warn_author_splits(splits, hint=CORE_METADATA_HINT)
    (line,) = caplog.messages
    assert line.startswith(
        f"AUTHOR=['A, B', 'C and D and E']: split into 5 names on {_ALL};"
    )
    assert "--project-dir" in line


def test_split_authors_same_on_wheel_and_sdist_readers(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Drift guard: one ``Author`` string through the wheel ``METADATA`` and
    sdist ``PKG-INFO`` readers gives the same names and the same warning."""
    text = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nAuthor: Ann, Bob\n"
    wheel = tmp_path / "demo-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("demo-1.0.dist-info/METADATA", text)
    seen: list[tuple[list[dict[str, str]], list[str]]] = []
    reads: list[Callable[[], ProjectMetadata]] = [
        lambda: read_wheel(wheel)[0],
        lambda: _parse_pkg_info(text, "src"),
    ]
    for read in reads:
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            seen.append((read().authors, list(caplog.messages)))
    assert seen[0] == seen[1]
    assert seen[0][0] == [{"name": "Ann"}, {"name": "Bob"}]
    assert len(seen[0][1]) == 1
