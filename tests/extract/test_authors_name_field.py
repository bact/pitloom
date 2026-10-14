# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.authors`: where a name field
(``Author``) is cut -- only next to an address: after a closed
``<address>`` or a bare address, before a bare address, between two
closed ``<address>`` entries; never between two names -- read by the same
splitter as its address field (``Author-email``).

See also: tests/extract/test_core_metadata_authors.py (the reading of
both fields), tests/extract/test_author_parts.py (the splitter's oracle
and linear time), tests/extract/test_authors.py (caps) and
tests/test_author_split_surfaces.py (every surface).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract.authors import read_author_fields
from pitloom.logging_config import excerpt
from tests._author_routes import one_author_lines

_A = {"name": "Ann", "email": "a@x.org"}
_B = {"name": "Bob", "email": "b@x.org"}
_AE = {"email": "a@x.org"}
_BE = {"email": "b@x.org"}
_TWO = "Ann <a@x.org>; Bob <b@x.org>"
_CUT = "; a name field is never cut between names -- HINT"


@pytest.mark.parametrize(
    ("author", "expected", "cut", "unread", "same"),
    [
        (_TWO, [_A, _B], 2, [], True),
        ("a@x.org, b@x.org", [_AE, _BE], 2, [], True),
        ("<a@x.org>, <b@x.org>", [_AE, _BE], 2, [], True),
        (
            '"Doe, Jane" <j@x.org>, Bob <b@x.org>',
            [{"name": "Doe, Jane", "email": "j@x.org"}, _B],
            2,
            [],
            True,
        ),
        ("Ann <a@x.org>;;Bob <b@x.org>", [_A, _B], 2, [], True),
        ('"A >" <a@x.org>, Bob <b@x.org>', [{"name": "A >", **_AE}, _B], 2, [], True),
        ("Ann <a@x.org> (A), Bob <b@x.org>", [_A, _B], 2, [], True),
        ("a@x.org (Ann), b@x.org", [_A, _BE], 2, [], True),
        ("Ann <a@x.org>, Bob", [_A, {"name": "Bob"}], 2, [], True),
        (
            "Jane <j@x.org> et al.",
            [{"name": "Jane", "email": "j@x.org"}, {"name": "et al."}],
            0,
            [],
            True,
        ),
        ("Ann <a@x.org>,", [_A], 0, [], True),
        (", Ann <a@x.org>", [_A], 0, [], True),
        ('"x>, y" <a@x.org>', [{"name": "x>, y", **_AE}], 0, [], True),
        # never after a name: the comma before a < is in the name
        (
            "Doe, Jane <j@x.org>",
            [{"name": "Doe, Jane", "email": "j@x.org"}],
            0,
            [],
            False,
        ),
        (
            "Doe, Jane <j@x.org>, Bob Lee <b@x.org>",
            [{"name": "Doe, Jane", "email": "j@x.org"}, {"name": "Bob Lee", **_BE}],
            2,
            [],
            False,
        ),
        ("Jane, Bob", [{"name": "Jane, Bob"}], 0, [], False),
        ("Ann, , Bob", [{"name": "Ann, , Bob"}], 0, [], False),
        # a part still no mailbox warns as before
        ("Ann <a@x.org, Bob <b@x.org>", [], 0, ["Ann <a@x.org, Bob <b@x.org>"], False),
        ("Ann>, Bob", [], 0, ["Ann>, Bob"], False),
        # before a bare address, which carries no display name
        ("Doe, a@x.org, b@x.org", [{"name": "Doe"}, _AE, _BE], 3, [], True),
        ("Jane Doe, a@x.org", [{"name": "Jane Doe"}, _AE], 2, [], True),
        ("Doe a@x.org", [], 0, ["Doe a@x.org"], True),
        # between two closed addresses, a joining and/& left out
        ("Ann <a@x.org> and Bob <b@x.org>", [_A, _B], 2, [], False),
        (
            "Ann <a@x.org> & Bob <b@x.org> et al.",
            [_A, _B, {"name": "et al."}],
            3,
            [],
            False,
        ),
        (
            "Ann <a@x.org>\nBob <b@x.org> Lee",
            [_A, {"name": "Bob"}],
            2,
            ["Bob <b@x.org> Lee"],
            False,
        ),
        ("Ann <a@x.org> Lee", [{"name": "Ann"}], 0, ["Ann <a@x.org> Lee"], True),
        (
            '"<a@x.org> and" <b@x.org>',
            [{"name": "<a@x.org> and", **_BE}],
            0,
            [],
            True,
        ),
    ],
    ids=[
        "two-mailboxes",
        "two-bare-addresses",
        "two-bare-angle-addresses",
        "quoted-comma-then-mailbox",
        "doubled-separator",
        "quoted-angle-in-name",
        "comment-after-address",
        "comment-after-bare-address",
        "name-after-mailbox",
        "group-after-address",
        "trailing-separator",
        "leading-separator",
        "quoted-separator",
        "comma-in-name",
        "comma-in-name-then-mailbox",
        "names-only",
        "blank-between-names",
        "unclosed-address",
        "angle-without-address",
        "bare-addresses-after-name",
        "bare-address-after-name",
        "address-in-name-unseparated",
        "and-between-mailboxes",
        "ampersand-between-mailboxes",
        "newline-between-mailboxes",
        "text-after-one-mailbox",
        "quoted-mailbox-in-name",
    ],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_name_field_cut_only_after_a_mailbox(
    caplog: pytest.LogCaptureFixture,
    author: str,
    expected: list[dict[str, str]],
    cut: int,
    unread: list[str],
    same: bool,
) -> None:
    """An ``Author`` holding several complete mailboxes records each, as
    ``Author-email`` reads the same text (*same*); a cut, only next to an
    address, gets one ``WARNING:`` naming the field and the count; a comma
    after a name is never a cut unless a bare address follows; a part that
    is still no mailbox warns as before."""
    with caplog.at_level(logging.WARNING):
        assert read_author_fields(author, None, hint=" -- HINT") == expected
    lines = [f"AUTHOR={e!r}: not an email address; not recorded" for e in unread]
    if cut:
        shown = excerpt(author)
        lines.append(
            f"AUTHOR={shown}: split into {cut} entries next to an address{_CUT}"
        )
    assert caplog.messages == lines
    as_email = read_author_fields(None, author, quiet=True)
    assert (as_email == expected) is same


def test_name_field_mailboxes_beside_an_address_field() -> None:
    """The mailboxes cut from ``Author`` keep their own addresses, and a
    bare ``Author-email`` beside them stands on its own: the legacy pair
    is one name beside one address."""
    assert read_author_fields(_TWO, "t@x.org", quiet=True) == [
        _A,
        _B,
        {"email": "t@x.org"},
    ]


@pytest.mark.parametrize(
    ("author", "info"),
    [
        ("Ann and Bob <a@x.org>", True),
        ("Ann and Bob <a b>", False),
        ("Ann <a@x.org> and Bob <b@x.org>", False),
    ],
    ids=["recorded", "address-not-recorded", "cut-between-mailboxes"],
)
def test_one_author_info_only_when_recorded_as_one(
    caplog: pytest.LogCaptureFixture, author: str, info: bool
) -> None:
    """Regression: the ``INFO:`` that a name field read as one author may
    list several came beside the ``WARNING:`` that it was not recorded, and
    for two mailboxes joined by ``and``. Only an entry recorded as one
    author gets it."""
    with caplog.at_level(logging.INFO):
        read_author_fields(author, None)
    assert bool(one_author_lines(caplog)) is info
