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
    :mod:`pitloom.extract._license_detect` for file candidate scanning.
"""

from __future__ import annotations

import logging
import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from licenseid import AggregatedLicenseMatcher
from py_spdx_license import ParseError as SpdxExpressionParseError
from py_spdx_license import parse as parse_spdx_expression

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

try:
    _PY_SPDX_LICENSE_VERSION: str | None = _pkg_version("py-spdx-license")
except PackageNotFoundError:
    _PY_SPDX_LICENSE_VERSION = None

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
    "canonicalize_license_id",
    "collect_license_candidates",
    "detect_independent_license",
    "detect_license_for_project",
    "detect_license_from_text",
    "find_license_files",
    "normalize_license_expression",
    "resolve_license_concluded",
    "tag_license_normalization",
]

#: Matches AND/OR/WITH/NOT only when they stand alone as their own token
_SPDX_OPERATOR_CASING_RE = re.compile(
    r"(?<![\w-])(and|or|with|not)(?![\w-])", re.IGNORECASE
)

# Detects compound SPDX expressions: "MIT OR Apache-2.0", "GPL-2.0 WITH ..."
_SPDX_LICENSE_EXPR_KEYWORDS_RE = re.compile(r"\s+(OR|AND|WITH)\s+", re.IGNORECASE)


def _looks_like_spdx_license_expression(value: str) -> bool:
    """Return True when *value* looks like a compound SPDX License Expression."""
    stripped = value.strip()
    if "\n" in stripped or len(stripped) > 200:
        return False
    return bool(_SPDX_LICENSE_EXPR_KEYWORDS_RE.search(stripped))


def detect_license_from_text(text: str, threshold: float = 0.85) -> str | None:
    """Detect SPDX License ID from *text* using the licenseid library.

    Returns the top-ranked SPDX License ID when its score meets *threshold*, or
    ``None`` when the database is not populated or no match exceeds the threshold.
    """
    try:
        matcher = AggregatedLicenseMatcher()
        if not matcher.match(license_id="MIT"):
            _logger.warning(
                "licenseid database appears empty -- "
                "run 'licenseid update' to enable license text detection"
            )
            return None
        results = matcher.match(text)
        filtered = [r for r in results if r["score"] >= threshold]
        return str(filtered[0]["license_id"]) if filtered else None
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        _logger.debug("licenseid detection failed: %s", exc)
        return None


def canonicalize_license_id(raw: str) -> str:
    """Return the canonical SPDX License ID for *raw*, or *raw* unchanged."""
    try:
        results = AggregatedLicenseMatcher().match(license_id=raw)
        if results:
            return str(results[0]["license_id"])
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        _logger.debug("Failed to canonicalize license id %r: %s", raw, exc)
    return raw


def normalize_license_expression(raw: str) -> str:
    """Return *raw* normalized to a canonical SPDX license expression."""
    operator_cased = _SPDX_OPERATOR_CASING_RE.sub(
        lambda m: m.group(1).upper(), raw.strip()
    )
    try:
        node = parse_spdx_expression(operator_cased, allow_unknown=True)
        return str(node.sort().to_string())
    except SpdxExpressionParseError as exc:
        _logger.debug("Failed to parse SPDX expression %r: %s", raw, exc)
    return canonicalize_license_id(raw)


def tag_license_normalization(provenance: str, raw: str, normalized: str) -> str:
    """Append a note to *provenance* when normalization changed the value."""
    if raw.strip() == normalized:
        return provenance
    note = f"{provenance} | Normalized-From: {raw.strip()}"
    if _PY_SPDX_LICENSE_VERSION is None:
        return note
    return f"{note} | Normalizer: py-spdx-license=={_PY_SPDX_LICENSE_VERSION}"


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
) -> tuple[str | None, str | None]:
    """Detect an SPDX license ID for a project, returning ``(id, provenance)``."""
    if license_hint:
        hint = license_hint.strip()
        if _looks_like_spdx_license_id(hint) or _looks_like_spdx_license_expression(
            hint
        ):
            return hint, None

        detected = detect_license_from_text(hint)
        if detected:
            return detected, _with_tool_tag("Method: licenseid_detection")

    directory_id, directory_prov = detect_independent_license(project_dir)
    if directory_id:
        return directory_id, directory_prov

    if license_hint and license_hint.strip():
        return license_hint.strip(), None

    return None, None
