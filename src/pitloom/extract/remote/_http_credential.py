# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A credential the hardened HTTP client sends to one origin only.

See also: :mod:`pitloom.extract.remote._http_fetch` (the client) and
:func:`pitloom.extract.remote._git_redirect.resolve_git_url`, whose rule for a
URL's user information this follows: a credential goes only back to the
server it was given for, never to another host or port, and never from
https down to http.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final
from urllib.parse import urlsplit

__all__ = ["DEFAULT_PORTS", "Credential", "origin_of"]

#: The port of each scheme when a URL writes none.
DEFAULT_PORTS: Final[Mapping[str, int]] = MappingProxyType({"http": 80, "https": 443})


def origin_of(url: str) -> tuple[str, str, int] | None:
    """The scheme and host of *url* (lower case) and its port (the scheme's
    default when none is written); ``None`` for a URL whose port is no
    number or that has no host."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        return None
    return scheme, host, DEFAULT_PORTS.get(scheme, 0) if port is None else port


@dataclass(frozen=True)
class Credential:
    """The ``Authorization`` header value *header* (``Bearer <token>``),
    sent to requests whose origin is *origin* only. Its value is never part
    of the object's text."""

    header: str = field(repr=False)
    origin: tuple[str, str, int]

    def header_for(self, url: str) -> str | None:
        """*header* when *url* is on :attr:`origin`, else ``None``."""
        return self.header if origin_of(url) == self.origin else None
