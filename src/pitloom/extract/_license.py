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
"""

from __future__ import annotations

import json
import logging
import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from licenseid import AggregatedLicenseMatcher
from py_spdx_license import ParseError as SpdxExpressionParseError
from py_spdx_license import parse as parse_spdx_expression

_logger = logging.getLogger(__name__)

try:
    _LICENSEID_VERSION: str | None = _pkg_version("licenseid")
except PackageNotFoundError:
    _LICENSEID_VERSION = None

try:
    _PY_SPDX_LICENSE_VERSION: str | None = _pkg_version("py-spdx-license")
except PackageNotFoundError:
    _PY_SPDX_LICENSE_VERSION = None

#: Matches AND/OR/WITH/NOT only when they stand alone as their own token
#: (whitespace/paren-delimited on both sides) -- exactly what SPDX expression
#: syntax requires of a real operator. Deliberately *not* a plain ``\b`` word
#: boundary: ``\b`` also fires at hyphens, which would mangle a hyphen-glued
#: identifier that merely contains "and"/"or"/"with" as a substring (a real
#: SPDX id like ``GPL-2.0-or-later``, or a custom ``LicenseRef-my-or-license``)
#: into wrongly-cased ``-OR-``.
_SPDX_OPERATOR_CASING_RE = re.compile(
    r"(?<![\w-])(and|or|with|not)(?![\w-])", re.IGNORECASE
)

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


def detect_license_from_text(text: str, threshold: float = 0.85) -> str | None:
    """Detect SPDX License ID from *text* using the licenseid library.

    Returns the top-ranked SPDX License ID when its score meets *threshold*, or
    ``None`` when the database is not populated or no match exceeds the threshold.

    The database must be built before detection is possible::

        licenseid update
    """
    try:
        matcher = AggregatedLicenseMatcher()
        # Probe with a well-known license ID to confirm the database is populated.
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
    """Return the canonical SPDX License ID for *raw*, or *raw* unchanged.

    Uses ``AggregatedLicenseMatcher.match(license_id=raw)`` for a direct
    database lookup.  Returns the canonical casing when *raw* is a recognised
    SPDX License ID (e.g. ``"bsd-3-clause"`` -> ``"BSD-3-Clause"``).

    For unrecognised values -- non-SPDX identifiers, deprecated bare
    copyleft forms (``"agpl-3.0"``, ``"gpl-3.0"``), or vendor-specific
    strings (``"gemma"``, ``"llama3.2"``) -- the original string is
    returned verbatim.  pitloom records what it found and leaves further
    interpretation (e.g. deciding whether to add a ``LicenseRef-`` prefix)
    to the ``licenseid`` library or downstream SBOM tooling.

    Requires a populated database (``licenseid update``).  When the database
    is not populated *raw* is returned unchanged.
    """
    try:
        results = AggregatedLicenseMatcher().match(license_id=raw)
        if results:
            return str(results[0]["license_id"])
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        _logger.debug("Failed to canonicalize license id %r: %s", raw, exc)
    return raw


def normalize_license_expression(raw: str) -> str:
    """Return *raw* normalized to a canonical SPDX license expression, or
    *raw* unchanged when it can't be parsed as one.

    Handles what :func:`canonicalize_license_id` cannot: a *compound*
    expression (``"MIT AND MIT"``, ``"Apache-2.0 OR MIT"``) is deduplicated
    and canonically reordered via ``py_spdx_license`` -- so two candidates
    that are semantically the same license, just spelled differently, are
    recognized as equal rather than misreported as a G2 conflict
    (``"MIT AND MIT"`` and ``"MIT OR Apache-2.0"``/``"Apache-2.0 OR MIT"``
    both normalize to the same string regardless of input ordering). A bare
    id is also canonicalized to its recognized SPDX casing as a side effect
    of parsing (``"mit"`` -> ``"MIT"``), same as :func:`canonicalize_license_id`.

    Before parsing, ``AND``/``OR``/``WITH``/``NOT`` are case-normalized to
    uppercase when they appear as their own whitespace/paren-delimited token
    (SPDX expression syntax is operator-case-strict; a lowercase ``"mit and
    mit"`` would otherwise fail to parse at all) -- but *only* when
    isolated like that, so a hyphen-glued identifier that merely contains
    "and"/"or"/"with" as a substring (``"GPL-2.0-or-later"``, a custom
    ``"LicenseRef-my-or-license"``) is never touched.

    Falls back to :func:`canonicalize_license_id` when the (operator-cased)
    string can't be parsed as a valid SPDX expression at all -- e.g. genuinely
    malformed syntax (unbalanced parens, a missing operand) -- so a simple
    bare id still gets at least casing normalization even in that case.
    """
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
    """Append a note to *provenance* when :func:`normalize_license_expression`
    actually changed *raw* to *normalized* (e.g. ``"mit"`` -> ``"MIT"``,
    ``"MIT AND MIT"`` -> ``"MIT"``), recording the ``py-spdx-license``
    version that did it.

    A no-op (returns *provenance* unchanged) when *raw* and *normalized*
    already match -- nothing to flag. Mirrors :func:`_with_tool_tag`'s
    pattern for ``licenseid``, so a G2 candidate whose declared-side value
    was rewritten before comparison stays auditable against the exact
    normalizer version that rewrote it, not just "some normalization ran".
    """
    if raw.strip() == normalized:
        return provenance
    note = f"{provenance} | Normalized-From: {raw.strip()}"
    if _PY_SPDX_LICENSE_VERSION is None:
        return note
    return f"{note} | Normalizer: py-spdx-license=={_PY_SPDX_LICENSE_VERSION}"


def find_license_files(project_dir: Path) -> list[Path]:
    """Return existing license files in *project_dir* in priority order.

    Checks both upper- and lower-case variants of common license filenames.
    No-extension filenames (e.g. ``LICENSE``) take priority over suffixed ones.
    """
    # Map lowercase name -> actual on-disk path so provenance uses the real filename
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

    # Strip URL prefix: https://spdx.org/licenses/MIT.html -> MIT
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
                rel = lf.relative_to(project_dir).as_posix()
                candidates.append((text, f"Source: {rel}"))
        except OSError:
            pass

    return candidates


def _with_tool_tag(provenance: str) -> str:
    """Append the ``licenseid`` library version to a detection provenance string.

    A ``licenseid_detection`` result is only as reproducible as the license
    database of the library version that produced it -- record which one ran,
    so a ``detected``-role G2 candidate's evidence stays auditable across
    library upgrades. Falls back to the bare string when the installed
    version can't be resolved (e.g. an unusual/editable install).
    """
    if _LICENSEID_VERSION is None:
        return provenance
    return f"{provenance} | Tool: licenseid=={_LICENSEID_VERSION}"


def detect_independent_license(project_dir: Path) -> tuple[str | None, str | None]:
    """Detect a license purely from project-directory files (``CITATION.cff``,
    ``codemeta.json``, license files), ignoring any already-declared value.

    Used to independently corroborate or conflict-check a declared license
    (G2) -- unlike :func:`detect_license_for_project`, this never considers a
    caller-supplied hint, so its result is a genuine second opinion.

    Returns ``(None, None)`` when nothing in *project_dir* yields a license.
    """
    for value, source in collect_license_candidates(project_dir):
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
    """Return ``(concluded_id, concluded_provenance)`` -- G2's independent
    second opinion -- or ``(None, None)`` when there's no declared value to
    compare it against.

    **Every extractor that resolves a project's own declared license must
    call this alongside its own declared-value resolution.** This is the
    single, canonical G2 entry point precisely so a *new* extraction path
    can't silently omit conflict detection the way the Hatchling build-hook
    path (:func:`~pitloom.extract.hatchling.metadata_from_hatchling`)
    originally did -- it called :func:`detect_license_for_project` directly
    and never ran the independent directory scan at all, so G2 only ever
    fired via the CLI's :func:`~pitloom.extract._pyproject.read_pyproject`.
    If you're adding a new project-metadata extractor, call this too; see
    ``tests/test_hatch_hook.py``'s
    ``test_metadata_from_hatchling_matches_read_pyproject_for_license_conflict``
    for the cross-path regression test this class of gap needs.

    Args:
        has_declared_license: Whether the caller's own metadata source
            already resolved *some* declared value (however obtained --
            a bare id, a license file reference, license text). When
            ``False``, there's nothing to compare a second opinion against,
            so no scan is performed.
        project_dir: Project root directory to independently scan.
    """
    if not has_declared_license:
        return None, None
    return detect_independent_license(project_dir)


def detect_license_for_project(
    project_dir: Path,
    license_hint: str | None = None,
) -> tuple[str | None, str | None]:
    """Detect an SPDX license ID for a project, returning ``(id, provenance)``.

    Resolution order:

    1. *license_hint* is already a bare SPDX License ID -> returned unchanged
       (caller should set provenance from the original metadata field).
    2. *license_hint* is a compound SPDX License Expression -> returned unchanged.
    3. *license_hint* is license text -> run :func:`detect_license_from_text`.
    4. :func:`detect_independent_license` over *project_dir*.

    Returns ``(None, None)`` when no license can be determined.
    """
    if license_hint:
        hint = license_hint.strip()
        if _looks_like_spdx_license_id(hint) or _looks_like_spdx_license_expression(
            hint
        ):
            return hint, None  # already good; let caller record original provenance

        # Hint is likely license text -- try detection first
        detected = detect_license_from_text(hint)
        if detected:
            return detected, _with_tool_tag("Method: licenseid_detection")

    directory_id, directory_prov = detect_independent_license(project_dir)
    if directory_id:
        return directory_id, directory_prov

    # Fall back to the raw hint (non-standard string) rather than returning None
    if license_hint and license_hint.strip():
        return license_hint.strip(), None

    return None, None
