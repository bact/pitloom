# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One hardened HTTPS client for the PyPI JSON API and the files it names,
and for the files of a Hugging Face repository.

See also: :mod:`pitloom.extract.remote.pypi` and
:mod:`pitloom.extract.remote._hub_files` (its callers),
:mod:`pitloom.extract.remote._http_watch` (the deadline and the opener),
:mod:`pitloom.extract.remote._http_credential` (a token's one origin) and
:mod:`pitloom.extract.remote._git_redirect` (the Git route's redirect probe,
whose per-hop check this follows).

Every URL requested, the first and each redirect target, is checked before
it is requested: its scheme is in :data:`ALLOWED_SCHEMES`, it has no user
information, its host (and port, when it is not the scheme's default) is in
the caller's allowlist, and the caller's ``check_url`` does not raise. The
opener has no redirect, cookie, authentication, ``file:``, ``ftp:`` or
``data:`` handler: a redirect is followed here, at most
:data:`MAX_REDIRECTS` times. An ``Authorization`` header is sent only with
the caller's :class:`~pitloom.extract.remote._http_credential.Credential`,
and only to a URL on its origin: never to a redirect target on another host,
port or scheme.

A read is bounded three ways: a timeout on each socket operation, an overall
deadline (a timer shuts the socket down at it, so a server that answers a
byte at a time cannot hold the caller longer), and a byte cap counted on the
bytes received. A ``Content-Length`` the server declares never gates the read;
it only tells a body cut short (a failed download).

Every failure is a :class:`~pitloom.extract.remote.errors.RemoteSourceError`
whose text is a catalogued line and whose ``pitloom_code`` is its code; a 404
or 410 is its subclass :class:`NotFoundError`, for the caller to name. Its
``code`` starts with the policy's route (``pypi.download-failed``,
``huggingface.download-failed``).
"""

from __future__ import annotations

import hashlib
import http.client
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast
from urllib.parse import urljoin, urlsplit

from pitloom.core.internal_error import InternalError
from pitloom.core.model_extract_limit import MAX_DOWNLOAD_BYTES_KEY
from pitloom.extract._extract_utils import json_nests_over
from pitloom.extract.remote._http_credential import Credential
from pitloom.extract.remote._http_errors import (
    CutShortError,
    NotFoundError,
    failed_error,
    not_found_error,
    remote_error,
    shown_url,
    timeout_error,
)
from pitloom.extract.remote._http_watch import Watch, opener
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.messages import (
    DOWNLOAD_LINE,
    JSON_MALFORMED,
    NOT_JSON_LINE,
    NOT_OBJECT_LINE,
    OVER_CAP,
    REDIRECT_REFUSED_LINE,
    SAVE_FAILED_LINE,
    SOURCE_LINE,
    TEMP_DIR_UNUSABLE,
    TOO_MANY_REDIRECTS_LINE,
    URL_MOVED,
    URL_REFUSED,
    Cap,
    emit,
)

log = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_SCHEMES",
    "MAX_REDIRECTS",
    "Credential",
    "CutShortError",
    "NotFoundError",
    "Policy",
    "fetch_json",
    "fetch_to_file",
    "remote_error",
    "shown_url",
    "url_refusal",
]

#: The schemes a request, or a redirect, may use.
ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})

#: Redirects followed before giving up.
MAX_REDIRECTS: Final = 5

#: Seconds to wait for one socket operation.
SOCKET_TIMEOUT_SECONDS: float = 30.0

#: Seconds for a whole JSON API request, redirects included.
JSON_DEADLINE_SECONDS: float = 120.0

#: Seconds for a whole file download, redirects included.
FILE_DEADLINE_SECONDS: float = 1800.0

#: The most bytes of a JSON API answer read.
JSON_MAX_BYTES: int = 64 * 1024 * 1024

#: The most levels of arrays and objects a JSON API answer may nest.
JSON_MAX_NESTING: Final = 64

#: Bytes asked of the socket per read.
CHUNK_BYTES: Final = 8192

#: The ``User-Agent`` of every request: this, a hyphen and the route.
USER_AGENT_PREFIX: Final = "pitloom-"

#: What a JSON API answer is read for, as its lines say it.
JSON_USE: Final = "for the PyPI release metadata"

_REDIRECT_CODES: Final = frozenset({301, 302, 303, 307, 308})
_NOT_FOUND_CODES: Final = frozenset({404, 410})
_DEFAULT_PORTS: Final = {"http": 80, "https": 443}


@dataclass(frozen=True)
class Policy:
    """Where a request may go: the hosts (``host``, or ``host:port`` for a
    port that is not the scheme's default), and the caller's own check of
    each URL, which raises for one that must not be fetched. *route* starts
    each error's code and the ``User-Agent``; *credential*, when given, is
    sent to its own origin only."""

    hosts: frozenset[str]
    check_url: Callable[[str], None] | None = None
    route: str = "pypi"
    credential: Credential | None = None


def url_refusal(url: str, hosts: Collection[str]) -> str | None:
    """Why *url* is not requested, or ``None`` when it may be: its scheme
    is not in :data:`ALLOWED_SCHEMES`, it holds user information, or its host
    (with its port when that is not the scheme's default) is not in *hosts*,
    compared in lower case."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "it is not a valid URL"
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return f"only {', '.join(sorted(ALLOWED_SCHEMES))} is followed"
    if "@" in parts.netloc:
        return "it holds user information"
    host = (parts.hostname or "").lower()
    if port is None or port == _DEFAULT_PORTS.get(scheme):
        allowed = host in hosts
    else:
        allowed = f"{host}:{port}" in hosts
    return None if host and allowed else f"its host is not {', '.join(sorted(hosts))}"


def _headers(url: str, policy: Policy) -> dict[str, str]:
    """The headers of the request to *url*: the policy's credential only
    when *url* is on its origin."""
    headers = {
        "User-Agent": USER_AGENT_PREFIX + policy.route,
        "Accept-Encoding": "identity",
    }
    if policy.credential is not None:
        authorization = policy.credential.header_for(url)
        if authorization is not None:
            headers["Authorization"] = authorization
    return headers


def _request_once(
    url: str, watch: Watch, policy: Policy
) -> http.client.HTTPResponse | str:
    """The response to *url*, or the ``Location`` of its redirect.

    Raises:
        NotFoundError: The server answered 404 or 410.
        RemoteSourceError: Any other failure.
    """
    route = policy.route
    remaining = watch.remaining()
    if remaining <= 0:
        raise timeout_error(url, watch, route)
    request = urllib.request.Request(url, headers=_headers(url, policy))
    watch.socket_seconds = min(SOCKET_TIMEOUT_SECONDS, remaining)
    try:
        response = opener(watch).open(request, timeout=watch.socket_seconds)
    except urllib.error.HTTPError as exc:
        # The error holds the response body: closed here, not left to the
        # garbage collector (Python 3.14 reports its temporary file then).
        with exc:
            location = exc.headers.get("Location") if exc.headers else None
            if exc.code in _REDIRECT_CODES and isinstance(location, str):
                return location
            if exc.code in _NOT_FOUND_CODES:
                raise not_found_error(url, exc, route) from None
            raise failed_error(url, exc, watch, route) from exc
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        OSError,
        ValueError,
    ) as exc:
        raise failed_error(url, exc, watch, route) from exc
    return cast(http.client.HTTPResponse, response)


def _checked(url: str, policy: Policy) -> None:
    """Pass *url* to the caller's check."""
    if policy.check_url is not None:
        policy.check_url(url)


def _open(url: str, policy: Policy, watch: Watch) -> http.client.HTTPResponse:
    """The response to *url*, redirects followed, each target checked
    before it is requested.

    Raises:
        InternalError: *url* itself is not allowed by *policy*.
        NotFoundError: The last URL asked answered 404 or 410.
        RemoteSourceError: A redirect is refused, there are too many, or
            the request failed.
        Exception: Whatever *policy*'s ``check_url`` raises, unchanged.
    """
    problem = url_refusal(url, policy.hosts)
    if problem is not None:
        raise InternalError(f"not a URL to fetch: {shown_url(url)} ({problem})")
    _checked(url, policy)
    current = url
    hop = 0
    while True:
        answer = _request_once(current, watch, policy)
        if not isinstance(answer, str):
            return answer
        target = urljoin(current, answer)
        why = url_refusal(target, policy.hosts)
        if why is not None:
            raise remote_error(
                f"{policy.route}.url-refused",
                URL_REFUSED,
                REDIRECT_REFUSED_LINE,
                url=shown_url(current),
                target=shown_url(target),
                why=why,
            )
        if hop >= MAX_REDIRECTS:
            raise remote_error(
                f"{policy.route}.too-many-redirects",
                URL_REFUSED,
                TOO_MANY_REDIRECTS_LINE,
                url=shown_url(url),
                number=MAX_REDIRECTS,
            )
        _checked(target, policy)
        emit(
            log,
            URL_MOVED,
            logging.INFO,
            url=shown_url(current),
            target=shown_url(target),
        )
        current = target
        hop += 1


def _check_complete(
    response: http.client.HTTPResponse,
    url: str,
    total: int,
    watch: Watch,
    route: str,
) -> None:
    """Raise when the body ended before its declared ``Content-Length``
    (``read1`` reads the early end of the connection as the end of the
    body). The declared length only tells a cut answer; it gates no read.

    Raises:
        RemoteSourceError: ``<route>.download-failed``.
    """
    declared = response.headers.get("Content-Length", "")
    if declared.isascii() and declared.isdigit() and total < int(declared):
        cut = CutShortError(f"the answer ended after {total} of {declared} bytes")
        raise failed_error(url, cut, watch, route)


def _chunks(
    response: http.client.HTTPResponse,
    url: str,
    watch: Watch,
    max_bytes: int,
    over: Callable[[], RemoteSourceError],
    route: str,
) -> Iterator[bytes]:
    """The body of *response* in chunks of at most :data:`CHUNK_BYTES`,
    each from one socket read; over *max_bytes* received, *over*'s error.

    Raises:
        RemoteSourceError: Over the cap, past the deadline, or a failed read.
    """
    total = 0
    while True:
        try:
            chunk = response.read1(CHUNK_BYTES)
        except (http.client.HTTPException, OSError, ValueError) as exc:
            raise failed_error(url, exc, watch, route) from exc
        # A socket shut at the deadline reads as the end of the body on POSIX;
        # on Windows the read waits for its timeout, which failed_error names.
        if watch.fired.is_set():
            raise timeout_error(url, watch, route)
        if not chunk:
            _check_complete(response, url, total, watch, route)
            return
        total += len(chunk)
        if total > max_bytes:
            raise over()
        yield chunk


def fetch_json(url: str, policy: Policy) -> dict[str, Any]:
    """The JSON object *url* answers, at most :data:`JSON_MAX_BYTES` and
    :data:`JSON_MAX_NESTING` levels deep, in :data:`JSON_DEADLINE_SECONDS`.

    Raises:
        NotFoundError: The server answered 404 or 410.
        RemoteSourceError: ``pypi.too-large`` (``over-cap``),
            ``pypi.response-invalid`` (``json-malformed``), or as
            :func:`_open`.
    """
    shown = shown_url(url)

    def over() -> RemoteSourceError:
        cap = Cap(JSON_MAX_BYTES, "byte", "pypi-json")
        return remote_error(
            "pypi.too-large",
            OVER_CAP,
            SOURCE_LINE,
            file=shown,
            use=JSON_USE,
            **cap.reason_values(),
        )

    with Watch(JSON_DEADLINE_SECONDS) as watch:
        response = _open(url, policy, watch)
        with response:
            chunks = _chunks(response, url, watch, JSON_MAX_BYTES, over, policy.route)
            raw = b"".join(chunks)
    if json_nests_over(raw, JSON_MAX_NESTING):
        cap = Cap(JSON_MAX_NESTING, "level", "pypi-json")
        raise remote_error(
            "pypi.too-large",
            OVER_CAP,
            SOURCE_LINE,
            file=shown,
            use=JSON_USE,
            **cap.reason_values(),
        )
    try:
        # Bytes, not text: a UTF-8 BOM is accepted, as the format allows.
        data = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise remote_error(
            "pypi.response-invalid",
            JSON_MALFORMED,
            NOT_JSON_LINE,
            file=shown,
            use=JSON_USE,
            failure=exc,
        ) from exc
    if not isinstance(data, dict):
        raise remote_error(
            "pypi.response-invalid",
            JSON_MALFORMED,
            NOT_OBJECT_LINE,
            file=shown,
            use=JSON_USE,
        )
    return data


def fetch_to_file(
    url: str, policy: Policy, dest: Path, *, max_bytes: int, file: str
) -> tuple[str, int]:
    """Download *url* into the new file *dest*, in
    :data:`FILE_DEADLINE_SECONDS`, and return the SHA-256 (lower-case hex)
    and the size of the bytes received. *file* names the file in a message.
    *dest* is left partly written on a failure (the caller's temporary
    directory removes it).

    Raises:
        NotFoundError: The server answered 404 or 410.
        RemoteSourceError: ``<route>.too-large`` (``over-cap``): more than
            *max_bytes* received, whatever ``Content-Length`` declared;
            ``<route>.save-failed`` (``temp-dir-unusable``): *dest* cannot be
            created or written (a full disk, a path too long), which is no
            network failure; past the deadline, a failed read, or as
            :func:`_open`.
    """
    route = policy.route

    def over() -> RemoteSourceError:
        cap = Cap(max_bytes, "byte", MAX_DOWNLOAD_BYTES_KEY)
        return remote_error(
            f"{route}.too-large",
            OVER_CAP,
            DOWNLOAD_LINE,
            file=file,
            **cap.reason_values(),
        )

    digest = hashlib.sha256()
    size = 0
    with Watch(FILE_DEADLINE_SECONDS) as watch:
        response = _open(url, policy, watch)
        with response:
            # Every read error is a RemoteSourceError from _chunks: an
            # OSError here is the local file's.
            try:
                with dest.open("xb") as out:
                    chunks = _chunks(response, url, watch, max_bytes, over, route)
                    for chunk in chunks:
                        digest.update(chunk)
                        size += len(chunk)
                        out.write(chunk)
            except OSError as exc:
                raise remote_error(
                    f"{route}.save-failed",
                    TEMP_DIR_UNUSABLE,
                    SAVE_FAILED_LINE,
                    file=file,
                    failure=exc,
                ) from exc
    return digest.hexdigest(), size
