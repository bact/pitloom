# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Decide whether a failure (an exception or captured text) is the network.

One explicit errno/winerror set and one message pattern serve both the
exception path (:func:`network_cause_of`) and the text path
(:func:`network_cause_in_text`), so the two cannot drift.

See also: tests/_network.py (skip and strict-mode helpers built on this),
tests/test_network_helpers.py.
"""

from __future__ import annotations

import errno
import http.client
import re
import socket
import ssl
import urllib.error

#: POSIX errnos of a network-level failure (plain ``OSError`` carries these).
_NETWORK_ERRNOS = frozenset(
    {
        errno.ENETUNREACH,
        errno.EHOSTUNREACH,
        errno.ECONNRESET,
        errno.ECONNREFUSED,
        errno.ETIMEDOUT,
        errno.ECONNABORTED,
    }
)
#: Windows Winsock codes: 10050-10054 (net down/unreachable/reset), 10060
#: (timeout), 10061 (refused), 10065 (host unreachable), 11001-11004 (DNS).
_NETWORK_WINERRORS = frozenset(
    {10050, 10051, 10052, 10053, 10054, 10060, 10061, 10065}
    | {11001, 11002, 11003, 11004}
)

# Message signatures of a network cause.
_NETWORK_TEXT = re.compile(
    r"urlopen error|URLError|SSLError|SSL:|CERTIFICATE_VERIFY|ConnectionError|"
    r"Connection (?:refused|reset|aborted)|ProxyError|Max retries exceeded|"
    r"Failed to establish a new connection|timed out|TimeoutError|"
    r"Name or service not known|nodename nor servname|getaddrinfo failed|"
    r"Temporary failure in name resolution|Network is unreachable|gaierror|"
    r"RemoteDisconnected|IncompleteRead|HTTP Error (?:429|5\d\d)|"
    r"WinError (?:1005[0-4]|10060|10061|10065|1100[1-4])|"
    r"Could not find a version that satisfies|No matching distribution",
    re.IGNORECASE,
)

# A traceback tail: ``pkg.mod.SomeError: message`` (not the CLI's ``ERROR:``).
_EXCEPTION_LINE = re.compile(
    r"^\s*(?:[\w.]+\.)?\w*(?:Error|Exception|gaierror|Disconnected|IncompleteRead"
    r"|timeout): "
)
# The CLI's ``ERROR: ...`` shape for a failure it wrapped.
_CLI_ERROR_LINE = re.compile(r"^ERROR:\s")
# A validator finding: its message quotes data and may contain any words.
_VALIDATION_FINDING = re.compile(
    r"\[(?:shacl|schema)\]|Value Node:|Focus Node:", re.IGNORECASE
)

# ``URLError`` reasons (plain strings) that are a malformed URL, not the network.
_URL_ERROR_LOCAL_REASONS = ("unknown url type", "no host given", "file not on local")

_NETWORK_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    socket.timeout,
    socket.gaierror,
    ssl.SSLError,
    http.client.HTTPException,
)


def network_cause_in_text(text: str) -> str | None:
    """Return the last exception line of *text* naming a network failure.

    Only traceback-tail and CLI ``ERROR:`` lines count, and never text that
    contains a validator finding (``[shacl]``/``[schema]``, ``Value Node:``):
    a finding quotes arbitrary data such as ``Request timed out``.
    """
    if _VALIDATION_FINDING.search(text):
        return None
    matches = [
        ln.strip()
        for ln in text.splitlines()
        if (_EXCEPTION_LINE.match(ln) or _CLI_ERROR_LINE.match(ln))
        and _NETWORK_TEXT.search(ln)
    ]
    return matches[-1] if matches else None


def _is_network_oserror(exc: OSError) -> bool:
    """Whether a plain ``OSError`` carries a network errno or winerror."""
    return exc.errno in _NETWORK_ERRNOS or (
        getattr(exc, "winerror", None) in _NETWORK_WINERRORS
    )


def _is_network_exception(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return _is_network_exception(reason)
        return not str(reason).startswith(_URL_ERROR_LOCAL_REASONS)
    if isinstance(exc, http.client.InvalidURL):
        return False
    if isinstance(exc, _NETWORK_EXCEPTIONS):
        return True
    return isinstance(exc, OSError) and _is_network_oserror(exc)


def network_cause_of(exc: BaseException) -> str | None:
    """Return a description if *exc* (or its cause chain) is a network failure.

    An HTTP error status counts only when transient (429 or 5xx); a 4xx is
    a real answer and stays a failure. A malformed URL is not the network.
    A plain ``OSError`` counts only with a network errno/winerror. The walk
    follows ``__cause__``, then ``__context__`` unless ``raise ... from None``
    suppressed it.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if _is_network_exception(cur):
            return f"{type(cur).__name__}: {cur}"
        if cur.__cause__ is not None:
            cur = cur.__cause__
        else:
            cur = None if cur.__suppress_context__ else cur.__context__
    return None
