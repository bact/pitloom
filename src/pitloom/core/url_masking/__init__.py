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
"""

from __future__ import annotations

import re
from collections import deque

from pitloom.core.url_masking._params import (
    PARAM_RE,
    WHOLE_PARAM_RE,
    mask_free_param,
    mask_param,
)
from pitloom.core.url_masking._scan import masked_once

__all__ = [
    "CHECKOUT_DIR_PREFIX",
    "CHECKOUT_PLACEHOLDER",
    "DOWNLOAD_DIR_PREFIX",
    "DOWNLOAD_PLACEHOLDER",
    "HUB_DIR_PREFIX",
    "URL_AS_PATH_RE",
    "mask_checkout",
    "masked_given_path",
    "sanitize_url",
    "sanitize_url_credentials",
    "url_without_credentials",
]

#: ``://`` and a userinfo (non-empty, up to the last ``@`` before a ``/`` or
#: whitespace: a password holding ``?`` or ``#`` is masked whole).
_URL_USERINFO_RE = re.compile(r"://[^/\s@][^/\s]*@")


#: A URL in a text, to its end at whitespace.
_URL_RE = re.compile(r"://\S+")

#: ``://`` and a userinfo of a text that is one URL: up to the last ``@``
#: before the first ``/``, whatever characters (a newline, a space, a ``\\``)
#: it holds. ``:/`` too, for a URL a POSIX path normalisation collapsed, and
#: ``:\\``, for one a Windows path wrote, where it ends at either separator.
_WHOLE_URL_USERINFO_RE = re.compile(r":(?:/{1,2}[^/@][^/]*|\\{1,2}[^/\\@][^/\\]*)@")


def _mask_url_secrets(match: re.Match[str]) -> str:
    return PARAM_RE.sub(mask_free_param, match.group(0))


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
    userinfo is redacted whole even when it holds a newline or a space, and
    a secret parameter's value up to the next ``&``, ``;``, ``#`` or the
    end, over a quote or white space."""
    return WHOLE_PARAM_RE.sub(
        mask_param, _WHOLE_URL_USERINFO_RE.sub("://***:***@", url)
    )


#: A URL at the start of a text, also as ``Path`` collapses its ``//``
#: (``https:/host``) or a Windows ``Path`` writes it (``https:\\host``): a
#: whole scheme of two or more characters (so a Windows drive ``C:\\`` is
#: not one), ``:`` and ``/`` or ``\\``. A scheme starts with a letter, and
#: one only starts a run of scheme characters, so a search tries each run
#: once and stays linear (``a1a1...``).
URL_AS_PATH_RE = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]+:[/\\]")
#: How many times :func:`masked_given_path` masks a text at most. A ``/`` or
#: white space in a secret value does not end a user information, so the
#: masking of one URL uncovers nothing of its own; a later URL masked in
#: another context (quoted or not) can take away the stop that ended an
#: earlier URL's (``u@"https:\h&u@:ab:\#sig=/a/b" ?\a/b'u:p@``). Random and
#: searched texts settle after two masking passes.
_MASK_PASSES = 4


def masked_given_path(text: str, *, line: bool = False) -> str:
    """*text*, a path as given or a message naming one, with the credentials
    of each URL in it replaced: the user information by ``***:***``, a
    secret parameter's value by ``***``; every other character is printed as
    given, so a path that only looks like a URL keeps its separators. A URL
    reaches a path check as a path, and a line names it without its
    credentials. The user information runs to the last ``@`` before the
    next ``/`` or the end of *text*, and in a message *line* before the next
    white space (``URL=https://h: unreachable; contact a@b.org`` keeps the
    address), either not in a secret parameter's value (masking the value
    would uncover a later ``@``); a quote is a character of it, never its
    end. When its ``@`` is in a secret value, the rest of that value is
    masked too (``https://u:p?token=x@h/x`` prints ``https://***:***@***``:
    RFC 3986 reads ``x@h/x`` as the token's). The rest of a URL runs to the
    end of *text*, or to the quote closing the one before it: one no
    backslash escapes, before white space or the end (after at most four
    characters ending a sentence: ``'...': not found``), so a quote inside
    a value does not close it. In a *line* a URL that is not quoted ends at
    the first white space after its user information, and each URL of the
    line is masked. A secret value runs to the next ``&``, ``;``, ``#`` or
    the URL's end, over a quote, and over white space unless in a *line*
    outside quotes. The masked text is masked again until nothing changes,
    at most :data:`_MASK_PASSES` times (a URL masked in a quoted context
    can take away the stop that ended an earlier URL's user information),
    so masking a masked text changes nothing unless a text needs more
    passes than that; none found so far needs more than two. The one
    masker of a path as given and of an ``ERROR:`` line
    (:func:`pitloom.logging_config.print_error`).

    After one separator (``https:/u:p@h``, a ``//`` a path collapsed) a
    scheme has a user information unless a ``/`` or ``\\`` comes before it
    (``/x/T10:/a@b`` is a path); a scheme a URL uses has one there too
    (:data:`_URL_SCHEMES`: ``/cwd/https:/u:p@h``). So a relative path
    ``backup:/u@h/x`` is read as a collapsed URL and its ``u`` masked: a
    credential shown costs more than a path's ``@`` hidden.

    Out of scope: a password holding a raw ``/``, or in a *line* white
    space, is not a user information (RFC 3986 percent-encodes both), so it
    is not masked. Accepted partial leaks, none showing the start of a
    secret: in a *line*, a secret value holding a space in a URL that is not
    quoted is masked to the space (``?token=SEC RET`` prints ``?token=***
    RET``), and the punctuation ending a sentence or a quotation is kept
    after a value, so a secret ending in it shows that end
    (``?token=abc...`` prints ``?token=***...``, ``?token=ab'`` prints
    ``?token=***'``); in a quoted URL, a secret value holding the URL's
    quote before white space or the end, after at most four such
    punctuation characters, is masked to that quote (``'...?token=ab'.
    cd'`` prints ``'...?token=***'. cd'``); a value ending in a backslash
    escapes the closing quote, so its URL runs on to the next quote that
    closes.
    """
    masked = masked_once(text, line=line)
    passes = 1
    while masked != text and passes < _MASK_PASSES:
        text, masked = masked, masked_once(masked, line=line)
        passes += 1
    return masked


def url_without_credentials(url: str) -> str:
    """*url*, one URL, without its user information (``https://user:pass@
    host/`` -> ``https://host/``) and with the value of a query parameter
    named like a secret masked (:func:`sanitize_url_credentials`): the URL
    to keep where a credential must not be (a clone's ``.git/config``)."""
    return sanitize_url_credentials(_WHOLE_URL_USERINFO_RE.sub("://", url))


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
