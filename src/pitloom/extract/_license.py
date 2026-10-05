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
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from licenseid import AggregatedLicenseMatcher
from licenseid.types import LicenseMatch

from pitloom.core.project import ProjectMetadata
from pitloom.extract._license_classify import (
    _PY_SPDX_LICENSE_VERSION,
    ClassifiedLicense,
    classify_license,
    is_listed_name,
    same_licence,
    tag_deprecated_license_ids,
    tag_license_normalization,
)
from pitloom.extract._license_detect import (
    _LICENSE_STEMS,
    _LICENSE_SUFFIXES,
    _SPDX_LICENSE_ID_RE,
    _looks_like_spdx_license_id,
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
    "_looks_like_spdx_license_expression",
    "_looks_like_spdx_license_id",
    "_with_tool_tag",
    "ClassifiedLicense",
    "apply_in_package_license",
    "canonicalize_license_id",
    "classify_license",
    "collect_license_candidates",
    "detect_independent_license",
    "detect_license_for_project",
    "detect_license_from_text",
    "find_license_files",
    "is_listed_name",
    "license_from_candidates",
    "same_licence",
    "resolve_license_concluded",
    "stated_license",
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


#: Two matches this close are a tie. ``licenseid`` ranks a near-variant of
#: a listed licence (``Pixar``, a modified Apache 2.0; ``JSON``, MIT plus one
#: sentence) a few thousandths above the licence itself for its verbatim
#: text; a different licence scores far lower. A *stated* licence wins a
#: tie; with none stated, a tie is no detection.
_STATED_TIE_MARGIN = 0.01


def _stated_among(results: Sequence[LicenseMatch], stated: str | None) -> str | None:
    """The id of *results* that is the single licence id *stated*, when it
    scores within :data:`_STATED_TIE_MARGIN` of the top match."""
    wanted = (stated or "").strip().casefold()
    if not wanted or not results:
        return None
    top = float(results[0]["score"])
    for result in results:
        if str(result["license_id"]).casefold() == wanted:
            near = float(result["score"]) >= top - _STATED_TIE_MARGIN
            return str(result["license_id"]) if near else None
    return None


#: A copyright notice line: ``Copyright`` with ``(c)``, a copyright sign or
#: a year, or ``(c)``/the sign with a year. The SPDX License List Matching
#: Guidelines leave a notice out of a match; ``licenseid`` can miss a listed
#: licence behind one (PyYAML's two notice lines give ``Xnet``, not ``MIT``).
_COPYRIGHT_NOTICE_RE = re.compile(
    r"^[ \t]*(?:copyright[ \t]*(?:\(c\)|\u00a9|\d)|(?:\(c\)|\u00a9)[ \t]*\d).*$",
    re.IGNORECASE | re.MULTILINE,
)


def _matches(
    matcher: AggregatedLicenseMatcher, text: str, threshold: float
) -> list[LicenseMatch]:
    """*matcher*'s ranked matches for *text* scoring at least *threshold*,
    from the text as written or without its copyright notice lines,
    whichever matches better: ``licenseid`` uses a notice to place the
    licence in mixed content, yet misses some licences behind one."""
    matches = [r for r in matcher.match(text) if r["score"] >= threshold]
    without_notice = _COPYRIGHT_NOTICE_RE.sub("", text)
    if without_notice == text:
        return matches
    other = [r for r in matcher.match(without_notice) if r["score"] >= threshold]
    if other and (not matches or other[0]["score"] > matches[0]["score"]):
        return other
    return matches


def detect_license_from_text(
    text: str, threshold: float = 0.85, *, stated: str | None = None
) -> str | None:
    """Detect SPDX License ID from *text* using the licenseid library.

    Returns the top-ranked SPDX License ID when its score meets *threshold*, or
    ``None`` when the database is not populated, *text* is too short to be a
    real license body, or no match exceeds the threshold (copyright notice
    lines read both ways, see :func:`_matches`). A *stated* licence
    (the manifest's own id) that the text matches nearly as well as the top
    match wins the near-tie (:data:`_STATED_TIE_MARGIN`); with none stated,
    a near-tie between two licences is ``None``.
    """
    try:
        matcher = _get_matcher()
        if not matcher.match(license_id="MIT"):
            _warn_empty_database()
            return None
        if len(text.strip()) < _MIN_LICENSE_TEXT_LENGTH:
            return None
        filtered = _matches(matcher, text, threshold)
        if not filtered:
            return None
        chosen = _stated_among(filtered, stated)
        if chosen:
            return chosen
        tied = len(filtered) > 1 and (
            filtered[1]["score"] >= filtered[0]["score"] - _STATED_TIE_MARGIN
        )
        return None if tied else str(filtered[0]["license_id"])
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


def license_from_candidates(
    candidates: Sequence[tuple[str, str]], *, stated: str | None = None
) -> tuple[str, str] | None:
    """``(id, provenance)`` from the first of *candidates* (see
    :func:`~pitloom.extract._license_detect.license_candidates_from_members`)
    that states an id or expression, or whose text ``licenseid`` identifies
    (the manifest's *stated* licence winning a near-tie, see
    :func:`detect_license_from_text`); ``None`` when none does."""
    for value, source in candidates:
        if _looks_like_spdx_license_id(value) or _looks_like_spdx_license_expression(
            value
        ):
            return value, source
        detected = detect_license_from_text(value, stated=stated)
        if detected:
            return detected, _with_tool_tag(f"{source} | Method: licenseid_detection")
    return None


def detect_independent_license(
    project_dir: Path, *, stated: str | None = None
) -> tuple[str | None, str | None]:
    """Detect a license purely from project-directory files (*stated*: see
    :func:`license_from_candidates`)."""
    found = license_from_candidates(
        collect_license_candidates(project_dir), stated=stated
    )
    return found if found is not None else (None, None)


def resolve_license_concluded(
    has_declared_license: bool, project_dir: Path, *, stated: str | None = None
) -> tuple[str | None, str | None]:
    """Return ``(concluded_id, concluded_provenance)`` (G2 second opinion;
    *stated*, the declared licence: see :func:`license_from_candidates`)."""
    if not has_declared_license:
        return None, None
    return detect_independent_license(project_dir, stated=stated)


def apply_in_package_license(
    metadata: ProjectMetadata, candidates: Sequence[tuple[str, str]]
) -> None:
    """Record what the project's own licence files say (*candidates*, see
    :func:`license_from_candidates`) on *metadata*, the one rule for every
    project reader (directory, Hatchling hook, sdist): when the manifest
    states a licence (``license_name`` not blank), the detection is the
    concluded second opinion (G2); when it is silent, the declared licence.
    Nothing changes when no candidate gives a licence."""
    stated = (metadata.license_name or "").strip()
    found = license_from_candidates(candidates, stated=stated)
    if found is None:
        return
    detected, provenance = found
    if stated:
        metadata.license_concluded = detected
        metadata.provenance["license_concluded"] = provenance
    else:
        metadata.license_name = detected
        metadata.provenance["license"] = provenance


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
    if not (license_hint or "").strip():
        return detect_independent_license(project_dir)
    return stated_license(license_hint, hint_source)


def stated_license(
    license_hint: str | None, hint_source: str = ""
) -> tuple[str | None, str | None]:
    """``(id, provenance)`` for the licence a manifest states, *license_hint*:
    an id or an expression stripped; text that ``licenseid`` identifies, the
    id, with *hint_source* and the method in the provenance; other text as
    written, with no provenance. ``(None, None)`` when blank: the project's
    own files are not read here (:func:`apply_in_package_license`)."""
    hint = (license_hint or "").strip()
    if not hint:
        return None, None
    if _looks_like_spdx_license_id(hint) or _looks_like_spdx_license_expression(hint):
        return hint, None
    detected = detect_license_from_text(hint)
    if detected:
        method = "Method: licenseid_detection"
        return detected, _with_tool_tag(
            f"{hint_source} | {method}" if hint_source else method
        )
    return license_hint, None
