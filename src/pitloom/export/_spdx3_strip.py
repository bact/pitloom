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
from pitloom.core.url_masking import (
    holds_url_credentials,
    is_whole_url,
    keeps_url_credential,
    normalised,
    split_enclosed,
    strip_url_secrets,
    without_format,
)
from pitloom.messages.url_credentials import (
    id_collision_error,
    warn_url_credential_kept,
    warn_url_credential_unremoved,
    warn_url_credentials_stripped,
)

__all__ = ["strip_graph_credentials"]

log = logging.getLogger(__name__)

#: White space, a quote, an angle bracket or a backtick: where a URL word of a
#: text ends.
_WORD_BREAK = re.compile(r"[\s\"'<>`]")
#: The punctuation that ends a sentence or closes a bracket after a URL.
_TRAILING = ".,;:!?)]}"
#: The ``@ URL`` (or ``@URL``) of a PEP 508 direct reference, alone or
#: inside a note: the URL runs to white space, so a quote in its user
#: information is part of it, not the end of a word in prose.
_DIRECT_REFERENCE = re.compile(
    r"(?P<head>@\s*)(?P<url>[A-Za-z][A-Za-z0-9+.-]*:[/\\]\S*)"
)


def _stripped_text(text: str, seen: list[str]) -> str:
    """*text* without the credentials of its URLs, those of a PURL's
    qualifier values included, read as the detector reads it
    (:func:`~pitloom.core.url_masking.normalised`): without its format
    characters, which go when something is removed, and inside one pair of
    enclosing ``<>`` or quotes, which stay. Each URL changed is added to
    *seen*, as :func:`~pitloom.core.url_masking.strip_url_secrets` shows
    it."""
    bare = without_format(text)
    head, value, tail = split_enclosed(bare)
    plain = head + _stripped_value_text(value, seen) + tail
    return text if plain == bare else plain


def _stripped_value_text(text: str, seen: list[str]) -> str:
    """:func:`_stripped_text` of *text*, a value as the detector reads it."""
    if is_purl(text):
        text, changed = strip_purl_secrets(text)
        seen.extend(changed)

    def direct(match: re.Match[str]) -> str:
        url = match["url"]
        # A sentence's punctuation after the URL is the text's.
        url_end = len(url.rstrip(_TRAILING))
        plain, changed = strip_url_secrets(url[:url_end], whole=True)
        seen.extend(changed)
        return match["head"] + plain + url[url_end:]

    text = _DIRECT_REFERENCE.sub(direct, text)
    plain, changed = strip_url_secrets(text, whole=is_whole_url(text))
    seen.extend(changed)
    return plain


def _url_words(text: str) -> list[str]:
    """Each run of *text* holding ``://``, to white space, a quote, an angle
    bracket or a backtick: a URL as a message names it. Linear: the start of
    a word is found by walking left from its ``://`` once."""
    words: list[str] = []
    floor = 0  # the end of the last word: the next one starts after it
    at = text.find("://")
    while at >= 0:
        end_match = _WORD_BREAK.search(text, at + 3)
        end = end_match.start() if end_match else len(text)
        if end > at + 3:
            start = at
            while start > floor and not _WORD_BREAK.match(text, start - 1):
                start -= 1
            words.append(text[start:end])
            floor = end
        at = text.find("://", max(end, at + 3))
    return words


def _kept_urls(text: str) -> list[str]:
    """Each URL of *text* (of a PURL's qualifier values too) that holds a
    value :func:`~pitloom.core.url_masking.strip_url_secrets` keeps that may
    be a credential and removes nothing from, as written. A string that is
    one URL is read as a whole (a URL field), else its URLs are read in free
    text."""
    views = purl_qualifier_values(text) if is_purl(text) else [text]
    found: list[str] = []
    for view in views:
        if "://" not in view and not is_whole_url(view):
            continue
        whole = is_whole_url(view)
        words = [view] if whole else _url_words(view)
        for word in words:
            url = word if whole else word.rstrip(_TRAILING)
            if (
                keeps_url_credential(url, whole=whole)
                and not (strip_url_secrets(url, whole=whole)[1])
            ):
                found.append(url)
    return found


def _stripped_value(value: Any, seen: list[str], kept: list[tuple[bool, str]]) -> Any:
    """*value*, a decoded JSON value, with the credentials of each URL in
    each string removed (:func:`_stripped_text`); each URL that keeps one is
    added to *kept* as ``(False, url)``, and each string that still holds a
    credential once stripped
    (:func:`~pitloom.core.url_masking.holds_url_credentials`) as ``(True,
    string)``. The same object when nothing in it changed, so a clean
    SBOM is not copied."""
    if isinstance(value, str):
        kept.extend((False, url) for url in _kept_urls(normalised(value)))
        plain = _stripped_text(value, seen)
        # What the detector refuses that the strip leaves: said, never silent.
        if holds_url_credentials(plain, account=True):
            kept.append((True, plain))
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
    one ``WARNING:`` per URL changed; one per URL that keeps a value that may
    be a credential (a ``code`` parameter, an ssh user name); and one per
    value that still holds a credential the removal does not read (an access
    token, an scp-style password, ``s3:/u:p@h``), which the SBOM states as
    written.

    Raises:
        pitloom.messages.CodedValueError: Two ids are one without their
            credentials (``credentials-unsafe/id-collision``); *graph* is
            left as it was.
    """
    _check_id_collisions(graph)
    seen: list[str] = []
    kept: list[tuple[bool, str]] = []
    graph[:] = _stripped_value(graph, seen, kept)
    for url in dict.fromkeys(seen):
        warn_url_credentials_stripped(log, url)
    for unremoved, url in dict.fromkeys(kept):
        if unremoved:
            warn_url_credential_unremoved(log, url)
        else:
            warn_url_credential_kept(log, url)
