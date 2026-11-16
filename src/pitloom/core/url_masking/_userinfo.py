# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where the user information of a URL ends: the one rule the masker
(:func:`pitloom.core.url_masking.masked_given_path`), the detector
(:func:`pitloom.core.url_masking.find_url_credentials`) and the Git
credential split read it by.

See also: :mod:`pitloom.core.url_masking` (the public functions) and
:mod:`pitloom.core.url_masking._scan` (the masker's scanner). Standard
library only.

A URL is read as ``urllib`` and git read it: the user information runs
from after ``scheme://`` to the last ``@`` before the end of the authority
(the first ``/``, or where the masker's line reading ends a URL; each caller
says where that is), and a quote, an angle bracket, a backtick or white
space in it is a character of it (RFC 3986 allows ``'``).

A *break* before that ``@`` (``?`` or ``#``) belongs to the user information
only when the *head*, the text before the first break, reads as
``user:password`` (a ``:`` not followed by a port number only, so
``https://h:8080?x=a@b`` and ``https://h:?x=a@b`` are a host and a query), or
holds an ``@``. But when the head's last ``@`` is followed by a host
(``https://u:PW@h?mail=a@b.org``, ``https://TOKEN@h?c=me@x.org``), the user
information ends at that ``@``, as ``urllib`` and git read it. Else there is
none (``https://h?contact=me@x.org``). An empty user information
(``https://@h``) is none.
"""

from __future__ import annotations

import re

from pitloom.core.url_masking._tokens import TOKEN_PREFIXES

__all__ = [
    "SCP_USERINFO_RE",
    "has_userinfo",
    "is_account_name",
    "mask_scp",
    "split_userinfo",
    "userinfo_end",
]

#: What may break a user information.
_URL_BREAKS = re.compile(r"[?#]")
#: A port number, which a ``:`` before a break may be followed by; an empty
#: one too (``h:?x`` is a host) unless a masker reads it (``u:?pw@h``).
_PORT = re.compile(r"[0-9]+")
#: A host and port (RFC 3986 ``reg-name``, an IP literal), not empty.
_HOST = re.compile(r"(?:\[[0-9A-Fa-f:.]+\]|[\w.~%!$&'()*+,;=-]+)(?::[0-9]*)?")
#: ``scheme://`` at the start of a text that is one URL.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")


def _reads_as_password(head: str, *, widest: bool) -> bool:
    """Whether *head*, the text of an authority before its first break,
    reads as ``user:password``: a ``:`` not followed by a port number only.
    An empty port is a port (``https://h:?x=a@b`` is a host and a query,
    as ``urllib`` reads it), except for a masker (*widest*), which reads
    ``u:?pw@h`` as an empty password before the break and the start of one.
    A bracketed IPv6 host (``[::1]:8080``) is no password."""
    if head.startswith("[") and "]" in head:
        return False
    _, colon, rest = head.partition(":")
    if not colon:
        return False
    if not rest and not widest:
        return False
    return _PORT.fullmatch(rest) is None


def userinfo_end(
    text: str, start: int, end: int, *, widest: bool = False
) -> int | None:
    """The index of the ``@`` that ends the user information of the
    authority of *text* that starts at *start* (after ``scheme://``) and
    ends at *end* (the caller's first ``/``), or ``None`` when it has none
    (the rule: :mod:`pitloom.core.url_masking._userinfo`). With *widest* (a
    masker), a
    head that reads as ``user:password`` or holds an ``@`` always runs to
    the last ``@``, never to the head's: masking ``https://u:PW@h?m=a@b.org``
    as ``https://***:***@b.org`` hides the host, but no password the head's
    ``@`` only seems to end (``https://u:"@SECRET?x@h``). Reads *text* from
    *start* to *end* at most three times."""
    at = text.rfind("@", start, end)
    if at <= start:
        return None
    return _ruled_end(text, start, at, widest=widest)


def _ruled_end(text: str, start: int, at: int, *, widest: bool) -> int | None:
    """The rule of :func:`userinfo_end` on the user information from *start*
    to the ``@`` at *at*."""
    first = _URL_BREAKS.search(text, start, at)
    if first is None:
        return at
    inner = text.rfind("@", start, first.start())
    if (
        not widest
        and inner >= start
        and _HOST.fullmatch(text, inner + 1, first.start())
    ):
        return inner if inner > start else None
    if inner >= start or _reads_as_password(text[start : first.start()], widest=widest):
        return at
    return None


def split_userinfo(url: str) -> tuple[str, str] | None:
    """*url*, a text that is one URL (``scheme://...``), without its user
    information, and that user information as written (not decoded), or
    ``None`` when it has none: ``https://u:p?x@h/r`` is
    ``("https://h/r", "u:p?x")``. The Git credential split takes the user
    information out of a command line by it, so that git and the masker
    agree on what it is."""
    scheme = _SCHEME.match(url)
    if scheme is None:
        return None
    start = scheme.end()
    slash = url.find("/", start)
    at = userinfo_end(url, start, len(url) if slash < 0 else slash)
    if at is None:
        return None
    return url[:start] + url[at + 1 :], url[start:at]


#: The schemes read as a URL after one separator even in a path segment
#: (``/cwd/https:/u:p@h``, a URL a path resolved), the last ``+`` part
#: (``git+https``). Another scheme after one separator is a URL unless a
#: ``/`` or ``\\`` comes before it (``/x/T10:/a@b`` is a path).
_URL_SCHEMES = frozenset(
    {"http", "https", "ftp", "ftps", "sftp", "ssh", "git", "svn", "hg", "bzr"}
    | {"s3", "s3a", "s3n", "gs", "hf", "ws", "wss", "file", "rsync", "ldap"}
    | {"ldaps", "az", "abfs", "abfss", "hdfs", "smb", "webdav", "davs"}
)


def has_userinfo(text: str, scheme: int, separator: int) -> bool:
    """Whether the URL whose scheme starts at *scheme* can have a user
    information: after two separators, after one for a scheme a URL uses
    (:data:`_URL_SCHEMES`), else after one unless a path separator comes
    before the scheme (a path segment ``T10:``)."""
    if text.startswith(("//", "\\\\"), separator):
        return True
    name = text[scheme : separator - 1].lower()
    if name.rpartition("+")[2] in _URL_SCHEMES:
        return True
    return not scheme or text[scheme - 1] not in "/\\"


#: Schemes whose user name alone (``git@``) is how the server is reached.
_ACCOUNT_SCHEMES = frozenset({"ssh", "git+ssh", "ssh+git", "git"})
#: A plausible account name: lower case, a letter or ``_`` first, at most 32
#: characters (the POSIX portable user name, ``.`` allowed).
_ACCOUNT = re.compile(r"[a-z_][a-z0-9_.-]{0,31}")
#: An account name holds fewer digits than this; more reads as a token.
_ACCOUNT_DIGITS = 8


def is_account_name(scheme: str, userinfo: str) -> bool:
    """Whether *userinfo*, the user information of a URL of *scheme*, is an
    account name that reaches the server, not a credential: a user name
    alone (no ``:``) on an ``ssh`` or ``git`` scheme (:data:`_ACCOUNT_SCHEMES`,
    any case: ``SSH://git@h``), that is a plausible account name (lower
    case, at most 32 characters, fewer than eight digits) and has no
    token prefix
    (:data:`~pitloom.core.url_masking._tokens.TOKEN_PREFIXES`: ``ghp_``,
    ``glpat-``...).
    ``ssh://git:PW@h`` and ``ssh://ghp_TOKEN@h`` are credentials."""
    return (
        scheme.lower() in _ACCOUNT_SCHEMES
        and _ACCOUNT.fullmatch(userinfo) is not None
        and not userinfo.startswith(TOKEN_PREFIXES)
        and sum(char.isdigit() for char in userinfo) < _ACCOUNT_DIGITS
    )


#: The ``user:password@`` of an scp-style address (``alice:pw@host:o/r``): no
#: scheme, so no URL scan finds it. A ``/`` or ``\\`` is not in the
#: password (a drive or a path), and the host is followed by ``:`` and a path.
#: A host of two characters or more may be followed by an absolute path
#: (``host:/srv/r``); a one-character one is a drive (``C:\\``). An image
#: reference (``python:3.11@sha256:abc``) is not an address.
SCP_USERINFO_RE = re.compile(
    r"(?<![\w.+:@/\\-])[\w.+-]+:[^\s@/\\:]+@"
    r"(?!(?i:sha\d+|md5|blake\w+):)"
    r"(?=[\w.-]{2,}:(?!//)|[\w.-]:(?![/\\]))"
)


def mask_scp(text: str) -> str:
    """*text* with the user information of an scp-style address masked."""
    return SCP_USERINFO_RE.sub("***:***@", text)
