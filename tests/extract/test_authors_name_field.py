# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.authors`: where a name field
(``Author``) is cut -- only after a closed ``<address>`` or a bare
address, never after a name -- read by the same splitter as its address
field (``Author-email``).

See also: tests/extract/test_core_metadata_authors.py (the reading of
both fields), tests/extract/test_authors.py (the splitter's oracle, caps
and linear time) and tests/test_author_split_surfaces.py (every surface).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract.authors import read_author_fields

_A = {"name": "Ann", "email": "a@x.org"}
_B = {"name": "Bob", "email": "b@x.org"}
_AE = {"email": "a@x.org"}
_BE = {"email": "b@x.org"}
_TWO = "Ann <a@x.org>; Bob <b@x.org>"
_CUT = "; a name field is cut only after an address -- HINT"


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
        ("Doe, a@x.org, b@x.org", [_BE], 2, ["Doe, a@x.org"], False),
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
        "bare-address-after-name",
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
    ``Author-email`` reads the same text (*same*); a cut, on a separator
    only, gets one ``WARNING:`` naming the field and the count; a comma
    after a name is never a cut; a part that is still no mailbox warns as
    before."""
    with caplog.at_level(logging.WARNING):
        assert read_author_fields(author, None, hint=" -- HINT") == expected
    lines = [f"AUTHOR={e!r}: not an email address; not recorded" for e in unread]
    if cut:
        lines.append(f"AUTHOR={author!r}: split into {cut} entries on ',' / ';'{_CUT}")
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
