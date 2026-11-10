# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A local stand-in for the PyPI JSON API and its file host, for ``loopback``
tests of :mod:`pitloom.extract.remote.pypi`.

Each path answers a scripted :class:`Route`: a status, a body, headers, a
redirect, a body sent a byte at a time, a ``Content-Length`` that lies, or a
head sent a byte at a time. Every path asked is recorded, so a test can assert
that a refused URL was never requested. :func:`point_at` makes the resolver
ask this server for both the API and the files.

See also: tests/_loopback_server.py (the server class),
tests/extract/remote/test_pypi_fetch.py and test_pypi_http_fetch.py.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from pitloom.extract.remote import _http_fetch, pypi_url
from tests._loopback_server import ThreadingLoopbackHTTPServer

__all__ = [
    "Dist",
    "FakePypi",
    "Route",
    "file_entry",
    "point_at",
    "publish",
    "redirect",
    "release_json",
    "serving",
    "sha256_of",
]


@dataclass
class Route:
    """What one path answers.

    ``length``: the ``Content-Length`` sent; ``None`` the body's real length,
    ``-1`` none (the body ends when the connection closes). ``drip``: seconds
    between the body's bytes. ``drip_head``: ``body`` alone is sent, raw, a
    byte at a time, ``drip`` apart, as the head of the answer (no status
    line or header is sent first).
    """

    status: int = 200
    body: bytes = b""
    headers: Sequence[tuple[str, str]] = ()
    length: int | None = None
    drip: float = 0.0
    drip_head: bool = False
    #: The status line's reason phrase (the server's own text).
    reason: str | None = None


def redirect(location: str, status: int = 302) -> Route:
    """A route that redirects to *location*."""
    return Route(status=status, headers=(("Location", location),))


@dataclass
class FakePypi:
    """A running server: its base URL (``http://127.0.0.1:<port>``), its
    routes (a test may change them), every path asked, in order, and the
    header names of each request (lower case)."""

    base: str
    routes: dict[str, Route]
    seen: list[str] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    stopping: threading.Event = field(default_factory=threading.Event)

    @property
    def host(self) -> str:
        """``127.0.0.1:<port>``, as an allowlist names it."""
        return self.base.removeprefix("http://")

    def url(self, path: str) -> str:
        """The URL of *path* on this server."""
        return self.base + path


def sha256_of(data: bytes) -> str:
    """The SHA-256 of *data*, lower-case hex."""
    return hashlib.sha256(data).hexdigest()


def file_entry(
    filename: str,
    url: str,
    data: bytes,
    *,
    yanked: bool = False,
    reason: str | None = None,
    sha256: object = "",
) -> dict[str, Any]:
    """A file of a JSON answer's ``urls`` or ``releases`` list; *sha256*
    ``""`` is the real digest of *data*, ``None`` none at all."""
    kind = "bdist_wheel" if filename.endswith(".whl") else "sdist"
    digests = {} if sha256 is None else {"sha256": sha256 or sha256_of(data)}
    return {
        "filename": filename,
        "packagetype": kind,
        "url": url,
        "digests": digests,
        "size": len(data),
        "yanked": yanked,
        "yanked_reason": reason,
    }


def release_json(
    name: str,
    version: str,
    files: Sequence[Mapping[str, Any]],
    releases: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    yanked_reason: str | None = None,
) -> bytes:
    """A JSON API answer for *name*: ``info``, ``urls`` and, when given,
    ``releases``."""
    answer: dict[str, Any] = {
        "info": {"name": name, "version": version, "yanked_reason": yanked_reason},
        "urls": list(files),
    }
    if releases is not None:
        answer["releases"] = {k: list(v) for k, v in releases.items()}
    return json.dumps(answer).encode()


@dataclass(frozen=True)
class Dist:
    """A file of a release to publish: its bytes, its yank, its declared
    digest (``""`` the real one, ``None`` none) and its URL (``None``: on
    the fake server, ``/files/<filename>``)."""

    filename: str
    data: bytes = b"PK\x05\x06" + b"\x00" * 18
    yanked: bool = False
    reason: str | None = None
    sha256: object = ""
    url: str | None = None


def publish(
    fake: FakePypi,
    name: str,
    releases: Mapping[str, Sequence[Dist]],
    *,
    answered: str | None = None,
    yanked_reason: str | None = None,
) -> None:
    """Serve project *name*'s JSON answers (the project's, with every
    release, and each release's) and its files; *answered* is the name the
    answers give (default *name*), *yanked_reason* each release answer's
    ``info.yanked_reason``."""
    entries: dict[str, list[dict[str, Any]]] = {}
    for version, dists in releases.items():
        entries[version] = []
        for dist in dists:
            url = dist.url or fake.url(f"/files/{dist.filename}")
            entry = file_entry(
                dist.filename,
                url,
                dist.data,
                yanked=dist.yanked,
                reason=dist.reason,
                sha256=dist.sha256,
            )
            entries[version].append(entry)
            fake.routes[f"/files/{dist.filename}"] = Route(body=dist.data)
    shown = answered or name
    latest = list(releases)[-1] if releases else "0"
    fake.routes[f"/pypi/{name}/json"] = Route(
        body=release_json(shown, latest, entries.get(latest, []), entries)
    )
    for version, files in entries.items():
        fake.routes[f"/pypi/{name}/{version}/json"] = Route(
            body=release_json(shown, version, files, yanked_reason=yanked_reason)
        )


class _Server(ThreadingLoopbackHTTPServer):
    """The HTTP server, holding the :class:`FakePypi` it answers for."""

    fake: FakePypi


class _Handler(http.server.BaseHTTPRequestHandler):
    """Answer each path from the server's routes."""

    @property
    def fake(self) -> FakePypi:
        """The fake PyPI this request is for."""
        return cast(_Server, self.server).fake

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Answer the path asked."""
        fake = self.fake
        fake.seen.append(self.path)
        fake.headers.append({k.lower(): v for k, v in self.headers.items()})
        route = fake.routes.get(self.path.split("?")[0])
        try:
            if route is None:
                self.send_error(404)
            elif route.drip_head:
                self._drip(route.body, route.drip)
            else:
                self._answer(route)
        except OSError:
            pass  # the client hung up, as a refused read does

    def _answer(self, route: Route) -> None:
        self.send_response(route.status, route.reason)
        for name, value in route.headers:
            self.send_header(name, value)
        if route.length != -1:
            length = len(route.body) if route.length is None else route.length
            self.send_header("Content-Length", str(length))
        self.end_headers()
        if route.drip:
            self._drip(route.body, route.drip)
        else:
            self.wfile.write(route.body)

    def _drip(self, data: bytes, seconds: float) -> None:
        for index in range(len(data)):
            if self.fake.stopping.wait(seconds):
                return
            self.wfile.write(data[index : index + 1])
            self.wfile.flush()

    # pylint: disable-next=redefined-builtin
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Keep the test output quiet."""


@contextmanager
def serving(routes: Mapping[str, Route] | None = None) -> Iterator[FakePypi]:
    """A fake PyPI on ``127.0.0.1``, stopped on exit."""
    fake = FakePypi(base="", routes=dict(routes or {}))
    httpd = _Server(("127.0.0.1", 0), _Handler)
    httpd.fake = fake
    port = cast(tuple[str, int], httpd.server_address)[1]
    fake.base = f"http://127.0.0.1:{port}"
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield fake
    finally:
        fake.stopping.set()
        httpd.shutdown()
        httpd.server_close()


def point_at(monkeypatch: pytest.MonkeyPatch, fake: FakePypi) -> None:
    """Make the resolver ask *fake* for the JSON API (``/pypi/``) and the
    files, over plain http, which only a test allows."""
    monkeypatch.setattr(pypi_url, "API_BASE", fake.url("/pypi/"))
    monkeypatch.setattr(pypi_url, "FILE_HOSTS", frozenset({fake.host}))
    monkeypatch.setattr(_http_fetch, "ALLOWED_SCHEMES", frozenset({"http", "https"}))
