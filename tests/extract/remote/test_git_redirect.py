# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A Git URL that the server redirects (GitLab's ``project`` to
``project.git``) is followed with every hop checked, and each redirect is one
``INFO:`` naming both URLs.

The servers are local ones, so the tests opt out of the socket block.
"""

from __future__ import annotations

import http.server
import logging
import socket
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import cast

import pytest

from pitloom.extract.remote import _git_redirect
from pitloom.extract.remote._git_redirect import (
    MAX_REDIRECTS,
    REDIRECT_INFO,
    resolve_git_url,
)
from pitloom.extract.remote.errors import RemoteSourceError

pytestmark = pytest.mark.network

Routes = Mapping[str, Callable[[int], str | None]]


def _no_redirect(_port: int) -> str | None:
    """A route that answers 200."""
    return None


@contextmanager
def _server(routes: Routes, seen: list[str] | None = None) -> Iterator[str]:
    """A local server: a route maps a path to a function of the server port
    returning the ``Location`` to redirect to, or ``None`` for a 200. Every
    probed path is appended to *seen*."""

    class Handler(http.server.BaseHTTPRequestHandler):
        """Answer ``/info/refs`` probes from *routes*."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            """Redirect or answer 200 for the probed path."""
            path = self.path.split("?")[0]
            if seen is not None:
                seen.append(self.path)
            port = cast(tuple[str, int], self.server.server_address)[1]
            where = routes.get(path, _no_redirect)(port)
            if where is None:
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(301)
                self.send_header("Location", where)
                self.end_headers()

        def log_message(self, *_args: object) -> None:
            """Keep the test output quiet."""

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _absolute(path: str) -> Callable[[int], str]:
    return lambda port: f"http://127.0.0.1:{port}{path}?service=git-upload-pack"


_PROJECT: Routes = {"/g/p/info/refs": _absolute("/g/p.git/info/refs")}


@pytest.mark.parametrize(
    ("routes", "start", "expected"),
    [
        pytest.param(_PROJECT, "/g/p", "/g/p.git", id="absolute"),
        pytest.param(
            {"/g/p/info/refs": lambda _p: "/g/p.git/info/refs?service=git-upload-pack"},
            "/g/p",
            "/g/p.git",
            id="relative",
        ),
        pytest.param(
            {
                "/a/info/refs": _absolute("/b/info/refs"),
                "/b/info/refs": _absolute("/c.git/info/refs"),
            },
            "/a",
            "/c.git",
            id="two-hops",
        ),
        pytest.param(_PROJECT, "/g/p/", "/g/p.git", id="trailing-slash"),
        pytest.param(_PROJECT, "/g/p?x=1", "/g/p.git", id="query"),
        pytest.param(_PROJECT, "/g/p#frag", "/g/p.git", id="fragment"),
        pytest.param({}, "/g/p", "/g/p", id="no-redirect"),
        pytest.param(
            {"/g/p/info/refs": lambda _p: "/users/sign_in"},
            "/g/p",
            "/g/p",
            id="sign-in",
        ),
    ],
)
def test_a_redirect_to_another_repository_is_followed(
    routes: Routes, start: str, expected: str
) -> None:
    """Only a redirect that leads to another ``/info/refs`` is followed; the
    query and fragment of the URL given are not probed."""
    with _server(routes) as base:
        assert resolve_git_url(base + start) == base + expected


def test_a_followed_redirect_is_one_info_naming_both_urls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The ``INFO:`` holds the URL asked and the URL it led to, with no
    credentials; no redirect, no line."""
    with _server(_PROJECT) as base, caplog.at_level(logging.INFO):
        resolve_git_url(base.replace("http://", "http://user:secret@") + "/g/p")
        resolve_git_url(base + "/g/p.git")
    lines = [r.getMessage() for r in caplog.records if "redirected to" in r.message]
    asked = base.replace("http://", "http://***:***@") + "/g/p"
    assert lines == [REDIRECT_INFO % (asked, base + "/g/p.git")]
    assert "secret" not in caplog.text


def test_the_probe_sends_no_user_information_but_finds_the_redirect() -> None:
    """The probe is anonymous: the user is not in the request."""
    with _server(_PROJECT) as base:
        with_user = base.replace("http://", "http://user:pw@")
        assert resolve_git_url(with_user + "/g/p") == base + "/g/p.git"


def test_every_hop_is_checked_before_it_is_requested() -> None:
    """The target reaches ``check_url`` exactly once, as the URL that would be
    asked next; when it raises, the target is never asked."""
    checked: list[str] = []
    asked: list[str] = []

    def refuse(url: str) -> None:
        checked.append(url)
        raise RemoteSourceError("test.refused", "refused")

    routes: Routes = {
        "/g/p/info/refs": lambda port: f"http://127.0.0.1:{port}/inner/info/refs"
    }
    with _server(routes, asked) as base, pytest.raises(RemoteSourceError) as excinfo:
        resolve_git_url(base + "/g/p", refuse)
    assert excinfo.value.code == "test.refused"
    assert checked == [base + "/inner"]
    assert [p for p in asked if "inner" in p] == []


@pytest.mark.parametrize(
    "location",
    [
        "file:///etc/info/refs",
        "ftp://example.org/x/info/refs",
        "ssh://example.org/x/info/refs",
        "http://127.0.0.1/a b/info/refs",
        "//evil.example/x/info/refs",
    ],
    ids=["file", "ftp", "ssh", "space", "protocol-relative"],
)
def test_a_redirect_that_is_not_an_http_repository_is_not_followed_or_requested(
    location: str,
) -> None:
    """A scheme that is not http(s) is never followed (not even without a
    ``check_url``); a protocol-relative or odd target reaches the check as an
    absolute URL or the walk stops, quietly."""
    checked: list[str] = []
    with _server({"/g/p/info/refs": lambda _p: location}) as base:
        result = resolve_git_url(base + "/g/p", checked.append)
    if location.startswith(("//", "http://127.0.0.1/a")):
        assert len(checked) == 1 and checked[0].startswith("http://")
    else:
        assert checked == [] and result == base + "/g/p"


def test_a_redirect_loop_is_refused() -> None:
    """More than ``MAX_REDIRECTS`` hops is an error, not a hang."""
    routes: Routes = {"/loop/info/refs": _absolute("/loop/info/refs")}
    with _server(routes) as base, pytest.raises(RemoteSourceError) as excinfo:
        resolve_git_url(base + "/loop")
    assert excinfo.value.code == "git.too-many-redirects"


@pytest.mark.parametrize(
    ("hops", "resolves"),
    [(MAX_REDIRECTS - 1, True), (MAX_REDIRECTS, True), (MAX_REDIRECTS + 1, False)],
)
def test_exactly_the_limit_of_redirects_resolves(hops: int, resolves: bool) -> None:
    """A chain of ``MAX_REDIRECTS`` redirects ends at a repository that answers;
    one more is refused."""
    routes: Routes = {
        f"/h{i}/info/refs": _absolute(f"/h{i + 1}/info/refs") for i in range(hops)
    }
    with _server(routes) as base:
        if resolves:
            assert resolve_git_url(base + "/h0") == base + f"/h{hops}"
        else:
            with pytest.raises(RemoteSourceError):
                resolve_git_url(base + "/h0")


def test_an_unreachable_server_is_left_to_git() -> None:
    """The probe's own failure is not an error: git reports it with its
    message."""
    url = "http://127.0.0.1:9/g/p"
    assert resolve_git_url(url) == url


def test_a_server_that_sends_garbage_is_left_to_git() -> None:
    """A reply that is no HTTP: the probe degrades, it does not raise."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def answer() -> None:
        conn, _ = listener.accept()
        conn.recv(4096)
        conn.sendall(b"not http at all\r\n\r\n")
        conn.close()

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{listener.getsockname()[1]}/g/p"
    try:
        assert resolve_git_url(url) == url
    finally:
        listener.close()


def test_a_slow_server_cannot_hold_the_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    """All probes of a URL together take at most the budget."""
    monkeypatch.setattr(_git_redirect, "PROBE_BUDGET_SECONDS", 0.3)

    def slow(_port: int) -> None:
        time.sleep(3)

    started = time.monotonic()
    with _server({"/g/p/info/refs": slow}) as base:
        assert resolve_git_url(base + "/g/p") == base + "/g/p"
    assert time.monotonic() - started < 2


def test_a_bad_port_is_an_invalid_url() -> None:
    """A port that is no number is ``git.url-invalid``."""
    with pytest.raises(RemoteSourceError) as excinfo:
        resolve_git_url("http://host:notaport/g/p")
    assert excinfo.value.code == "git.url-invalid"
