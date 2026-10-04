# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""License text detection utilities using the licenseid library.

Provides SPDX license ID detection from license text and metadata found in
project files.  Text detection requires a populated database; other sources
(``CITATION.cff``, ``codemeta.json``) work without it.

Build the database before first use::

    licenseid update

See Also:
    :mod:`pitloom.extract._license_detect` for file candidate scanning, and
    :mod:`pitloom.extract._license_classify` for classifying a value
    (re-exported here).
"""

from __future__ import annotations

import functools
import logging
import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from licenseid import AggregatedLicenseMatcher

from pitloom.extract._license_classify import (
    _PY_SPDX_LICENSE_VERSION,
    _SPDX_OPERATOR_CASING_RE,
    ClassifiedLicense,
    classify_license,
    is_listed_name,
    tag_deprecated_license_ids,
    tag_license_normalization,
)
from pitloom.extract._license_detect import (
    _LICENSE_STEMS,
    _LICENSE_SUFFIXES,
    _SPDX_LICENSE_ID_RE,
    _looks_like_spdx_license_id,
    _read_license_from_citation_cff,
    _read_license_from_codemeta_json,
    collect_license_candidates,
    find_license_files,
)

_logger = logging.getLogger(__name__)

try:
    _LICENSEID_VERSION: str | None = _pkg_version("licenseid")
except PackageNotFoundError:
    _LICENSEID_VERSION = None

__all__ = [
    "_LICENSE_STEMS",
    "_LICENSE_SUFFIXES",
    "_LICENSEID_VERSION",
    "_PY_SPDX_LICENSE_VERSION",
    "_SPDX_LICENSE_EXPR_KEYWORDS_RE",
    "_SPDX_LICENSE_ID_RE",
    "_SPDX_OPERATOR_CASING_RE",
    "_looks_like_spdx_license_expression",
    "_looks_like_spdx_license_id",
    "_read_license_from_citation_cff",
    "_read_license_from_codemeta_json",
    "_with_tool_tag",
    "ClassifiedLicense",
    "canonicalize_license_id",
    "classify_license",
    "collect_license_candidates",
    "detect_independent_license",
    "detect_license_for_project",
    "detect_license_from_text",
    "find_license_files",
    "is_listed_name",
    "resolve_license_concluded",
    "tag_deprecated_license_ids",
    "tag_license_normalization",
]


# Detects compound SPDX expressions: "MIT OR Apache-2.0", "GPL-2.0 WITH ..."
_SPDX_LICENSE_EXPR_KEYWORDS_RE = re.compile(r"\s+(OR|AND|WITH)\s+", re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def _get_matcher() -> AggregatedLicenseMatcher:
    """Return a process-wide shared matcher instead of one per lookup --
    each construction opens a sqlite3 connection, wasteful at project scale."""
    return AggregatedLicenseMatcher()


@functools.cache
def _warn_empty_database() -> None:
    """Warn once per process: an empty database is a fact about the
    environment, not about each lookup, so one run's several detections
    (a project read, then an embed of each wheel) share one warning."""
    _logger.warning(
        "licenseid database appears empty -- "
        "run 'licenseid update' to enable license text detection"
    )


def _looks_like_spdx_license_expression(value: str) -> bool:
    """Return True when *value* looks like a compound SPDX License Expression."""
    stripped = value.strip()
    if "\n" in stripped or len(stripped) > 200:
        return False
    return bool(_SPDX_LICENSE_EXPR_KEYWORDS_RE.search(stripped))


_MIN_LICENSE_TEXT_LENGTH = 100
"""Below this length, *text* is a short label (e.g. ``"MIT License
(MIT)"``, seen in real-world ``[project.license].text`` values), not an
actual license body -- similarity-matching it against ``licenseid``'s
database is unreliable at this length and can score a coincidental
false positive above the match threshold. Every real SPDX license
text is well over this length (0BSD, the shortest, is ~500 characters),
so this only ever excludes non-license-body input, never a genuine
short license."""


def detect_license_from_text(text: str, threshold: float = 0.85) -> str | None:
    """Detect SPDX License ID from *text* using the licenseid library.

    Returns the top-ranked SPDX License ID when its score meets *threshold*, or
    ``None`` when the database is not populated, *text* is too short to be a
    real license body, or no match exceeds the threshold.
    """
    try:
        matcher = _get_matcher()
        if not matcher.match(license_id="MIT"):
            _warn_empty_database()
            return None
        if len(text.strip()) < _MIN_LICENSE_TEXT_LENGTH:
            return None
        results = matcher.match(text)
        filtered = [r for r in results if r["score"] >= threshold]
        return str(filtered[0]["license_id"]) if filtered else None
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        _logger.debug("licenseid detection failed: %s", exc)
        return None


def canonicalize_license_id(raw: str) -> str:
    """Return the canonical SPDX License ID for *raw*, or *raw* unchanged."""
    try:
        results = _get_matcher().match(license_id=raw)
        if results:
            return str(results[0]["license_id"])
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        _logger.debug("Failed to canonicalize license id %r: %s", raw, exc)
    return raw


def _with_tool_tag(provenance: str) -> str:
    """Append the ``licenseid`` library version to a detection provenance string."""
    if _LICENSEID_VERSION is None:
        return provenance
    return f"{provenance} | Tool: licenseid=={_LICENSEID_VERSION}"


def detect_independent_license(project_dir: Path) -> tuple[str | None, str | None]:
    """Detect a license purely from project-directory files."""
    candidates = collect_license_candidates(project_dir)
    for value, source in candidates:
        if _looks_like_spdx_license_id(value) or _looks_like_spdx_license_expression(
            value
        ):
            return value, source
        detected = detect_license_from_text(value)
        if detected:
            return detected, _with_tool_tag(f"{source} | Method: licenseid_detection")
    return None, None


def resolve_license_concluded(
    has_declared_license: bool, project_dir: Path
) -> tuple[str | None, str | None]:
    """Return ``(concluded_id, concluded_provenance)`` (G2 second opinion)."""
    if not has_declared_license:
        return None, None
    return detect_independent_license(project_dir)


def detect_license_for_project(
    project_dir: Path,
    license_hint: str | None = None,
    hint_source: str = "",
) -> tuple[str | None, str | None]:
    """Detect an SPDX license ID for a project, returning ``(id, provenance)``.

    A stated *license_hint* is the manifest's own licence: an id or an
    expression is returned stripped; text that ``licenseid`` identifies gives
    the id, with *hint_source* and the method in the provenance; other text
    is returned as written, with no provenance (no detection happened). The
    project directory is read only when no hint is stated: against a stated
    licence it is the G2 second opinion (:func:`resolve_license_concluded`),
    not a replacement.
    """
    hint = (license_hint or "").strip()
    if not hint:
        return detect_independent_license(project_dir)
    if _looks_like_spdx_license_id(hint) or _looks_like_spdx_license_expression(hint):
        return hint, None
    detected = detect_license_from_text(hint)
    if detected:
        method = "Method: licenseid_detection"
        return detected, _with_tool_tag(
            f"{hint_source} | {method}" if hint_source else method
        )
    return license_hint, None
