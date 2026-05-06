# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""License text detection utilities using the licenseid library.

Provides best-effort SPDX license ID detection from license text found in
project files.  All detection is optional and degrades gracefully when the
``licenseid`` package is not installed or its database has not been built.

To enable detection, install the package and build the database::

    pip install licenseid
    licenseid update
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

_logger = logging.getLogger(__name__)

# Heuristic: single-token SPDX License IDs and expressions like "GPL-3.0-or-later"
_SPDX_LICENSE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-+]*$")
# Detects compound SPDX expressions: "MIT OR Apache-2.0", "GPL-2.0 WITH ..."
_SPDX_LICENSE_EXPR_KEYWORDS_RE = re.compile(r"\s+(OR|AND|WITH)\s+", re.IGNORECASE)

# Candidate filenames in priority order (no-extension first, then common suffixes)
_LICENSE_STEMS = ("LICENSE", "LICENCE", "COPYING", "COPYRIGHT")
_LICENSE_SUFFIXES = ("", ".txt", ".rst", ".md")


def _looks_like_spdx_license_id(value: str) -> bool:
    """Return True when *value* looks like a bare SPDX License ID, not license text."""
    stripped = value.strip()
    return bool(
        stripped
        and "\n" not in stripped
        and len(stripped) < 100
        and _SPDX_LICENSE_ID_RE.match(stripped)
    )


def _looks_like_spdx_license_expression(value: str) -> bool:
    """Return True when *value* looks like a compound SPDX License Expression.

    SPDX License Expressions are single-line and short (e.g. ``MIT OR Apache-2.0``).
    Full license texts that happen to contain the word "AND" are excluded.
    """
    stripped = value.strip()
    if "\n" in stripped or len(stripped) > 200:
        return False
    return bool(_SPDX_LICENSE_EXPR_KEYWORDS_RE.search(stripped))


def _get_licenseid_db_path() -> Path:
    return Path.home() / ".local" / "share" / "licenseid" / "licenses.db"


def detect_license_from_text(text: str, threshold: float = 0.85) -> str | None:
    """Detect SPDX License ID from *text* using the licenseid library.

    Returns the top-ranked SPDX License ID when its score meets *threshold*, or
    ``None`` when the database is absent, the library is not installed, or no
    match exceeds the threshold.

    The database must be built before detection is possible::

        licenseid update
    """
    db_path = _get_licenseid_db_path()
    if not db_path.exists():
        _logger.warning(
            "licenseid database not found at %s — "
            "run 'licenseid update' to enable license text detection",
            db_path,
        )
        return None
    try:
        # pylint: disable=import-outside-toplevel
        from licenseid import AggregatedLicenseMatcher
    except ImportError:
        _logger.debug("licenseid not installed; skipping license text detection")
        return None
    try:
        matcher = AggregatedLicenseMatcher(str(db_path))
        results = matcher.match(text)
        filtered = [r for r in results if r["score"] >= threshold]
        return filtered[0]["license_id"] if filtered else None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.debug("licenseid detection failed: %s", exc)
        return None


def find_license_files(project_dir: Path) -> list[Path]:
    """Return existing license files in *project_dir* in priority order.

    Checks both upper- and lower-case variants of common license filenames.
    No-extension filenames (e.g. ``LICENSE``) take priority over suffixed ones.
    """
    # Map lowercase name → actual on-disk path so provenance uses the real filename
    try:
        actual: dict[str, Path] = {
            p.name.lower(): p for p in project_dir.iterdir() if p.is_file()
        }
    except OSError:
        return []

    seen: set[str] = set()
    found: list[Path] = []
    for stem in _LICENSE_STEMS:
        for suffix in _LICENSE_SUFFIXES:
            name_key = (stem + suffix).lower()
            if name_key not in seen and name_key in actual:
                seen.add(name_key)
                found.append(actual[name_key])
    return found


def _read_license_from_citation_cff(project_dir: Path) -> str | None:
    """Extract the ``license:`` field from ``CITATION.cff`` without a YAML dep.

    Handles the common scalar form (``license: MIT``) and the first item of the
    list form (``- MIT`` on the line after ``license:``).  Falls back to
    ``None`` when the file is absent or the field cannot be parsed.
    """
    cff_path = project_dir / "CITATION.cff"
    if not cff_path.exists():
        return None
    try:
        text = cff_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # Scalar: license: MIT  or  license: "MIT"
    scalar_m = re.search(
        r'^license:\s*["\']?([A-Za-z0-9][A-Za-z0-9.\-+]*)["\']?\s*$',
        text,
        re.MULTILINE,
    )
    if scalar_m:
        return scalar_m.group(1)

    # List: first item after "license:"
    list_m = re.search(
        r'^license:\s*\n\s*-\s*["\']?([A-Za-z0-9][A-Za-z0-9.\-+]*)["\']?',
        text,
        re.MULTILINE,
    )
    if list_m:
        return list_m.group(1)

    return None


def _read_license_from_codemeta_json(project_dir: Path) -> str | None:
    """Extract the ``license`` field from ``codemeta.json``.

    The field may be an SPDX License ID string or a URL such as
    ``https://spdx.org/licenses/MIT.html``.  URL-style values are reduced to
    their trailing path segment with common extensions stripped.

    TODO: If the URL prefix is not https://spdx.org/licenses/,
    we could try fetching the URL and applying licenseid detection to the
    content as a fallback.
    """
    codemeta_path = project_dir / "codemeta.json"
    if not codemeta_path.exists():
        return None
    try:
        data = json.loads(codemeta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    value = data.get("license", "")
    if not isinstance(value, str) or not value:
        return None

    # Strip URL prefix: https://spdx.org/licenses/MIT.html → MIT
    if "/" in value:
        candidate = value.rstrip("/").rsplit("/", 1)[-1]
        candidate = re.sub(r"\.(html|txt|md)$", "", candidate, flags=re.IGNORECASE)
        return candidate if _looks_like_spdx_license_id(candidate) else None

    return value if _looks_like_spdx_license_id(value) else None


def collect_license_candidates(project_dir: Path) -> list[tuple[str, str]]:
    """Return ``[(value, source_description), ...]`` for all license sources.

    Each *value* is either a bare SPDX License ID
    (check with :func:`_looks_like_spdx_license_id`)
    or full license text suitable for passing to :func:`detect_license_from_text`.
    Sources are ordered by priority: ``CITATION.cff``, ``codemeta.json``,
    then license files.
    """
    candidates: list[tuple[str, str]] = []

    cff_id = _read_license_from_citation_cff(project_dir)
    if cff_id:
        candidates.append((cff_id, "Source: CITATION.cff | Field: license"))

    codemeta_id = _read_license_from_codemeta_json(project_dir)
    if codemeta_id:
        candidates.append((codemeta_id, "Source: codemeta.json | Field: license"))

    for lf in find_license_files(project_dir):
        try:
            text = lf.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                rel = str(lf.relative_to(project_dir))
                candidates.append((text, f"Source: {rel}"))
        except OSError:
            pass

    return candidates


def detect_license_for_project(
    project_dir: Path,
    license_hint: str | None = None,
) -> tuple[str | None, str | None]:
    """Detect an SPDX license ID for a project, returning ``(id, provenance)``.

    Resolution order:

    1. *license_hint* is already a bare SPDX License ID → returned unchanged
       (caller should set provenance from the original metadata field).
    2. *license_hint* is a compound SPDX License Expression → returned unchanged.
    3. *license_hint* is license text → run :func:`detect_license_from_text`.
    4. Search ``CITATION.cff``, ``codemeta.json``, and license files in
       *project_dir*.

    Returns ``(None, None)`` when no license can be determined.
    """
    if license_hint:
        hint = license_hint.strip()
        if _looks_like_spdx_license_id(hint) or _looks_like_spdx_license_expression(
            hint
        ):
            return hint, None  # already good; let caller record original provenance

        # Hint is likely license text — try detection first
        detected = detect_license_from_text(hint)
        if detected:
            return detected, "Method: licenseid_detection"

    # Search project directory sources
    for value, source in collect_license_candidates(project_dir):
        if _looks_like_spdx_license_id(value) or _looks_like_spdx_license_expression(
            value
        ):
            return value, source
        detected = detect_license_from_text(value)
        if detected:
            return detected, f"{source} | Method: licenseid_detection"

    # Fall back to the raw hint (non-standard string) rather than returning None
    if license_hint and license_hint.strip():
        return license_hint.strip(), None

    return None, None
