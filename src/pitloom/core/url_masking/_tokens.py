# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The shapes of the access tokens a host issues, found anywhere in a text:
by the detector (:mod:`pitloom.core.url_masking._detect`), the masker
(:func:`pitloom.core.url_masking.masked_given_path`) and the account-name
rule (:func:`pitloom.core.url_masking.is_account_name`).

See also: :mod:`pitloom.core.url_masking._userinfo` (the account-name
rule). Standard library only.

A shape is the vendor's prefix and a body of the vendor's characters: of
the vendor's fixed length where it fixes one (GitHub, AWS, Hugging Face,
npm), else at least the shortest real one. A body a vendor draws at random
from mixed characters must hold what such a draw holds (a digit, an upper-
and a lower-case letter), so a slug such as ``glpat-token-rotation-guide``
is none. Every repetition is bounded, so a search stays linear.
"""

from __future__ import annotations

import re

__all__ = [
    "TOKEN_PREFIXES",
    "TOKEN_RE",
    "TOKEN_SHAPES",
    "mask_tokens",
    "token_prefix",
]

#: Not followed by another character of a base-62 body.
_END = "(?![A-Za-z0-9])"


def _mixed(chars: str, length: int, *, digit: bool = True) -> str:
    """A body of *length* characters of the class *chars* holding an upper-
    and a lower-case letter, and a digit unless *digit* is false."""
    ahead = f"[{chars}]{{0,{length - 1}}}"
    need = ("[0-9]", "[A-Z]", "[a-z]") if digit else ("[A-Z]", "[a-z]")
    return "".join(f"(?={ahead}{one})" for one in need) + f"[{chars}]{{{length}}}"


_GITLAB = _mixed("A-Za-z0-9_-", 20)
_HF = _mixed("A-Za-z", 34, digit=False) + _END

#: The access tokens of GitHub, GitLab, Slack, Hugging Face, AWS, PyPI and
#: npm, as (prefix, the body after it as a regular expression).
TOKEN_SHAPES: tuple[tuple[str, str], ...] = (
    *((f"gh{kind}_", f"[A-Za-z0-9]{{36}}{_END}") for kind in "porsu"),
    ("github_pat_", f"[A-Za-z0-9]{{22}}_[A-Za-z0-9]{{59}}{_END}"),
    *((prefix, _GITLAB) for prefix in ("glpat-", "gldt-", "glptt-", "glrt-")),
    *((prefix, _GITLAB) for prefix in ("gloas-", "glcbt-")),
    *((f"xox{kind}-", "[0-9]{1,15}-[0-9]{1,15}-[A-Za-z0-9]{8}") for kind in "abeprs"),
    ("xapp-", "[0-9]{1,3}-[A-Z0-9]{8,15}-[0-9]{1,15}-[A-Za-z0-9]{8}"),
    ("hf_", _HF),
    ("api_org_", _HF),
    *((prefix, f"[A-Z0-9]{{16}}{_END}") for prefix in ("AKIA", "ASIA")),
    ("pypi-", "AgE[A-Za-z0-9_-]{50}"),
    ("npm_", f"[A-Za-z0-9]{{36}}{_END}"),
)
#: The prefixes of those tokens.
TOKEN_PREFIXES = tuple(prefix for prefix, _ in TOKEN_SHAPES)
#: A token of a known shape, not inside a longer word, though right after a
#: percent-encoded character (``Bearer%20ghp_...``). Each prefix is a group.
TOKEN_RE = re.compile(
    r"(?:(?<![A-Za-z0-9_-])|(?<=%[0-9A-Fa-f]{2}))(?:"
    + "|".join(f"({re.escape(prefix)}){body}" for prefix, body in TOKEN_SHAPES)
    + ")"
)


def token_prefix(found: re.Match[str]) -> str:
    """The prefix of the token *found* by :data:`TOKEN_RE`."""
    return next(group for group in found.groups() if group is not None)


def mask_tokens(text: str) -> str:
    """*text* with each token of a known shape written as its prefix and
    ``***`` (``ghp_***``)."""
    return TOKEN_RE.sub(lambda found: f"{token_prefix(found)}***", text)
