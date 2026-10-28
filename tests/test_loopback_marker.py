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
        with socket.create_connection((host, port), timeout=5):
            conn, _ = server.accept()
            conn.close()


@pytest.mark.loopback
@pytest.mark.parametrize("connect", ["connect", "connect_ex"])
def test_a_loopback_test_cannot_reach_another_host(connect: str) -> None:
    """192.0.2.1 is a documentation address: refused before any packet leaves."""
    with socket.socket() as sock:
        with pytest.raises(RuntimeError, match="loopback test reached"):
            getattr(sock, connect)(("192.0.2.1", 9))


def test_an_unmarked_test_cannot_open_a_socket() -> None:
    with pytest.raises(RuntimeError, match="Real network access attempted"):
        socket.socket()
