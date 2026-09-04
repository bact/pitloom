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

import functools
import hashlib
import logging
import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from licenseid import AggregatedLicenseMatcher
from packaging.utils import canonicalize_name
from py_spdx_license import ParseError as SpdxExpressionParseError
from py_spdx_license import parse as parse_spdx_expression

from pitloom.core.project import ProjectFile
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
    "resolve_license_file_entries",
    "tag_license_normalization",
]

#: Matches AND/OR/WITH/NOT only when they stand alone as their own token
_SPDX_OPERATOR_CASING_RE = re.compile(
    r"(?<![\w-])(and|or|with|not)(?![\w-])", re.IGNORECASE
)

# Detects compound SPDX expressions: "MIT OR Apache-2.0", "GPL-2.0 WITH ..."
_SPDX_LICENSE_EXPR_KEYWORDS_RE = re.compile(r"\s+(OR|AND|WITH)\s+", re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def _get_matcher() -> AggregatedLicenseMatcher:
    """Return a process-wide shared matcher instead of one per lookup --
    each construction opens a sqlite3 connection, wasteful at project scale."""
    return AggregatedLicenseMatcher()


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
            _logger.warning(
                "licenseid database appears empty -- "
                "run 'licenseid update' to enable license text detection"
            )
            return None
        if len(text.strip()) < _MIN_LICENSE_TEXT_LENGTH:
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
        results = _get_matcher().match(license_id=raw)
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
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        # py-spdx-license can raise other than ParseError on malformed
        # input (e.g. unbalanced ")" -> IndexError); degrade gracefully
        # either way, same as canonicalize_license_id's fallback below.
        _logger.debug("SPDX expression parser raised unexpectedly for %r: %s", raw, exc)
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


def resolve_license_file_entries(
    project_dir: Path,
    name: str,
    version: str | None,
    license_files: list[str],
) -> list[ProjectFile]:
    """Build a :class:`~pitloom.core.project.ProjectFile` for each PEP 639
    ``[project.license-files]`` entry, ready to merge into
    :attr:`~pitloom.core.project.ProjectMetadata.files`.

    Pitloom's file discovery (``get_wheel_files()`` /
    ``_discover_included_files()``) is a static, config-driven file-selection
    walk, never a real wheel build -- so it never reproduces the
    ``<name>-<version>.dist-info/licenses/<path>`` entries a real build's
    ``WheelBuilder.add_licenses()`` would add. This fills that gap directly:
    called by the CLI/library generation path
    (:mod:`pitloom.assemble._generators`) and the Hatchling build hook
    (:mod:`pitloom.plugins.hatch`) after they've resolved ``project_dir`` and
    ``metadata.license_files``, so the resulting entries survive those call
    sites' ``metadata.files = project_files`` overwrite instead of being
    built too late for it.

    ``distribution_path`` uses the same name/version escaping every wheel
    build produces for its ``dist-info`` directory, per the current
    `Binary Distribution Format spec
    <https://packaging.python.org/en/latest/specifications/binary-distribution-format/#escaping-and-unicode>`_:
    regular name normalization (PEP 503, :func:`packaging.utils.canonicalize_name`)
    followed by replacing every ``-`` with ``_`` -- independent of which
    build backend actually produced *license_files*. A path that can't be
    read (already deleted, a broken glob match) is skipped with a warning
    rather than raising, since a project's SBOM generation should not
    hard-fail over one missing license file. A *version* that can't be
    resolved (e.g. a dynamic/SCM version outside a git checkout) is
    likewise a skip-with-warning for every entry, rather than fabricating
    one -- there is no real wheel filename to reproduce a path from.
    """
    if not license_files:
        return []
    if version is None:
        _logger.warning(
            "NAME=%s: project version could not be resolved -- skipping %d "
            "declared license-files entr%s (no real `.dist-info/licenses/` "
            "path to reproduce without a version)",
            name,
            len(license_files),
            "y" if len(license_files) == 1 else "ies",
        )
        return []
    escaped_name = canonicalize_name(name).replace("-", "_")
    dist_info_prefix = f"{escaped_name}-{version}.dist-info"
    entries: list[ProjectFile] = []
    seen: set[str] = set()
    for rel_path in license_files:
        if rel_path in seen:
            continue
        seen.add(rel_path)
        source = project_dir / rel_path
        try:
            raw_bytes = source.read_bytes()
        except OSError as exc:
            _logger.warning(
                "FILE=%s: could not read declared license-files entry; %s",
                rel_path,
                exc,
            )
            continue
        entries.append(
            ProjectFile(
                physical_path=rel_path,
                distribution_path=f"{dist_info_prefix}/licenses/{rel_path}",
                digest_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                is_license_file=True,
            )
        )
    return entries
