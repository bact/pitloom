# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the SBOM strip (:func:`pitloom.core.url_masking.
strip_url_secrets`): where a URL in free text ends, a URL inside another,
the secret parameter names, what is kept and what a message shows.

See also: test_url_masking_userinfo.py (the user information rule),
test_url_masking_differential.py (the deciders against each other) and
test_url_masking_query.py (the masking of a parameter), all in this folder.
"""

from __future__ import annotations

import time

import pytest

from pitloom.core.url_masking import (
    holds_url_credentials,
    is_secret_name,
    keeps_url_credential,
    keeps_weak_parameter,
    masked_given_path,
    sanitize_url_credentials,
    strip_url_secrets,
)


@pytest.mark.parametrize(
    ("text", "plain", "shown"),
    [
        (
            "(see https://h/x?token=T) more",
            "(see https://h/x) more",
            "https://h/x?token=***",
        ),
        ("'https://h/x?token=T'.", "'https://h/x'.", "https://h/x?token=***"),
        ("at https://u:p@h/x, ok", "at https://h/x, ok", "https://***:***@h/x"),
        ("https://h/w_(x)?token=T", "https://h/w_(x)", "https://h/w_(x)?token=***"),
        ("https://h/x?token=T&&a=1", "https://h/x?a=1", "https://h/x?token=***&&a=1"),
        ("https://h/x?token=T;a=1", "https://h/x?a=1", "https://h/x?token=***;a=1"),
        ("https://h/x?token=T#f", "https://h/x#f", "https://h/x?token=***#f"),
        ("https://h/x?&token=T", "https://h/x?", None),
        (
            "https://h/x?redirect=https://u:PW@evil/y",
            "https://h/x?redirect=https://evil/y",
            "https://***:***@evil/y",
        ),
        (
            "https://h/x?a=https://h2/?token=T&b=1",
            "https://h/x?a=https://h2/?b=1",
            "https://h2/?token=***&b=1",
        ),
        ("https://h/x?token=ab:/cd&a=1", "https://h/x?a=1", None),
        ("Mirror at 1.https://u:S@h/x", "Mirror at 1.https://h/x", None),
        ("x.https://u:S@h/x", "x.https://h/x", None),
        ("https://h?x=123://&token=T", "https://h?x=123://", None),
        ("https://u:#P@h?token=a@b&c=1", "https://h?c=1", None),
        ("https://u:p?token=x@h&a=2", "https://&a=2", "https://***:***@***&a=2"),
        (
            "see https://h/x?token=https://evil/y?a=1 end",
            "see https://h/x end",
            "https://h/x?token=***",
        ),
        ("https://u:#P@h" + "?token=a@h" * 9 + "&c=1", "https://&c=1", None),
    ],
    ids=[
        "parenthesis",
        "quote-and-full-stop",
        "comma",
        "own-parenthesis",
        "double-ampersand",
        "semicolon",
        "fragment",
        "empty-first",
        "nested-userinfo",
        "nested-query",
        "url-in-secret-value",
        "digit-before-scheme",
        "dot-before-scheme",
        "digit-scheme",
        "at-in-secret-value",
        "only-at-in-secret-value",
        "url-inside-secret-value",
        "many-secret-values-before-at",
    ],
)
def test_a_url_in_free_text_keeps_what_is_around_it(
    text: str, plain: str, shown: str | None
) -> None:
    """Punctuation after a URL and a bracket it does not open are the
    text's; a URL in a parameter value is read on its own; a removed
    ``?`` parameter hands its ``?`` to the next one. The URL a message shows
    ends where the URL ends."""
    stripped, changed = strip_url_secrets(text)
    assert stripped == plain
    if shown is not None:
        assert changed == [shown]
    assert strip_url_secrets(stripped) == (stripped, [])


_REMOVED = [
    *("access_token[]", "token[0]", "secret[key]", "api_key%5B%5D", "user[password]"),
    *("session_id", "sessionid", "jsessionid", "PHPSESSID", "bearer", "passphrase"),
    *("privatekey", "passcode", "creds", "userpwd", "tokens", "token1", "password1"),
    *("token_", "token-v2", "token.value", "t%256Fken", "ssh_key", "api-key"),
    *("accesstoken", "db_passphrase", "SessionId"),
]
_KEPT = [
    *("monkey", "author", "keyword", "sort_key", "primary-key", "tokenizer"),
    *("max_tokens", "country_code", "state", "Policy", "oauth2", "keys[0]"),
]
_WEAK = ["code", "session", "ticket", "sid", "otp", "code1", "Session"]


@pytest.mark.parametrize("name", _REMOVED)
def test_a_secret_name_is_masked_and_removed(name: str) -> None:
    """The masker and the strip read one list of names: a name the strip
    removes, the masker masks."""
    url = f"https://h/x?{name}=S3CRET&a=1"
    assert strip_url_secrets(url)[0] == "https://h/x?a=1"
    assert "S3CRET" not in masked_given_path(url)
    assert "S3CRET" not in sanitize_url_credentials(url)
    assert holds_url_credentials(url)


@pytest.mark.parametrize("name", _KEPT + _WEAK)
def test_an_ordinary_or_weak_name_is_kept_in_an_sbom(name: str) -> None:
    url = f"https://h/x?{name}=V&a=1"
    assert strip_url_secrets(url) == (url, [])
    assert not holds_url_credentials(url)
    masked = name in _WEAK or name in ("sort_key", "primary-key")
    assert is_secret_name(name) is masked
    assert keeps_weak_parameter(url) is (name in _WEAK)


@pytest.mark.parametrize(
    ("url", "kept"),
    [
        ("https://u:p@h/x?code=WK", True),
        ("https://u:p@h/x?sort_key=V&primary-key=W", False),
        ("ssh://git@h/r?token=T", True),
        ("ssh://ghp_TOKEN@h/r", False),
        ("https://h/x?token=T", False),
    ],
    ids=["weak", "key-names", "account", "token-user", "removed"],
)
def test_a_kept_credential_is_told_apart(url: str, kept: bool) -> None:
    """A message says a credential is kept only when one is, and shows a
    kept value as the SBOM states it (never ``sort_key=***``)."""
    _, changed = strip_url_secrets(url)
    assert changed and keeps_url_credential(changed[0]) is kept
    assert keeps_url_credential(url) is kept
    assert "***" not in changed[0].partition("?")[2].replace("token=***", "")


def test_the_strip_is_linear() -> None:
    """An adversarial text of 40,000 characters is stripped in well under a
    second (a quadratic scan takes seconds)."""
    shapes = [
        "a://h?a=" * 5_000,
        "https://" + "u:p " * 10_000,
        "https://h?" + "token" * 8_000,
        "1" * 40_000 + "://",
        "x://" + "@" * 40_000,
        "https://h/" + ")" * 40_000,
        "a://?" * 8_000,
    ]
    started = time.perf_counter()
    for text in shapes:
        strip_url_secrets(text)
        holds_url_credentials(text)
    assert time.perf_counter() - started < 1
