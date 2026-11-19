# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Masking of credentials in a URL, and of the temporary Git checkout and
PyPI download directory in a text.

See also: :mod:`pitloom.logging_config` (its ``escape_controls`` masks both
directories in every logged line), :mod:`pitloom.extract.remote.git` (the Git
URL ingestion that makes the checkout) and :mod:`pitloom.extract.remote.pypi`
(the PyPI URL ingestion that makes the download directory).

The contract, for every function here:

* Standard library only. This package imports no other Pitloom module (its
  own submodules apart), so :mod:`pitloom.logging_config` and any extractor
  can import it without a cycle.
* A text is returned as it is when it holds nothing to mask.
* The patterns bound every repetition that could backtrack, so a long
  adversarial text cannot stall a log line.
* :func:`sanitize_url_credentials` masks URLs inside free text, which ends
  at white space; :func:`sanitize_url` is for a text that is one URL.
  :func:`mask_checkout` writes the checkout directory as
  :data:`CHECKOUT_PLACEHOLDER`, and the download directory as
  :data:`DOWNLOAD_PLACEHOLDER`, so two runs read the same.
* :func:`find_url_credentials` reports the credentials of a value stored as
  written and never rewrites it (:mod:`pitloom.core.url_masking._detect`).
"""

from __future__ import annotations

import re
from collections import deque

from pitloom.core.url_masking._detect import (
    Finding,
    find_url_credentials,
    holds_url_credentials,
)
from pitloom.core.url_masking._hits import without_format
from pitloom.core.url_masking._mask import masked_given_path
from pitloom.core.url_masking._params import (
    PARAM_RE,
    WHOLE_PARAM_RE,
    is_secret_name,
    mask_free_param,
    mask_free_params,
    mask_param,
    sub_params,
)
from pitloom.core.url_masking._userinfo import (
    is_account_name,
    mask_scp,
    split_userinfo,
    userinfo_end,
)

__all__ = [
    "CHECKOUT_DIR_PREFIX",
    "CHECKOUT_PLACEHOLDER",
    "DOWNLOAD_DIR_PREFIX",
    "DOWNLOAD_PLACEHOLDER",
    "Finding",
    "HUB_DIR_PREFIX",
    "URL_AS_PATH_RE",
    "find_url_credentials",
    "holds_url_credentials",
    "is_account_name",
    "is_secret_name",
    "mask_checkout",
    "mask_free_params",
    "masked_given_path",
    "sanitize_url",
    "sanitize_url_credentials",
    "split_userinfo",
    "userinfo_end",
    "without_format",
]

#: ``://``, where a user information may follow, in free text; it ends at
#: the first ``/`` or white space.
_FREE_OPENER = re.compile("://")
_FREE_STOP = re.compile(r"[/\s]")
#: A URL in a text, to its end at whitespace.
_URL_RE = re.compile(r"://\S+")
#: The same in a text that is one URL, also as ``Path`` collapses its
#: ``//`` (``https:/u@h``) or a Windows ``Path`` writes it (``https:\\u@h``);
#: it ends at the first separator of its kind, whatever else it holds.
_WHOLE_OPENER = re.compile(r":(?:/{1,2}|\\{1,2})")
_WHOLE_STOP = {"/": re.compile("/"), "\\": re.compile(r"[/\\]")}


def _replaced_userinfo(
    text: str, opener: re.Pattern[str], replacement: str, *, whole: bool
) -> str:
    """*text* with each opener and the user information after it
    (:func:`userinfo_end`, to the first ``/``, or white space unless
    *whole*) replaced by *replacement*. Each opener's search for its end
    stops at the next opener at the latest, so the scan is linear."""
    parts: list[str] = []
    done = 0
    for found in opener.finditer(text):
        start = found.end()
        if found.start() < done:
            continue
        stop = _WHOLE_STOP[found.group()[1]] if whole else _FREE_STOP
        end = stop.search(text, start)
        at = userinfo_end(
            text,
            start,
            len(text) if end is None else end.start(),
            widest=True,
        )
        if at is not None:
            parts += (text[done : found.start()], replacement)
            done = at + 1
    if not parts:
        return text
    parts.append(text[done:])
    return "".join(parts)


def _mask_url_secrets(match: re.Match[str]) -> str:
    return sub_params(PARAM_RE, mask_free_param, match.group(0))


def sanitize_url_credentials(text: str) -> str:
    """Redact username and password from URLs in *text* (e.g.
    ``https://user:pass@host/`` -> ``https://***:***@host/``), and the value of
    a query parameter named like a secret (``?private_token=***``).

    Used across extractors, build backends, and error loggers to prevent
    sensitive auth tokens from leaking into log and error messages (an SBOM
    field is written as it is: see :mod:`pitloom.core.credential_policy`).
    The userinfo ends at the last ``@`` before the first ``/`` or whitespace
    (:func:`userinfo_end`), so a password holding ``@``, ``?`` or ``#`` is
    redacted whole, and ``https://h?contact=me@x.org`` is a query. For a
    text that is one URL, use :func:`sanitize_url`.
    """
    text = _replaced_userinfo(mask_scp(text), _FREE_OPENER, "://***:***@", whole=False)
    return _URL_RE.sub(_mask_url_secrets, text)


def sanitize_url(url: str) -> str:
    """:func:`sanitize_url_credentials` for a text that is one URL: the
    userinfo is redacted whole even when it holds a newline or a space, and
    a secret parameter's value up to the next ``&``, ``#`` or the end, over
    a ``;``, a quote or white space."""
    masked = _replaced_userinfo(url, _WHOLE_OPENER, "://***:***@", whole=True)
    return sub_params(WHOLE_PARAM_RE, mask_param, masked)


#: A URL at the start of a text, also as ``Path`` collapses its ``//``
#: (``https:/host``) or a Windows ``Path`` writes it (``https:\\host``): a
#: whole scheme of two or more characters (so a Windows drive ``C:\\`` is
#: not one), ``:`` and ``/`` or ``\\``. A scheme starts with a letter, and
#: one only starts a run of scheme characters, so a search tries each run
#: once and stays linear (``a1a1...``).
URL_AS_PATH_RE = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]+:[/\\]")


#: The name prefix of the temporary directory a Git URL is checked out in.
CHECKOUT_DIR_PREFIX = "pitloom-git-"
#: What a message shows for that directory, so two runs read the same.
CHECKOUT_PLACEHOLDER = "<checkout>"
#: The name prefix of the temporary directory a PyPI release file is
#: downloaded into.
DOWNLOAD_DIR_PREFIX = "pitloom-pypi-"
#: What a message shows for that directory.
DOWNLOAD_PLACEHOLDER = "<download>"
#: The name prefix of the temporary directory the files of a Hugging Face
#: repository are downloaded into; a message shows it as a download.
HUB_DIR_PREFIX = "pitloom-hf-"
#: Each prefix and what a message shows for its directory.
_PLACEHOLDERS = {
    CHECKOUT_DIR_PREFIX: CHECKOUT_PLACEHOLDER,
    DOWNLOAD_DIR_PREFIX: DOWNLOAD_PLACEHOLDER,
    HUB_DIR_PREFIX: DOWNLOAD_PLACEHOLDER,
}
#: ``tempfile.mkdtemp`` appends eight characters of ``[a-z0-9_]``: a directory
#: of another name (a worktree called ``pitloom-git-fix``) is not the checkout.
_TEMP_DIR = re.compile(
    "("
    + "|".join(re.escape(prefix) for prefix in _PLACEHOLDERS)
    + r")[a-z0-9_]{8}(?![a-z0-9_])"
)
#: A word of a message: a run without a space, quote, bracket, backtick, ``=``,
#: ``,`` or ``;`` (where a path ends in a message that quotes, brackets or
#: follows ``KEY=``).
_WORD = re.compile(r"[^\s'\"`()\[\]<>=,;]+")
#: ``user@host:path``, the scp-style address of a repository.
_SCP_ADDRESS = re.compile(r"[\w.+-]+@[\w.-]+:")


#: Where a path in a message cannot go on: a quote, a bracket, a backtick,
#: ``=``, ``,``, ``;`` or a line break (a space can be inside a path).
_PATH_ENDS = "'\"`()[]<>=,;\n\r\t\v\f"
#: The root of an absolute path: a Windows drive, a UNC share or ``/``.
_ROOT_TEXT = r"[A-Za-z]:[\\/]|\\\\|/"
_ROOT_HERE = re.compile(_ROOT_TEXT)
#: Such a root at the start of a word (after a space or at the start).
_ROOT = re.compile(rf"(?:(?<= )|^)(?:{_ROOT_TEXT})")


def _has_prefix(text: str) -> bool:
    return any(prefix in text for prefix in _PLACEHOLDERS)


def _masked_word(word: str) -> str | None:
    """*word* with its last temporary directory and all before it written
    as the placeholder, or ``None`` when it holds none or is an address."""
    if not _has_prefix(word) or "://" in word or _SCP_ADDRESS.match(word) is not None:
        return None
    last = deque(_TEMP_DIR.finditer(word), maxlen=1)
    if not last:
        return None
    return _PLACEHOLDERS[last[0].group(1)] + word[last[0].end() :]


def _path_start(text: str, low: int, word_start: int) -> int:
    """Where the path holding the word at *word_start* starts: the word
    itself when it starts at a root, else the last root before it on the
    same stretch of text (back over spaces: ``C:\\Users\\John Smith\\...``),
    not before *low* or a character of :data:`_PATH_ENDS`."""
    if _ROOT_HERE.match(text, word_start) is not None:
        return word_start
    stretch = max((text.rfind(c, low, word_start) for c in _PATH_ENDS), default=-1)
    low = max(low, stretch + 1)
    roots = deque(_ROOT.finditer(text[low:word_start]), maxlen=1)
    return low + roots[0].start() if roots else word_start


def mask_checkout(text: str) -> str:
    """*text* with the temporary checkout of a Git URL written as
    ``<checkout>``, and the temporary download directory of a PyPI URL or a
    Hugging Face repository as ``<download>``: each path holding the
    directory (``pitloom-git-``, ``pitloom-pypi-`` or ``pitloom-hf-`` and its
    eight random characters) becomes the
    placeholder and what follows the directory, so a path below it keeps its
    tail (``<checkout>/setup.cfg``, ``<download>/x.whl``). A path is read
    back from the word holding the directory to its root, over spaces
    (``C:\\Users\\John Smith\\AppData\\...``), up to a quote, bracket, ``=``
    or line break. A word that is an address
    (``https://host/o/pitloom-git-abcdefgh``, ``git@host:o/pitloom-git-
    abcdefgh``) is kept. One pass over the words; text without a prefix is
    returned as it is."""
    if not _has_prefix(text):
        return text
    parts: list[str] = []
    done = 0
    for word in _WORD.finditer(text):
        masked = _masked_word(word.group(0))
        if masked is None:
            continue
        start = _path_start(text, done, word.start())
        parts += (text[done:start], masked)
        done = word.end()
    parts.append(text[done:])
    return "".join(parts)
