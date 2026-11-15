# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where the user information of a URL ends: the one rule the masker
(:func:`pitloom.core.url_masking.masked_given_path`), the SBOM strip
(:func:`pitloom.core.url_masking.strip_url_secrets`), the refusal of a
stored value (:func:`pitloom.core.url_masking.holds_url_credentials`) and
the Git credential split read it by.

See also: :mod:`pitloom.core.url_masking` (the public functions) and
:mod:`pitloom.core.url_masking._scan` (the masker's scanner). Standard
library only.

The rule: the user information runs from after ``scheme://`` to the last
``@`` before the end of the authority (the first ``/``; each caller says
where that is). A *break* before that ``@`` (``?`` or ``#``, in free text
also white space, a quote, ``<``, ``>`` or a backtick) belongs to the user
information only when the *head*, the text before the first break, reads
as ``user:password`` (a ``:`` not followed by a port number only, so
``https://h:8080?x=a@b`` is a host and a query), or holds an ``@``. But when
the head's last ``@`` is followed by a host (``https://u:PW@h?mail=a@b.org``,
``https://TOKEN@h?c=me@x.org``), the user information ends at that ``@``,
as ``urllib`` and git read it. Else there is none
(``https://h?contact=me@x.org``). An empty user information
(``https://@h``) is none.
"""

from __future__ import annotations

import re

__all__ = [
    "ACCOUNT_SCHEMES",
    "is_account_name",
    "split_userinfo",
    "userinfo_end",
]

#: What may break a user information in a text that is one URL.
_URL_BREAKS = re.compile(r"[?#]")
#: The same in free text, where a URL also ends at white space, a quote, an
#: angle bracket or a backtick.
_TEXT_BREAKS = re.compile(r"[?#\s\"'<>`]")
#: A port number, which a ``:`` before a break may be followed by.
_PORT = re.compile(r"[0-9]+")
#: A host and port (RFC 3986 ``reg-name``, an IP literal), not empty.
_HOST = re.compile(r"(?:\[[0-9A-Fa-f:.]+\]|[\w.~%!$&'()*+,;=-]+)(?::[0-9]*)?")
#: ``scheme://`` at the start of a text that is one URL.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")


def _reads_as_password(head: str) -> bool:
    """Whether *head*, the text of an authority before its first break,
    reads as ``user:password``: a ``:`` not followed by a port number only
    (``u:?pw@h``: an empty password before the break is read as the start
    of one). A bracketed IPv6 host (``[::1]:8080``) does not."""
    if head.startswith("[") and "]" in head:
        return False
    _, colon, rest = head.partition(":")
    return bool(colon) and _PORT.fullmatch(rest) is None


def userinfo_end(
    text: str, start: int, end: int, *, free_text: bool = False, widest: bool = False
) -> int | None:
    """The index of the ``@`` that ends the user information of the
    authority of *text* that starts at *start* (after ``scheme://``) and
    ends at *end* (the caller's first ``/``), or ``None`` when it has none
    (the rule: :mod:`pitloom.core.url_masking._userinfo`). With *free_text*
    a white space, quote, ``<``, ``>`` or backtick is a break too. With
    *widest* (a masker), a head that reads as ``user:password`` or holds an
    ``@`` always runs to the last ``@``, never to the head's: masking
    ``https://u:PW@h?m=a@b.org`` as ``https://***:***@b.org`` hides the
    host, but no password the head's ``@`` only seems to end
    (``https://u:"@SECRET?x@h``). Reads *text* from *start* to *end* at
    most six times."""
    at = text.rfind("@", start, end)
    if at <= start:
        return None
    ruled = _ruled_end(text, start, at, _URL_BREAKS, widest=widest)
    if ruled is None or not free_text:
        return ruled
    return _ruled_end(text, start, ruled, _TEXT_BREAKS, widest=widest)


def _ruled_end(
    text: str, start: int, at: int, breaks: re.Pattern[str], *, widest: bool
) -> int | None:
    """The rule of :func:`userinfo_end` for one kind of *breaks*, on the
    user information from *start* to the ``@`` at *at*: first the URL's
    own (``?``, ``#``), then in free text the text's, on what the first left."""
    first = breaks.search(text, start, at)
    if first is None:
        return at
    inner = text.rfind("@", start, first.start())
    if (
        not widest
        and inner >= start
        and _HOST.fullmatch(text, inner + 1, first.start())
    ):
        return inner if inner > start else None
    if inner >= start or _reads_as_password(text[start : first.start()]):
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


#: Schemes whose user name alone (``git@``) is how the server is reached.
ACCOUNT_SCHEMES = frozenset({"ssh", "git+ssh", "ssh+git", "git"})
#: A plausible account name: lower case, a letter or ``_`` first, at most 32
#: characters (the POSIX portable user name, ``.`` allowed).
_ACCOUNT = re.compile(r"[a-z_][a-z0-9_.-]{0,31}")
#: The prefixes of access tokens a host issues (GitHub, GitLab, Slack).
_TOKEN_PREFIXES = (
    *("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"),
    *("glpat-", "gldt-", "glptt-", "xoxb-", "xoxp-"),
)
#: An account name holds fewer digits than this; more reads as a token.
_ACCOUNT_DIGITS = 8


def is_account_name(scheme: str, userinfo: str) -> bool:
    """Whether *userinfo*, the user information of a URL of *scheme*, is an
    account name that reaches the server, not a credential: a user name
    alone (no ``:``) on an ``ssh`` or ``git`` scheme (:data:`ACCOUNT_SCHEMES`,
    any case: ``SSH://git@h``), that is a plausible account name (lower
    case, at most 32 characters, fewer than eight digits) and has no
    token prefix (``ghp_``, ``glpat-``...). ``ssh://git:PW@h`` and
    ``ssh://ghp_TOKEN@h`` are credentials."""
    return (
        scheme.lower() in ACCOUNT_SCHEMES
        and _ACCOUNT.fullmatch(userinfo) is not None
        and not userinfo.startswith(_TOKEN_PREFIXES)
        and sum(char.isdigit() for char in userinfo) < _ACCOUNT_DIGITS
    )
