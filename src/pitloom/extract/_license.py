# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""License text detection utilities using the licenseid library.

Provides SPDX license ID detection from license text and metadata found in
project files, and the shared ``licenseid.resolve`` reading of a declared
value (:func:`resolve_declared_value`).  Text detection requires a populated
database; the reading of a declared value (``Apache2`` -> ``Apache-2.0``)
uses the SPDX License List packaged with ``licenseid`` and needs none, as
other sources (``CITATION.cff``, ``codemeta.json``) do not.

Build the database for text detection before first use::

    licenseid update --source packaged

Every ``licenseid`` call runs inside
:func:`pitloom.extract._licenseid_relay.relay_licenseid_warnings`.

See Also:
    :mod:`pitloom.extract._license_detect` for file candidate scanning,
    :mod:`pitloom.extract._license_classify` for classifying a value
    (re-exported here), and :mod:`pitloom.extract._license_resolve` for
    which ``licenseid`` readings are accepted.
"""

from __future__ import annotations

import copy
import functools
import logging
import re
from collections.abc import Mapping, Sequence
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from licenseid import (
    DatabaseNotReadyError,
    Detection,
    LicenseDetector,
    Resolution,
    resolve,
)

from pitloom.core.lfs_pointer import is_pointer_text
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import provenance_segment
from pitloom.core.quote_source import quote_source
from pitloom.extract._license_classify import (
    _PY_SPDX_LICENSE_VERSION,
    ClassifiedLicense,
    classify_license,
    empty_blank_lines,
    is_listed_name,
    is_weak_licence,
    same_licence,
    tag_deprecated_license_ids,
    tag_license_normalization,
    warn_unless_expression,
    with_successor_ids,
)
from pitloom.extract._license_detect import (
    _LICENSE_STEMS,
    _LICENSE_SUFFIXES,
    _SPDX_LICENSE_ID_RE,
    _looks_like_spdx_license_id,
    collect_license_candidates,
    find_license_files,
    license_candidates_from_members,
)
from pitloom.extract._licenseid_relay import relay_licenseid_warnings, say
from pitloom.extract.copyright_notices import (
    COPYRIGHT_NOTICE_LINE_RE,
    apply_in_package_copyright,
)
from pitloom.logging_config import log_once, one_line, warn_once

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
    "apply_in_package_license_files",
    "classify_license",
    "clear_resolution_cache",
    "collect_license_candidates",
    "detect_independent_license",
    "detect_license_for_project",
    "detect_license_from_text",
    "empty_blank_lines",
    "find_license_files",
    "is_listed_name",
    "is_weak_licence",
    "license_from_candidates",
    "same_licence",
    "resolve_declared_value",
    "resolve_license_concluded",
    "stated_license",
    "tag_deprecated_license_ids",
    "tag_license_normalization",
    "warn_unless_expression",
]


# Detects compound SPDX expressions: "MIT OR Apache-2.0", "GPL-2.0 WITH ..."
_SPDX_LICENSE_EXPR_KEYWORDS_RE = re.compile(r"\s+(OR|AND|WITH)\s+", re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def _get_detector() -> LicenseDetector:
    """Return a process-wide shared detector instead of one per lookup --
    each construction opens a sqlite3 connection, wasteful at project scale.
    A failed construction raises and is not cached: :func:`_detector` retries
    it on the next lookup. What ``licenseid`` warns while building it (a
    database built by an older release) is relayed."""
    with relay_licenseid_warnings():
        return LicenseDetector()


#: The sub-prefix of every message about the database, so the sibling lines
#: of :func:`_database_unusable` keep one grammar.
_DB_PREFIX = "licenseid database"


def _database_missing(exc: BaseException) -> bool:
    """True when *exc* says the database file is absent (condition ``not
    found``, the path as its detail), not empty, invalid or unreadable.
    ``no home directory`` is a setup problem (``pass --db``), not a database
    to build: it stays a warning."""
    return (
        isinstance(exc, DatabaseNotReadyError)
        and exc.condition == "not found"
        and exc.detail is not None
        and exc.detail != "no home directory"
    )


def _missing_database_path(exc: BaseException) -> str:
    """The path licenseid says it looked for (the detail of its ``not
    found``), so a missing database names where Pitloom looked."""
    detail = exc.detail if isinstance(exc, DatabaseNotReadyError) else None
    return detail or ""


def _database_unusable(exc: BaseException, *, declared: bool = False) -> None:
    """Warn once per process that the database cannot be used, and drop the
    cached detector, so the next lookup builds (and checks) it again.

    With *declared* (a licence is stated, so only the licence-file second
    opinion needs the database) a missing database is said once at INFO: the
    stated value is recorded as it is. Any other condition still warns."""
    _get_detector.cache_clear()
    if declared and _database_missing(exc):
        log_once(
            _logger,
            logging.INFO,
            "licenseid database missing",
            "%s not found: %s -- license text detection skipped; "
            "run 'licenseid update --source packaged'",
            _DB_PREFIX,
            quote_source(_missing_database_path(exc)),
        )
        return
    warn_once(
        _logger,
        "licenseid database",
        "%s cannot be used: %s -- license text detection skipped",
        _DB_PREFIX,
        one_line(exc),
    )


def _detector(*, declared: bool = False) -> LicenseDetector | None:
    """The shared detector, or None when the database cannot be used
    (missing, empty, unreadable). Warned once per process (*declared*:
    :func:`_database_unusable`); retried on every lookup, so a database
    built later in a long-lived process is used."""
    try:
        return _get_detector()
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        _database_unusable(exc, declared=declared)
        return None


#: How many answers of :func:`_resolved` are kept: a value asked about by
#: several callers costs one lookup.
_MAX_RESOLUTIONS = 4096


@functools.lru_cache(maxsize=_MAX_RESOLUTIONS)
def _resolved(value: str) -> Resolution:
    """``licenseid``'s reading of *value* on the SPDX License List packaged
    with it (``source="packaged"``: the same answer whatever database the
    user has, and with none). A failure raises and is not cached."""
    with relay_licenseid_warnings():
        return resolve(value, source="packaged")


def clear_resolution_cache() -> None:
    """Forget the answers of :func:`resolve_declared_value`."""
    _resolved.cache_clear()


def resolve_declared_value(value: str) -> Resolution | None:
    """``licenseid``'s reading of the declared licence *value*
    (:func:`licenseid.resolve` on its packaged SPDX License List), or
    ``None`` when there is no packaged list (a ``licenseid`` installed
    without it: warned once per process) or the resolver fails; a failure
    is not cached. Each caller gets its own copy."""
    try:
        return copy.deepcopy(_resolved(value))
    except DatabaseNotReadyError as exc:
        say(f"{exc}; declared licence values recorded as written")
        return None
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        _logger.debug("Failed to resolve license value %r: %s", value, exc)
        return None


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

#: The highest score ``licenseid`` (0.4 and later) gives: a capped score no
#: longer tells how far above the licence a near-variant scores.
_SCORE_CAP = 1.0

#: The ids an expression names; operators are not ids.
_EXPRESSION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+:-]*")
_EXPRESSION_OPERATORS = frozenset({"and", "or", "with"})


def _stated_ids(stated: str | None) -> frozenset[str]:
    """The licence ids *stated* names, case-folded, deprecated ``+`` ids as
    their successors (``MIT OR GPL-2.0+`` names ``MIT`` and
    ``GPL-2.0-or-later``); none for a licence text or name."""
    value = (stated or "").strip()
    if not (
        _looks_like_spdx_license_id(value) or _looks_like_spdx_license_expression(value)
    ):
        return frozenset()
    return frozenset(
        token.casefold()
        for token in _EXPRESSION_ID_RE.findall(with_successor_ids(value))
        if token.casefold() not in _EXPRESSION_OPERATORS
    )


def _stated_among(
    results: Sequence[Detection], stated: frozenset[str]
) -> str | None:
    """The best-scoring id of *results* that *stated* names, when it scores
    within :data:`_STATED_TIE_MARGIN` of the top match. Against a top match
    at :data:`_SCORE_CAP` the score no longer tells how close they are, so
    the stated match must also fit the input as well (:func:`_fits_worse`):
    ``JSON`` stated over a verbatim MIT text (1.0) is no near-tie, while
    requests' Apache 2.0 text still concludes a stated ``Apache-2.0`` over
    ``Pixar`` (0.9921 against 0.9963, a better fit)."""
    if not stated or not results:
        return None
    ranked = sorted(results, key=lambda r: -float(r["score"]))
    top_score = float(ranked[0]["score"])
    floor = top_score - _STATED_TIE_MARGIN
    for result in ranked:
        if float(result["score"]) < floor:
            return None
        if str(result["expression"]).casefold() not in stated:
            continue
        if top_score < _SCORE_CAP or not _fits_worse(result, ranked[0]):
            return str(result["expression"])
    return None


def _family(license_id: str) -> str:
    """*license_id* without its ``-only``/``-or-later`` suffix: a verbatim
    GPL text scores both alike, and cannot tell them apart."""
    return re.sub(r"-(?:only|or-later)$", "", license_id)


def _measured(value: object) -> float | None:
    """*value* as a number; ``None`` where ``licenseid`` measured nothing
    (0.4 gives ``None``, 0.3 always a number)."""
    return float(value) if isinstance(value, (int, float)) else None


def _fit(match: Detection) -> tuple[float | None, float | None]:
    """How closely the input matches *match*'s licence: its ``similarity``,
    and the share of the licence the input holds, its ``coverage`` (input
    words over licence words) up to 1, as above 1 the input only has words
    besides the licence."""
    coverage = _measured(match.get("coverage"))
    held = None if coverage is None else min(coverage, 1.0)
    return _measured(match.get("similarity")), held


def _fits_worse(runner_up: Detection, top: Detection) -> bool:
    """Whether *runner_up* fits the input measurably worse than *top*
    (:func:`_fit`): its similarity, or the share of its licence the input
    holds, more than :data:`_STATED_TIE_MARGIN` below *top*'s. A score alone
    cannot tell: ``licenseid`` caps it to 1, where ``MIT`` verbatim and
    ``FSL-1.1-MIT``, which holds the MIT text as a quarter of its own, both
    score 1. Unmeasured, it does not."""
    return any(
        mine is not None and theirs is not None and mine < theirs - _STATED_TIE_MARGIN
        for mine, theirs in zip(_fit(runner_up), _fit(top), strict=True)
    )


def _decisive(results: Sequence[Detection], threshold: float) -> str | None:
    """The top id of *results* when it meets *threshold* and no other
    licence family scores within :data:`_STATED_TIE_MARGIN` of it (a
    runner-up below *threshold* counts) without fitting the input
    measurably worse (:func:`_fits_worse`). Equal scores keep
    ``licenseid``'s own ranking order."""
    if not results:
        return None
    ranked = sorted(results, key=lambda r: -float(r["score"]))
    if float(ranked[0]["score"]) < threshold:
        return None
    top = str(ranked[0]["expression"])
    floor = float(ranked[0]["score"]) - _STATED_TIE_MARGIN
    for result in ranked[1:]:
        if float(result["score"]) < floor:
            break
        if _family(str(result["expression"])) != _family(top) and not _fits_worse(
            result, ranked[0]
        ):
            return None
    return top


def _readings(detector: LicenseDetector, text: str) -> list[list[Detection]]:
    """*detector*'s ranked matches for *text* as written and, when it has
    copyright notice lines (:data:`COPYRIGHT_NOTICE_LINE_RE`, templates
    too), without them: ``licenseid`` uses a notice to place the licence in
    mixed content, yet misses some licences behind one (PyYAML's two notice
    lines give ``Xnet``, not ``MIT``)."""
    with relay_licenseid_warnings():
        readings = [detector.detect(text)]
        without_notice = COPYRIGHT_NOTICE_LINE_RE.sub("", text)
        if without_notice != text:
            readings.append(detector.detect(without_notice))
    return readings


def _top_score(results: Sequence[Detection]) -> float:
    """The best score in *results*, or -1 for none."""
    return max((float(r["score"]) for r in results), default=-1.0)


def _best_readings(
    readings: Sequence[Sequence[Detection]],
) -> list[Sequence[Detection]]:
    """The readings whose top score is the best: one, or both when their
    top scores are equal (as when both reach the cap). A weaker reading
    decides nothing, nor lets a stated licence win (iniconfig's notice
    puts ``FSL-1.1-MIT`` on top of the reading as written; without it, MIT
    scores 1)."""
    best = max(_top_score(results) for results in readings)
    return [results for results in readings if _top_score(results) == best]


def _best_reading_decides(
    readings: Sequence[Sequence[Detection]], threshold: float
) -> str | None:
    """The answer of the best-scoring reading (:func:`_best_readings`); of
    two tied at the top, the first that decides (:func:`_decisive`), so a
    near-tie in one never hides the other's answer. Two that decide
    differently give the first's: reading order is fixed."""
    answers = (_decisive(results, threshold) for results in _best_readings(readings))
    return next((answer for answer in answers if answer), None)


def detect_license_from_text(
    text: str, threshold: float = 0.85, *, stated: str | None = None
) -> str | None:
    """Detect SPDX License ID from *text* using the licenseid library.

    Returns the top-ranked SPDX License ID when its score meets *threshold*, or
    ``None`` when the database cannot be used, *text* is too short to be a
    real license body, or no match exceeds the threshold. *text* is read as
    written and without its copyright notice lines (:func:`_readings`); the
    better-scoring reading counts (:func:`_best_readings`). A licence
    *stated* (the manifest's own id or expression) that it matches at
    *threshold* nearly as well as its top match, and fits the input as
    well, wins (:data:`_STATED_TIE_MARGIN`); else that reading decides
    (:func:`_best_reading_decides`),
    ``None`` when its top match is a near-tie with another licence family.
    """
    declared = bool(stated and stated.strip())
    detector = _detector(declared=declared)
    if detector is None:
        return None
    try:
        if len(text.strip()) < _MIN_LICENSE_TEXT_LENGTH:
            return None
        readings = _readings(detector, text)
        wanted = _stated_ids(stated)
        for results in _best_readings(readings):
            above = [r for r in results if r["score"] >= threshold]
            chosen = _stated_among(above, wanted)
            if chosen:
                return chosen
        return _best_reading_decides(readings, threshold)
    # The database failed after the detector was built (deleted, truncated,
    # corrupted): licenseid raises this for any failed read.
    except DatabaseNotReadyError as exc:
        _database_unusable(exc, declared=declared)
        return None
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        _logger.debug("licenseid detection failed: %s", exc)
        return None


def _with_tool_tag(provenance: str) -> str:
    """Append the ``licenseid`` library version to a detection provenance string."""
    if _LICENSEID_VERSION is None:
        return provenance
    return provenance_segment(provenance, "Tool", f"licenseid=={_LICENSEID_VERSION}")


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
            return detected, _with_tool_tag(
                provenance_segment(source, "Method", "licenseid_detection")
            )
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
    project reader (:func:`apply_in_package_license_files`): when the manifest
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


def apply_in_package_license_files(
    metadata: ProjectMetadata,
    members: Mapping[str, bytes],
    archive: str | None = None,
) -> None:
    """Record what the project's own licence sources say on *metadata*,
    the one call every project reader (directory, Hatchling hook, sdist)
    makes: its licence (:func:`apply_in_package_license`) and the copyright
    notices found (:func:`~pitloom.extract.copyright_notices.\
apply_in_package_copyright`). *members* maps a root-level name to its bytes
    (:func:`~pitloom.extract._license_detect.read_license_members` for a
    directory); *archive* names the archive they come from."""
    apply_in_package_license(
        metadata, license_candidates_from_members(members, archive)
    )
    apply_in_package_copyright(metadata, members, archive)


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
    written, with no provenance. ``(None, None)`` when blank, or when the
    whole hint is a Git LFS pointer (a licence file not pulled, read by a
    build backend as its text: no licence text); the project's own files
    are not read here (:func:`apply_in_package_license`)."""
    hint = (license_hint or "").strip()
    if not hint or is_pointer_text(license_hint or ""):
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
