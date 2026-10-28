# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A Git URL that the server redirects (GitLab's ``project`` to
``project.git``) is followed with every hop checked, and each redirect is one
``INFO:`` naming both URLs.

The servers are local ones (`loopback`), so the tests may open sockets to this
machine only.
"""

from __future__ import annotations

import gc
import http.server
import logging
import socket
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import cast
from urllib.parse import urlsplit

import pytest

from pitloom.extract.remote import _git_redirect
from pitloom.extract.remote._git_redirect import (
    MAX_REDIRECTS,
    PROBE_FAILED_INFO,
    REDIRECT_INFO,
    REDIRECT_REFUSED_WARNING,
    _carried_userinfo,
    _probe_url,
    resolve_git_url,
)
from pitloom.extract.remote.errors import RemoteSourceError

pytestmark = pytest.mark.loopback

Routes = Mapping[str, Callable[[int], str | None]]


def _no_redirect(_port: int) -> str | None:
    """A route that answers 200."""
    return None


@contextmanager
def _server(routes: Routes, seen: list[str] | None = None) -> Iterator[str]:
    """A local server: a route maps a path to a function of the server port
    returning the ``Location`` to redirect to (``""``: none given), or ``None``
    for a 200. Every
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
                if where:  # "" is a redirect that names no place
                    self.send_header("Location", where)
                self.end_headers()

        # pylint: disable-next=redefined-builtin
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
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
    masked = base.replace("http://", "http://***:***@")
    assert lines == [REDIRECT_INFO % (masked + "/g/p", masked + "/g/p.git")]
    assert "secret" not in caplog.text


@pytest.mark.parametrize(
    ("host", "kept"),
    [("127.0.0.1", True), ("localhost", False)],
    ids=["same-host", "other-host"],
)
def test_a_redirect_keeps_the_user_only_on_the_same_host(
    host: str, kept: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """The anonymous probe finds the redirect; the clone URL keeps the user
    information only on the same host. ``check_url`` and the log never see
    the secret."""
    checked: list[str] = []
    routes: Routes = {
        "/g/p/info/refs": lambda p: f"http://{host}:{p}/g/p.git/info/refs"
    }
    with _server(routes) as base, caplog.at_level(logging.INFO):
        with_user = base.replace("http://", "http://user:secret@")
        result = resolve_git_url(with_user + "/g/p", checked.append)
    target = base.replace("127.0.0.1", host) + "/g/p.git"
    expected = target.replace("http://", "http://user:secret@") if kept else target
    assert result == expected
    assert checked == [target]
    assert "secret" not in caplog.text and "user" not in caplog.text


@pytest.mark.parametrize(
    ("source", "target", "carried"),
    [
        ("https://u:t@host.example/g/p", "https://HOST.example/g/p.git", "u:t"),
        ("https://u:t@host.example/g/p", "https://host.example:443/x", "u:t"),
        ("https://u:t@host.example/g/p", "https://other.example/x", ""),
        ("https://u:t@host.example/g/p", "https://host.example:8443/x", ""),
        ("https://u:t@host.example/g/p", "http://host.example/x", ""),
        ("http://u:t@host.example/g/p", "https://host.example/x", ""),
        ("https://host.example/g/p", "https://host.example/x", ""),
        ("https://u:t@host.example:bad/g/p", "https://host.example/x", ""),
        ("https://u:t@host.example/g/p", "https://host.example:0/x", ""),
    ],
    ids=[
        "host-case",
        "default-port",
        "other-host",
        "other-port",
        "downgrade",
        "upgrade",
        "no-user",
        "bad-port",
        "port-zero",
    ],
)
def test_the_user_is_carried_only_to_the_same_origin(
    source: str, target: str, carried: str
) -> None:
    """Scheme, host (any case) and port (default filled in) must all match."""
    assert _carried_userinfo(source, urlsplit(target)) == carried


def test_a_target_with_its_own_user_keeps_its_own() -> None:
    """A target that names a user keeps it; ``check_url`` sees neither."""
    checked: list[str] = []
    routes: Routes = {
        "/g/p/info/refs": lambda p: f"http://other:own@127.0.0.1:{p}/g/q/info/refs"
    }
    with _server(routes) as base:
        result = resolve_git_url(
            base.replace("http://", "http://user:secret@") + "/g/p", checked.append
        )
    assert result == base.replace("http://", "http://other:own@") + "/g/q"
    assert checked == [base + "/g/q"]


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
        "//127.0.0.1:{port}/x/info/refs",
    ],
    ids=["file", "ftp", "ssh", "space", "protocol-relative"],
)
def test_an_odd_redirect_target_is_checked_as_a_local_url_or_dropped(
    location: str,
) -> None:
    """A scheme that is not http(s) is never followed (not even without a
    ``check_url``); a protocol-relative target reaches the check as an
    absolute URL on the server's own host and port, and another odd target
    ends the walk, quietly."""
    checked: list[str] = []
    routes: Routes = {"/g/p/info/refs": lambda port: location.format(port=port)}
    with _server(routes) as base:
        result = resolve_git_url(base + "/g/p", checked.append)
    if location.startswith("//"):
        # Resolved against the request's host and port, not another host.
        assert len(checked) == 1 and checked[0].startswith(base + "/")
    elif location.startswith("http://127.0.0.1/a"):
        assert len(checked) == 1 and checked[0].startswith("http://")
    else:
        assert not checked and result == base + "/g/p"


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
    with socket.socket() as closed:  # a port nothing listens on
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    url = f"http://127.0.0.1:{port}/g/p"
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


def test_a_slow_server_cannot_hold_the_walk(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """All probes of a URL together take at most the budget: the walk gives
    up on a server that is still silent, and says so, without a wall clock."""
    monkeypatch.setattr(_git_redirect, "PROBE_BUDGET_SECONDS", 0.3)
    release = threading.Event()

    def silent(_port: int) -> None:
        release.wait(10)

    try:
        with _server({"/g/p/info/refs": silent}) as base:
            with caplog.at_level(logging.INFO):
                assert resolve_git_url(base + "/g/p") == base + "/g/p"
    finally:
        release.set()
    assert "no answer in time" in caplog.text


def test_a_bad_port_is_an_invalid_url() -> None:
    """A port that is no number is ``git.url-invalid``."""
    with pytest.raises(RemoteSourceError) as excinfo:
        resolve_git_url("http://host:notaport/g/p")
    assert excinfo.value.code == "git.url-invalid"


@pytest.mark.parametrize(
    ("location", "why"),
    [
        ("file:///etc/info/refs", "only http and https are followed"),
        ("ssh://example.org/x/info/refs", "only http and https are followed"),
        ("/users/sign_in", "it does not lead to a repository (a sign-in page?)"),
    ],
    ids=["file", "ssh", "sign-in"],
)
def test_a_redirect_that_is_not_followed_is_said_in_a_warning(
    location: str, why: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Not following is never silent: one ``WARNING:`` names the URL asked,
    the target and why; the URL is then left to git."""
    with _server({"/g/p/info/refs": lambda _p: location}) as base:
        with caplog.at_level(logging.WARNING):
            assert resolve_git_url(base + "/g/p") == base + "/g/p"
    target = location if "://" in location else base + location
    assert [r.getMessage() for r in caplog.records] == [
        REDIRECT_REFUSED_WARNING % (base + "/g/p", target, why)
    ]


@pytest.mark.parametrize(
    ("routes", "_why"),
    [
        ({"/g/p/info/refs": lambda _p: None}, None),
        ({}, None),
    ],
    ids=["answers-200", "not-routed-200"],
)
def test_a_server_that_does_not_redirect_says_nothing(
    routes: Routes, _why: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """A plain 200 is the normal answer: no ``INFO:`` or ``WARNING:``."""
    with _server(routes) as base, caplog.at_level(logging.INFO):
        resolve_git_url(base + "/g/p")
    assert caplog.records == []


def test_a_probe_that_cannot_be_made_is_said_in_an_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unreachable server or an HTTP error: one ``INFO:`` with the reason; the
    URL goes to git, whose message the user sees."""
    with caplog.at_level(logging.INFO):
        down = "http://127.0.0.1:9/g/p"
        assert resolve_git_url(down) == down
    assert [r.getMessage() for r in caplog.records] == [
        PROBE_FAILED_INFO % (down, "ConnectionRefusedError")
    ]


def test_an_http_error_status_is_said_in_an_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 404 (a private or missing repository) is named, not swallowed."""

    class NotFound(http.server.BaseHTTPRequestHandler):
        """Answer every request with 404."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            """Answer 404."""
            self.send_response(404)
            self.end_headers()

        # pylint: disable-next=redefined-builtin
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Keep the test output quiet."""

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), NotFound)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/g/p"
    try:
        with caplog.at_level(logging.INFO):
            assert resolve_git_url(url) == url
    finally:
        server.shutdown()
        server.server_close()
    assert [r.getMessage() for r in caplog.records] == [
        PROBE_FAILED_INFO % (url, "HTTP 404")
    ]


@pytest.mark.parametrize(
    ("url", "probe"),
    [
        (
            "http://[::1]:8080/g/p",
            "http://[::1]:8080/g/p/info/refs?service=git-upload-pack",
        ),
        ("https://h/g/p/?x=1#f", "https://h/g/p/info/refs?service=git-upload-pack"),
        ("http://u:p@h:81/g/p", "http://h:81/g/p/info/refs?service=git-upload-pack"),
    ],
    ids=["ipv6", "query-and-fragment", "userinfo-and-port"],
)
def test_the_probe_url_is_the_path_of_the_repository(url: str, probe: str) -> None:
    """Scheme, host (IPv6 in brackets) and port, the path, ``/info/refs``."""
    assert _probe_url(url) == probe


def test_a_redirect_that_names_no_place_is_said_not_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The server answered 301 without a ``Location``: git is asked directly,
    and the ``INFO:`` says why."""
    with _server({"/g/p/info/refs": lambda _port: ""}) as base:
        with caplog.at_level(logging.INFO):
            assert resolve_git_url(base + "/g/p") == base + "/g/p"
    assert "HTTP 301 without a Location" in caplog.text


def test_the_probe_leaves_no_open_response_to_the_garbage_collector(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An HTTP error holds its response body; Python 3.14 reports a temporary
    file closed by the collector as an unraisable error, which this suite
    turns into a failure. Collect while the warnings are errors."""
    with _server(
        {"/g/p/info/refs": lambda port: f"http://127.0.0.1:{port}/o/r/info/refs"}
    ) as base:
        with caplog.at_level(logging.INFO):
            resolve_git_url(base + "/g/p")
    gc.collect()
