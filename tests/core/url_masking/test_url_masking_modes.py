# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The two readings of a URL's credentials: a URL field (the text is one URL,
read as ``urllib`` reads it, by the detector and the Git split) and a line
(a URL inside prose, read by the masker), and the cases that told them
apart.

See also: test_url_masking_userinfo.py (the user information rule),
test_url_masking_urls.py (the URL scanner) and
test_url_masking_differential.py (the deciders against each other), all in
this folder.
"""

from __future__ import annotations

import time

import pytest

from pitloom.core.iri import NAMESPACE_CREDENTIALS
from pitloom.core.url_masking import (
    find_url_credentials,
    holds_url_credentials,
    masked_given_path,
    sanitize_url_credentials,
    split_userinfo,
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
    """A ``:`` and an ``@`` in a sentence are no user information for the
    masker of a line, and a sentence is no value the detector reads."""
    assert masked_given_path(text, line=True) == text
    assert sanitize_url_credentials(text) == text
    assert not find_url_credentials(text)


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
    assert holds_url_credentials(url)
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
    query holds is not user information, for the refusal and the Git split
    alike."""
    split = split_userinfo(url)
    assert (split[0] if split else None) == plain
    assert holds_url_credentials(url) is (plain is not None)


def test_the_masker_reads_an_empty_port_as_the_start_of_a_password() -> None:
    """Hiding too much is safe: the masker hides ``u:?PW@h``, as a host and
    its query cannot be told from it."""
    assert "PW" not in masked_given_path("https://u:?PW@h/r")
    assert userinfo_end("https://u:?PW@h/r", 8, 15, widest=True) == 13


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
    ``https://u:p@h``: the masker and the refusal find the password."""
    assert "BSSEC" not in masked_given_path(f"see {url} ok", line=True)
    assert holds_url_credentials(url)


def test_a_path_is_not_read_as_a_url_after_one_separator() -> None:
    """A path segment ``T10:`` and a drive are no scheme; another scheme at
    the start of a value is one (``backup:/u:p@h``)."""
    for text in ("/x/T10:/a@b", "C:\\Users\\u@h\\x"):
        assert not holds_url_credentials(text)
    assert holds_url_credentials("backup:/u:p@h/x")


@pytest.mark.parametrize(
    "text",
    [
        "user:S3CRET@h.example:o/r",
        "alice:S3CRET@host:/srv/r",
    ],
)
def test_an_address_with_a_password_is_refused_and_shown_masked(text: str) -> None:
    shown = "***:***@" + text.partition("@")[2]
    assert [(f.kind, f.shown) for f in find_url_credentials(text)] == [("scp", shown)]


@pytest.mark.parametrize(
    "url",
    [
        "https://h/x?q=1?token=PWQ2",
        "https://h/x?token=a?b&z=1",
        "https://h/x#a=1?sig=S&b=2",
    ],
    ids=["second-question", "question-in-secret", "fragment"],
)
def test_a_secret_after_a_second_question_mark_is_a_parameter(url: str) -> None:
    """A ``?`` in a query is a character of it, but a name after one is read
    as a parameter; the masker and the refusal both see it."""
    assert holds_url_credentials(url)
    assert "PWQ2" not in masked_given_path(url) and "?sig=S" not in masked_given_path(
        url
    )
    assert sanitize_url_credentials(url) != url


def test_the_masker_never_leaks_a_password_that_hides_behind_a_quote() -> None:
    """``https://u:"@SECRET?x@h``: the ``@`` after the quote is the user
    information's, the masker hides all of it."""
    assert "SECRET" not in sanitize_url_credentials('https://u:"@SECRET?x@h')
    assert "SECRET" not in masked_given_path('https://u:"@SECRET?x@h')


def test_the_given_path_masker_reads_a_parameter_after_a_second_question_mark() -> None:
    assert WHOLE_PARAM_RE.sub(mask_param, "?a=b?token=T&c=1") == "?a=b?token=***&c=1"


_DEEP = "ftp://u:S3CRET@h.invalid/x?" + "q=1?" * 1000 + "token=T0KEN"


def test_a_query_with_a_thousand_question_marks_is_read_without_nesting() -> None:
    """Nested reading is bounded: a value with more ``?`` than the limit is a
    secret, so no entry point raises ``RecursionError`` and no secret stays."""
    started = time.perf_counter()
    assert holds_url_credentials(_DEEP)
    shown = masked_given_path(_DEEP) + masked_text(_DEEP)
    assert "S3CRET" not in shown and "T0KEN" not in shown
    holds_url_credentials("https://h/?r=" * 1000)
    assert time.perf_counter() - started < 5


def test_the_log_text_of_a_failing_masker_is_a_fixed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> str:
        raise RecursionError

    monkeypatch.setattr("pitloom.log_masking.masked_given_path", fail)
    assert masked_text(_DEEP) == UNSHOWN_MESSAGE


@pytest.mark.parametrize(
    "url",
    [
        "https://h/x?code=1?token=T0KEN",
        "https://h/x?ticket=1?api_key=T0KEN",
        "https://h/x?otp=1?secret=T0KEN",
        "https://h/x?primary-key=1?password=T0KEN",
        "https://h/x?q=1?code=1?token=T0KEN",
    ],
    ids=["code", "ticket", "otp", "primary-key", "two-levels"],
)
def test_a_secret_nested_after_a_weak_value_is_refused(url: str) -> None:
    """A weak name's value is read inside: the refusal and the masker find
    the same secret."""
    assert "T0KEN" not in masked_given_path(url)
    assert holds_url_credentials(url)


def test_a_query_nested_too_deeply_is_refused_and_the_message_says_so() -> None:
    """The finding and the message name the nesting, not only a
    credential."""
    url = "https://h/x?q=a" + "?a" * 17 + "b"
    assert [f.kind for f in find_url_credentials(url)] == ["nesting"]
    assert NAMESPACE_CREDENTIALS.endswith("nested or encoded too deeply to read")
