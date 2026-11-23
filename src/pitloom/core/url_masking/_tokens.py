# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The shapes of the access tokens a host issues: found by the detector in
a URL value (:mod:`pitloom.core.url_masking._hits`), hidden anywhere by the
masker (:func:`pitloom.core.url_masking.masked_given_path`) and kept from
reading as an account name
(:func:`pitloom.core.url_masking.is_account_name`).

See also: :mod:`pitloom.core.url_masking._userinfo` (the account-name
rule). Standard library only.

Each shape is the vendor's prefix and body, as the gitleaks rule set
(``config/gitleaks.toml``, read 2026-11-16) states them, widened where
Pitloom's own shape finds more: of the vendor's fixed length where it
fixes one (GitHub, AWS, Hugging Face, npm, OpenAI, Anthropic, Google),
followed by no further body character, else a minimum and then every
further body character, so that a match covers the whole token and
masking leaves none of it. A GitLab
token's 20 characters must hold a digit, an upper- and a lower-case letter
(Pitloom's own rule), so a documentation slug such as
``glpat-ApiProjectPypiInstallSetup`` is none; a random 20-character body
lacks a digit about 3 times in 100 and is then missed. A Google API key's
35 characters must hold the same three (a random body lacks one about 3
times in 1,000). An AWS key id is base32, so a word such as
``ASIAPACIFICREGION123`` is none.

Slack: every ``xox[abeoprs]-`` token of two digit groups and 8 letters or
digits (Pitloom's own shape, which also covers the user token), and
the gitleaks shapes fixed by digit groups or length: bot
(``xoxb-<10-13 digits>-<10-13 digits>``), legacy (``xoxo-``, ``xoxs-``:
three digit groups and hex), configuration refresh (``xoxe-``, 146) and
configuration access (``xoxe.xoxb-``, ``xoxe.xoxp-``, 163 to 166); each
runs on over every further letter, digit and ``-``. The gitleaks legacy
workspace (``xoxa-``, ``xoxr-``: 8 to 48 letters or digits) and legacy bot
(``xoxb-<8-14 digits>-<18-26 letters or digits>``) shapes are not read:
a documentation word fits them (``xoxr-Configuration``), so such a token
without the digit groups is missed. An app token (``xapp-``) has an
upper-case app id, as in Pitloom's own shape. A GitLab pipeline
trigger, OAuth or CI build token is found in its gitleaks shape or as such
20 characters. PyPI: any version-2
macaroon (``AgE``), so a TestPyPI token (location ``test.pypi.org``,
``AgENdGVzdC5weXBpLm9yZw``) is found as well as a PyPI one (gitleaks
names only ``AgEIcHlwaS5vcmc``, location ``pypi.org``). Every repetition
is bounded or followed by nothing that could backtrack, so a search stays
linear.
"""

from __future__ import annotations

import re

from pitloom.core.url_masking._boundary import word_start

__all__ = [
    "TOKEN_PREFIXES",
    "TOKEN_RE",
    "TOKEN_SHAPES",
    "mask_tokens",
    "token_prefix",
]

#: Not followed by another character of a base-62 body.
_END = "(?![A-Za-z0-9])"
#: The kinds of character a random token body holds one of at least.
_MIXED = ("[0-9]", "[A-Z]", "[a-z]")


def _mixed(chars: str, length: int) -> str:
    """*length* characters of the class *chars*, a digit, an upper- and a
    lower-case letter among them."""
    ahead = f"[{chars}]{{0,{length - 1}}}"
    return "".join(f"(?={ahead}{one})" for one in _MIXED) + f"[{chars}]{{{length}}}"


#: The 20 characters of a GitLab token, a digit, an upper- and a
#: lower-case letter among them, and the rest of a longer one.
_GITLAB = _mixed("A-Za-z0-9_-", 20) + "[A-Za-z0-9_.-]*"
#: The 34 letters of a Hugging Face token.
_HF = f"[A-Za-z]{{34}}{_END}"
#: Not followed by another character of a base-64 URL-safe body.
_END64 = "(?![A-Za-z0-9_-])"
#: One half of an OpenAI project, service account or admin key.
_OPENAI = "(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})"

#: The rest of a Slack token: every further letter, digit and ``-``.
_RUN = "[A-Za-z0-9-]*"
#: Each Slack token kind's gitleaks shapes beyond the common one, those
#: fixed by digit groups or length only.
_SLACK: dict[str, tuple[str, ...]] = {
    "b": ("[0-9]{10,13}-[0-9]{10,13}",),
    "e": ("[0-9]-[A-Za-z0-9]{146}",),
    "o": ("[0-9]+-[0-9]+-[0-9]+-[0-9A-Fa-f]+",),
    "s": ("[0-9]+-[0-9]+-[0-9]+-[0-9A-Fa-f]+",),
}


def _slack(kind: str) -> str:
    """The body of an ``xox<kind>-`` Slack token: two digit groups and 8
    letters or digits, or a gitleaks shape of *kind*, and the rest of it."""
    common = "[0-9]{1,15}-[0-9]{1,15}-[A-Za-z0-9]{8}"
    return f"(?:{'|'.join((common, *_SLACK.get(kind, ())))}){_RUN}"


#: The access tokens of GitHub, GitLab, Slack, Hugging Face, AWS, PyPI,
#: npm, OpenAI, Anthropic and Google, as (prefix, the body after it as a
#: regular expression). No bare ``sk-``: too many words start so.
TOKEN_SHAPES: tuple[tuple[str, str], ...] = (
    *((f"gh{kind}_", f"[A-Za-z0-9]{{36}}{_END}") for kind in "porsu"),
    ("github_pat_", f"[A-Za-z0-9]{{22}}_[A-Za-z0-9]{{59}}{_END}"),
    *((prefix, _GITLAB) for prefix in ("glpat-", "gldt-", "glrt-")),
    ("glcbt-", f"(?:[A-Za-z0-9]{{1,5}}_)?{_GITLAB}"),
    ("glptt-", f"(?:[0-9a-f]{{40}}{_END}|{_GITLAB})"),
    ("gloas-", f"(?:[A-Za-z0-9_-]{{64}}{_END64}|{_GITLAB})"),
    *((f"xox{kind}-", _slack(kind)) for kind in "abeoprs"),
    *((f"xoxe.xox{kind}-", f"[0-9]-[A-Za-z0-9]{{163,166}}{_RUN}") for kind in "bp"),
    ("xapp-", "[0-9]{1,3}-[A-Z0-9]{8,15}-[0-9]{1,15}-[A-Za-z0-9]{8,}"),
    ("hf_", _HF),
    ("api_org_", _HF),
    *((prefix, f"[A-Z2-7]{{16}}{_END}") for prefix in ("AKIA", "ASIA")),
    ("pypi-", "AgE[A-Za-z0-9_-]{50,}"),
    ("npm_", f"[A-Za-z0-9]{{36}}{_END}"),
    *(
        (f"sk-{kind}-", f"{_OPENAI}T3BlbkFJ{_OPENAI}{_END64}")
        for kind in ("proj", "svcacct", "admin")
    ),
    *(
        (prefix, f"[A-Za-z0-9_-]{{93}}AA{_END64}")
        for prefix in ("sk-ant-api03-", "sk-ant-admin01-")
    ),
    ("AIza", _mixed("A-Za-z0-9_-", 35) + _END64),
)
#: The prefixes of those tokens.
TOKEN_PREFIXES = tuple(prefix for prefix, _ in TOKEN_SHAPES)
#: A token of a known shape, not inside a longer word, though right after a
#: percent-encoded character (``Bearer%20ghp_...``) or an escape sequence
#: (``token:\\tghp_...``, :func:`~pitloom.core.url_masking._boundary.word_start`).
#: Each prefix is a group. A position is tried only at the first character
#: of a prefix, before the lookbehinds, so a search stays fast on a long run
#: of escapes (``\\t\\t...``).
TOKEN_RE = re.compile(
    f"(?=[{''.join(sorted({prefix[0] for prefix, _ in TOKEN_SHAPES}))}])"
    + word_start("A-Za-z0-9_-", "(?<=%[0-9A-Fa-f]{2})")
    + "(?:"
    + "|".join(f"({re.escape(prefix)}){body}" for prefix, body in TOKEN_SHAPES)
    + ")"
)


def token_prefix(found: re.Match[str]) -> str:
    """The prefix of the token *found* by :data:`TOKEN_RE`."""
    return next(group for group in found.groups() if group is not None)


def mask_tokens(text: str) -> str:
    """*text* with each token of a known shape, all of it, written as its
    prefix and ``***`` (``ghp_***``)."""
    return TOKEN_RE.sub(lambda found: f"{token_prefix(found)}***", text)
