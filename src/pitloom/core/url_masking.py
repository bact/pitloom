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

* Standard library only. This module imports no other Pitloom module, so
  :mod:`pitloom.logging_config` and any extractor can import it without a
  cycle.
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
from urllib.parse import unquote

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
]

#: ``://`` and a userinfo (non-empty, up to the last ``@`` before a ``/`` or
#: whitespace: a password holding ``?`` or ``#`` is masked whole).
_URL_USERINFO_RE = re.compile(r"://[^/\s@][^/\s]*@")


#: A URL in a text, to its end at whitespace.
_URL_RE = re.compile(r"://\S+")

#: A query or fragment parameter in free text, as ``(delimiter, name,
#: value)``; the value ends at white space. The name has no length bound: it
#: is a run of name characters after one delimiter, so a failed match
#: backtracks over that run only and matching stays linear.
_PARAM_RE = re.compile(r"([?&;#])([\w.%-]+)=([^&;#\s]*)")
#: The same in a text that is one URL (:func:`sanitize_url`): the value runs
#: over a space or a line break, to the next delimiter, a quote or the end.
_WHOLE_PARAM_RE = re.compile(r"([?&;#])([\w.%-]+)=([^&;#'\"]*)")

#: Words naming a secret: a parameter is named by one, or its last word is
#: one (``access_token``, ``db-password``, ``accessToken``,
#: ``X-Amz-Signature``).
_SECRET_WORDS = (
    *("token", "key", "secret", "password", "passwd", "signature", "sig"),
    *("jwt", "credential", "credentials", "auth"),
)
#: Lower-case names of a parameter that holds a secret, matched whole.
_SECRET_NAMES = frozenset(
    {*_SECRET_WORDS, "apikey", "pass", "pwd", "pw", "authorization"}
)
#: The endings of such a name: a separator and a word (``monkey`` and
#: ``author`` are not secrets).
_SECRET_ENDINGS = tuple(sep + word for word in _SECRET_WORDS for sep in "_-")
#: Where a camelCase name starts a word: ``accessToken`` is read as
#: ``access_token``.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

#: ``://`` and a userinfo of a text that is one URL: up to the last ``@``
#: before the first ``/``, whatever characters (a newline, a space, a ``\\``)
#: it holds. ``:/`` too, for a URL a POSIX path normalisation collapsed, and
#: ``:\\``, for one a Windows path wrote, where it ends at either separator.
_WHOLE_URL_USERINFO_RE = re.compile(r":(?:/{1,2}[^/@][^/]*|\\{1,2}[^/\\@][^/\\]*)@")


def _mask_param(match: re.Match[str]) -> str:
    delimiter, name, value = match.groups()
    plain = unquote(name) if "%" in name else name
    if not plain.islower():
        plain = _CAMEL_BOUNDARY.sub("_", plain).lower()
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
    userinfo is redacted whole even when it holds a newline or a space, and
    a secret parameter's value up to the next delimiter, quote or the end."""
    return _WHOLE_PARAM_RE.sub(
        _mask_param, _WHOLE_URL_USERINFO_RE.sub("://***:***@", url)
    )


#: A URL in a path as given, also as ``Path`` collapses its ``//``
#: (``https:/host``) or a Windows ``Path`` writes it (``https:\\host``): a
#: whole scheme of two or more characters (so a Windows drive ``C:\\`` is
#: not one), ``:`` and ``/`` or ``\\``. A digit before it is not part of it
#: (``1https://``): a scheme starts with a letter.
URL_AS_PATH_RE = re.compile(r"(?<![A-Za-z+.-])[A-Za-z][A-Za-z0-9+.-]+:[/\\]")
#: The quotes a message puts around a path it names.
_QUOTES = "'\""


def _url_end(text: str, start: int) -> int:
    """Where the URL starting at *start* in *text* ends: at the quote
    closing the one before it (``'https://...' (choose from``), else at the
    end of *text* (a path or URL can hold a space)."""
    quote = text[start - 1] if start else ""
    end = text.find(quote, start) if quote and quote in _QUOTES else -1
    return len(text) if end == -1 else end


def _masked_url(url: str) -> str:
    """*url*, which starts at a :data:`URL_AS_PATH_RE` match, masked
    (:func:`sanitize_url`) and read with ``://`` after its scheme; as it is
    when it holds nothing to mask.

    After ``:/`` (typed, or a POSIX path's) a ``\\`` is a character of the
    URL. After ``:\\`` (a Windows path's) every ``\\`` is read as ``/``, but
    it may as well have been a character of the password: the two cannot be
    told apart, so the userinfo is masked to the last ``@`` of *url*, which
    may mask a path's ``@`` too but never leaves a password shown."""
    if "@" not in url and "=" not in url:
        return url
    scheme, _, rest = url.partition(":")
    body = rest.lstrip("/\\")
    windows = rest.startswith("\\")
    if windows:
        body = body.replace("\\", "/")
    restored = f"{scheme}://{body}"
    at = body.rfind("@") if windows else -1
    masked = sanitize_url(
        f"{scheme}://***:***@{body[at + 1 :]}" if at > 0 else restored
    )
    return url if masked == restored else masked


def masked_given_path(text: str) -> str:
    """*text*, a path as given or a message naming one, with each URL in it
    masked (:func:`_masked_url`): a URL Pitloom does not read reaches a path
    check as a path, and a line names it without its credentials. A URL
    runs to the end of *text*, or to the quote closing the one before it.
    *text* is returned as it is when no URL holds anything to mask. The one
    masker of a path as given and of an ``ERROR:`` line
    (:func:`pitloom.logging_config.print_error`)."""
    parts: list[str] = []
    done = 0
    while (found := URL_AS_PATH_RE.search(text, done)) is not None:
        end = _url_end(text, found.start())
        parts += (text[done : found.start()], _masked_url(text[found.start() : end]))
        done = end
    if not parts:
        return text
    parts.append(text[done:])
    return "".join(parts)


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
