# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""HTTP servers for ``loopback`` tests that never ask the resolver anything.

``http.server.HTTPServer.server_bind`` sets ``server_name`` with
``socket.getfqdn(host)``, a reverse lookup of the bound address. On a macOS CI
runner that lookup stalled for about 35 s the first time each test process
made a server, in tests that have nothing to do with names. A test server is
on ``127.0.0.1`` and its ``server_name`` is never read, so these subclasses
skip the lookup and bind the socket only.

See also: tests/_network.py (``bypass_proxies``), tests/_git_http_server.py,
tests/test_loopback_marker.py (the tests of both).
"""

from __future__ import annotations

import http.server
import socketserver

__all__ = ["LoopbackHTTPServer", "ThreadingLoopbackHTTPServer"]


class LoopbackHTTPServer(http.server.HTTPServer):
    """:class:`http.server.HTTPServer` that does no reverse lookup on bind."""

    def server_bind(self) -> None:
        """Bind the socket; set the name and port without a DNS query."""
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = port


class ThreadingLoopbackHTTPServer(socketserver.ThreadingMixIn, LoopbackHTTPServer):
    """A :class:`LoopbackHTTPServer` that serves each request in a thread
    (as :class:`http.server.ThreadingHTTPServer` does)."""

    daemon_threads = True
