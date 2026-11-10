# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A local stand-in for the Hugging Face Hub's file host and its CDN, for
``loopback`` tests of :mod:`pitloom.extract.remote._hub_files`.

Two servers from :func:`tests._fake_pypi_server.serving`: the Hub, which
answers ``/<repo>/resolve/<revision>/<file>`` as the real Hub does (a file
kept in Git: a redirect on its own host to ``/api/resolve-cache/...``; one
kept in Xet storage: a redirect to the CDN), and the CDN, on another port, so
another origin. Every path asked and its headers are recorded on each.

See also: tests/_fake_pypi_server.py (the server and its routes) and
tests/extract/remote/test_hub_files.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from pitloom.extract.remote import _http_fetch, _hub_files
from tests._fake_pypi_server import FakePypi, Route, redirect, serving

__all__ = [
    "TOKEN",
    "FakeHub",
    "hub_and_cdn",
    "point_hub_at",
    "serve_in_git",
    "serve_in_xet",
]

#: The token the tests sign in with.
TOKEN = "hf_test_token_value"


@dataclass
class FakeHub:
    """The Hub and its CDN."""

    hub: FakePypi
    cdn: FakePypi


@contextmanager
def hub_and_cdn() -> Iterator[FakeHub]:
    """A fake Hub and a fake CDN on ``127.0.0.1``, stopped on exit."""
    with serving() as hub, serving() as cdn:
        yield FakeHub(hub, cdn)


def serve_in_git(
    fake: FakeHub,
    repo: str,
    filename: str,
    body: bytes,
    *,
    revision: str = "main",
    length: int | None = None,
) -> str:
    """Serve *filename* of *repo* as a file kept in Git: the resolve URL
    redirects (307, relative) to its resolve-cache path on the Hub; return
    that path. *length* is the ``Content-Length`` sent (see
    :class:`~tests._fake_pypi_server.Route`)."""
    cache = f"/api/resolve-cache/models/{repo}/{revision}/{filename}"
    fake.hub.routes[f"/{repo}/resolve/{revision}/{filename}"] = redirect(
        cache, status=307
    )
    fake.hub.routes[cache] = Route(body=body, length=length)
    return cache


def serve_in_xet(
    fake: FakeHub, repo: str, filename: str, body: bytes, *, revision: str = "main"
) -> str:
    """Serve *filename* of *repo* as a file kept in Xet storage: the resolve
    URL redirects (302) to a signed URL on the CDN; return the CDN path."""
    signed = f"/xet-bridge/{filename}"
    fake.hub.routes[f"/{repo}/resolve/{revision}/{filename}"] = redirect(
        fake.cdn.url(signed + "?X-Xet-Signed=1"), status=302
    )
    fake.cdn.routes[signed] = Route(body=body)
    return signed


def point_hub_at(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeHub,
    *,
    token: str | None = TOKEN,
    offline: bool = False,
) -> None:
    """Make the Hub route ask *fake* over plain http (only a test allows it),
    with *token* as the signed-in user's and *offline* as
    ``HF_HUB_OFFLINE``."""
    monkeypatch.setattr(_hub_files, "HUB_BASE", fake.hub.base)
    monkeypatch.setattr(
        _hub_files, "FILE_HOSTS", frozenset({fake.hub.host, fake.cdn.host})
    )
    monkeypatch.setattr(_http_fetch, "ALLOWED_SCHEMES", frozenset({"http", "https"}))
    monkeypatch.setattr(_hub_files, "hub_token", lambda: token)
    monkeypatch.setattr(_hub_files, "hub_offline", lambda: offline)
