# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credentials of a Git URL, kept out of ``git``'s command line.

See also: :mod:`pitloom.extract.remote._git_run` (which runs ``git`` with
what is built here).

A URL's user information is taken out of the argument list (``ps`` shows an
argument to every user), and handed to ``git`` by a credential helper that
reads two environment variables of the child. Every other helper is reset
first, so nothing is stored in a keychain or in ``~/.git-credentials``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit

from pitloom.core.url_masking import sanitize_url
from pitloom.messages.url_credentials import warn_git_credentials_unsent

log = logging.getLogger(__name__)

__all__ = [
    "RESET_HELPERS",
    "GitCredentials",
    "credential_config",
    "split_credentials",
]

#: An empty value resets the list of helpers (a system or global one).
RESET_HELPERS = "credential.helper="

#: The environment variables the helper reads.
_USER_ENV = "PITLOOM_GIT_USER"
_PASSWORD_ENV = "PITLOOM_GIT_PASSWORD"  # nosec B105: a name, not a value

#: What git runs (``sh -c "<this> get"``) for ``credential.<url>.helper``.
_HELPER = (
    "!f() { printf 'username=%s\\n' \"$" + _USER_ENV + '"; '
    "printf 'password=%s\\n' \"$" + _PASSWORD_ENV + '"; }; f'
)


_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class GitCredentials:
    """The user information of one Git URL, and the origin it is for."""

    origin: str
    user: str
    password: str

    def environment(self) -> dict[str, str]:
        """The variables the helper reads."""
        return {_USER_ENV: self.user, _PASSWORD_ENV: self.password}


def credential_config(credentials: GitCredentials | None) -> list[str]:
    """The ``-c`` settings that reset every credential helper and, with
    *credentials*, add the helper for their origin alone (a call to another
    host gets none)."""
    settings = [RESET_HELPERS, "credential.interactive=false", "core.askPass="]
    if credentials is not None:
        settings.append(f"credential.{credentials.origin}.helper={_HELPER}")
    return settings


def _split(arg: str) -> tuple[str, GitCredentials | None]:
    if "://" not in arg:
        return arg, None
    try:
        parts = urlsplit(arg)
        has = parts.username is not None or parts.password is not None
    except ValueError:
        return arg, None
    if not has or not parts.hostname:
        return arg, None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    try:
        # The scheme's default port is not part of the origin git matches.
        port = parts.port if parts.port != _DEFAULT_PORTS.get(parts.scheme) else None
        netloc = host + (f":{port}" if port else "")
    except ValueError:
        return arg, None
    plain = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    origin = f"{parts.scheme}://{netloc}"
    user, password = unquote(parts.username or ""), unquote(parts.password or "")
    if re.search(r"[\r\n]", user + password):
        # A line break would add a line to what the helper writes.
        warn_git_credentials_unsent(log, sanitize_url(arg))
        return plain, None
    return plain, GitCredentials(origin, user, password)


def split_credentials(
    args: list[str],
) -> tuple[list[str], GitCredentials | None]:
    """*args* with the user information of each URL in them taken out, and
    the credentials of the last such URL (a run has one repository)."""
    plain: list[str] = []
    found: GitCredentials | None = None
    for arg in args:
        arg, credentials = _split(arg)
        plain.append(arg)
        found = credentials or found
    return plain, found
