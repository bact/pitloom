# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Masking of credentials in a URL and of the temporary Git checkout in a text.

See also: :mod:`pitloom.logging_config` (its ``escape_controls`` masks the
checkout in every logged line) and :mod:`pitloom.extract.remote.git` (the Git
URL ingestion that makes the checkout).

The contract, for every function here:

* Standard library only. This module imports no other Pitloom module, so
  :mod:`pitloom.logging_config` and any extractor can import it without a
  cycle.
* A text is returned as it is when it holds nothing to mask.
* The patterns bound every repetition that could backtrack, so a long
  adversarial text cannot stall a log line.
* :func:`sanitize_url_credentials` masks URLs inside free text, which ends
  at white space; :func:`sanitize_url` is for a text that is one URL.
  :func:`mask_checkout` writes the checkout directory as
  :data:`CHECKOUT_PLACEHOLDER` so two runs read the same.
"""

from __future__ import annotations

import re
from collections import deque
from urllib.parse import unquote

__all__ = [
    "CHECKOUT_DIR_PREFIX",
    "CHECKOUT_PLACEHOLDER",
    "mask_checkout",
    "sanitize_url",
    "sanitize_url_credentials",
]

#: ``://`` and a userinfo (non-empty, up to the last ``@`` before a ``/`` or
#: whitespace: a password holding ``?`` or ``#`` is masked whole).
_URL_USERINFO_RE = re.compile(r"://[^/\s@][^/\s]*@")


#: A URL in a text, to its end at whitespace.
_URL_RE = re.compile(r"://\S+")

#: A query or fragment parameter (name at most 64 characters, so matching is
#: linear), as ``(delimiter, name, value)``.
_PARAM_RE = re.compile(r"([?&;#])([\w.%-]{1,64})=([^&;#\s]*)")

#: Names (lower case) of a parameter that holds a secret, and the endings of
#: such a name (``access_token``, ``db-password``).
_SECRET_NAMES = frozenset(
    {
        "token",
        "key",
        "apikey",
        "secret",
        "password",
        "passwd",
        "pass",
        "pwd",
        "pw",
        "sig",
        "signature",
        "jwt",
        "credential",
        "credentials",
    }
)
_SECRET_ENDINGS = ("_token", "-token", "_secret", "-secret", "_key", "-key") + (
    "_password",
    "-password",
    "_signature",
    "-signature",
)

#: ``://`` and a userinfo of a text that is one URL: up to the last ``@``
#: before the first ``/``, whatever characters (a newline, a space) it holds.
#: ``:/`` and ``:\\`` too, for a URL a path normalisation collapsed.
_WHOLE_URL_USERINFO_RE = re.compile(r":[/\\]{1,2}[^/\\@][^/\\]*@")


def _mask_param(match: re.Match[str]) -> str:
    delimiter, name, value = match.groups()
    plain = unquote(name).lower()
    if plain in _SECRET_NAMES or plain.endswith(_SECRET_ENDINGS):
        value = "***"
    return f"{delimiter}{name}={value}"


def _mask_url_secrets(match: re.Match[str]) -> str:
    return _PARAM_RE.sub(_mask_param, match.group(0))


def sanitize_url_credentials(text: str) -> str:
    """Redact username and password from URLs in *text* (e.g.
    ``https://user:pass@host/`` -> ``https://***:***@host/``), and the value of
    a query parameter named like a secret (``?private_token=***``).

    Used across extractors, build backends, and error loggers to prevent
    sensitive auth tokens from leaking into error messages or SBOM output.
    The userinfo ends at the last ``@`` before the first ``/`` or whitespace,
    so a password holding ``@``, ``?`` or ``#`` is redacted whole. For a text
    that is one URL, use :func:`sanitize_url`.
    """
    return _URL_RE.sub(_mask_url_secrets, _URL_USERINFO_RE.sub("://***:***@", text))


def sanitize_url(url: str) -> str:
    """:func:`sanitize_url_credentials` for a text that is one URL: the
    userinfo is redacted whole even when it holds a newline or a space."""
    return sanitize_url_credentials(_WHOLE_URL_USERINFO_RE.sub("://***:***@", url))


#: The name prefix of the temporary directory a Git URL is checked out in.
CHECKOUT_DIR_PREFIX = "pitloom-git-"
#: What a message shows for that directory, so two runs read the same.
CHECKOUT_PLACEHOLDER = "<checkout>"
#: ``tempfile.mkdtemp`` appends eight characters of ``[a-z0-9_]``: a directory
#: of another name (a worktree called ``pitloom-git-fix``) is not the checkout.
_CHECKOUT_DIR = re.compile(
    re.escape(CHECKOUT_DIR_PREFIX) + r"[a-z0-9_]{8}(?![a-z0-9_])"
)
#: A word of a message: a run without a space, quote, bracket, backtick, ``=``,
#: ``,`` or ``;`` (where a path ends in a message that quotes, brackets or
#: follows ``KEY=``).
_WORD = re.compile(r"[^\s'\"`()\[\]<>=,;]+")
#: ``user@host:path``, the scp-style address of a repository.
_SCP_ADDRESS = re.compile(r"[\w.+-]+@[\w.-]+:")


def _mask_word(found: re.Match[str]) -> str:
    word = found.group(0)
    if (
        CHECKOUT_DIR_PREFIX not in word
        or "://" in word
        or _SCP_ADDRESS.match(word) is not None
    ):
        return word
    last = deque(_CHECKOUT_DIR.finditer(word), maxlen=1)
    return CHECKOUT_PLACEHOLDER + word[last[0].end() :] if last else word


def mask_checkout(text: str) -> str:
    """*text* with the temporary checkout of a Git URL written as
    ``<checkout>``: each word that is a path holding the directory
    (``pitloom-git-`` and its eight random characters) becomes ``<checkout>``
    and what follows the directory, so a path below it keeps its tail
    (``<checkout>/setup.cfg``). A word that is an address (``https://host/o/
    pitloom-git-abcdefgh``, ``git@host:o/pitloom-git-abcdefgh``) is kept. One
    pass over the words; text without the prefix is returned as it is."""
    if CHECKOUT_DIR_PREFIX not in text:
        return text
    return _WORD.sub(_mask_word, text)
