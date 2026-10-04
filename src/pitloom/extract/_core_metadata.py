# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared RFC 822 Core-Metadata parsing helpers, usable against either
:class:`email.message.Message` (raw ``METADATA``/``PKG-INFO`` text) or
:class:`importlib.metadata.PackageMetadata` (an installed distribution) --
both expose the same ``__contains__``/``__getitem__``/``get_all()``
interface.
"""

from __future__ import annotations

import email.message
from importlib.metadata import PackageMetadata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    #: The two RFC 822 Core-Metadata carriers callers pass to
    #: :func:`parse_project_urls`. A structural ``Protocol`` was tried
    #: first and rejected: mypy's protocol-conformance check does not
    #: reliably match a single, non-overloaded ``Protocol`` method against
    #: these two types' real ``@overload``-ed ``get_all()`` (verified
    #: interactively -- a minimal repro still fails even with matching
    #: parameter names/kinds), so a plain union of the two concrete types
    #: is used instead. Guarded by ``TYPE_CHECKING`` since
    #: ``email.message.Message[str, str]`` is only subscriptable for a
    #: type checker, not at runtime.
    _MessageLike = email.message.Message[str, str] | PackageMetadata


def _get_str(msg: _MessageLike, name: str) -> str | None:
    """Return *msg*'s value for header *name*, or ``None`` when absent --
    guards with ``in`` before ``__getitem__`` since ``PackageMetadata``'s
    ``__getitem__`` is typed to return ``str`` (not ``str | None``), i.e.
    it may raise/misbehave on a missing key rather than returning
    ``None`` the way :meth:`email.message.Message.get` does."""
    return msg[name] if name in msg else None


def parse_project_urls(
    msg: _MessageLike,
    *,
    lowercase_labels: bool = False,
    include_homepage: bool = True,
    include_download: bool = False,
) -> dict[str, str]:
    """``Project-URL`` (``Label, URL`` -- first-comma-only split, a URL's
    own query string can legally contain commas) plus optionally legacy
    ``Home-page``/``Download-URL``. ``Project-URL`` always wins on a key
    collision with ``Home-page``, matching every existing call site's net
    behavior regardless of which order they used to achieve it.

    Parameters preserve each existing call site's own tested behavior --
    see each call site for which flags it needs; this function
    intentionally stays parametrized rather than one-size-fits-all so no
    site's behavior changes silently.

    A malformed ``Project-URL`` entry (no comma) is silently dropped --
    matches every existing call site's behavior, not a deviation worth a
    ``WARNING:``.
    """
    urls: dict[str, str] = {}
    if include_homepage:
        homepage = _get_str(msg, "Home-page")
        if homepage:
            urls["Homepage"] = homepage
    if include_download:
        download = _get_str(msg, "Download-URL")
        if download:
            urls["Download"] = download
    for entry in msg.get_all("Project-URL") or []:
        if "," in entry:
            label, url = entry.split(",", 1)
            label = label.strip()
            if lowercase_labels:
                label = label.lower()
            urls[label] = url.strip()
    return urls


def core_metadata_license(msg: _MessageLike) -> str | None:
    """The licence a Core-Metadata carrier declares: ``License-Expression``
    (PEP 639), else the legacy free-text ``License``.

    Spec 2.4+ makes the two mutually exclusive, but a real file can carry
    both, so the first non-empty one wins, ``License-Expression`` first.
    ``None`` means neither header is declared; ``""`` means one is
    declared but empty (declared, authoritative "no value", not absent).
    Callers decide what that distinction means for their provenance.
    """
    declared = False
    for field in ("License-Expression", "License"):
        value = _get_str(msg, field)
        if value is None:
            continue
        if value:
            return value
        declared = True
    return "" if declared else None
