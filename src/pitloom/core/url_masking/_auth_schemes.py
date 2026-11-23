# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential after an HTTP authentication scheme in a text
(``Authorization: Bearer <token>``, ``Basic <base64>``), as a build's output
or an HTTP client's debug line prints it: masked by
:func:`~pitloom.core.url_masking.masked_given_path`, the scheme kept
(``Bearer ***``).

See also: :mod:`pitloom.core.url_masking._boundary` (where the scheme word
may start) and :mod:`pitloom.core.url_masking._tokens` (a token of a known
shape, masked first, so ``Bearer ghp_***`` keeps its prefix). Standard
library only.

The rule:

* The scheme is the word ``Bearer`` or ``Basic``, of any case, not glued to
  the word before it (a ``_``, ``-``, letter or digit), or right after an
  escape sequence; then one or more spaces, tabs, escaped tabs (``\\t``)
  or ``%20``; then a run of the characters of RFC 6750's ``b64token``
  (letters, digits, ``-._~+/`` and ``=``), the credential. A ``.`` ending
  the run ends a sentence and is kept.
* A ``Basic`` credential is standard base64 (RFC 7617): letters, digits,
  ``+``, ``/``, then at most two ``=``; anything else (``well-formed``) is
  prose.
* Prose follows a scheme word too (``the bearer of bad news``, ``Bearer
  token required``, ``Basic authentication``), so the run is a credential
  only when it holds 8 characters or more and a digit, one of ``.~+/=``
  inside it, letters of mixed case past a capital first one (``dXNlcjpwYXNz``,
  not ``Authentication``), or 20 characters or more. A ``-`` or ``_`` alone
  does not count (``co-signer``, ``access_token``). So a credential of 8 to
  19 letters (and ``-``, ``_``) all of one case, or a capital and then lower
  case, is missed.

Linear: the run is read once in a lookahead after its scheme and its
separators, and two runs never overlap, so each character is read a
bounded number of times.
"""

from __future__ import annotations

import re

from pitloom.core.url_masking._boundary import word_start

__all__ = ["mask_auth_schemes"]

#: A scheme word, its separators, and (group ``run``, in a lookahead) the
#: run of ``b64token`` characters after them.
_SCHEME_RE = re.compile(
    "(?=[Bb])"
    + word_start("A-Za-z0-9_-")
    + r"(?P<scheme>(?i:bearer|basic))(?:[ \t]|\\t|%20)+"
    + r"(?=(?P<run>[A-Za-z0-9._~+/=-]+))"
)
#: A ``Basic`` credential: standard base64.
_BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
#: The fewest characters of a credential.
_SHORTEST = 8
#: A run this long is a credential whatever it holds.
_LONG = 20
#: Characters of a ``b64token`` that prose rarely holds inside a word.
_TOKEN_MARKS = frozenset(".~+/=")


def _is_credential(scheme: str, core: str) -> bool:
    """Whether *core*, the run after *scheme* without its ending ``.``, is
    a credential, not prose (see the module's rule)."""
    if len(core) < _SHORTEST:
        return False
    if scheme.lower() == "basic" and _BASE64.fullmatch(core) is None:
        return False
    return (
        len(core) >= _LONG
        or any(char.isdigit() or char in _TOKEN_MARKS for char in core)
        or not (core.islower() or core.isupper() or core.istitle())
    )


def mask_auth_schemes(text: str) -> str:
    """*text* with the credential after each ``Bearer`` or ``Basic`` scheme
    written as ``***``, the scheme, its separators and a ``.`` ending the
    run kept (see the module's rule)."""
    parts: list[str] = []
    done = 0
    for found in _SCHEME_RE.finditer(text):
        run = found.group("run")
        core = run.rstrip(".")
        if not _is_credential(found.group("scheme"), core):
            continue
        start = found.end()
        parts += (text[done:start], "***")
        done = start + len(core)
    if not parts:
        return text
    return "".join(parts) + text[done:]
