# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the URL scanner of the detector
(:func:`pitloom.core.url_masking._urls.find_urls`): where each URL of a
value starts and ends, a URL inside another, its user information and the
secret parameter names the masker and the detector read alike.

See also: test_url_masking_userinfo.py (the user information rule),
test_url_masking_differential.py (the deciders against each other) and
test_url_masking_query.py (the masking of a parameter), all in this folder.
"""

from __future__ import annotations

import pytest

from pitloom.core.url_masking import (
    find_url_credentials,
    holds_url_credentials,
    is_secret_name,
    masked_given_path,
    sanitize_url_credentials,
)
from pitloom.core.url_masking._urls import find_urls

#: A URL as found: its text, its user information, whether that is an
#: account name, and each secret parameter (separator, name and value) with
#: whether it is refused (else its name is weak).
_Found = tuple[str, str | None, bool, list[tuple[str, bool]]]


def _found(text: str) -> list[_Found]:
    found: list[_Found] = []
    for url in find_urls(text):
        userinfo = None if url.userinfo is None else text[slice(*url.userinfo)]
        params = [(text[start:end], refused) for start, _, end, refused in url.params]
        found.append((text[url.start : url.end], userinfo, url.account, params))
    return found


_DEEP_AT = "https://u:p#P@h" + "?token=a@h" * 9 + "&c=1"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "https://h/w_(x)?token=T",
            [("https://h/w_(x)?token=T", None, False, [("?token=T", True)])],
        ),
        (
            "https://h/x?token=T;a=1",
            [("https://h/x?token=T;a=1", None, False, [("?token=T;a=1", True)])],
        ),
        (
            "https://h/x?&token=T",
            [("https://h/x?&token=T", None, False, [("&token=T", True)])],
        ),
        (
            "https://h/x?code=1&b=2",
            [("https://h/x?code=1&b=2", None, False, [("?code=1", False)])],
        ),
        (
            "https://h/x?redirect=https://u:PW@evil/y",
            [
                ("https://h/x?redirect=", None, False, []),
                ("https://u:PW@evil/y", "u:PW", False, []),
            ],
        ),
        (
            "https://h/x?a=https://h2/?token=T&b=1",
            [
                ("https://h/x?a=", None, False, []),
                ("https://h2/?token=T&b=1", None, False, [("?token=T", True)]),
            ],
        ),
        (
            "https://u:p@h/x see https://u:q@h2/y",
            [
                ("https://u:p@h/x see ", "u:p", False, []),
                ("https://u:q@h2/y", "u:q", False, []),
            ],
        ),
        ("1.https://u:S@h/x", [("https://u:S@h/x", "u:S", False, [])]),
        ("x.https://u:S@h/x", [("x.https://u:S@h/x", "u:S", False, [])]),
        (
            "https://h?x=123://&token=T",
            [("https://h?x=123://&token=T", None, False, [("&token=T", True)])],
        ),
        (
            "https://u:p#P@h?token=a@b&c=1",
            [("https://u:p#P@h?token=a@b&c=1", "u:p#P", False, [("?token=a@b", True)])],
        ),
        (
            "https://u:p?token=x@h&a=2",
            [("https://u:p?token=x@h&a=2", "u:p?token=x", False, [])],
        ),
        (
            "https://h/x?token=https://evil/y?a=1",
            [
                (
                    "https://h/x?token=https://evil/y?a=1",
                    None,
                    False,
                    [("?token=https://evil/y?a=1", True)],
                )
            ],
        ),
        (
            "https://h/x?token=ab:/cd&a=1",
            [("https://h/x?token=ab:/cd&a=1", None, False, [("?token=ab:/cd", True)])],
        ),
        (_DEEP_AT, [(_DEEP_AT, _DEEP_AT[8 : _DEEP_AT.rindex("@")], False, [])]),
        ("s3:/u:p@h/x", [("s3:/u:p@h/x", "u:p", False, [])]),
        ("/x/T10:/a@b", [("T10:/a@b", None, False, [])]),
        ("ssh://git@h/r", [("ssh://git@h/r", "git", True, [])]),
        # Adversarial: an ``@`` in a secret value that starts the authority,
        # after an empty user, after ``;``, or after ``&`` in the value.
        ("https://&token=x@h.://", [("https://&token=x@h.://", "&token=x", False, [])]),
        (
            "https://@?token=@?token=@.",
            [("https://@?token=@?token=@.", "@?token=", False, [])],
        ),
        (
            "https://&&token=@;?token=",
            [("https://&&token=@;?token=", "&&token=", False, [("?token=", True)])],
        ),
        ("https://b@?token=&@", [("https://b@?token=&@", "b@?token=&", False, [])]),
    ],
    ids=[
        *("own-parenthesis", "semicolon", "empty-first", "weak"),
        *("nested-userinfo", "nested-query", "white-space"),
        *("digit-before-scheme", "dot-before-scheme", "digit-scheme"),
        *("at-in-secret-value", "only-at-in-secret-value", "url-inside-secret-value"),
        *("wide-url-inside-secret-value", "many-secret-values-before-at"),
        *("one-slash", "path-segment", "account"),
        *("secret-first", "empty-user-at", "semicolon-value-end", "delimiter-in-value"),
    ],
)
def test_each_url_of_a_value_is_read_to_its_end(
    text: str, expected: list[_Found]
) -> None:
    """A URL runs to the end of the value, over white space and brackets; a
    URL in a parameter value is read on its own, unless a secret value runs
    over it; an ``@`` inside a secret value does not end the user
    information before it."""
    assert _found(text) == expected


_REFUSED = [
    *("access_token[]", "token[0]", "secret[key]", "api_key%5B%5D", "user[password]"),
    *("session_id", "sessionid", "jsessionid", "PHPSESSID", "bearer", "passphrase"),
    *("privatekey", "passcode", "creds", "userpwd", "tokens", "token1", "password1"),
    *("token_", "token-v2", "token.value", "t%256Fken", "ssh_key", "api-key"),
    *("accesstoken", "db_passphrase", "SessionId"),
    *("subscription-key", "Ocp-Apim-Subscription-Key", "application_key", "app_key"),
    *("client_key", "master_key", "consumer_key", "deploy_key", "AccountKey"),
    *("secretkey", "accesskey", "sessionkey", "ApiKey", "x_api_key"),
]
_ORDINARY = [
    *("monkey", "author", "keyword", "tokenizer", "max_tokens", "country_code"),
    *("state", "Policy", "oauth2", "keys[0]"),
]
#: Masked in a message, never refused, told as weak: a name that holds a
#: secret only sometimes, and a ``_key`` that is no kind of secret key.
_WEAK = ["code", "session", "ticket", "sid", "otp", "code1", "Session"]
_WEAK_KEYS = ["sort_key", "primary-key", "foreign_key"]


@pytest.mark.parametrize("name", _REFUSED)
def test_a_secret_name_is_masked_and_refused(name: str) -> None:
    """The masker and the detector read one list of names: a name the
    detector refuses, the masker masks."""
    url = f"https://h/x?{name}=S3CRET&a=1"
    assert _found(url) == [(url, None, False, [(f"?{name}=S3CRET", True)])]
    assert "S3CRET" not in masked_given_path(url)
    assert "S3CRET" not in sanitize_url_credentials(url)
    assert holds_url_credentials(url)


@pytest.mark.parametrize("name", _ORDINARY + _WEAK + _WEAK_KEYS)
def test_an_ordinary_or_weak_name_is_not_refused(name: str) -> None:
    url = f"https://h/x?{name}=V&a=1"
    assert not holds_url_credentials(url)
    weak = name in _WEAK + _WEAK_KEYS
    assert [f.kind for f in find_url_credentials(url)] == (["weak"] if weak else [])
    assert is_secret_name(name) is weak


# The scanner's linear time is tested by the growth-ratio test of
# test_url_masking_hits.py: ``find_urls`` is one of its views.
