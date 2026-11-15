# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A differential test of the four deciders of a URL's credentials: the
masker (:func:`pitloom.core.url_masking.masked_given_path`), the SBOM strip
(:func:`pitloom.core.url_masking.strip_url_secrets`), the refusal of a
stored value (:func:`pitloom.core.url_masking.holds_url_credentials`) and
the Git split (:func:`pitloom.core.url_masking.split_userinfo`), on seeded
random URL-ish texts, read in the two modes: a text that is one URL (a URL
field, the whole RFC 3986 user information alphabet) and free text (a URL
ends at white space or a quote). The masker is never weaker than the strip,
except the listed gaps (a ``/`` or white space in a password in a URL field,
a break in the user information of a URL in free text).

See also: test_url_masking_userinfo.py (the rule case by case) and
test_url_masking_planted_secrets.py (the masker alone), both in this
folder.
"""

from __future__ import annotations

import random

import pytest

from pitloom.core.url_masking import (
    holds_url_credentials,
    keeps_weak_parameter,
    masked_given_path,
    split_userinfo,
    strip_url_secrets,
)

_SCHEMES = ["https", "HTTPS", "ftp", "ssh", "SSH", "git+ssh", "s3"]
#: What may stand around the secret in a password of a URL field: breaks,
#: quotes, ``:`` and the rest of the RFC 3986 user information alphabet
#: (``/`` and white space are no part of it); ``@`` only after the secret (an
#: ``@`` before it followed by the secret and a break reads as a host, as
#: ``urllib`` reads it).
_FIELD_AROUND = "?#\"'<>:!$&()*+,;=%41\u00e9`"
#: The same in free text, where a quote, an angle bracket or a backtick ends
#: the URL.
_TEXT_AROUND = "?#:!$&()*+,;=%41\u00e9"
_HOSTS = ["h.example", "h", "h:8443", "[::1]:22"]
_PATHS = ["", "/", "/o/r.git", "/x?a=1"]
#: Parameter names: each removed from an SBOM, or kept (an ordinary name
#: the masker masks, a weak one, an ordinary one).
_REMOVED = [
    *("token", "access_token", "api-key", "password1", "token[0]", "Sig"),
    *("subscription-key", "AccountKey", "secretkey", "app_key", "sessionkey"),
]
_KEPT = ["sort_key", "code", "session", "a"]
_VALUE = "a.:@/%-"
_LEADS = ["", " ", "(", '"', "'", "1.", "=", "see "]
_TAILS = ["", " ", ")", ".", "'", '"', ",", " and mail me@x.org"]


def _random(rng: random.Random, chars: str, most: int) -> str:
    return "".join(rng.choice(chars) for _ in range(rng.randint(0, most)))


def _url(
    rng: random.Random, secret: str, field: bool
) -> tuple[str, str, list[str], list[str]]:
    """A random URL, the kind of its user information, the secrets an SBOM
    may not state (the user information by the rule first, a removed
    parameter's value) and those it keeps (a kept parameter's value)."""
    around = _FIELD_AROUND if field else _TEXT_AROUND
    names = ["u", "", "git", "o'brien", "a!b"] if field else ["u", "", "git", "a!b"]
    tokens = ["ghp_", "TOK'EN", "a(b)"] if field else ["ghp_", "TOK", "a(b)"]
    removed: list[str] = []
    kept: list[str] = []
    kind = rng.choice(["none", "password", "token"])
    userinfo = ""
    if kind == "password":
        word = f"P{secret}"
        # A password that starts with a break after ``u:`` reads as an empty
        # port and a query (``h:?x=a@b``), so it starts with a letter.
        password = "p" + _random(rng, around, 2) + word + _random(rng, around + "@", 2)
        userinfo = rng.choice(names) + ":" + password + "@"
        removed.append(word)
    elif kind == "token":
        word = f"T{secret}"
        userinfo = rng.choice(tokens) + word + "@"
        removed.append(word)
    query = []
    for index in range(rng.randint(0, 3)):
        word = f"V{index}{secret}"
        name = rng.choice(_REMOVED + _KEPT)
        (removed if name in _REMOVED else kept).append(word)
        query.append(f"{name}={_random(rng, _VALUE, 2)}{word}")
    url = f"{rng.choice(_SCHEMES)}://{userinfo}{rng.choice(_HOSTS)}"
    url += rng.choice(_PATHS)
    if query:
        url += ("&" if "?" in url else "?") + "&".join(query)
    if rng.random() < 0.2:
        url = f"https://outer.example/r?redirect={url}"
    return url, kind, removed, kept


@pytest.mark.parametrize("seed", [3, 487])
def test_a_url_field_is_read_alike_by_every_decider(seed: int) -> None:
    """On 400 random texts that are one URL: no secret an SBOM may not state
    survives the strip, the masker or the Git split; the strip of a stripped
    text changes nothing (``strip(strip(x)) == strip(x)``); a text the
    refusal refuses is changed by the masker."""
    rng = random.Random(seed)
    for index in range(400):
        url, kind, removed, kept = _url(rng, f"QZ{index:03d}K", field=True)
        plain, changed = strip_url_secrets(url, whole=True)
        masked = masked_given_path(url)
        for word in removed:
            assert word not in plain and word not in "".join(changed), url
            assert word not in masked, url
        for word in kept:
            assert word in plain, url
        assert strip_url_secrets(plain, whole=True) == (plain, []), url
        if holds_url_credentials(url, whole=True):
            assert masked != url, url
        if kind != "none" and not url.startswith("https://outer"):
            split = split_userinfo(url)
            assert split is not None and removed[0] not in split[0], url


@pytest.mark.parametrize("seed", [5, 2026])
def test_a_url_in_free_text_is_read_alike_by_the_masker_and_the_strip(
    seed: int,
) -> None:
    """On 400 random texts around a URL: no secret an SBOM may not state
    survives the strip or the masker; the strip settles."""
    rng = random.Random(seed)
    for index in range(400):
        url, _, removed, kept = _url(rng, f"QZ{index:03d}K", field=False)
        text = rng.choice(_LEADS) + url + rng.choice(_TAILS)
        plain, changed = strip_url_secrets(text, whole=False)
        masked = masked_given_path(text)
        for word in removed:
            assert word not in plain and word not in "".join(changed), text
            assert word not in masked, text
        for word in kept:
            assert word in plain, text
        assert strip_url_secrets(plain, whole=False) == (plain, []), text


def test_the_masker_hides_every_name_the_strip_removes_or_keeps_as_weak() -> None:
    """One list of names: what the masker masks is removed from an SBOM or
    weak (kept, and told as kept); nothing is masked and silently kept."""
    names = [
        *_REMOVED,
        *_KEPT,
        *("x_key", "foreign_key", "Ocp-Apim-Subscription-Key", "deploy_key"),
        *("masterkey", "clientkey", "AppKey", "monkey", "keyword", "tokenizer"),
    ]
    for name in names:
        url = f"https://h/x?{name}=V"
        masked = "V" not in masked_given_path(url)
        removed = strip_url_secrets(url, whole=True)[0] != url
        assert masked == (removed or keeps_weak_parameter(url)), name
