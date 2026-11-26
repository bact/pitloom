# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credentials of a Git URL, kept out of ``git``'s command line.

See also: :mod:`pitloom.extract.remote._git_run` (which runs ``git`` with
what is built here).

A URL's user information is taken out of the argument list (``ps`` shows an
argument to every user), and handed to ``git`` by a credential helper that
reads two environment variables of the child. When a URL carries user
information, every other helper and ask-pass program is reset first: nothing
is read from a keychain, a system helper or ``~/.git-credentials``, and
nothing is stored in one. A URL without user information leaves the user's
own helpers in place, as ``git clone`` would.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import NoReturn
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from pitloom.core.internal_error import reraise_internal
from pitloom.core.url_masking import sanitize_url, split_userinfo
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.messages import url_text
from pitloom.messages.network import GIT_HOST_SPELLING_LINE, URL_HOST_SPELLING
from pitloom.messages.url_credentials import (
    CREDENTIALS_UNSAFE_GIT_USERINFO,
    GIT_USERINFO_LINE,
)
from pitloom.messages.url_credentials_git import (
    warn_git_credentials_in_clear,
    warn_git_credentials_line_break,
)

log = logging.getLogger(__name__)

__all__ = [
    "RESET_HELPERS",
    "GitCredentials",
    "credential_config",
    "host_is_plain",
    "split_credentials",
]

#: A host name as DNS spells one (letters, digits, ``-``, ``_``, ``.``, not
#: starting with ``-`` or ``.``), never in brackets. Anything else (``=``,
#: ``!``, white space, ``;``) names no host, and would end or extend git's
#: ``-c credential.<origin>.helper=`` key.
_HOST_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")

#: An IPv6 address, which ``urlsplit`` reads from brackets and drops them;
#: a zone id (``%25eth0``) is not one. A bracketed name (``[v1.x]``, an
#: IPvFuture) is neither: its brackets dropped, it would be a DNS name.
_IPV6 = re.compile(r"[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*")

#: An empty value resets the list of helpers (a system or global one).
RESET_HELPERS = "credential.helper="

#: Settings of every call: no helper (a manager) may prompt.
_NO_PROMPT = ("credential.interactive=false",)

#: Settings of a call whose URL carried user information: no other helper is
#: asked or told, and no ask-pass program of the configuration runs.
_RESET = (RESET_HELPERS, "core.askPass=")

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
    """The user information of one Git URL, and the origin it is for; the
    representation shows the origin alone (a token is often the user
    name)."""

    origin: str
    user: str = field(repr=False)
    password: str = field(repr=False)

    def environment(self) -> dict[str, str]:
        """The variables the helper reads."""
        return {_USER_ENV: self.user, _PASSWORD_ENV: self.password}


def credential_config(credentials: GitCredentials | None, *, reset: bool) -> list[str]:
    """The ``-c`` settings of a call: no prompt; with *reset* (the URL
    carried user information), every credential helper and ask-pass program
    reset; with *credentials*, the helper for their origin alone (a call to
    another host gets none)."""
    settings: list[str] = [*_RESET, *_NO_PROMPT] if reset else [*_NO_PROMPT]
    if credentials is not None:
        settings.append(f"credential.{credentials.origin}.helper={_HELPER}")
    return settings


def host_is_plain(parts: SplitResult) -> bool:
    """Whether the host of *parts* is a plain ASCII host name
    (:data:`_HOST_NAME`) or, in brackets, an IPv6 address
    (:data:`_IPV6`): not percent-encoded, not holding a character no host
    name holds.

    Raises:
        ValueError: ``urlsplit`` cannot read the host (an unclosed bracket).
    """
    host = parts.hostname or ""
    bracketed = parts.netloc.rpartition("@")[2].startswith("[")
    return (_IPV6 if bracketed else _HOST_NAME).fullmatch(host) is not None


def _git_authority(arg: str) -> str:
    """What git reads as the authority of the URL *arg*: up to the first
    ``/`` after ``://``, a ``?`` or ``#`` included (git takes the user
    information up to the ``@`` before it, where RFC 3986 ends the authority
    at the ``?``)."""
    return arg.partition("://")[2].partition("/")[0]


def _refuse(arg: str) -> NoReturn:
    """Raise ``git.url-invalid`` for *arg*, which holds user information
    that cannot be split off, shown masked: up to the last ``@`` git reads as
    ending it (the masker may read the ``@`` after a ``?`` as part of a
    query)."""
    scheme, _, rest = arg.partition("://")
    authority = _git_authority(arg)
    shown = f"{scheme}://***@{rest[authority.rfind('@') + 1 :]}"
    raise RemoteSourceError(
        "git.url-invalid",
        GIT_USERINFO_LINE.render({"url": url_text(shown)}),
        pitloom_code=CREDENTIALS_UNSAFE_GIT_USERINFO.code,
    )


def _origin(parts: SplitResult) -> str:
    """``scheme://host[:port]`` of *parts*, as git matches a helper: an IPv6
    host in brackets, the scheme's default port left out.

    Raises:
        ValueError: The port is not a number.
    """
    host = parts.hostname or ""
    host = f"[{host}]" if ":" in host else host
    port = parts.port
    if port is not None and port != _DEFAULT_PORTS.get(parts.scheme):
        host += f":{port}"
    return f"{parts.scheme}://{host}"


def _split(arg: str) -> tuple[str, GitCredentials | None]:
    """*arg* without its user information, and the credentials it held. The
    user information is what the masker reads as one
    (:func:`pitloom.core.url_masking.split_userinfo`).

    Raises:
        RemoteSourceError: ``git.url-invalid``, *arg* holds an ``@`` in
            what git reads as the authority, but the masker and Python do not
            split it into user information and host as git does, or a
            NUL in its user information (no environment variable can hold
            one); ``url-unsafe/host-spelling``, a host that is not plain
            (:func:`host_is_plain`), as the typed URL is refused.
    """
    if "://" not in arg or "@" not in _git_authority(arg):
        return arg, None
    found = split_userinfo(arg)
    if found is None:
        # Git reads user information the masker does not see.
        _refuse(arg)
    rest, userinfo = found
    try:
        parts = urlsplit(rest)
        origin = _origin(parts)
    except ValueError as exc:
        reraise_internal(exc)
        _refuse(arg)
    netloc = origin.partition("://")[2]
    plain = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    if not parts.hostname or "@" in _git_authority(plain):
        _refuse(arg)
    shown = sanitize_url(arg)
    if not host_is_plain(parts):
        raise RemoteSourceError(
            "git.url-invalid",
            GIT_HOST_SPELLING_LINE.render({"url": url_text(arg)}),
            pitloom_code=URL_HOST_SPELLING.code,
        )
    user, _, password = (unquote(part) for part in userinfo.partition(":"))
    if "\x00" in user + password:
        _refuse(arg)
    if re.search(r"[\r\n]", user + password):
        # A line break would add a line to what the helper writes.
        warn_git_credentials_line_break(log, shown)
        return plain, None
    if parts.scheme == "http":
        warn_git_credentials_in_clear(log, shown)
    return plain, GitCredentials(origin, user, password)


def split_credentials(
    args: list[str],
) -> tuple[list[str], GitCredentials | None]:
    """*args* with the user information of each URL in them taken out, and
    the credentials of the last such URL (a run has one repository). A URL
    whose credentials are not sent (a line break) is still taken out: the
    result differs from *args* whenever one carried user information.

    Raises:
        RemoteSourceError: ``git.url-invalid``, a URL whose user
            information cannot be split off (:func:`_split`).
    """
    plain: list[str] = []
    found: GitCredentials | None = None
    for arg in args:
        arg, credentials = _split(arg)
        plain.append(arg)
        found = credentials or found
    return plain, found
