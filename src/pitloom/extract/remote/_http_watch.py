# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The overall deadline of a fetch, and the opener that keeps to it.

See also: :mod:`pitloom.extract.remote._http_fetch` (the one client that
uses them).

A timeout on each socket operation does not bound a server that answers a
byte at a time, each byte inside the timeout. A :class:`Watch` shuts down
every socket its fetch opened once its deadline passes, so a blocked read
returns at once. The opener built by :func:`opener` handles ``http:`` and
``https:`` only, has no redirect, cookie or authentication handler, and
reports a redirect or an error status as an
:class:`urllib.error.HTTPError`.

What the deadline does not bound: a socket joins its :class:`Watch` when
``connect()`` returns, and the stdlib offers no public hook before that. The
name lookup (``getaddrinfo``, which no Python timeout bounds), the TCP
connect to each address, an ``HTTPS_PROXY`` ``CONNECT`` tunnel and the TLS
handshake therefore run outside it, each socket operation bounded only by
the per-operation timeout the caller passes (at most the time left). A
socket that joins after the deadline is shut at once. The hosts are the
allowlisted PyPI and Hugging Face hosts, or the user's own proxy.
"""

from __future__ import annotations

import functools
import http.client
import socket
import ssl
import threading
import time
import urllib.request
from types import TracebackType
from typing import Any, cast

__all__ = ["Watch", "opener", "shut_socket"]


class Watch:
    """The overall deadline of one fetch: at it, every socket the fetch
    opened is shut down, so a blocked read returns at once on POSIX. Windows
    does not end a read on a socket shut for reading; there the read ends at
    its per-operation timeout, never longer than the time left when the
    request began, and the read loop stops at the deadline."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.deadline = time.monotonic() + seconds
        #: The timeout of each socket operation of the latest request: the
        #: per-operation timeout, or less when the deadline was nearer.
        self.socket_seconds = seconds
        self.fired = threading.Event()
        self._sockets: list[socket.socket] = []
        self._lock = threading.Lock()
        self._timer = threading.Timer(max(seconds, 0.0), self._fire)
        self._timer.daemon = True

    def __enter__(self) -> Watch:
        self._timer.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._timer.cancel()

    def remaining(self) -> float:
        """Seconds left before the deadline. Read *expired* as ``<= 0``: the
        Windows clock ticks in about 15.6 ms steps, so it can read exactly 0
        at a zero-second deadline."""
        return self.deadline - time.monotonic()

    def add(self, sock: socket.socket | None) -> None:
        """Watch *sock*; shut it at once when the deadline has passed."""
        if sock is None:
            return
        with self._lock:
            self._sockets.append(sock)
            if self.fired.is_set():
                shut_socket(sock)

    def _fire(self) -> None:
        with self._lock:
            self.fired.set()
            for sock in self._sockets:
                shut_socket(sock)


def shut_socket(sock: socket.socket) -> None:
    """Shut *sock* down for reading and writing, through the plain socket
    (a TLS socket's own ``shutdown`` drops its TLS state under a reader)."""
    try:
        socket.socket.shutdown(sock, socket.SHUT_RDWR)
    except OSError:
        pass


class _WatchedHTTP(http.client.HTTPConnection):
    """An HTTP connection whose socket a :class:`Watch` can shut."""

    def __init__(self, host: str, *, watch: Watch, **kwargs: Any) -> None:
        super().__init__(host, **kwargs)
        self._watch = watch

    def connect(self) -> None:
        super().connect()
        self._watch.add(self.sock)


class _WatchedHTTPS(http.client.HTTPSConnection):
    """An HTTPS connection whose socket a :class:`Watch` can shut."""

    def __init__(self, host: str, *, watch: Watch, **kwargs: Any) -> None:
        super().__init__(host, **kwargs)
        self._watch = watch

    def connect(self) -> None:
        super().connect()
        self._watch.add(self.sock)


class _HTTPHandler(urllib.request.HTTPHandler):
    """Opens ``http:`` (a test server only) through :class:`_WatchedHTTP`."""

    def __init__(self, watch: Watch) -> None:
        super().__init__()
        self._watch = watch

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        factory = functools.partial(_WatchedHTTP, watch=self._watch)
        return self.do_open(cast(Any, factory), req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    """Opens ``https:`` through :class:`_WatchedHTTPS`, verifying the
    certificate and the host name."""

    def __init__(self, watch: Watch) -> None:
        super().__init__()
        self._watch = watch
        self._tls = ssl.create_default_context()

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        factory = functools.partial(_WatchedHTTPS, watch=self._watch)
        return self.do_open(cast(Any, factory), req, context=self._tls)


def opener(watch: Watch) -> urllib.request.OpenerDirector:
    """An opener for http(s) only, with no redirect, cookie or
    authentication handler: a redirect or an error status is an
    :class:`urllib.error.HTTPError`."""
    director = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.ProxyHandler(),
        _HTTPHandler(watch),
        _HTTPSHandler(watch),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        director.add_handler(handler)
    return director
