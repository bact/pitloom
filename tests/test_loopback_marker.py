# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``loopback`` marker: a test may open sockets, but only to this machine.

``network`` is for a real remote host and is left out of the default CI job;
``loopback`` is for a server the test starts and runs everywhere.

See also: tests/conftest.py (``_block_network_access``), tests/_network.py
(``bypass_proxies``), tests/_loopback_server.py.
"""

from __future__ import annotations

import http.server
import socket
import threading
import urllib.request
from typing import Any

import pytest

from tests._loopback_server import (
    LoopbackHTTPServer,
    ThreadingLoopbackHTTPServer,
)
from tests._network import bypass_proxies

#: Nothing answers at this address (an unrouted one in 10/8) or on port 9.
_BLACK_HOLE = "http://10.255.255.1:9"


@pytest.mark.loopback
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_a_loopback_test_reaches_a_server_on_this_machine(host: str) -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        with socket.socket() as client:
            client.settimeout(5)
            client.connect((host, port))  # the guard sees the name as written
            server.accept()[0].close()


@pytest.mark.loopback
def test_a_loopback_test_reaches_a_server_on_ipv6_loopback() -> None:
    try:
        server = socket.socket(socket.AF_INET6)
        server.bind(("::1", 0))
    except OSError:
        pytest.skip("IPv6 loopback is not available")
    with server:
        server.listen()
        with socket.socket(socket.AF_INET6) as client:
            client.settimeout(5)
            client.connect(("::1", server.getsockname()[1]))
            server.accept()[0].close()


@pytest.mark.loopback
@pytest.mark.parametrize("connect", ["connect", "connect_ex"])
@pytest.mark.parametrize("host", ["192.0.2.1", "127.0.0.2.example", "8.8.8.8"])
def test_a_loopback_test_cannot_reach_another_host(connect: str, host: str) -> None:
    """Refused before any packet leaves (192.0.2.1 is a documentation address);
    the timeout bounds the test if the guard were gone."""
    with socket.socket() as sock:
        sock.settimeout(2)
        with pytest.raises(RuntimeError, match="loopback test reached"):
            getattr(sock, connect)((host, 9))


def test_an_unmarked_test_cannot_open_a_socket() -> None:
    with pytest.raises(RuntimeError, match="Real network access attempted"):
        socket.socket()


def _no_lookup(*_args: Any, **_kwargs: Any) -> str:
    raise AssertionError("a reverse lookup of the bound address")


@pytest.mark.loopback
@pytest.mark.parametrize(
    "server_class",
    [LoopbackHTTPServer, ThreadingLoopbackHTTPServer],
    ids=["plain", "threading"],
)
def test_a_loopback_server_does_no_reverse_lookup(
    monkeypatch: pytest.MonkeyPatch, server_class: type[LoopbackHTTPServer]
) -> None:
    """``HTTPServer`` calls ``socket.getfqdn`` on bind, which stalled for 35 s
    on a macOS runner."""
    with pytest.MonkeyPatch.context() as control:
        control.setattr(socket, "getfqdn", _no_lookup)
        # The premise: the stock server does look the address up.
        with pytest.raises(AssertionError, match="reverse lookup"):
            http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
    monkeypatch.setattr(socket, "getfqdn", _no_lookup)
    with server_class(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler) as server:
        assert server.server_port == server.server_address[1] != 0
        assert server.server_name == "127.0.0.1"


@pytest.mark.loopback
def test_a_loopback_test_has_no_proxy() -> None:
    """The autouse fixture applies to the marker, whatever the machine sets."""
    assert urllib.request.getproxies_environment() == {"no": "*"}
    assert urllib.request.proxy_bypass("127.0.0.1")


@pytest.mark.loopback
@pytest.mark.parametrize("name", ["http_proxy", "HTTP_PROXY", "ALL_PROXY"])
def test_a_proxy_variable_does_not_reach_a_local_server(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """With a black-hole proxy set, ``urllib`` still reaches the server at once
    (a request through the proxy would wait for the connect timeout)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        """Answer one GET with ``ok``."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            """Answer."""
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        # pylint: disable-next=redefined-builtin
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Stay quiet."""

    # Undo the autouse fixture. On Windows both spellings are one variable, so
    # the second delete finds it gone.
    for bypass in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(bypass, raising=False)
    monkeypatch.setenv(name, _BLACK_HOLE)
    # The premise: with the variable set and no bypass, urllib uses the proxy.
    assert _BLACK_HOLE in urllib.request.getproxies().values()
    assert not urllib.request.proxy_bypass("127.0.0.1")
    bypass_proxies(monkeypatch)
    assert _BLACK_HOLE not in urllib.request.getproxies().values()
    with LoopbackHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        with urllib.request.urlopen(url, timeout=10) as answer:  # nosec B310
            assert answer.read() == b"ok"
        thread.join(10)
