# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.core.url_masking.masked_given_path`: a URL given
as a path (``Path`` collapses its ``//``), or named in a message line, is
written without its credentials and otherwise as given.

See also: test_url_masking_query.py (credentials in a URL),
test_url_masking_given_path.py (a URL given as a path or in a line) and
test_url_masking_checkout.py (the temporary directories), all in this
folder.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

import pytest

from pitloom.core.url_masking import masked_given_path
from pitloom.core.url_masking._scan import masked_once


@pytest.mark.parametrize(
    ("given", "shown"),
    [
        ("https:/user:SECRET@h/x", "https:/***:***@h/x"),
        ("https:/h/x?token=SECRET", "https:/h/x?token=***"),
        (
            "/cwd/https:/h/x?a=1&access_token=SECRET",
            "/cwd/https:/h/x?a=1&access_token=***",
        ),
        ("https:/h/x#access_token=SECRET", "https:/h/x#access_token=***"),
        ("https:\\\\h\\x?token=SECRET", "https:\\\\h\\x?token=***"),
        (r"D:\a\https:\u:SECRET@h\x", r"D:\a\https:\***:***@h\x"),
        (
            "ftp:/u:SECRET@h/x-1-py3-none-any.whl",
            "ftp:/***:***@h/x-1-py3-none-any.whl",
        ),
        ("git+https:/h/r?private_token=SECRET", "git+https:/h/r?private_token=***"),
        ("ssh:/u:SECRET@h/r", "ssh:/***:***@h/r"),
        ("HTTPS:/u:SECRET@h/x?token=SECRET", "HTTPS:/***:***@h/x?token=***"),
        ("https://u:SECRET@h/x", "https://***:***@h/x"),
        ("backup://u@h/x", "backup://***:***@h/x"),
        ("backup:\\\\u@h\\x", "backup:\\\\***:***@h\\x"),
        # Nothing to mask: the text as given, separators and all.
        ("https:/h/x?q=1", "https:/h/x?q=1"),
        (r"https:\h\x", r"https:\h\x"),
        (r"C:\dir\x?token=SECRET", r"C:\dir\x?token=SECRET"),
        ("a:/x?token=SECRET", "a:/x?token=SECRET"),
        ("dir/x.whl", "dir/x.whl"),
        # One separator after a path separator, a scheme no URL uses: a
        # path segment, its @ kept; with nothing before it, a collapsed URL.
        ("/x/T10:/a@b", "/x/T10:/a@b"),
        ("backup:/u@h/x", "backup:/***:***@h/x"),
        (r"D:\x\T10:\a@b", r"D:\x\T10:\a@b"),
        # A scheme a URL uses, after a path separator too (its last + part).
        ("/cwd/git+https:/u:S@h/x", "/cwd/git+https:/***:***@h/x"),
        ("/cwd/svn+ssh:/u:S@h/x", "/cwd/svn+ssh:/***:***@h/x"),
        # The userinfo: to the last @ before the next /, never empty.
        ("https://u:p@ss@h/x", "https://***:***@h/x"),
        ("https://u:p@ss:w@h/x", "https://***:***@h/x"),
        ("https://u:S@h/p@q", "https://***:***@h/p@q"),
        ("https://@h/x", "https://@h/x"),
        ("https://:S@h", "https://***:***@h"),
        ("https://u:p?pass@h/x", "https://***:***@h/x"),
        # An @ in a secret value ends a userinfo: the rest of the value is
        # masked too (RFC 3986 reads ``x@h/x`` as the token's).
        ("https://u:p?token=x@h/x", "https://***:***@***"),
        ("https:/h?apiKey=@=SECRET&a=1", "https:/***:***@***&a=1"),
        ("'https:\\u@h\\p?a=1&key=@=SECRET' x", "'https:\\***:***@***' x"),
        # Each URL of a path; a value holding what reads as a URL is one.
        ("/a/https:/u:A@h/x/ftp:/v:B@h/y", "/a/https:/***:***@h/x/ftp:/***:***@h/y"),
        ("https://h/?token=SE:/CRET&a=1", "https://h/?token=***&a=1"),
        (
            "https://h/?r=https://v:B@h2&token=X",
            "https://h/?r=https://***:***@h2&token=***",
        ),
        # A value runs over a space or a line break, to a delimiter or quote.
        ("https:/h/x?token=SEC RET&a=1", "https:/h/x?token=***&a=1"),
        ("https:/h/x?token=SEC\nRET", "https:/h/x?token=***"),
        # A digit before the scheme is not part of it.
        ("1https://u:SECRET@h", "1https://***:***@h"),
        # After ``://`` a backslash is the password's; after ``:\`` it may
        # be, so the userinfo runs to the last ``@``.
        ("https://u:SEC\\RET@h/", "https://***:***@h/"),
        ("https:\\u:SEC\\RET@h\\x", "https:\\***:***@h\\x"),
        ("https:\\h\\p@q", "https:\\***:***@q"),
        # A quote is a character of the userinfo (RFC 3986 allows ``'``).
        ("'https://u:Zq'A@h/x'", "'https://***:***@h/x'"),
        ("'https://u:p'@h'", "'https://***:***@h'"),
        ("ftp://u:Zq'A\"B@h/x.json", "ftp://***:***@h/x.json"),
        # Each URL of a message, each to the quote closing it.
        (
            "'https://h/?token=SECRET' and \"ftp:/u:SECRET@h\" 'ab:/x'",
            "'https://h/?token=***' and \"ftp:/***:***@h\" 'ab:/x'",
        ),
        ("'https:/u:SECRET@h", "'https:/***:***@h"),
        # A quote in a secret value does not end it (RFC 3986 allows one);
        # a quote closes a URL only before white space, punctuation or the end.
        ("x https://h/p?token=Zq'V&a=1 y", "x https://h/p?token=***&a=1 y"),
        ("x 'https://h/p?token=Zq'V' y", "x 'https://h/p?token=***' y"),
        ('"https://h/p?token=Zq\'V&a=1" y', '"https://h/p?token=***&a=1" y'),
        ("'https://h/p?token=Zq'.V' y", "'https://h/p?token=***' y"),
        # A closing quote after an even run of backslashes is not escaped.
        ("'https://h/p?token=SEC\\\\' and 'x y'", "'https://h/p?token=***' and 'x y'"),
        # A / in a secret value does not end a userinfo: masking the value
        # would uncover one.
        (
            "'https:/#sig=/'@#sig=/'@#sig=/'@#sig=/'@&token=ZqS",
            "'https:/***:***@&token=***",
        ),
        ("https:\\h?token=a/b&u@h2", "https:\\***:***@h2"),
    ],
    ids=[
        "userinfo",
        "query-token",
        "access-token-after-amp",
        "fragment-token",
        "windows-backslashes",
        "windows-under-a-drive",
        "ftp",
        "git-plus-https",
        "ssh",
        "upper-case-scheme",
        "two-slashes",
        "two-slashes-any-scheme",
        "two-backslashes-any-scheme",
        "nothing-to-mask",
        "nothing-to-mask-windows",
        "windows-drive-is-no-scheme",
        "one-letter-is-no-scheme",
        "plain-path",
        "path-segment-with-colon",
        "unknown-scheme-one-slash",
        "unknown-scheme-one-backslash",
        "plus-scheme-in-a-path",
        "svn-ssh-in-a-path",
        "at-in-password",
        "at-and-colon-in-password",
        "at-in-path",
        "empty-userinfo",
        "empty-user",
        "question-mark-in-password",
        "query-in-password",
        "at-in-secret-value",
        "at-in-quoted-secret-value",
        "two-urls-in-a-path",
        "url-in-a-secret-value",
        "url-in-a-value",
        "value-over-a-space",
        "value-over-a-newline",
        "digit-before-scheme",
        "backslash-in-password",
        "windows-backslash-in-password",
        "windows-at-in-path",
        "quote-in-password",
        "quote-ends-password",
        "both-quotes-in-password",
        "two-quoted-urls",
        "unclosed-quote",
        "quote-in-value",
        "quote-in-quoted-value",
        "other-quote-in-value",
        "quote-dot-in-value",
        "even-backslashes",
        "slash-in-value-chain",
        "slash-in-value",
    ],
)
def test_a_url_given_as_a_path_is_masked(given: str, shown: str) -> None:
    """``Path`` collapses ``//`` to ``/`` (and Windows writes ``\\``): the
    secret spans are replaced and every other character is kept as given.
    After one separator a scheme has a userinfo unless a path separator
    comes before it (a scheme a URL uses has one there too); any scheme of
    two or more characters has a query; a drive letter is not a scheme.
    Masking a masked text changes nothing."""
    assert masked_given_path(given) == shown
    assert masked_given_path(shown) == shown
    assert masked_given_path(shown, line=True) == shown


@pytest.mark.parametrize(
    ("given", "shown"),
    [
        (
            "URL=https://h/m?token=S: a model; use x",
            "URL=https://h/m?token=***: a model; use x",
        ),
        (
            "FILE=https://h/x?access_token=S [code]",
            "FILE=https://h/x?access_token=*** [code]",
        ),
        (
            "U=https://h/x?X-Amz-Signature=S, then",
            "U=https://h/x?X-Amz-Signature=***, then",
        ),
        ("U=https://u:S@h/x: cond; act", "U=https://***:***@h/x: cond; act"),
        ("U=https:/u:S@h/x?token=S. act", "U=https:/***:***@h/x?token=***. act"),
        ("U=https://h/x?token=SEC RET", "U=https://h/x?token=*** RET"),
        ("U=https://h/x?token=:: cond", "U=https://h/x?token=***:: cond"),
        ("'https://h/x?token=SEC RET' (choose", "'https://h/x?token=***' (choose"),
        (
            "unrecognized arguments: https://u:A@h/a https://v:B@h/b",
            "unrecognized arguments: https://***:***@h/a https://***:***@h/b",
        ),
        (
            "a https://u:A@h/a b https://v:B@h/b c ftp://w:C@h",
            "a https://***:***@h/a b https://***:***@h/b c ftp://***:***@h",
        ),
        (
            "https://u:A@h/a\nhttps://v:B@h/b",
            "https://***:***@h/a\nhttps://***:***@h/b",
        ),
        (
            "x 'https://h/a?token=X' https://v:B@h/b",
            "x 'https://h/a?token=***' https://***:***@h/b",
        ),
        ("https://h/a,https://v:B@h/b", "https://h/a,https://***:***@h/b"),
        ("x https://h/?token=ab:/cd next", "x https://h/?token=*** next"),
        ("U=https://h/x: see ?token=a", "U=https://h/x: see ?token=a"),
        (
            "x https:\\u:A@h\\x https:\\v:B@h\\y",
            "x https:\\***:***@h\\x https:\\***:***@h\\y",
        ),
        # A quote in the password does not end it, quoted or escaped.
        (
            "FILE='https://u:Zq'A@h/x.json': not found",
            "FILE='https://***:***@h/x.json': not found",
        ),
        (
            "invalid choice: 'ftp://u:Zq\\'A\"B@h/x.json' (choose from 'a')",
            "invalid choice: 'ftp://***:***@h/x.json' (choose from 'a')",
        ),
        (
            "invalid choice: 'https:/u:SECRET@h' (choose from 'a@b', 'c')",
            "invalid choice: 'https:/***:***@h' (choose from 'a@b', 'c')",
        ),
        ("'https://h/a\\'b?token=SEC' (choose", "'https://h/a\\'b?token=***' (choose"),
        # White space ends a userinfo: an address after a URL is kept.
        (
            "CI run https://ci.example.org, contact ops@example.com",
            "CI run https://ci.example.org, contact ops@example.com",
        ),
        (
            "URL=https://pypi.org: unreachable; contact admin@example.com",
            "URL=https://pypi.org: unreachable; contact admin@example.com",
        ),
        ("https://u:A@h/a, mail ops@x.com", "https://***:***@h/a, mail ops@x.com"),
        ("https://h\tops@x.com", "https://h\tops@x.com"),
        ("https://h\nops@x.com", "https://h\nops@x.com"),
        # A quote inside a secret value, quoted or not.
        ("x https://h/p?token=Zq'V y", "x https://h/p?token=*** y"),
        ("x 'https://h/p?token=Zq'V' y", "x 'https://h/p?token=***' y"),
        ('x "https://h/p?token=Zq"V&a=1" y', 'x "https://h/p?token=***&a=1" y'),
        ("'https://h?token=S' (from 'a@b')", "'https://h?token=***' (from 'a@b')"),
        ("'https://h/p?token=S', 'x y'", "'https://h/p?token=***', 'x y'"),
        ("https://h&x=1&token=S ops@x.com", "https://h&x=1&token=*** ops@x.com"),
        # White space in a quoted secret value does not end a userinfo.
        ("'https:/h?token=a b/c'@?token=a b/c'@&x", "'https:/***:***@&x"),
    ],
    ids=[
        "token-colon",
        "access-token-code",
        "amz-signature-comma",
        "userinfo",
        "collapsed-userinfo",
        "value-stops-at-space",
        "value-only-punctuation",
        "quoted-runs-to-quote",
        "two-urls",
        "three-urls",
        "newline-between",
        "quoted-then-unquoted",
        "comma-between",
        "url-in-a-secret-value",
        "text-after-the-url",
        "windows-two-urls",
        "quote-in-password",
        "escaped-quote-in-password",
        "quoted-then-a-quoted-address",
        "escaped-quote-in-path",
        "address-after-comma",
        "address-after-colon",
        "address-after-userinfo",
        "address-after-tab",
        "address-after-newline",
        "quote-in-value",
        "quote-in-quoted-value",
        "same-quote-in-value",
        "quoted-then-an-address",
        "quote-then-comma",
        "address-after-a-secret-value",
        "space-in-quoted-value-chain",
    ],
)
def test_a_url_in_a_line_keeps_the_line(given: str, shown: str) -> None:
    """In a line a URL not quoted is followed by the condition: it ends at
    white space after its userinfo, a secret value at white space with the
    punctuation ending a sentence kept, and each URL of the line is masked;
    a quoted URL runs to its quote, one a backslash escapes skipped. A
    userinfo ends at white space, never at a quote. Masking the line again
    changes nothing."""
    assert masked_given_path(given, line=True) == shown
    assert masked_given_path(shown, line=True) == shown


@pytest.mark.parametrize(
    ("given", "line", "shown"),
    [
        ("'https:/#sig=/'@#sig=/'@&token=ZqS", False, "'https:/***:***@&token=***"),
        ("'https:/#sig=/'@#sig=/'@&token=ZqS", True, "'https:/***:***@&token=***"),
        ("https:\\h&token=a?b=c/d&u@h2", False, "https:\\***:***@h2"),
        ("https:\\h?token=/b&u@h2", False, "https:\\***:***@h2"),
        ("'https:/h?token=a b/c'@?token=a b/c'@&x", True, "'https:/***:***@&x"),
        ("https://u:p?token=x@h/x", False, "https://***:***@***"),
    ],
    ids=["slash-chain", "slash-chain-line", "question-mark-head", "slash-first"]
    + ["space-chain", "at-in-value"],
)
def test_one_pass_masks_a_value_that_hides_a_userinfo_end(
    given: str, line: bool, shown: str
) -> None:
    """A ``/`` or white space in a secret value does not end a user
    information, so one pass finds the whole of it: a second pass, which
    no longer sees the value, changes nothing."""
    assert masked_once(given, line=line) == shown
    assert masked_once(shown, line=line) == shown


@pytest.mark.parametrize(
    "scheme",
    [
        *("ldap", "ldaps", "rsync", "file", "s3a", "az", "hdfs", "abfss"),
        *("ws", "wss", "svn+ssh", "git+https", "smb", "custom", "x-y.z"),
    ],
)
@pytest.mark.parametrize(
    ("template", "line"),
    [
        ("{s}:/u:SECRET@h/x", False),
        ("project path not found: '{s}:/u:SECRET@h/x' [code]", True),
        ("wheel file not found: {s}:/u:SECRET@h/x.whl", True),
        ("{s}:\\u:SECRET@h\\x", False),
    ],
    ids=["path", "quoted-line", "line", "windows"],
)
def test_any_scheme_after_one_separator_is_masked(
    scheme: str, template: str, line: bool
) -> None:
    """A URL whose ``//`` a path collapsed, of any scheme: its user
    information is masked."""
    shown = masked_given_path(template.format(s=scheme), line=line)
    assert "SECRET" not in shown and "***:***@h" in shown


@pytest.mark.parametrize("make", [Path, PureWindowsPath], ids=["native", "windows"])
def test_a_url_through_a_path_is_masked(
    make: type[Path] | type[PureWindowsPath],
) -> None:
    """What argparse's ``Path`` makes of a URL is masked on every platform."""
    given = str(make("https://h/x?token=SECRET&f=x-1-py3-none-any.whl"))
    assert "//" not in given
    assert "SECRET" not in masked_given_path(given)


#: Each adversarial text, of about *n* characters.
_ADVERSARIAL: dict[str, Callable[[int], str]] = {
    "long-query": lambda n: "https://" + "a" * n + "?" + "x=1&" * (n // 4),
    "long-camel-name": lambda n: "https://h/?" + "aB" * (n // 2) + "=1",
    "windows-ats": lambda n: "https:\\" + "@\\" * (n // 3),
    "long-name": lambda n: "https:/" + "?" + "a" * n,
    "many-urls": lambda n: "'ab:/=" * (n // 6),
    "scheme-run": lambda n: "a1" * (n // 2),
    "glued-urls": lambda n: "https://" * (n // 8),
    "windows-no-at": lambda n: "ab:\\a " * (n // 6),
    "windows-no-slash": lambda n: "ab:\\a" * (n // 5) + " @",
    "url-in-values": lambda n: "https://h/?token=ab:/" * (n // 20),
    "one-at-at-the-end": lambda n: "ab:/" * (n // 4) + "@",
    "escaped-quotes": lambda n: "'ab:/\\'" * (n // 7),
    "values-over-slashes": lambda n: "https:\\h" + "?token=a/b&c@d" * (n // 14),
    "secret-slash-chain": lambda n: "'https:/" + "#sig=/'@" * (n // 8),
    "secret-space-chain": lambda n: "'hx:/" + "&token= '@" * (n // 10),
    "skipped-stops": lambda n: "ab:/?a=?token=" * (n // 14) + "&/x@",
    "quote-tails": lambda n: "'ab:/" + "x'." * (n // 3),
}


def _best_time(text: str, line: bool) -> float:
    """The shortest of three runs of the masker on *text*."""
    times = []
    for _ in range(3):
        started = time.perf_counter()
        masked_given_path(text, line=line)
        times.append(time.perf_counter() - started)
    return min(times)


@pytest.mark.parametrize("line", [False, True], ids=["path", "line"])
@pytest.mark.parametrize("shape", sorted(_ADVERSARIAL))
def test_a_given_path_is_masked_in_linear_time(shape: str, line: bool) -> None:
    """Masking an adversarial text five times as long takes about five times
    as long (a quadratic masker: twenty-five). The ratio, not a wall-clock
    bound, so a slow or loaded runner, or coverage tracing, cancels out;
    each time is the best of three, and a run under 5 ms counts as 5 ms."""
    make = _ADVERSARIAL[shape]
    short = max(_best_time(make(100_000), line), 0.005)
    long = _best_time(make(500_000), line)
    assert long / short < 12
