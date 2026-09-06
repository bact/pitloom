# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PyPI JSON API lookups for dependency enrichment.

See also: :mod:`pitloom.assemble.spdx3.deps`, which calls into this module
for whatever installed metadata doesn't cover.
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote as url_quote

from packaging.utils import canonicalize_name

from pitloom.assemble.spdx3.deps_originator import _extract_name_email_pairs
from pitloom.extract._extract_utils import fetch_json

# Best-effort PyPI JSON API fetch timeout -- short enough that a blocked or
# slow network doesn't meaningfully stall a build; see _fetch_pypi_release_info.
_PYPI_TIMEOUT_SECONDS = 5.0

# A `license` field this long is almost certainly a project pasting its
# entire LICENSE file into PyPI's free-text `license` metadata (a known,
# common anti-pattern) rather than a short identifier/expression -- treated
# as absent rather than polluting the license/copyright fields with it.
_PYPI_LICENSE_FIELD_MAX_LEN = 200

# Cap on concurrent PyPI JSON API requests, so a project with hundreds of
# dependencies doesn't open hundreds of sockets at once.
_PYPI_MAX_CONCURRENT_FETCHES = 8


def _extract_pypi_originator(
    info: dict[str, Any],
) -> list[tuple[str | None, str | None]]:
    """Return a list of ``(name, email)`` tuples for a dependency's originator
    from a PyPI JSON API ``info`` object, or an empty list. Same
    author-then-maintainer precedence as
    :func:`~pitloom.assemble.spdx3.deps_originator._resolve_author_or_maintainer`."""
    for name_key, email_key in (
        ("author", "author_email"),
        ("maintainer", "maintainer_email"),
    ):
        results = _extract_name_email_pairs(
            info.get(name_key) or "", info.get(email_key) or ""
        )
        if results:
            return results
    return []


def _extract_pypi_license(info: dict[str, Any]) -> str | None:
    """Return a license expression/identifier from a PyPI JSON API ``info``
    object, or ``None``. Prefers PEP 639 ``license_expression``, then the
    legacy free-text ``license`` field (skipped if implausibly long -- see
    :data:`_PYPI_LICENSE_FIELD_MAX_LEN`), then an OSI/other ``License ::``
    trove classifier.
    """
    license_expression = (info.get("license_expression") or "").strip()
    if license_expression and license_expression.upper() != "UNKNOWN":
        return license_expression

    license_field = (info.get("license") or "").strip()
    if (
        license_field
        and license_field.upper() != "UNKNOWN"
        and len(license_field) <= _PYPI_LICENSE_FIELD_MAX_LEN
    ):
        return license_field

    classifiers: list[str] = info.get("classifiers") or []
    for classifier in classifiers:
        if classifier.startswith("License ::"):
            return classifier.rsplit("::", maxsplit=1)[-1].strip()
    return None


def _fetch_pypi_release_info(name: str, version: str | None) -> dict[str, Any] | None:
    """Best-effort fetch of PyPI JSON API release info for *name*, optionally
    pinned to *version* (the unversioned endpoint returns the latest
    release). Returns ``None`` on any failure -- no network, DNS blocked,
    timeout, non-200, or a malformed response -- so this is always a
    silent, non-blocking enrichment layer, never a hard requirement.

    Delegates the actual fetch to :func:`~pitloom.extract._extract_utils.
    fetch_json` (also used for Croissant metadata) rather than a second
    urlopen/json.loads implementation, so the scheme-restriction and
    HTTP-exception handling only need to be reviewed and gotten right once.
    """
    path = (
        f"{url_quote(name)}/{url_quote(version)}/json"
        if version
        else f"{url_quote(name)}/json"
    )
    url = f"https://pypi.org/pypi/{path}"
    try:
        return fetch_json(url, timeout=_PYPI_TIMEOUT_SECONDS)
    except ValueError:
        return None


def _extract_release_hash(release_info: dict[str, Any]) -> str | None:
    """Return the hex SHA-256 digest of the release's wheel (preferred) or
    sdist artifact from a PyPI JSON API response, or ``None``."""
    urls = release_info.get("urls") or []
    by_type = {u.get("packagetype"): u for u in urls if isinstance(u, dict)}
    entry = by_type.get("bdist_wheel") or by_type.get("sdist")
    if entry is None and urls:
        entry = urls[0]
    if entry is None:
        return None
    digest = (entry.get("digests") or {}).get("sha256")
    return digest or None


def _prefetch_pypi_release_infos(
    name_versions: Iterable[tuple[str, str]],
) -> dict[tuple[str, str | None], dict[str, Any] | None]:
    """Concurrently fetch PyPI JSON API release info for each distinct
    ``(canonicalize_name(name), version)`` pair, so N dependencies cost roughly
    one network round-trip's worth of wall time instead of N sequential ones (each
    with its own TCP+TLS handshake and up to a
    :data:`_PYPI_TIMEOUT_SECONDS` timeout on failure).

    ``version == "unknown"`` is normalized to ``None`` here, matching
    :func:`_fetch_pypi_release_info`'s own "no pin -> latest release"
    semantics -- so two dependencies that both have an unresolved version
    share a single fetch instead of one per occurrence.
    """
    canon_to_name: dict[tuple[str, str | None], tuple[str, str | None]] = {}
    for name, version in name_versions:
        norm_version = version if version != "unknown" else None
        canon_key: tuple[str, str | None] = (
            str(canonicalize_name(name)),
            norm_version,
        )
        if canon_key not in canon_to_name:
            canon_to_name[canon_key] = (name, norm_version)

    if not canon_to_name:
        return {}
    results: dict[tuple[str, str | None], dict[str, Any] | None] = {}
    with ThreadPoolExecutor(
        max_workers=min(_PYPI_MAX_CONCURRENT_FETCHES, len(canon_to_name))
    ) as pool:
        futures = {
            pool.submit(_fetch_pypi_release_info, orig_name, norm_ver): k
            for k, (orig_name, norm_ver) in canon_to_name.items()
        }
        for future, k in futures.items():
            results[k] = future.result()
    return results
