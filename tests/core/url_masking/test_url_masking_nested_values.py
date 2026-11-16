# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The detector reads a URL field's query values and fragment once
percent-decoded, a password that starts with ``?`` or ``#`` after
``user:``, and the signed-URL parameter names as decided
(working-docs/implementation/credential-leak-fixes.md); the masker hides
each, and the HTTP clients' request targets are masked in free text.

See also: test_url_masking_decode.py (an identifier read at each depth),
test_url_masking_modes.py (an empty port), test_url_masking_hits.py
(the timing shapes).
"""

from __future__ import annotations

import pytest

from pitloom.core.url_masking import (
    find_url_credentials,
    holds_url_credentials,
    mask_free_params,
    masked_given_path,
    split_userinfo,
)
from tests.core.url_masking._probe_corpus import b62, encoded

_INNER = "https://u:S3CRET@h2.example/x"

#: A URL field holding a credentialed URL once decoded, in a query value or
#: its fragment, and what kind it is found as.
_DECODED = [
    ("query", f"https://h/?next={encoded(_INNER, 1)}", "secret"),
    ("query-twice", f"https://h/?next={encoded(_INNER, 2)}", "secret"),
    ("query-later", f"https://h/?a=1&next={encoded(_INNER, 1)}&b=2", "secret"),
    ("query-semicolon", f"https://h/x;a=1;next={encoded(_INNER, 1)}", "secret"),
    ("fragment", f"https://h/x#{encoded(_INNER, 1)}", "secret"),
    ("fragment-param", f"https://h/x#next={encoded(_INNER, 1)}&a=1", "secret"),
    (
        "inner-param",
        "https://h/?next=" + encoded("https://h2/x?token=S3CRET", 1),
        "secret",
    ),
    (
        "inner-nested",
        "https://h/?n=" + encoded(f"https://h2/?n={encoded(_INNER, 1)}", 1),
        "secret",
    ),
    ("scp", "https://h/?next=" + encoded("u:S3CRET@host:o/r", 1), "scp"),
    ("deepest", f"https://h/?next={encoded(_INNER, 5)}", "secret"),
    # A token prefix with a letter encoded.
    ("token", f"https://h/?t=%67hp_S3CRET{b62(30)}", "token"),
]


@pytest.mark.parametrize(
    ("text", "kind"), [row[1:] for row in _DECODED], ids=[row[0] for row in _DECODED]
)
def test_a_decoded_query_value_or_fragment_is_read(text: str, kind: str) -> None:
    assert "%" in text  # the credential is visible only once decoded
    assert kind in [found.kind for found in find_url_credentials(text)]
    assert holds_url_credentials(text)
    assert "S3CRET" not in masked_given_path(text)
    assert not any("S3CRET" in found.shown for found in find_url_credentials(text))


@pytest.mark.parametrize(
    "text",
    [
        "https://h/?next=https%3A%2F%2Fexample.org%2Fa",
        "https://h/?next=" + encoded("https://h2/x?a=1&b=2", 2),
        "https://h/?q=a%40b.org&f=a%20b%40c.txt",
        "https://h/s?q=user%3Apass%40example",
        "https://h/x#section%3A2%40v1",
        "https://h/?q=%40%3A%2F",
        # Deeper than read: a redirect chain may encode a plain URL so.
        f"https://h/?next={encoded(_INNER, 6)}",
    ],
    ids=["url", "url-twice", "mail", "words", "fragment", "marks", "too-deep"],
)
def test_an_ordinary_encoded_value_is_no_hit(text: str) -> None:
    assert not find_url_credentials(text)


def test_a_weak_name_once_decoded_is_weak() -> None:
    text = "https://h/?next=" + encoded("https://h2/x?code=1", 1)
    found = find_url_credentials(text)
    assert [f.kind for f in found] == ["weak"] and not holds_url_credentials(text)


#: A password that starts with a break after ``user:``: ``urllib`` and git
#: read ``u`` as the host and the rest as a query or fragment, yet the value
#: states the password.
_BREAK_PASSWORDS = [
    "https://u:?S3CRET@h/x",
    "https://u:#S3CRET@h/x",
    "https://:?S3CRET@h/x",
    "https://u:?S3CRET@h?mail=a@b.org",
    "https://u:?S3CRET@h/x?token=T",
]


@pytest.mark.parametrize("text", _BREAK_PASSWORDS)
def test_a_password_after_a_break_is_found(text: str) -> None:
    assert [f.kind for f in find_url_credentials(text)][:1] == ["secret"]
    assert "S3CRET" not in masked_given_path(text)
    # The Git split keeps git's reading: no user information there.
    assert split_userinfo(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "https://h:?x=a@b",
        "https://h:#x=a@b",
        "https://files.example:?mirror=eu@cdn.example/c.whl",
        "https://h:?a&b@c",
        "https://h.example:?@evil.example/o/r",
        "https://[v1.a]:?x@h",
        "https://h?mail@h2",
        "https://h:8080?x@h2",
    ],
    ids=[
        *("equals", "fragment", "mirror", "ampersand", "empty", "ip-literal"),
        *("no-colon", "port"),
    ],
)
def test_an_empty_port_and_a_query_stay_a_host(text: str) -> None:
    """Each side of the rule: a ``=`` or ``&`` before the ``@`` reads as a
    query, an empty password, a bracketed host, no ``:`` or a port before
    the break is no such password."""
    assert not holds_url_credentials(text)


#: CloudFront signed URLs: the signature is the secret; the policy (base64
#: JSON: resource, expiry) and the key pair id (the public key's id) are not.
_CLOUDFRONT = "https://d.example.net/x?Policy=eyJTdGF0&Signature=S3CRET&Key-Pair-Id=K2"


def test_a_cloudfront_signature_is_refused_its_policy_and_key_id_kept() -> None:
    found = find_url_credentials(_CLOUDFRONT)
    assert [(f.kind, f.weak) for f in found] == [("secret", False)]
    shown = masked_given_path(_CLOUDFRONT)
    assert shown == _CLOUDFRONT.replace("S3CRET", "***")


@pytest.mark.parametrize(
    "text",
    [
        "https://h/cb?state=xyz",
        "https://h/cb?code=c&state=xyz",
        "https://h/geo?country=US&state=CA",
        "https://h/x?Policy=eyJTdGF0&Key-Pair-Id=K2",
    ],
)
def test_state_policy_and_key_pair_id_are_no_secret(text: str) -> None:
    assert not holds_url_credentials(text)
    assert masked_given_path(text) == text.replace("code=c", "code=***")


@pytest.mark.parametrize(
    "text",
    ["https://h/x;jsessionid=S3CRET?a=1", "https://h/x;JSESSIONID=S3CRET"],
)
def test_a_jsessionid_path_parameter_is_refused(text: str) -> None:
    assert holds_url_credentials(text)
    assert "S3CRET" not in masked_given_path(text)


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ('"GET /x?token=T0KEN HTTP/1.1" 200', '"GET /x?token=*** HTTP/1.1" 200'),
        ("(url='/x?access_token=T0KEN&a=1')", "(url='/x?access_token=***&a=1')"),
        ("/x?code=T0KEN;b=2#sig=T0KEN", "/x?code=***;b=2#sig=***"),
        ("Starting new HTTPS connection (1): h.example:443", None),
        ("a=b, no parameter here", None),
    ],
    ids=["request-target", "retry", "weak-and-fragment", "clean", "no-delimiter"],
)
def test_free_params_are_masked_without_a_url(text: str, shown: str | None) -> None:
    assert mask_free_params(text) == (text if shown is None else shown)
