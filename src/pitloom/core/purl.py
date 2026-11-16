# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Package URLs (PURL) for AI models and datasets.

``pkg:huggingface`` names a Hugging Face model repository at a revision;
``pkg:generic`` names anything else by a name plus a ``checksum`` or a
``download_url`` qualifier. The PyPI form is
:func:`pitloom.core.models.build_pypi_purl`.

See also: https://github.com/package-url/purl-spec (type definitions) and
:mod:`pitloom.export._spdx3_strip` (the SBOM-wide strip that calls
:func:`strip_purl_secrets`).
"""

from __future__ import annotations

import re
from urllib.parse import quote

from pitloom.core.url_masking import (
    PURL_DECODE_ROUNDS,
    is_purl,
    is_whole_url,
    purl_qualifiers,
    qualifier_levels,
    strip_url_secrets,
)

__all__ = [
    "build_generic_purl",
    "build_huggingface_purl",
    "commit_hash",
    "is_purl",
    "purl_qualifier_values",
    "strip_purl_secrets",
]

_GIT_SHA = re.compile(r"[0-9a-fA-F]{40}")
#: The ``safe`` characters of a qualifier value written as a URL.
_URL_SAFE = "/:"


def commit_hash(revision: object) -> str | None:
    """Return *revision* lowercased when it is a 40-digit Git commit hash, else
    ``None``: a branch, a tag or a short hash names no fixed revision."""
    if isinstance(revision, str) and _GIT_SHA.fullmatch(revision):
        return revision.lower()
    return None


def _encode(text: str, safe: str = "") -> str:
    return quote(text, safe=safe)


def build_huggingface_purl(model_id: str, revision: str | None) -> str | None:
    """Return ``pkg:huggingface/<owner>/<name>[@<revision>]``, or ``None``.

    The type needs an owner, so a legacy id without one (``gpt2``) gets no
    PURL. *revision* is kept, lowercased, only when it is a Git commit hash.
    """
    parts = model_id.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    base = f"pkg:huggingface/{_encode(parts[0])}/{_encode(parts[1])}"
    commit = commit_hash(revision)
    return f"{base}@{commit}" if commit else base


def build_generic_purl(
    name: str,
    *,
    version: str | None = None,
    checksum: str | None = None,
    download_url: str | None = None,
) -> str:
    """Return ``pkg:generic/<name>[@<version>][?checksum=..&download_url=..]``.

    *checksum* is ``<algorithm>:<hex>``. Qualifiers are in key order, as the
    PURL specification canonicalises them. *download_url* goes in without
    its credentials (:func:`~pitloom.core.url_masking.strip_url_secrets`):
    encoded, they would pass the SBOM-wide strip unread. The caller states
    the URL itself elsewhere, where that strip says what it removed.
    """
    if download_url:
        download_url = _stripped(download_url)[0]
    purl = f"pkg:generic/{_encode(name)}"
    if version:
        purl += f"@{_encode(version)}"
    qualifiers = [
        f"{key}={_encode(value, safe=safe)}"
        for key, value, safe in (
            ("checksum", checksum, ":"),
            ("download_url", download_url, _URL_SAFE),
        )
        if value
    ]
    return purl + ("?" + "&".join(qualifiers) if qualifiers else "")


def _stripped(value: str) -> tuple[str, list[str]]:
    """:func:`~pitloom.core.url_masking.strip_url_secrets` of *value*, read
    as one URL when it is one (a qualifier value is: ``download_url``)."""
    return strip_url_secrets(value, whole=is_whole_url(value))


def _stripped_once(value: str) -> tuple[str, list[str]]:
    """*value* with the credentials of its URL removed at the least depth of
    percent-encoding that shows them
    (:func:`~pitloom.core.url_masking.qualifier_levels`), and encoded again
    exactly that many times, so what an inner value was encoded as stays:
    ``...%3Fa%3D100%2525`` keeps its ``%25``, and a value as written
    (depth 0) is not encoded at all. Unchanged when no depth shows any."""
    for depth, level in enumerate(qualifier_levels(value)[0]):
        plain, found = _stripped(level)
        if found:
            for _ in range(depth):
                plain = _encode(plain, safe=_URL_SAFE)
            return plain, found
    return value, []


def _stripped_at_depth(value: str) -> tuple[str, list[str]]:
    """*value*, a qualifier value as written, stripped (:func:`_stripped_once`)
    again while that finds a URL, at most
    :data:`~pitloom.core.url_masking.PURL_DECODE_ROUNDS` times."""
    changed: list[str] = []
    for _ in range(PURL_DECODE_ROUNDS):
        value, found = _stripped_once(value)
        if not found:
            break
        changed += found
    return value, changed


def purl_qualifier_values(purl: str) -> list[str]:
    """Each qualifier value of *purl* (a ``#`` and the subpath kept in the
    last, :func:`~pitloom.core.url_masking.purl_qualifiers`), percent-decoded
    as far as it goes (:func:`~pitloom.core.url_masking.qualifier_levels`)."""
    return [
        qualifier_levels(item.partition("=")[2])[0][-1]
        for item in purl_qualifiers(purl)[1]
    ]


def strip_purl_secrets(purl: str) -> tuple[str, list[str]]:
    """*purl* with the credentials of each URL in a qualifier value removed:
    each value is percent-decoded to the least depth that shows them (at
    most :data:`~pitloom.core.url_masking.PURL_DECODE_ROUNDS` times),
    stripped (:func:`~pitloom.core.url_masking.strip_url_secrets`) and, when
    that changed it, encoded again (:func:`_stripped_at_depth`); an encoded
    ``@`` or ``?`` would hide them from a strip of the PURL as written. A
    ``#`` and the subpath stay in the
    last value (:func:`~pitloom.core.url_masking.purl_qualifiers`), so a URL
    in the subpath is stripped too. Also returns each URL changed, as
    :func:`~pitloom.core.url_masking.strip_url_secrets` shows it."""
    head, qualifiers = purl_qualifiers(purl)
    changed: list[str] = []
    kept: list[str] = []
    for item in qualifiers:
        key, _, value = item.partition("=")
        value, found = _stripped_at_depth(value)
        if found:
            item = f"{key}={value}"
            changed += found
        kept.append(item)
    if not changed:
        return purl, []
    return f"{head}?{'&'.join(kept)}", changed
