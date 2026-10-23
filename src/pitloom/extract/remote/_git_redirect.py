# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where a Git URL lives: follow the server's redirects, checking each hop.

A Git server may answer ``<url>/info/refs`` with a redirect: GitLab sends
``https://host/group/project`` to ``https://host/group/project.git``, and a
renamed GitHub repository goes to its new name. ``git`` runs with
``http.followRedirects=false``, since a redirect to an internal host would
bypass the caller's address check, so git alone fails with ``error: 301``.

:func:`resolve_git_url` follows the redirects itself, one hop at a time, and
passes each target to the caller's URL check before requesting it. The clone
then uses the final URL, with redirects still off. The user information of the
URL given is carried to a target on the same scheme, host and port only.
"""

from __future__ import annotations

import http.client
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git_url import scheme_allowed
from pitloom.logging_config import loggable, sanitize_url_credentials

log = logging.getLogger(__name__)

__all__ = [
    "MAX_REDIRECTS",
    "PROBE_FAILED_INFO",
    "REDIRECT_INFO",
    "REDIRECT_REFUSED_WARNING",
    "resolve_git_url",
]

#: Redirects followed before giving up.
MAX_REDIRECTS = 5

#: Seconds to wait for the server's answer to one socket operation of a probe.
PROBE_TIMEOUT_SECONDS = 20.0

#: Seconds for all the probes of one URL together: a server that answers a
#: byte at a time cannot hold the caller for longer.
PROBE_BUDGET_SECONDS = 60.0

#: ``log.info()`` format for a followed redirect. Arguments: the URL asked,
#: the URL it redirected to.
REDIRECT_INFO = "Git source: %s redirected to %s"

#: ``log.warning()`` format for a redirect that is not followed. Arguments: the
#: URL asked, the redirect target, why it is not followed.
REDIRECT_REFUSED_WARNING = "Git source: %s redirected to %s, which is not followed: %s"

#: ``log.info()`` format for a probe that could not be made. Arguments: the
#: URL asked, why.
PROBE_FAILED_INFO = (
    "Git source: could not check %s for a redirect (%s); asking git directly"
)

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_INFO_REFS = "/info/refs"
_PROBE_QUERY = "service=git-upload-pack"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report a redirect as an error instead of following it."""

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> None:
        return None


def _probe_url(url: str) -> str:
    """The ``/info/refs`` URL of the repository *url*: its scheme, host and
    port, and its path without a query or fragment (user information is left
    out: the probe is anonymous)."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    try:
        port = f":{parts.port}" if parts.port else ""
    except ValueError as exc:
        raise RemoteSourceError("git.url-invalid", f"Invalid URL: {exc}") from exc
    path = parts.path.rstrip("/") + _INFO_REFS
    return urlunsplit((parts.scheme, host + port, path, _PROBE_QUERY, ""))


@dataclass(frozen=True)
class _Probe:
    """What a probe found: the ``Location`` of a redirect, or why nothing was
    found (``None``: the server simply did not redirect)."""

    location: str | None = None
    failure: str | None = None


def _probe_of_status(exc: urllib.error.HTTPError) -> _Probe:
    """What the HTTP status *exc* says: a redirect's ``Location``, a failure
    (4xx, 5xx), or nothing."""
    if exc.code in _REDIRECT_CODES:
        location = exc.headers.get("Location")
        if location is None:
            return _Probe(failure=f"HTTP {exc.code} without a Location")
        return _Probe(location=location)
    return _Probe(failure=f"HTTP {exc.code}") if exc.code >= 400 else _Probe()


def _probe_once(probe_url: str) -> _Probe:
    """Ask *probe_url* once: its redirect, or why it cannot be asked (git then
    reports the problem itself)."""
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(
        probe_url, headers={"User-Agent": "pitloom-git-redirect-probe"}
    )
    try:
        with opener.open(request, timeout=PROBE_TIMEOUT_SECONDS):
            return _Probe()
    except urllib.error.HTTPError as exc:
        # The error holds the response body: closed here, not left to the
        # garbage collector (Python 3.14 reports its temporary file then).
        with exc:
            return _probe_of_status(exc)
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        OSError,
        ValueError,
    ) as exc:
        reason = getattr(exc, "reason", exc)
        return _Probe(failure=type(reason).__name__)


def _probe_within(probe_url: str, seconds: float) -> _Probe:
    """:func:`_probe_once` with an overall limit: a probe still waiting after
    *seconds* is given up on (its thread ends with its socket timeout)."""
    answer: list[_Probe] = []
    worker = threading.Thread(
        target=lambda: answer.append(_probe_once(probe_url)), daemon=True
    )
    worker.start()
    worker.join(max(seconds, 0.0))
    return answer[0] if answer else _Probe(failure="no answer in time")


def _shown(url: str) -> str:
    """*url* as written in a message: without credentials, escaped."""
    return loggable(sanitize_url_credentials(url))


def resolve_git_url(url: str, check_url: Callable[[str], None] | None = None) -> str:
    """The URL to clone for *url*: *url* itself, or where the Git server
    redirects its ``/info/refs`` to. Each hop is passed to *check_url*, which
    raises for an address that must not be fetched, before it is requested;
    *check_url* sees the hop without user information.

    The user information of the URL redirected from is kept on a target with
    the same scheme, host and port that has none of its own, and dropped on
    any other.

    A redirect that does not lead to another repository's ``/info/refs`` (a
    sign-in page) is not followed. All probes together take at most
    :data:`PROBE_BUDGET_SECONDS`. Each redirect is one ``INFO:``
    (:data:`REDIRECT_INFO`) naming both URLs.

    Raises:
        RemoteSourceError: ``git.too-many-redirects``, more than
            :data:`MAX_REDIRECTS` redirects, or ``git.url-invalid``.
    """
    current = url
    deadline = time.monotonic() + PROBE_BUDGET_SECONDS
    hop = 0
    while True:
        probe = _probe_url(current)
        found = _probe_within(probe, deadline - time.monotonic())
        if found.location is None:
            if found.failure:
                log.info(PROBE_FAILED_INFO, _shown(current), found.failure)
            return current
        target = urlsplit(urljoin(probe, found.location))
        refusal = _not_followed(target)
        if refusal:
            log.warning(
                REDIRECT_REFUSED_WARNING,
                _shown(current),
                _shown(target.geturl()),
                refusal,
            )
            return current
        if hop == MAX_REDIRECTS:
            raise RemoteSourceError(
                "git.too-many-redirects",
                f"{_shown(url)} redirects more than {MAX_REDIRECTS} times.",
            )
        userinfo, _at, host_port = target.netloc.rpartition("@")
        path = target.path.removesuffix(_INFO_REFS)
        base = urlunsplit((target.scheme, host_port, path, "", ""))
        if check_url is not None:
            check_url(base)
        if not userinfo:
            userinfo = _carried_userinfo(current, target)
        following = base
        if userinfo:
            following = urlunsplit(
                (target.scheme, f"{userinfo}@{host_port}", path, "", "")
            )
        log.info(REDIRECT_INFO, _shown(current), _shown(following))
        current = following
        hop += 1


def _origin(parts: SplitResult) -> tuple[str, str, int | None] | None:
    """The scheme, host (lower case) and port (the scheme's default when none
    is written) of *parts*, or ``None`` for a port that is no number."""
    try:
        port = parts.port
    except ValueError:
        return None
    default = {"http": 80, "https": 443}.get(parts.scheme.lower())
    return parts.scheme.lower(), (parts.hostname or ""), port or default


def _carried_userinfo(source: str, target: SplitResult) -> str:
    """The user information of *source* when *target* has the same origin,
    else ``""``."""
    # Credentials go only back to the server they were given for: never to
    # another host or port, and never from https down to http.
    parts = urlsplit(source)
    origin = _origin(parts)
    if origin is None or origin != _origin(target):
        return ""
    return parts.netloc.rpartition("@")[0]


def _not_followed(target: SplitResult) -> str | None:
    """Why the redirect to *target* is not followed, or ``None`` when it is."""
    if not scheme_allowed(target.geturl()):
        return "only http and https are followed"
    if not target.path.endswith(_INFO_REFS):
        return "it does not lead to a repository (a sign-in page?)"
    return None
