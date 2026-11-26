# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom._log_text`: untrusted text masked first, then
collapsed, cut and escaped, so neither a collapse, a drop nor an escape
shows a credential the masker would have read.

See also: tests/test_logging_config.py (the formatter and the sink),
tests/messages/test_messages_field_writers.py (the field writers).
"""

from __future__ import annotations

import sys
from collections.abc import Callable

import pytest

from pitloom.cli.kv_output import kv_line
from pitloom.logging_config import (
    EXCERPT_CHARS,
    collapsed,
    escaped_literal,
    excerpt,
    failure_reason,
    loggable,
    one_line,
)
from pitloom.messages._field_writers import _steady, failure_text
from tests._linear_time import RATIO_BOUND, linear_ratio

#: A fake token, built at run time so no secret scanner reads the source.
_BODY = "A1b2C3d4E5" * 3 + "F6g7H8"
_TOKEN = "ghp_" + _BODY


def _drop_parens(text: str) -> str:
    """A ``steady`` step dropping each ``(x)``."""
    return text.replace("(x)", "")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("a\n\n  b\r\nc", "a b c", id="multi_line_str"),
        pytest.param(ValueError("x\ny"), "x y", id="multi_line_exception"),
        pytest.param(ValueError(), "ValueError", id="empty_exception"),
        pytest.param("", "", id="empty_str"),
    ],
)
def test_one_line(value: object, expected: str) -> None:
    assert one_line(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("six>=1", "'six>=1'"),
        ("a" * 120, repr("a" * 120)),
        ("a" * 121, repr("a" * 120) + "..."),
        ("a\n  b", "'a b'"),
        ("\x1b[31m", "'\\x1b[31m'"),
        ("\x1b" * 200, ascii("\x1b" * 120) + "..."),
        (5, "5"),
    ],
    ids=["short", "at-cap", "over-cap", "multi-line", "escaped", "escaped-cut", "int"],
)
def test_excerpt(value: object, expected: str) -> None:
    """One literal, escaped once, cut after :data:`EXCERPT_CHARS`."""
    assert excerpt(value) == expected


def test_excerpt_masks_a_url_before_it_cuts() -> None:
    """A cut inside a URL's user information would leave its start unmasked."""
    # The cut lands inside the user information, whatever the cap is.
    shown = excerpt(
        "x" * (EXCERPT_CHARS - 15) + " https://user:secretpassword@host/path"
    )
    assert "secret" not in shown and "user:" not in shown


@pytest.mark.parametrize("space", ["\n", "\t", "\r\n"], ids=["lf", "tab", "crlf"])
def test_excerpt_masks_a_password_before_it_collapses_white_space(space: str) -> None:
    """A line break or a tab inside a URL's password is masked with the
    rest of it, not turned into a space first, which ends the user
    information and shows both halves."""
    shown = excerpt(f"see https://u:pa{space}ss99@h/x")
    assert "pa" not in shown and "ss99" not in shown
    assert shown == "'see https://***:***@h/x'"


@pytest.mark.parametrize(
    "raw",
    ["Bearer\ns3cr3tvalue99", "Bearer \n s3cr3tvalue99", "Bearer\r\n\ts3cr3tvalue99"],
    ids=["lf", "spaced", "crlf-tab"],
)
def test_excerpt_masks_a_scheme_credential_split_by_a_line_break(raw: str) -> None:
    """A scheme word and its credential on two lines read as one run only
    once the white space is collapsed: masked again after it."""
    assert excerpt(raw) == "'Bearer ***'"


def test_excerpt_masks_a_header_value_moved_up_by_the_collapse() -> None:
    """A header's own separators hold no line break: the value reads as one
    only once the line break is a space, so it is masked after collapsing."""
    assert excerpt("Authorization: Bearer\nabc") == "'Authorization: Bearer ***'"


_VIEWS: list[Callable[[str], str]] = [
    one_line,
    lambda text: failure_reason(RuntimeError(text)),
    lambda text: failure_text(RuntimeError(text)),
]


@pytest.mark.parametrize("view", _VIEWS, ids=["one-line", "reason", "failure-text"])
@pytest.mark.parametrize(
    "space",
    ["\n", "\r\n", "\t", "\n ", "\u2028"],
    ids=["lf", "crlf", "tab", "lf-space", "u2028"],
)
def test_one_line_masks_before_it_collapses(
    view: Callable[[str], str], space: str
) -> None:
    """A line break or a tab inside a password is masked with the rest of
    it; collapsed first, it would be a space, which ends the user
    information and shows both halves."""
    shown = view(f"see https://user:S3cr{space}3tPw99x@h/x")
    assert "S3cr" not in shown and "3tPw99x" not in shown
    assert shown == "see https://***:***@h/x"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("abc(x)" + _TOKEN, "abcghp_***"),
        ("https://u:pw99x(x)@h/r", "https://***:***@h/r"),
        ("see https://u:S3cr\n3tPw99x@h/r(x)", "see https://***:***@h/r"),
        ("(x)", ""),
    ],
    ids=["glued-token", "joined-userinfo", "split-password", "all-dropped"],
)
def test_collapsed_masks_before_and_after_the_steady_step(
    text: str, expected: str
) -> None:
    """The first pass masks a token the drop then glues to a word (the
    second would read ``abcghp_...`` as one word); the second masks user
    information the drop joins (the first reads two harmless pieces)."""
    shown = collapsed(text, _drop_parens)
    assert _BODY not in shown and "pw99x" not in shown and "S3cr" not in shown
    assert shown == expected


def test_one_line_names_the_class_when_the_steady_step_drops_all() -> None:
    assert one_line(RuntimeError(" (x) "), steady=_drop_parens) == "RuntimeError"


def test_failure_text_collapses_the_space_a_drop_leaves() -> None:
    assert failure_text(ValueError("a (Request ID: x) b")) == "a b"


def test_one_line_escapes_its_cut_as_one_literal() -> None:
    """The masked text is cut, then escaped as a literal (not masked again
    and escaped as a bare text)."""
    shown = one_line("\x07https://h.example/x?access_token=" + "S3CRET", 34)
    assert "S3CRET" not in shown
    assert shown == "'\\x07https://h.example/x?access_token='"


#: Each white space :meth:`str.split` reads (:meth:`str.isspace`) but the
#: masker reads as the end of a URL in a line: neither a space, a tab nor a
#: line break (:meth:`str.splitlines`). Derived, so a white space a new
#: Unicode version adds is a new case.
_URL_ENDING_SPACES = [
    space
    for space in map(chr, range(sys.maxunicode + 1))
    if space.isspace() and space not in " \t" and len(f"a{space}b".splitlines()) == 1
]


_SPACE_VIEWS: list[Callable[[str], str]] = [
    one_line,
    lambda text: excerpt(text).strip("'"),
    lambda text: failure_reason(RuntimeError(text)),
    lambda text: failure_text(RuntimeError(text)),
]


@pytest.mark.parametrize(
    "view", _SPACE_VIEWS, ids=["one-line", "excerpt", "reason", "failure-text"]
)
@pytest.mark.parametrize(
    "space", _URL_ENDING_SPACES, ids=[f"u{ord(c):04x}" for c in _URL_ENDING_SPACES]
)
def test_a_password_split_by_a_space_the_collapse_reads_is_masked(
    view: Callable[[str], str], space: str
) -> None:
    """A no-break space (or another white space the collapse makes a space)
    inside a password is masked with the rest of it, not shown as two
    halves; in a text with no credential it is a space, as before."""
    shown = view(f"see https://u:hunter2Qz{space}9pW7xK4v@h/x")
    assert "hunter2Qz" not in shown and "9pW7xK4v" not in shown
    assert shown == "see https://***:***@h/x"
    assert view(f"a{space}b{space}{space}c") == "a b c"


_ZERO_WIDTH_SPLIT = _TOKEN[:10] + "\u200b" + _TOKEN[10:]
_SCP_TAB = "alice:p\u00e4ssw0rd9@host:o/r\t"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (_ZERO_WIDTH_SPLIT, "ghp_***"),
        ("see " + _ZERO_WIDTH_SPLIT + "\t", "'see ghp_***\\t'"),
        (_SCP_TAB, "'***:***@host:o/r\\t'"),
    ],
    ids=["zero-width", "zero-width-tab", "scp-non-ascii"],
)
def test_loggable_masks_before_it_escapes(text: str, expected: str) -> None:
    """Escaped first, a zero-width space would read ``\\u200b`` inside the
    token and a non-ASCII letter ``\\xe4`` inside the password, which no
    shape matches."""
    shown = loggable(text)
    assert _BODY[:6] not in shown and _BODY[6:] not in shown
    assert "ssw0rd9" not in shown and "alice" not in shown
    assert shown == expected


def test_a_printable_text_is_returned_as_given() -> None:
    """The fast path: the sink masks it as the line is printed."""
    assert loggable("x https://u:pw@h") == "x https://u:pw@h"


@pytest.mark.parametrize(
    "value",
    ["meet 10:30@ab:c.json\t", _SCP_TAB, "C:\\Users\\a b\\t.json\t"],
    ids=["scp-like-name", "scp-password", "windows-path"],
)
def test_stdout_data_is_escaped_but_never_masked(value: str) -> None:
    """A ``KEY=VALUE`` value without a URL is data: escaped, never masked
    by the scp-style rule (``meet 10:30@ab:c.json`` is a file name)."""
    assert escaped_literal(value) == ascii(value)
    assert kv_line(V=value) == f"V={ascii(value)}"


#: Each text stressing the collapse and the ``steady`` step, of about *n*
#: characters.
_COLLAPSE_SHAPES: dict[str, Callable[[int], str]] = {
    "space-runs": lambda n: ("a" + " \t\n" * 3) * (n // 10),
    "request-ids": lambda n: "(Request ID: a)" * (n // 15),
    "url-line-breaks": lambda n: "https://u:p\na" * (n // 13),
    "nbsp-run": lambda n: "a" + "\xa0" * n + "@h",
    "ideographic-runs": lambda n: ("https://u:p" + "\u3000" * 9) * (n // 20),
    "header-lf": lambda n: "Authorization: Bearer\n" * (n // 22),
}


@pytest.mark.parametrize("shape", sorted(_COLLAPSE_SHAPES))
def test_one_line_with_steady_is_linear_in_time(shape: str) -> None:
    """Five times the text takes about five times as long through both
    masker passes, the collapse and the ``steady`` step (a quadratic step:
    twenty-five); each time the best of three, at least 5 ms."""
    make = _COLLAPSE_SHAPES[shape]
    ratio = linear_ratio(lambda text: one_line(text, steady=_steady), make)
    assert ratio < RATIO_BOUND, f"ratio {ratio:.1f}"
