# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which PyPI release a project URL names, from the JSON API.

See also: :mod:`pitloom.extract.remote.pypi` (its one caller) and
:mod:`pitloom.extract.remote.pypi_select` (the cascade when no version is
given).

A named version is asked for as written; when PyPI holds none of that
spelling, the project's release whose version is PEP 440 equal is read
(``1.0.0`` for ``1.0``). Every answer must be about the project asked for
(its ``info.name`` canonically equal) and the release asked for (its
``info.version`` PEP 440 equal), and hold a ``urls`` list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

from packaging.utils import canonicalize_name
from packaging.version import Version

from pitloom.core.pep440 import parse_version
from pitloom.extract.remote._http_fetch import (
    NotFoundError,
    Policy,
    fetch_json,
    remote_error,
)
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.pypi_select import select_release, versions_equal_to
from pitloom.extract.remote.pypi_url import PypiTarget, pypi_json_url
from pitloom.logging_config import loggable
from pitloom.messages import (
    NAME_MISMATCH_LINE,
    NO_USABLE_RELEASE_LINE,
    PYPI_PROJECT_NOT_FOUND_LINE,
    PYPI_RESPONSE_INVALID,
    RELEASE_NOT_FOUND,
    RESPONSE_SHAPE_LINE,
    VERSION_NOT_FOUND_LINE,
)

__all__ = ["NAME_SHOWN", "Release", "hosts_of", "resolve_release"]

#: A name from the answer shown in a message is cut to this many characters.
NAME_SHOWN: Final = 255


@dataclass(frozen=True)
class Release:
    """A release's JSON answer: its version as PyPI lists it, its files, its
    ``info`` and how it was chosen (``None``: the URL named it)."""

    version: str
    #: :attr:`version`, parsed.
    parsed: Version
    urls: object
    info: dict[str, Any]
    choice: str | None


def hosts_of(base: str) -> frozenset[str]:
    """The host of *base*, with its port when it is not 443."""
    parts = urlsplit(base)
    host = (parts.hostname or "").lower()
    return frozenset({host if parts.port in (None, 443) else f"{host}:{parts.port}"})


def _shown_name(name: str) -> str:
    """*name* as is when ASCII, else its ASCII-escaped literal."""
    return name if name.isascii() else ascii(name)


def _shape(target: PypiTarget, field: str) -> RemoteSourceError:
    return remote_error(
        "pypi.response-invalid",
        PYPI_RESPONSE_INVALID,
        RESPONSE_SHAPE_LINE,
        name=target.canonical,
        field=field,
    )


def _not_found(target: PypiTarget, version: str | None) -> RemoteSourceError:
    if version is None:
        return remote_error(
            "pypi.project-not-found",
            RELEASE_NOT_FOUND,
            PYPI_PROJECT_NOT_FOUND_LINE,
            name=target.canonical,
        )
    return remote_error(
        "pypi.release-not-found",
        RELEASE_NOT_FOUND,
        VERSION_NOT_FOUND_LINE,
        name=target.canonical,
        version=loggable(version),
    )


def _answer(
    target: PypiTarget, version: str | None, policy: Policy
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The JSON answer for the project (*version* ``None``) or a release,
    and its ``info``, checked to be about the project asked for.

    Raises:
        NotFoundError: PyPI answered 404 or 410.
    """
    data = fetch_json(pypi_json_url(target.canonical, version), policy)
    info = data.get("info")
    if not isinstance(info, dict):
        raise _shape(target, "info")
    answered = info.get("name")
    if not isinstance(answered, str) or not answered:
        raise _shape(target, "info.name")
    # ASCII first: canonicalize_name lowers U+212A (Kelvin) to ``k``.
    if not answered.isascii() or canonicalize_name(answered) != target.canonical:
        raise remote_error(
            "pypi.response-invalid",
            PYPI_RESPONSE_INVALID,
            NAME_MISMATCH_LINE,
            name=target.canonical,
            # Escaped when not ASCII, so a look-alike letter shows as such.
            answered=_shown_name(answered[:NAME_SHOWN]),
        )
    return data, info


def _releases(target: PypiTarget, policy: Policy) -> dict[str, Any]:
    """The ``releases`` of the project's JSON answer."""
    try:
        data, _info = _answer(target, None, policy)
    except NotFoundError:
        raise _not_found(target, None) from None
    releases = data.get("releases")
    if not isinstance(releases, dict):
        raise _shape(target, "releases")
    return releases


def _versioned(
    target: PypiTarget, version: str, policy: Policy, choice: str | None
) -> Release:
    """Release *version*'s JSON answer.

    Raises:
        NotFoundError: PyPI answered 404 or 410.
    """
    data, info = _answer(target, version, policy)
    listed = info.get("version")
    parsed = parse_version(listed)
    if (
        not isinstance(listed, str)
        or parsed is None
        or parsed != parse_version(version)
    ):
        raise _shape(target, "info.version")
    if not isinstance(data.get("urls"), list):
        raise _shape(target, "urls")
    return Release(
        version=listed, parsed=parsed, urls=data["urls"], info=info, choice=choice
    )


def resolve_release(target: PypiTarget, policy: Policy) -> Release:
    """The release to read: the one the URL names (a PEP 440 equal
    spelling of it when PyPI lists it so), else the latest by
    :func:`~pitloom.extract.remote.pypi_select.select_release`."""
    if target.version is None:
        choice = select_release(_releases(target, policy), target.canonical)
        if choice is None:
            raise remote_error(
                "pypi.release-not-found",
                RELEASE_NOT_FOUND,
                NO_USABLE_RELEASE_LINE,
                name=target.canonical,
            )
        key, kind = choice.version, choice.kind
    else:
        try:
            return _versioned(target, target.version, policy, None)
        except NotFoundError:
            pass
        asked = parse_version(target.version)
        keys = (
            [] if asked is None else versions_equal_to(_releases(target, policy), asked)
        )
        if not keys:
            raise _not_found(target, target.version)
        key, kind = keys[0], None
    try:
        return _versioned(target, key, policy, kind)
    except NotFoundError:
        raise _not_found(target, key) from None
