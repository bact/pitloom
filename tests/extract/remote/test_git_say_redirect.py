# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""What the redirect walk of a Git URL says, as the catalogue's lines after
``Git source: ``: a redirect followed (``url-moved``), one not followed
(``url-unsafe`` warning), more than five (``url-unsafe`` error, the code
``git.too-many-redirects`` kept), a probe that got no usable answer
(``git-redirect-unusable``, the reason named by status or error class) and a
port that is no number (``git-url-invalid``, no credential).

The servers are local ones (`loopback`), so the tests may open sockets to this
machine only.

See also: tests/extract/remote/test_git_redirect.py (the walk itself) and
tests/extract/remote/test_git_say.py (what a fetch decides).
"""

from __future__ import annotations

import http.server
import logging
import socket
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import cast

import pytest

from pitloom.extract.remote import _git_redirect
from pitloom.extract.remote._git_redirect import MAX_REDIRECTS, resolve_git_url
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import GIT_PREFIX, Line, Message, code_of, trusted_message
from pitloom.messages.git import GIT_REDIRECT_UNUSABLE, GIT_URL_PORT_LINE
from pitloom.messages.network import (
    GIT_REDIRECT_OUTCOME,
    REDIRECT_LINE,
    REDIRECT_REFUSED_WARNING_LINE,
    TOO_MANY_REDIRECTS_LINE,
    URL_MOVED,
    URL_REFUSED,
)
from tests._git_say_repos import printed
from tests._loopback_server import ThreadingLoopbackHTTPServer

pytestmark = [pytest.mark.loopback, pytest.mark.platform]

Routes = Mapping[str, Callable[[int], str | None]]
_UNUSABLE = GIT_REDIRECT_UNUSABLE.lines[0]


def _no_redirect(_port: int) -> str | None:
    """A route that answers 200."""
    return None


def _silent(release: threading.Event) -> Callable[[int], str | None]:
    """A route that answers nothing until *release* is set."""

    # pylint: disable-next=useless-return
    def route(_port: int) -> str | None:
        release.wait(10)
        return None

    return route


@contextmanager
def _server(routes: Routes, status: int = 301) -> Iterator[str]:
    """A local server: a route maps a path to a function of the server port
    returning the ``Location`` of a redirect (``""``: none given), or ``None``
    for a 200; a path of no route answers 200."""

    class Handler(http.server.BaseHTTPRequestHandler):
        """Answer ``/info/refs`` probes from *routes*."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            """Redirect, fail or answer 200."""
            port = cast(tuple[str, int], self.server.server_address)[1]
            where = routes.get(self.path.split("?")[0], _no_redirect)(port)
            if where is None:
                self.send_response(200)
            else:
                self.send_response(status)
                if where:
                    self.send_header("Location", where)
            self.end_headers()

        # pylint: disable-next=redefined-builtin
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Keep the test output quiet."""

    server = ThreadingLoopbackHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _to(path: str) -> Callable[[int], str]:
    return lambda port: f"http://127.0.0.1:{port}{path}?service=git-upload-pack"


def _said(message: Message, line: Line, **values: object) -> str:
    """*line* of *message* as the walk prints it."""
    return f"{line.level}: {GIT_PREFIX}{line.render(values)} [{message.code}]"


def _walk(url: str, caplog: pytest.LogCaptureFixture) -> tuple[str, list[str]]:
    """The URL the walk ends at, and the coded lines it said."""
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        result = resolve_git_url(url)
    return result, printed(caplog)


def test_a_followed_redirect_is_said_with_both_urls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    routes: Routes = {"/g/p/info/refs": _to("/g/p.git/info/refs")}
    with _server(routes) as base:
        result, said = _walk(base + "/g/p", caplog)
    assert result == base + "/g/p.git"
    assert said == [
        _said(URL_MOVED, REDIRECT_LINE, url=base + "/g/p", target=base + "/g/p.git")
    ]
    assert trusted_message(said[0]) is URL_MOVED


@pytest.mark.parametrize(
    ("location", "why"),
    [
        ("file:///etc/info/refs", "only http and https are followed"),
        ("ssh://example.org/x/info/refs", "only http and https are followed"),
        ("/users/sign_in", "it does not lead to a repository (a sign-in page?)"),
    ],
    ids=["file", "ssh", "sign-in"],
)
def test_a_redirect_not_followed_is_one_warning_and_git_asks_the_url(
    caplog: pytest.LogCaptureFixture, location: str, why: str
) -> None:
    with _server({"/g/p/info/refs": lambda _p: location}) as base:
        result, said = _walk(base + "/g/p", caplog)
        target = location if "://" in location else base + location
    assert result == base + "/g/p"
    expected = _said(
        URL_REFUSED,
        REDIRECT_REFUSED_WARNING_LINE,
        url=base + "/g/p",
        target=target,
        why=why,
        outcome=GIT_REDIRECT_OUTCOME,
    )
    assert said == [expected] and said[0].startswith("WARNING: ")
    assert trusted_message(said[0]) is URL_REFUSED


def test_a_redirect_target_with_a_credential_is_said_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    routes: Routes = {
        "/g/p/info/refs": lambda p: f"http://x:tok3n@127.0.0.1:{p}/users/sign_in"
    }
    with _server(routes) as base:
        _result, said = _walk(base + "/g/p", caplog)
    assert "tok3n" not in caplog.text and "tok3n" not in said[0]
    assert "http://***:***@127.0.0.1:" in said[0]


@pytest.mark.parametrize("hops", [MAX_REDIRECTS, MAX_REDIRECTS + 1], ids=["5", "6"])
def test_five_hops_pass_and_six_are_refused_with_the_code_kept(
    caplog: pytest.LogCaptureFixture, hops: int
) -> None:
    routes: Routes = {
        f"/h{i}/info/refs": _to(f"/h{i + 1}/info/refs") for i in range(hops)
    }
    with _server(routes) as base:
        if hops == MAX_REDIRECTS:
            result, said = _walk(base + "/h0", caplog)
            assert result == base + f"/h{hops}" and len(said) == hops
            return
        with pytest.raises(RemoteSourceError) as raised:
            resolve_git_url(base + "/h0")
        line = TOO_MANY_REDIRECTS_LINE.render({"url": base + "/h0", "number": 5})
    assert raised.value.code == "git.too-many-redirects"
    assert code_of(raised.value) == URL_REFUSED.code
    assert str(raised.value) == line
    assert trusted_message(f"ERROR: {line} [{URL_REFUSED.code}]") is URL_REFUSED


@contextmanager
def _unusable_probe(kind: str) -> Iterator[str]:
    """A URL whose redirect probe gets no usable answer, of *kind*."""
    if kind == "refused":
        with socket.socket() as closed:  # a port nothing listens on
            closed.bind(("127.0.0.1", 0))
            port = closed.getsockname()[1]
        yield f"http://127.0.0.1:{port}/g/p"
    elif kind == "unknown-scheme":
        yield "foo://127.0.0.1/g/p"
    elif kind == "silent":
        release = threading.Event()
        try:
            with _server({"/g/p/info/refs": _silent(release)}) as b:
                yield b + "/g/p"
        finally:
            release.set()
    else:
        status = 404 if kind == "404" else 301
        with _server({"/g/p/info/refs": lambda _p: ""}, status) as base:
            yield base + "/g/p"


@pytest.mark.parametrize(
    ("kind", "why"),
    [
        ("404", "HTTP 404"),
        ("no-location", "HTTP 301 without a Location"),
        ("silent", "no answer in time"),
        ("refused", "ConnectionRefusedError"),
        ("unknown-scheme", "URLError"),
    ],
    ids=["status", "no-location", "silent", "os-error", "str-reason"],
)
def test_a_probe_that_got_no_usable_answer_names_why(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    why: str,
) -> None:
    """The reason is a status, a redirect with no ``Location``, no answer in
    time, or the class name of an error: an :class:`OSError` subclass's, and
    ``URLError`` for one whose reason is a ``str`` (an unknown URL scheme),
    never that text."""
    if kind == "silent":  # a short budget only here: a refusal needs none
        monkeypatch.setattr(_git_redirect, "PROBE_BUDGET_SECONDS", 0.3)
    with _unusable_probe(kind) as url:
        result, said = _walk(url, caplog)
    assert result == url
    assert said == [_said(GIT_REDIRECT_UNUSABLE, _UNUSABLE, url=url, why=why)]
    assert trusted_message(said[0]) is GIT_REDIRECT_UNUSABLE
    assert "unknown url type" not in caplog.text


@pytest.mark.parametrize(
    "url",
    ["https://u:s3cret@h.example:abc/x", "http://u:s3cret@h.example:99999999/x"],
    ids=["letters", "too-big"],
)
def test_a_port_that_is_no_number_is_invalid_and_leaks_no_secret(
    caplog: pytest.LogCaptureFixture, url: str
) -> None:
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            resolve_git_url(url)
    text = str(raised.value)
    assert raised.value.code == "git.url-invalid"
    assert code_of(raised.value) == "git-url-invalid"
    assert "s3cret" not in text and "s3cret" not in caplog.text
    assert text.startswith("URL=") and text.endswith(
        GIT_URL_PORT_LINE.template.split(": ", 1)[1]
    )
    assert getattr(raised.value, CODE_ATTR) == "git-url-invalid"
    assert trusted_message(f"ERROR: {text} [git-url-invalid]") is not None
