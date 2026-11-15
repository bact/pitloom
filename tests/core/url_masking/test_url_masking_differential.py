# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A differential test of the four deciders of a URL's credentials: the
masker (:func:`pitloom.core.url_masking.masked_given_path`), the SBOM strip
(:func:`pitloom.core.url_masking.strip_url_secrets`), the refusal of a
stored value (:func:`pitloom.core.url_masking.holds_url_credentials`) and
the Git split (:func:`pitloom.core.url_masking.split_userinfo`), on seeded
random URL-ish texts.

See also: test_url_masking_userinfo.py (the rule case by case) and
test_url_masking_planted_secrets.py (the masker alone), both in this
folder.
"""

from __future__ import annotations

import random

import pytest

from pitloom.core.url_masking import (
    holds_url_credentials,
    masked_given_path,
    split_userinfo,
    strip_url_secrets,
)

_SCHEMES = ["https", "HTTPS", "ftp", "ssh", "SSH", "git+ssh", "s3"]
#: What may stand around the secret in a password: breaks, quotes, ``:``;
#: ``@`` only after it (an ``@`` before it followed by the secret and a
#: break reads as a host, as ``urllib`` reads it).
_AROUND = "?#\"'<> \t:"
_HOSTS = ["h.example", "h", "h:8443", "[::1]:22"]
_PATHS = ["", "/", "/o/r.git", "/x?a=1"]
#: Parameter names: each removed from an SBOM, or kept (an ordinary name
#: the masker masks, a weak one, an ordinary one).
_REMOVED = ["token", "access_token", "api-key", "password1", "token[0]", "Sig"]
_KEPT = ["sort_key", "code", "session", "a"]
_VALUE = "a.:@/%-"
_LEADS = ["", " ", "(", '"', "'", "1.", "=", "see "]
_TAILS = ["", " ", ")", ".", "'", '"', ",", " and mail me@x.org"]


def _random(rng: random.Random, chars: str, most: int) -> str:
    return "".join(rng.choice(chars) for _ in range(rng.randint(0, most)))


def _url(rng: random.Random, secret: str) -> tuple[str, str, list[str], list[str]]:
    """A random URL, the kind of its user information, the secrets an SBOM
    may not state (the user information by the rule first, a removed
    parameter's value) and those it keeps (a kept parameter's value)."""
    removed: list[str] = []
    kept: list[str] = []
    kind = rng.choice(["none", "password", "token"])
    userinfo = ""
    if kind == "password":
        word = f"P{secret}"
        password = _random(rng, _AROUND, 2) + word + _random(rng, _AROUND + "@", 2)
        userinfo = rng.choice(["u", "", "git"]) + ":" + password + "@"
        removed.append(word)
    elif kind == "token":
        word = f"T{secret}"
        userinfo = f"ghp_{word}@"
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
def test_the_masker_is_never_weaker_and_the_strip_settles(seed: int) -> None:
    """On 400 random texts: no secret an SBOM may not state survives the
    strip or the masker; a text the refusal refuses is changed by the
    masker; the strip of a stripped text changes nothing; the Git split of a
    URL takes out its password."""
    rng = random.Random(seed)
    for index in range(400):
        url, kind, removed, kept = _url(rng, f"QZ{index:03d}K")
        text = rng.choice(_LEADS) + url + rng.choice(_TAILS)
        plain, changed = strip_url_secrets(text)
        masked = masked_given_path(text)
        for word in removed:
            assert word not in plain and word not in "".join(changed), text
            assert word not in masked, text
        for word in kept:
            assert word in plain, text
        assert strip_url_secrets(plain) == (plain, []), text
        if holds_url_credentials(url):
            assert masked_given_path(url) != url, url
        if kind != "none" and not url.startswith("https://outer"):
            split = split_userinfo(url)
            assert split is not None and removed[0] not in split[0], url
