# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential after an ``Authorization`` header's scheme on the next
line, and a quoted credential after a scheme
(:mod:`pitloom.core.url_masking._auth_schemes`): masked, the next header's
name and the quotes kept.

See also: test_url_masking_auth_schemes.py (the scheme and header rules)
in this folder.
"""

from __future__ import annotations

import json
import logging

import pytest

from pitloom.core.url_masking import masked_given_path
from pitloom.log_masking import mask_record, masked_text


def _forms(text: str) -> tuple[str, str, str]:
    """*text*, as ``ascii()`` writes it, and that written again."""
    return text, ascii(text), ascii(ascii(text))


def _logged(text: str) -> str:
    """The message of a log record interpolating *text*, once masked."""
    record = logging.LogRecord(
        "pitloom.x", logging.WARNING, "f", 1, "got %s", (text,), None
    )
    mask_record(record)
    return record.getMessage()


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("Authorization: Bearer\nhunter2Xabc", "Authorization: Bearer\n***"),
        ("Authorization: Bearer\r\nhunter2Xabc", "Authorization: Bearer\r\n***"),
        ("Authorization: Bearer \n  hunter2Xabc", "Authorization: Bearer \n  ***"),
        ("Proxy-Authorization: token\nabcdefghij", "Proxy-Authorization: token\n***"),
        ("Authorization: Bearer\n\nhunter2Xabc", "Authorization: Bearer\n\n***"),
        (
            "Authorization: Bearer\nhunter2Xabc\nX-Other: 1",
            "Authorization: Bearer\n***\nX-Other: 1",
        ),
        ("Authorization: Bearer\n'hunter2Xabc'", "Authorization: Bearer\n'***'"),
        ("Authorization: Bearer\rhunter2Xabc", "Authorization: Bearer\r***"),
        ("Authorization: Bearer\u2028hunter2Xabc", "Authorization: Bearer\u2028***"),
        ("Authorization: Bearer\x85hunter2Xabc", "Authorization: Bearer\x85***"),
        ("Authorization: Bearer\x0bhunter2Xabc", "Authorization: Bearer\x0b***"),
        (
            "Authorization: Bearer \x1b[1mhunter2Xabc",
            "Authorization: Bearer \x1b[1m***",
        ),
    ],
    ids=[
        *("lf", "crlf", "spaces", "proxy-token", "blank-line", "then-header"),
        *("quote", "cr", "u2028", "nel", "vt", "ansi"),
    ],
)
def test_header_credential_after_a_line_break(text: str, shown: str) -> None:
    """A line break after a header's scheme (any :meth:`str.splitlines`
    reads), or an ANSI sequence, raw or escaped once or twice (``\\n``,
    ``\\r\\n``, ``\\\\n``, ``\\u2028``), separates it from its credential,
    which is masked, through ``masked_text`` and a log record."""
    secret = "hunter2Xabc" if "hunter" in text else "abcdefghij"
    for given, expected in zip(_forms(text), _forms(shown), strict=True):
        assert given != expected
        for masked in (masked_text(given), _logged(given).removeprefix("got ")):
            assert secret not in masked, given
            assert masked == expected


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer\nX-Other: 1",
        "Authorization: Bearer\r\nX-Other: 1",
        "Authorization: Bearer\nContent-Type : text/plain",
        "Authorization: Bearer\n\nX-Other: 1",
        "Authorization: Basic\nx_custom.h~1:abc",
        "Authorization: Negotiate\n  continued",
        "Authorization:\nnext line",
        "Authorization: Bearer\n  X-Other: 1",
        "Authorization: Bearer\r\tX-Other: 1",
        "Authorization: NTLM\nmore",
    ],
    ids=[
        *("lf", "crlf", "space-colon", "blank-line", "tchar", "prose", "no-scheme"),
        *("indented", "cr-tab", "ntlm"),
    ],
)
def test_the_next_header_name_after_a_line_break_is_kept(text: str) -> None:
    """A header name and ``:`` after the line break are the next header,
    not a credential: printed as written, raw and escaped once or twice; so
    is a prose word after a scheme other than ``Bearer``, ``Basic`` or
    ``token``."""
    for given in _forms(text):
        assert masked_text(given) == given
        assert masked_given_path(given, line=True, free_params=True) == given


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ('Bearer "s3cr3tvalue99"', 'Bearer "***"'),
        ("Bearer 's3cr3tvalue99'", "Bearer '***'"),
        ('Bearer \\"s3cr3tvalue99\\"', 'Bearer \\"***\\"'),
        ('Basic "dXNlcjpwYXNz"', 'Basic "***"'),
        ("Authorization: Bearer 'hunter2Xabc'", "Authorization: Bearer '***'"),
        ('Authorization: Bearer "hunter2Xabc"', 'Authorization: Bearer "***"'),
        ('Authorization: Bearer \\"hunter2Xabc\\"', 'Authorization: Bearer \\"***\\"'),
        ('Authorization: Negotiate "s3cr3tvalue99"', 'Authorization: Negotiate "***"'),
    ],
    ids=[
        *("double", "single", "json", "basic"),
        *("header-single", "header-double", "header-json", "header-negotiate"),
    ],
)
def test_a_quoted_credential_after_a_scheme(text: str, shown: str) -> None:
    """A quote between a scheme's separators and its credential, also
    escaped, is kept, and so is the closing quote; the credential is
    masked, raw and escaped once (masking it again changes nothing)."""
    secret = text.split()[-1].strip("\\\"'")
    for given, expected in zip(_forms(text)[:2], _forms(shown)[:2], strict=True):
        masked = masked_text(given)
        assert secret not in masked and masked == expected
        assert masked_text(masked) == masked


@pytest.mark.parametrize(
    "text",
    [
        'Bearer "token"',
        'the "Bearer" scheme',
        "use 'Bearer' tokens",
        "Basic 'auth'",
        'Bearer "access_token"',
        "Bearer 'Authorization'",
        'Bearer "',
    ],
    ids=["token", "quoted-scheme", "single-quoted", "basic", "word", "name", "bare"],
)
def test_quoted_prose_after_a_scheme_word_is_kept(text: str) -> None:
    """A quoted prose word after a scheme word alone, or a quoted scheme
    word, is printed as written, as the same word unquoted is."""
    for given in _forms(text):
        assert masked_text(given) == given


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (
            "Authorization: sk-live-abcdefgh12345678\nHTTP 401 Unauthorized",
            "Authorization: ***\nHTTP 401 Unauthorized",
        ),
        (
            "Authorization: sk-live-abcdefgh12345678\r\naccept */*",
            "Authorization: ***\r\naccept */*",
        ),
        (
            "Proxy-Authorization: sk-live-abcdefgh12345678\nmore",
            "Proxy-Authorization: ***\nmore",
        ),
    ],
    ids=["lf", "crlf", "proxy"],
)
def test_a_credential_with_no_scheme_before_a_line_break(text: str, shown: str) -> None:
    """A header's one-word credential with no scheme is judged alone when a
    line break follows it: the next line's word is not its run, raw and
    escaped once or twice."""
    for given, expected in zip(_forms(text), _forms(shown), strict=True):
        masked = masked_text(given)
        assert "abcdefgh12345678" not in masked and "sk-live" not in masked
        assert masked == expected


#: A fake credential, built at run time.
_SECRET = "hunter2" + "Qz9pW7xK"


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ({"Authorization": f"Bearer {_SECRET}"}, '{"Authorization": "Bearer ***"}'),
        ({"X-Api-Key": _SECRET}, '{"X-Api-Key": "***"}'),
        ({"Cookie": f"sid={_SECRET}"}, '{"Cookie": "sid=***"}'),
    ],
    ids=["bearer", "secret-header", "cookie"],
)
def test_a_header_in_json_escaped_twice(value: dict[str, str], shown: str) -> None:
    """A header quoted in JSON written as a JSON string twice (three
    backslashes before each quote) is masked as the plain JSON is."""
    text = json.dumps(json.dumps(json.dumps(value)))
    masked = masked_text(text)
    assert _SECRET not in masked and "hunter2" not in masked
    assert masked == json.dumps(json.dumps(shown))


#: A fake credential no prose rule masks alone (no upper case, no token
#: shape): only the header rule hides it.
_PLAIN = "abcdefgh" + "12"


@pytest.mark.parametrize(
    "brk",
    ["\x1c", "\x1d", "\x1e", "\u2029", "\\x1c", "\\x1d", "\\x1e", "\\x0B"],
    ids=["fs", "gs", "rs", "u2029", "esc-fs", "esc-gs", "esc-rs", "esc-vt-upper"],
)
def test_a_rarer_line_break_after_the_scheme(brk: str) -> None:
    """Each line break :meth:`str.splitlines` reads, raw or escaped (hex in
    either case), separates a header's scheme from its credential."""
    masked = masked_text(f"Authorization: Bearer{brk}{_PLAIN}")
    assert _PLAIN not in masked
    assert masked == f"Authorization: Bearer{brk}***"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("use Bearer \x1b[1mAbC9xYz2kQ7mN", "use Bearer \x1b[1m***"),
        (
            '{\\\\\\"Authorization\\\\\\": \\\\\\"Bearer ' + _PLAIN + '\\\\\\"}',
            '{\\\\\\"Authorization\\\\\\": \\\\\\"Bearer ***\\\\\\"}',
        ),
        (
            f'[("Authorization", "Bearer {_PLAIN}")]',
            '[("Authorization", "Bearer ***")]',
        ),
        # No quote after the ",": no pair, as without the quoted name.
        (f'the "Authorization", Bearer {_PLAIN}', None),
        ('the "Authorization", Bearer tokens', None),
    ],
    ids=["csi-after-word", "json-escaped-thrice", "pair", "prose-key", "prose"],
)
def test_scheme_and_header_shapes(text: str, shown: str | None) -> None:
    """An ANSI sequence after a scheme word, a header in JSON with three
    backslashes before each quote, and a ``(name, value)`` pair: the
    credential masked; a quoted name, ``,`` and an unquoted word is prose."""
    masked = masked_text(text)
    assert masked == (shown or text)
    if shown is not None:
        assert "AbC9" not in masked and _PLAIN not in masked
