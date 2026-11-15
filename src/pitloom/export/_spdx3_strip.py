# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The removal of credentials from every URL of an SBOM's ``@graph``: the
one place every surface's SBOM passes, which a wheel can embed and anyone
can publish.

See also: :mod:`pitloom.export.spdx3_json` (its caller),
:func:`pitloom.core.url_masking.strip_url_secrets` (what is removed from a
text) and :func:`pitloom.core.purl.strip_purl_secrets` (from a PURL).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pitloom.core.purl import is_purl, purl_qualifier_values, strip_purl_secrets
from pitloom.core.url_masking import keeps_url_credential, strip_url_secrets
from pitloom.messages.url_credentials import (
    id_collision_error,
    warn_url_credential_kept,
    warn_url_credentials_stripped,
)

__all__ = ["strip_graph_credentials"]

log = logging.getLogger(__name__)

#: A run of text holding ``://``, to white space, a quote, an angle bracket
#: or a backtick: a URL as a message names it.
_URL_WORD = re.compile(r"[^\s\"'<>`]*://[^\s\"'<>`]+")
#: The punctuation that ends a sentence or closes a bracket after a URL.
_TRAILING = ".,;:!?)]}"


def _stripped_text(text: str, seen: list[str]) -> str:
    """*text* without the credentials of its URLs, those of a PURL's
    qualifier values included; each URL changed is added to *seen*, as
    :func:`~pitloom.core.url_masking.strip_url_secrets` shows it."""
    if is_purl(text):
        text, changed = strip_purl_secrets(text)
        seen.extend(changed)
    plain, changed = strip_url_secrets(text)
    seen.extend(changed)
    return plain


def _kept_urls(text: str) -> list[str]:
    """Each URL of *text* (of a PURL's qualifier values too) that holds a
    value :func:`~pitloom.core.url_masking.strip_url_secrets` keeps that may
    be a credential and removes nothing from, as written."""
    views = purl_qualifier_values(text) if is_purl(text) else [text]
    found: list[str] = []
    for view in views:
        if "://" not in view or not keeps_url_credential(view):
            continue
        for word in _URL_WORD.findall(view):
            url = word.rstrip(_TRAILING)
            if keeps_url_credential(url) and not strip_url_secrets(url)[1]:
                found.append(url)
    return found


def _stripped_value(value: Any, seen: list[str], kept: list[str]) -> Any:
    """*value*, a decoded JSON value, with the credentials of each URL in
    each string removed (:func:`_stripped_text`); each URL that keeps one is
    added to *kept*. The same object when nothing in it changed, so a clean
    SBOM is not copied."""
    if isinstance(value, str):
        kept.extend(_kept_urls(value))
        plain = _stripped_text(value, seen)
        return value if plain == value else plain
    if isinstance(value, list):
        items = [_stripped_value(item, seen, kept) for item in value]
        return (
            value if all(a is b for a, b in zip(items, value, strict=True)) else items
        )
    if isinstance(value, dict):
        fields = {k: _stripped_value(item, seen, kept) for k, item in value.items()}
        same = all(fields[k] is item for k, item in value.items())
        return value if same else fields
    return value


def _check_id_collisions(graph: list[dict[str, Any]]) -> None:
    """Raise when two element ids of *graph* are one without their
    credentials: an id and each reference to it are stripped alike, so
    they would merge.

    Raises:
        pitloom.messages.CodedValueError: ``credentials-unsafe/id-collision``.
    """
    ids: dict[str, str] = {}
    held = {str(e[k]) for e in graph for k in ("spdxId", "@id") if k in e}
    for element in graph:
        for key in ("spdxId", "@id"):
            old = element.get(key)
            if not isinstance(old, str):
                continue
            new = _stripped_text(old, [])
            if new == old:
                continue
            # The same id twice (a copy of one element) is no clash.
            if ids.get(old) != new and (new in held or new in ids.values()):
                raise id_collision_error(old)
            ids[old] = new


def strip_graph_credentials(graph: list[dict[str, Any]]) -> None:
    """The user information and secret query parameters of each URL in
    *graph* (a project URL, a dependency's direct URL or PURL, a provenance
    note, an element id and every reference to it), removed in place, with
    one ``WARNING:`` per URL changed; and one per URL that keeps a value
    that may be a credential (a ``code`` parameter, an ssh user name).

    Raises:
        pitloom.messages.CodedValueError: Two ids are one without their
            credentials (``credentials-unsafe/id-collision``); *graph* is
            left as it was.
    """
    _check_id_collisions(graph)
    seen: list[str] = []
    kept: list[str] = []
    graph[:] = _stripped_value(graph, seen, kept)
    for url in dict.fromkeys(seen):
        warn_url_credentials_stripped(log, url)
    for url in dict.fromkeys(kept):
        warn_url_credential_kept(log, url)
