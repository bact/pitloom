# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The two readings of a URL's credentials: a URL field (the text is one URL,
read as ``urllib`` reads it) and free text (a URL inside prose, read hard at
white space and a quote), and the cases that told them apart.

See also: test_url_masking_userinfo.py (the user information rule),
test_url_masking_strip.py (the strip of a text) and
test_url_masking_differential.py (the deciders against each other), all in
this folder.
"""

from __future__ import annotations

import time

import pytest

from pitloom.core.iri import NAMESPACE_CREDENTIALS
from pitloom.core.url_masking import (
    holds_url_credentials,
    is_whole_url,
    masked_given_path,
    sanitize_url_credentials,
    split_userinfo,
    strip_url_secrets,
    userinfo_end,
)
from pitloom.core.url_masking._params import WHOLE_PARAM_RE, mask_param
from pitloom.log_masking import UNSHOWN_MESSAGE, masked_text

_PROSE = [
    "Open http://localhost:<port> in a browser. Questions: dev@example.org",
    "Serve on http://host:port and report bugs to bugs@example.org",
    'Use "http://HOST:PORT" - author jane@example.org',
    "Run `uvicorn app:app --port 8000`; see http://localhost: then mail a@b.org",
    "See https://h/x for details (mail me@x.org)",
]


@pytest.mark.parametrize("text", _PROSE, ids=range(len(_PROSE)))
def test_prose_that_only_looks_like_a_url_with_user_information_is_kept(
    text: str,
) -> None:
    """A ``:`` and an ``@`` in a sentence are no user information: the text
    is byte-identical and nothing is said."""
    assert not is_whole_url(text)
    assert strip_url_secrets(text, whole=False) == (text, [])


@pytest.mark.parametrize(
    ("url", "userinfo"),
    [
        ("https://o'brien:PW@h.example/x", "o'brien:PW"),
        ("https://TOK'ENPW@h.example/x", "TOK'ENPW"),
        ('https://u:"PW@h/x', 'u:"PW'),
        ("https://u:<PW>@h/x", "u:<PW>"),
        ("https://a!b:$&(x)*+,;=%41\u00e9@h/x", "a!b:$&(x)*+,;=%41\u00e9"),
        ("https://u:`PW`@h/x", "u:`PW`"),
    ],
    ids=["apostrophe", "token", "double-quote", "angle", "sub-delims", "backtick"],
)
def test_a_url_field_reads_the_whole_rfc_3986_user_information(
    url: str, userinfo: str
) -> None:
    """A quote, an angle bracket or a backtick in the user information of a
    URL field is part of it, as ``urllib`` and git read it: every decider
    agrees and the password is gone from each."""
    plain = url.replace(userinfo + "@", "")
    assert is_whole_url(url)
    assert strip_url_secrets(url, whole=True)[0] == plain
    assert holds_url_credentials(url, whole=True)
    assert split_userinfo(url) == (plain, userinfo)
    assert "PW" not in masked_given_path(url)


@pytest.mark.parametrize(
    ("url", "plain"),
    [
        ("https://files.example:?mirror=eu@cdn.example/c.whl", None),
        ("https://h:?x=a@b", None),
        ("https://u:S3CRET@h:?x=a@b", "https://h:?x=a@b"),
        ("https://github.com:?@evil.example/o/r", None),
    ],
    ids=["mirror", "query", "after-password", "git-host"],
)
def test_an_empty_port_is_a_port(url: str, plain: str | None) -> None:
    """``host:`` before a ``?`` is a host and an empty port, and what the
    query holds is not user information, for the strip, the refusal and the
    Git split alike; stripping again changes nothing."""
    expected = url if plain is None else plain
    stripped = strip_url_secrets(url, whole=True)[0]
    assert stripped == expected
    assert strip_url_secrets(stripped, whole=True)[0] == stripped
    assert (split_userinfo(url) is not None) is (plain is not None)


def test_the_masker_reads_an_empty_port_as_the_start_of_a_password() -> None:
    """Hiding too much is safe: the masker hides ``u:?PW@h``, as a host and
    its query cannot be told from it."""
    assert "PW" not in masked_given_path("https://u:?PW@h/r")
    assert userinfo_end("https://u:?PW@h/r", 8, 15, free_text=False, widest=True) == 13


@pytest.mark.parametrize(
    "url",
    [
        "https:\\\\u:BSSEC@h/i.whl",
        "https:/u:BSSEC@h/x",
        "https:///u:BSSEC@h/x",
        "https:////u:BSSEC@h/x",
        "HTTPS:\\u:BSSEC@h/x",
        "wss:/u:BSSEC@h/x",
        "file:/u:BSSEC@h/x",
    ],
    ids=["backslashes", "one", "three", "four", "upper", "wss", "file"],
)
def test_a_special_scheme_with_other_separators_is_a_url(url: str) -> None:
    """A browser reads ``https:/u:p@h`` and ``https:\\\\u:p@h`` as
    ``https://u:p@h``: the strip and the refusal find the password."""
    assert "BSSEC" not in strip_url_secrets(url, whole=True)[0]
    assert "BSSEC" not in strip_url_secrets(f"see {url} ok", whole=False)[0]
    assert holds_url_credentials(url, whole=True)


def test_a_path_is_not_read_as_a_url_after_one_separator() -> None:
    """Only a special scheme, so ``T10:/a@b`` and a drive stay as written."""
    for text in ("/x/T10:/a@b", "C:\\Users\\u@h\\x", "backup:/u:p@h/x"):
        assert strip_url_secrets(text, whole=is_whole_url(text)) == (text, [])


@pytest.mark.parametrize(
    "text",
    [
        "user:S3CRET@h.example:o/r",
        "alice:S3CRET@host:/srv/r",
    ],
)
def test_an_address_with_a_password_loses_it(text: str) -> None:
    plain, changed = strip_url_secrets(text, whole=True)
    assert "S3CRET" not in plain and changed == [f"***:***@{plain}"]


@pytest.mark.parametrize(
    ("url", "plain", "shown"),
    [
        ("https://h/x?q=1?token=PWQ2", "https://h/x?q=1", "https://h/x?q=1?token=***"),
        (
            "https://h/x?token=a?b&z=1",
            "https://h/x?z=1",
            "https://h/x?token=***&z=1",
        ),
        ("https://h/x#a=1?sig=S&b=2", "https://h/x#a=1?b=2", None),
    ],
    ids=["second-question", "question-in-secret", "fragment"],
)
def test_a_secret_after_a_second_question_mark_is_a_parameter(
    url: str, plain: str, shown: str | None
) -> None:
    """A ``?`` in a query is a character of it, but a name after one is read
    as a parameter; the masker, the strip and the refusal all see it."""
    stripped, changed = strip_url_secrets(url, whole=True)
    assert stripped == plain
    if shown is not None:
        assert changed == [shown]
    assert holds_url_credentials(url, whole=True)
    assert "PWQ2" not in masked_given_path(url) and "?sig=S" not in masked_given_path(
        url
    )
    assert sanitize_url_credentials(url) != url


@pytest.mark.parametrize(
    ("url", "plain"),
    [
        ("https://h/x?&token=T&&a=1", "https://h/x?a=1"),
        ("https://h/x?a=1&token=T&", "https://h/x?a=1"),
        ("https://h/x?a=1&token=T&b=2", "https://h/x?a=1&b=2"),
        ("https://h/x?a=1&token=T&&b=2", "https://h/x?a=1&b=2"),
        ("https://h/x?token=T&sig=S&a=1", "https://h/x?a=1"),
        ("https://h/x#token=T&?sig=U&b=1", "https://h/x#b=1"),
        ("https://h/x?token=T#f", "https://h/x#f"),
    ],
    ids=["leading", "trailing", "middle", "doubled", "two", "fragment", "to-fragment"],
)
def test_a_removed_parameter_leaves_one_separator(url: str, plain: str) -> None:
    assert strip_url_secrets(url, whole=True)[0] == plain


def test_a_closing_backtick_is_not_part_of_the_url() -> None:
    assert strip_url_secrets("see `https://u:p@h/x?token=T`.", whole=False)[0] == (
        "see `https://h/x`."
    )


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("https://u:p@q@h?m=a@b.org", "https://h?m=a@b.org"),
        ("https://u:p@h:8080?m=a@b.org", "https://h:8080?m=a@b.org"),
        ("https://u:p@h/a@b/c", "https://h/a@b/c"),
        ("https://u:p@a,b;c.example/x", "https://a,b;c.example/x"),
        ("https://h/?token=https://u:p@g/x", "https://h/"),
        ("{https://u:p@h/x}", "{https://h/x}"),
        ("[https://u:p@h/x] (https://u:p@h/y)", "[https://h/x] (https://h/y)"),
        ("https://u:p@h/Foo_(bar)", "https://h/Foo_(bar)"),
        ("(https://u:p@h/Foo_(bar))", "(https://h/Foo_(bar))"),
    ],
)
def test_the_strip_keeps_the_host_and_the_brackets(text: str, plain: str) -> None:
    assert strip_url_secrets(text, whole=is_whole_url(text))[0] == plain


def test_the_masker_never_leaks_a_password_that_hides_behind_a_quote() -> None:
    """``https://u:"@SECRET?x@h``: the ``@`` after the quote is the user
    information's, the masker hides all of it."""
    assert "SECRET" not in sanitize_url_credentials('https://u:"@SECRET?x@h')
    assert "SECRET" not in masked_given_path('https://u:"@SECRET?x@h')


def test_a_url_seen_in_one_text_twice_is_two_changes_of_one_url() -> None:
    text = "https://u:p@h/x and https://u:p@h/x"
    plain, changed = strip_url_secrets(text, whole=False)
    assert plain == "https://h/x and https://h/x"
    assert changed == ["https://***:***@h/x"] * 2


def test_an_unknown_closing_bracket_is_safe() -> None:
    """Every bracket of a text is one the scanner knows, whatever the URL
    around it holds."""
    text = "{[(https://h/x?token=T)]} {{ }} }}} ((( https://u:p@h/y}"
    plain, changed = strip_url_secrets(text, whole=False)
    assert "token" not in plain and "u:p" not in plain and len(changed) == 2


def test_the_given_path_masker_reads_a_parameter_after_a_second_question_mark() -> None:
    assert WHOLE_PARAM_RE.sub(mask_param, "?a=b?token=T&c=1") == "?a=b?token=***&c=1"


_DEEP = "ftp://u:S3CRET@h.invalid/x?" + "q=1?" * 1000 + "token=T0KEN"


@pytest.mark.parametrize("whole", [True, False], ids=["field", "text"])
def test_a_query_with_a_thousand_question_marks_is_read_without_nesting(
    whole: bool,
) -> None:
    """Nested reading is bounded: a value with more ``?`` than the limit is a
    secret, so no entry point raises ``RecursionError`` and no secret stays."""
    started = time.perf_counter()
    stripped = strip_url_secrets(_DEEP, whole=whole)[0]
    assert "S3CRET" not in stripped and "T0KEN" not in stripped
    assert holds_url_credentials(_DEEP, whole=whole)
    shown = masked_given_path(_DEEP) + masked_text(_DEEP)
    assert "S3CRET" not in shown and "T0KEN" not in shown
    strip_url_secrets("https://h/?r=" * 1000, whole=whole)
    assert time.perf_counter() - started < 5


def test_the_log_text_of_a_failing_masker_is_a_fixed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> str:
        raise RecursionError

    monkeypatch.setattr("pitloom.log_masking.masked_given_path", fail)
    assert masked_text(_DEEP) == UNSHOWN_MESSAGE


@pytest.mark.parametrize(
    "text",
    ["meeting-10:30@room:notes.txt", "build:42@ci:linux", "a:1@b:c"],
)
def test_a_string_that_only_looks_like_an_address_is_not_rewritten(
    text: str,
) -> None:
    assert strip_url_secrets(text, whole=is_whole_url(text)) == (text, [])


@pytest.mark.parametrize(
    ("url", "plain"),
    [
        ("https://h/x?code=1?token=T0KEN", "https://h/x?code=1"),
        ("https://h/x?ticket=1?api_key=T0KEN", "https://h/x?ticket=1"),
        ("https://h/x?otp=1?secret=T0KEN", "https://h/x?otp=1"),
        ("https://h/x?primary-key=1?password=T0KEN", "https://h/x?primary-key=1"),
        ("https://h/x?q=1?code=1?token=T0KEN", "https://h/x?q=1?code=1"),
    ],
    ids=["code", "ticket", "otp", "primary-key", "two-levels"],
)
def test_a_secret_nested_after_a_weak_value_is_removed(url: str, plain: str) -> None:
    """The strip keeps a weak name's value, but still reads inside it; the
    masker hides the same secret."""
    assert strip_url_secrets(url, whole=True)[0] == plain
    assert "T0KEN" not in masked_given_path(url)
    assert holds_url_credentials(url, whole=True)


def test_a_query_nested_too_deeply_is_removed_and_the_message_says_so() -> None:
    """The warning names the nesting, not only a credential."""
    url = "https://h/x?q=a" + "?a" * 17 + "b"
    assert strip_url_secrets(url, whole=True)[0] == "https://h/x"
    assert NAMESPACE_CREDENTIALS.endswith("nested too deeply to read")
