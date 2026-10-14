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
_JE = {"email": "j@x.org"}
_J = {"name": "Jane", **_JE}
_AE = {"email": "a@x.org"}
#: A quoted display name holding angle brackets, with its address.
_QB = {"name": "A <b>", **_AE}
_QB_LEE = {"name": '"A <b>" Lee', **_AE}
#: The ``Author`` example of the core metadata specification, folded.
_SPEC_AUTHOR = (
    "C. Schultz, Universal Features Syndicate,\n"
    "        Los Angeles, CA <cschultz@peanuts.example.com>"
)


@pytest.mark.parametrize(
    ("author", "author_email", "expected"),
    [
        (None, "Ann <ann@example.com>, Bob <bob@example.com>", [_A, _B]),
        (None, "ann@example.com", [{"email": "ann@example.com"}]),
        ("Ann", "ann@example.com", [_A]),
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
        ("Jane and others", None, [{"name": "Jane and others"}]),
        (
            "J. Smith et al.",
            "team@example.com",
            [{"name": "J. Smith et al.", "email": "team@example.com"}],
        ),
        (
            "Jane and others <t@x.org>",
            None,
            [{"name": "Jane and others", "email": "t@x.org"}],
        ),
        ("Ann <others@x.org>", None, [{"name": "Ann", "email": "others@x.org"}]),
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
        # Author-email is split on , and ;, never on "and": a part with no
        # <, > or @ is a name
        (None, "Doe, Jane <j@x.org>", [{"name": "Doe"}, _J]),
        ("Doe", "Doe, Jane <j@x.org>", [{"name": "Doe"}, _J]),
        (None, "Ann and Bob <b@x.org>", [{"name": "Ann and Bob", "email": "b@x.org"}]),
        (None, "Ann and Bob", [{"name": "Ann and Bob"}]),
        (None, "Jane <j@x.org> and others", [_J, {"name": "and others"}]),
        (None, "Jane and others <j@x.org>", [{"name": "Jane and others", **_JE}]),
        # Author entries read as Author-email ones: quotes, a bare address
        ("\u201cDoe, Jane\u201d", None, [{"name": "Doe, Jane"}]),
        ('""', None, []),
        ("a@x.org", "b@x.org", [{"email": "a@x.org"}, {"email": "b@x.org"}]),
        # Author is cut only next to an address -- a free-text list of names
        # is one author, its name all the text before a sole <
        ("Ann, Bob and Cee", None, [{"name": "Ann, Bob and Cee"}]),
        # hatchling/setuptools: addressed authors, then name-only ones
        ("Cee, Dan", "Ann <ann@example.com>", [_A, {"name": "Cee, Dan"}]),
        (
            "Ann and Bob",
            "team@example.com",
            [{"name": "Ann and Bob", "email": "team@example.com"}],
        ),
        ("Doe, Jane", None, [{"name": "Doe, Jane"}]),
        ("Doe, Jane <j@x.org>", None, [{"name": "Doe, Jane", **_JE}]),
        ("Ann; Bob", None, [{"name": "Ann; Bob"}]),
        ('"Doe, Jane", Ann', None, [{"name": '"Doe, Jane", Ann'}]),
        (
            "Ann and Bob <others@x.org>",
            None,
            [{"name": "Ann and Bob", "email": "others@x.org"}],
        ),
        # Hatchling joins [{name="Doe, Jane"}, {name="Ann and others"}]
        ("Doe, Jane, Ann and others", None, [{"name": "Doe, Jane, Ann and others"}]),
        (
            "Smith, J. et al.",
            "team@example.com",
            [{"name": "Smith, J. et al.", "email": "team@example.com"}],
        ),
        # the specification's own example: one author with an affiliation
        (
            _SPEC_AUTHOR,
            None,
            [
                {
                    "name": "C. Schultz, Universal Features Syndicate, Los Angeles, CA",
                    "email": "cschultz@peanuts.example.com",
                }
            ],
        ),
        # a folded name, quoted or not, address or not, is one-spaced
        (
            _SPEC_AUTHOR.partition(" <")[0],
            None,
            [{"name": "C. Schultz, Universal Features Syndicate, Los Angeles, CA"}],
        ),
        ("Ann\r\n\tLee", None, [{"name": "Ann Lee"}]),
        ('"Ann\n        Lee" <a@x.org>', None, [{"name": "Ann Lee", **_AE}]),
        # angle brackets inside a quoted display name are its text
        ('"A <b>" <a@x.org>', None, [_QB]),
        (None, '"A <b>" <a@x.org>, Bob <bob@example.com>', [_QB, _B]),
        ('"A \\"<b>\\" C" <a@x.org>', None, [{"name": 'A "<b>" C', **_AE}]),
        (None, "\u201cA <b>\u201d <a@x.org>", [_QB]),
        ('"A <b>" Lee <a@x.org>', None, [_QB_LEE]),
        (None, '"A <b>" Lee <a@x.org>', [_QB_LEE]),
    ],
    ids=[
        "email-list",
        "bare-address",
        "legacy-pair",
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
        "author-own-address",
        "and-inside-address",
        "comment-name",
        "spaced",
        "author-address-legacy",
        "and-others",
        "et-al-legacy-pair",
        "group-with-address",
        "group-word-in-address",
        "group-word-address-only",
        "typographic-quotes",
        "unquoted-comma-email",
        "unquoted-comma-email-repeat",
        "and-in-email",
        "and-in-email-name",
        "group-after-address-in-email",
        "group-in-email",
        "typographic-name-in-author",
        "empty-quoted-name",
        "address-in-author",
        "one-list",
        "one-both",
        "one-and-legacy-pair",
        "one-comma",
        "one-comma-address",
        "one-semicolon",
        "one-quote-inside",
        "one-and-address",
        "one-joined-group",
        "one-group-legacy-pair",
        "one-spec-example",
        "folded-name-only",
        "folded-crlf-tab",
        "folded-quoted",
        "quoted-brackets-author",
        "quoted-brackets-email",
        "quoted-brackets-escaped-quote",
        "quoted-brackets-typographic",
        "quoted-brackets-then-text-author",
        "quoted-brackets-then-text-email",
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
        # an address needs its closing >; an empty <> is no address to note
        ("Ann <a@x.org", "", [{"name": "Ann"}], ["Ann <a@x.org"]),
        ("Ann <>", "", [{"name": "Ann"}], []),
        # one Author mailbox; text after its address makes it no address
        ("Ann <a@x.org> Lee", "", [{"name": "Ann"}], ["Ann <a@x.org> Lee"]),
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
        "unclosed-address",
        "empty-address",
        "text-after-address",
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
        ("J. Smith et al.", None, None),
        # a split right after an address is no guess
        (None, "Ann <a@x.org>, Bob <b@x.org>", None),
        (None, "Jane Doe <j@x.org> et al.", None),
        (None, "Jane Doe <j@x.org>, and others", None),
        (None, "a@x.org, b@x.org", None),
        (None, "Doe, Jane <j@x.org>", ("Doe, Jane <j@x.org>", 2)),
        ("Ann", "Doe, Jane <j@x.org>", ("Doe, Jane <j@x.org>", 2)),
        # an Author holding no address is never split, so never warned about
        ("Ann, Bob", None, None),
        ("Ann and Bob", None, None),
        ("Ann, Bob", "team@example.com", None),
        (_SPEC_AUTHOR, None, None),
        ("Ann, Bob", "Doe, Jane <j@x.org>", ("Doe, Jane <j@x.org>", 2)),
    ],
    ids=[
        "single",
        "legacy-pair",
        "quoted-comma-whole",
        "quoted-and-whole",
        "unquoted-and-whole",
        "contributor-group",
        "addresses",
        "address-then-group",
        "address-comma-group",
        "email-addresses",
        "email-comma",
        "email-comma-author-whole",
        "one-comma",
        "one-and",
        "one-legacy-pair",
        "one-spec-example",
        "one-both-fields",
    ],
)
def test_split_author_warns_once(
    caplog: pytest.LogCaptureFixture,
    author: str | None,
    author_email: str | None,
    warned: tuple[str, int] | None,
    quiet: bool,
) -> None:
    """A split ``Author-email`` gets one ``WARNING:`` per call naming the
    string and the count; an ``Author`` holding no address is never split
    (its cuts: tests/extract/test_authors_name_field.py); nothing split, or
    *quiet*, no line -- no other line either."""
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
        field, count = warned
        assert line.startswith(
            f"AUTHOR_EMAIL={field!r}: split into {count} entries on ',' / ';';"
        )


def test_warn_splits_several_fields_is_one_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One line for several split fields, their entries counted together."""
    with caplog.at_level(logging.WARNING):
        splits = [AuthorSplit("A, B", 2), AuthorSplit("C; D; E", 3)]
        warn_author_splits(splits, hint=CORE_METADATA_HINT)
    (line,) = caplog.messages
    assert line.startswith(
        "AUTHOR_EMAIL=['A, B', 'C; D; E']: split into 5 entries on ',' / ';';"
    )
    assert line.endswith(CORE_METADATA_HINT)


def test_split_authors_same_on_wheel_and_sdist_readers(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Drift guard: one ``Author``/``Author-email`` pair through the wheel
    ``METADATA`` and sdist ``PKG-INFO`` readers gives the same names and the
    same warning."""
    text = (
        "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nAuthor: Ann, Bob\n"
        "Author-email: Cee, Dan <d@x.org>\n"
    )
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
    assert seen[0][0] == [
        {"name": "Cee"},
        {"name": "Dan", "email": "d@x.org"},
        {"name": "Ann, Bob"},
    ]
    assert len(seen[0][1]) == 1
