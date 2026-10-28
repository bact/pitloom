# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``loopback`` marker: a test may open sockets, but only to this machine.

``network`` is for a real remote host and is left out of the default CI job;
``loopback`` is for a server the test starts and runs everywhere.

See also: tests/conftest.py (``_block_network_access``), tests/_network.py.
"""

from __future__ import annotations

import socket

import pytest


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
