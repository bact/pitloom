# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A differential test of the three deciders of a URL's credentials: the
masker (:func:`pitloom.core.url_masking.masked_given_path`), the refusal of
a stored value (:func:`pitloom.core.url_masking.holds_url_credentials`) and
the Git split (:func:`pitloom.core.url_masking.split_userinfo`), on seeded
random URL-ish texts, read in the two modes: a text that is one URL (a URL
field, the whole RFC 3986 user information alphabet) and free text (a URL
ends at white space or a quote), which only the masker reads.

A PURL (a URL, an scp-style address or a token in a qualifier or the
subpath, encoded up to three times) is read alike by the detector, the
masker and the refusal: what the detector refuses the masker hides.

See also: test_url_masking_userinfo.py (the rule case by case) and
test_url_masking_planted_secrets.py (the masker alone), both in this
folder.
"""

from __future__ import annotations

import random

import pytest

from pitloom.core.url_masking import (
    find_url_credentials,
    holds_url_credentials,
    masked_given_path,
    split_userinfo,
)
from tests.core.url_masking._probe_corpus import encoded

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
#: Parameter names: each refused, or not (an ordinary name the masker
#: masks, a weak one, an ordinary one).
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
    may not state (the user information by the rule first, a refused
    parameter's value) and the values that are no such secret."""
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
    """On 400 random texts that are one URL: a text holding a secret an SBOM
    may not state is refused, and the secret survives neither the masker
    nor the Git split; a text the refusal refuses is changed by the
    masker."""
    rng = random.Random(seed)
    for index in range(400):
        url, kind, removed, _ = _url(rng, f"QZ{index:03d}K", field=True)
        masked = masked_given_path(url)
        for word in removed:
            assert word not in masked, url
        held = holds_url_credentials(url)
        assert held or not removed, url
        if held:
            assert masked != url, url
        if kind != "none" and not url.startswith("https://outer"):
            split = split_userinfo(url)
            assert split is not None and removed[0] not in split[0], url


@pytest.mark.parametrize("seed", [5, 2026])
def test_a_url_in_free_text_is_masked(seed: int) -> None:
    """On 400 random texts around a URL: no secret an SBOM may not state
    survives the masker, as a value or as a line."""
    rng = random.Random(seed)
    for index in range(400):
        url, _, removed, _ = _url(rng, f"QZ{index:03d}K", field=False)
        text = rng.choice(_LEADS) + url + rng.choice(_TAILS)
        masked = masked_given_path(text) + masked_given_path(text, line=True)
        for word in removed:
            assert word not in masked, text


def test_the_masker_hides_every_name_the_detector_finds() -> None:
    """One list of names: what the masker masks the detector finds, refused
    or weak (told, never refused); nothing is masked and silently
    accepted."""
    names = [
        *_REMOVED,
        *_KEPT,
        *("x_key", "foreign_key", "Ocp-Apim-Subscription-Key", "deploy_key"),
        *("masterkey", "clientkey", "AppKey", "monkey", "keyword", "tokenizer"),
    ]
    for name in names:
        url = f"https://h/x?{name}=V"
        masked = "V" not in masked_given_path(url)
        assert masked == bool(find_url_credentials(url)), name
        if name in _REMOVED:
            assert holds_url_credentials(url), name


def _purl(rng: random.Random, secret: str) -> tuple[str, str]:
    """A random PURL holding one planted *secret* (or none), and the
    secret."""
    token = f"ghp_{secret}" + "aB3" * 12
    token = token[: len("ghp_") + 36]
    values = {
        "url": f"https://u:P{secret}@h/x",
        "scp": f"alice:P{secret}@host:o/r",
        "token": token,
        "none": "https://h/x",
    }
    kind = rng.choice([*values, "key"])
    planted = "" if kind == "none" else (token[4:] if kind == "token" else secret)
    if kind == "key":
        return f"pkg:generic/x@1?private_token=P{secret}&a=1", secret
    value = encoded(values[kind], rng.randint(0, 3))
    if rng.random() < 0.5:
        return f"pkg:generic/x@1?a=1&v={value}", planted
    # An scp-style address counts in a subpath only as all of it.
    lead = "" if kind == "scp" else "sub/"
    return f"pkg:generic/x@1?a=1#{lead}{value}", planted


@pytest.mark.parametrize("seed", [7, 489])
def test_a_purl_is_read_alike_by_every_decider(seed: int) -> None:
    """On 300 random PURLs: the refusal is the detector's non-weak finding;
    a planted secret is refused, and hidden by the masker and every
    finding."""
    rng = random.Random(seed)
    for index in range(300):
        purl, planted = _purl(rng, f"QZ{index:03d}K")
        found = find_url_credentials(purl)
        held = holds_url_credentials(purl)
        assert held == any(not f.weak for f in found), purl
        assert held == bool(planted), purl
        if planted:
            assert planted not in masked_given_path(purl), purl
            assert planted not in masked_given_path(f"see {purl} ok", line=True)
            assert not any(planted in f.shown for f in found), purl
