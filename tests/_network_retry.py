# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Retry a live fetch that a host answered with a transient server error.

A third-party host can answer one request with a 5xx and the next one fine
(``git.savannah.gnu.org`` answered ``RPC failed; HTTP 500 ... expected
flush after ref listing`` once, in the release gate).
:func:`retry_on_transient_server_error` runs a callable up to three times and
retries only when the failure is such an answer: HTTP 5xx, 429 or 408. A DNS
failure, a refused connection, a TLS error and any other 4xx are not retried;
they reach ``tests/_network.py`` at once. After the last attempt the last
error is raised unchanged, so ``skip_on_network_error()`` treats it as before
and strict mode (``PITLOOM_REQUIRE_NETWORK``) still fails on a persistent
outage.

See also: tests/_network.py, tests/_network_classify.py (what is a network
failure at all), tests/test_network_retry.py.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.error
from collections.abc import Callable
from typing import TypeVar

from pitloom.extract.remote.errors import RemoteSourceError

T = TypeVar("T")

log = logging.getLogger(__name__)

#: Waits (seconds) before the second and the third attempt.
RETRY_DELAYS: tuple[float, ...] = (5.0, 20.0)

#: HTTP statuses that are the server's momentary state, not the request's.
_TRANSIENT_4XX = frozenset({408, 429})

# How ``git`` (libcurl) words a transient answer in a ``RemoteSourceError``.
_TRANSIENT_TEXT = re.compile(
    r"\bHTTP (?:5\d\d|408|429)\b|returned error: (?:5\d\d|408|429)\b|"
    r"expected flush after ref listing|HTTP Error (?:5\d\d|408|429)\b",
    re.IGNORECASE,
)


def transient_server_cause_in_text(text: str) -> str | None:
    """Return the matched wording if *text* shows a transient server answer."""
    match = _TRANSIENT_TEXT.search(text)
    return match.group(0) if match else None


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code in _TRANSIENT_4XX
    if isinstance(exc, RemoteSourceError):
        return transient_server_cause_in_text(str(exc)) is not None
    return False


def transient_server_cause_of(exc: BaseException) -> str | None:
    """Return a description if *exc* (or its cause chain) is a transient
    server-side answer (HTTP 5xx, 429, 408), else ``None``.

    Walks ``__cause__``, then ``__context__`` unless ``raise ... from None``
    suppressed it, as :func:`tests._network_classify.network_cause_of` does.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if _is_transient(cur):
            return f"{type(cur).__name__}: {cur}"
        if cur.__cause__ is not None:
            cur = cur.__cause__
        else:
            cur = None if cur.__suppress_context__ else cur.__context__
    return None


def retry_on_transient_server_error(
    func: Callable[[], T],
    *,
    delays: tuple[float, ...] = RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call *func*; on a transient server answer wait and call it again.

    There is one attempt more than there are *delays* (three by default,
    after 5 s then 20 s). Any other failure, and the failure of the last
    attempt, is raised unchanged. *sleep* is a parameter so a test never waits.
    """
    for attempt, delay in enumerate(delays, start=1):
        try:
            return func()
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:
            cause = transient_server_cause_of(exc)
            if cause is None:
                raise
            log.info(
                "Live fetch attempt %d of %d failed (%s); retrying in %g s",
                attempt,
                len(delays) + 1,
                cause,
                delay,
            )
            sleep(delay)
    return func()
