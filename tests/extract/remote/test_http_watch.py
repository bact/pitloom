# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The https half of :mod:`pitloom.extract.remote._http_watch`: the
connection a :class:`~pitloom.extract.remote._http_watch.Watch` can shut, and
the handler that opens it with a verifying TLS context.

The loopback server speaks plain http, so the TLS connect itself is stood in
for: what is tested is that the socket an https connection opens joins the
watch, and that the handler opens with certificate and host name checks on.

See also: tests/extract/remote/test_pypi_http_fetch.py (the http half,
against a real local server).
"""

from __future__ import annotations

import http.client
import socket
import ssl
import sys
import urllib.request
from typing import Any

import pytest

from pitloom.extract.remote import _http_watch
from pitloom.extract.remote._http_watch import Watch, opener

#: Windows ends no ``recv`` on a socket shut for reading.
_WINDOWS = sys.platform == "win32"

pytestmark = pytest.mark.loopback


def test_an_https_socket_joins_the_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The socket the TLS connect opens is watched: at the deadline it is
    shut, so a blocked read ends."""
    left, right = socket.socketpair()
    left.settimeout(5)

    def tls_connect(self: http.client.HTTPSConnection) -> None:
        self.sock = left

    monkeypatch.setattr(http.client.HTTPSConnection, "connect", tls_connect)
    shut: list[socket.socket] = []
    real_shut = _http_watch.shut_socket

    def spy(sock: socket.socket) -> None:
        shut.append(sock)
        real_shut(sock)

    monkeypatch.setattr(_http_watch, "shut_socket", spy)
    with left, right, Watch(0.0) as watch:
        assert watch.fired.wait(5)
        # pylint: disable-next=protected-access
        connection = _http_watch._WatchedHTTPS("pypi.org", watch=watch)
        connection.connect()
        assert shut == [left]
        if not _WINDOWS:
            assert left.recv(1) == b""


# pylint: disable-next=too-few-public-methods
class _Answer:
    """A 200 answer, as the opener's error processor reads one."""

    code = 200
    msg = "OK"

    def info(self) -> dict[str, str]:
        """No headers."""
        return {}


def test_https_opens_with_a_verifying_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """The https handler opens through the watched connection, with a
    context that checks the certificate and the host name."""
    seen: dict[str, Any] = {}

    def do_open(
        _handler: urllib.request.AbstractHTTPHandler,
        factory: Any,
        _req: urllib.request.Request,
        **kwargs: Any,
    ) -> _Answer:
        seen["connection"] = factory("pypi.org")
        seen["context"] = kwargs["context"]
        return answer

    answer = _Answer()
    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", do_open)
    with Watch(100.0) as watch:
        response = opener(watch).open("https://pypi.org/pypi/x/json", timeout=1)
    assert response is answer
    # pylint: disable-next=protected-access
    assert isinstance(seen["connection"], _http_watch._WatchedHTTPS)
    context = seen["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
