# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Licence text detection with LicenseID's detector.

:func:`detect_license_from_text` names the SPDX licence a text is, from the
LicenseID database: built once per process (:func:`_get_detector`), warned
about once when it cannot be used (:func:`_database_unusable`), and read
with the stated licence winning a near-tie. Build the database before first
use::

    licenseid update --source packaged

Every LicenseID call runs inside
:func:`pitloom.extract._licenseid_relay.relay_licenseid_warnings`.

See also: :mod:`pitloom.extract._license` (licence files and a stated
licence) and :mod:`pitloom.extract.remote.huggingface_fetch` (a Hub
repository's licence files), the callers, and
:mod:`pitloom.extract._license_detect` (which files are read).
"""

from __future__ import annotations

import functools
import logging
import re
from collections.abc import Sequence

from licenseid import DatabaseNotReadyError, Detection, LicenseDetector

from pitloom.core.quote_source import quote_source
from pitloom.extract._license_detect import (
    _looks_like_spdx_license_expression,
    _looks_like_spdx_license_id,
)
from pitloom.extract._license_resolve import resolve_value
from pitloom.extract._licenseid_relay import relay_licenseid_warnings
from pitloom.extract.copyright_notices import COPYRIGHT_NOTICE_LINE_RE
from pitloom.logging_config import log_once, one_line, warn_once

_logger = logging.getLogger(__name__)

__all__ = ["detect_license_from_text"]


@functools.lru_cache(maxsize=1)
def _get_detector() -> LicenseDetector:
    """Return a process-wide shared detector instead of one per lookup --
    each construction opens a sqlite3 connection, wasteful at project scale.
    A failed construction raises and is not cached: :func:`_detector` retries
    it on the next lookup. What LicenseID warns while building it (a
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
    """The path LicenseID says it looked for (the detail of its ``not
    found``), so a missing database names where Pitloom looked."""
    detail = exc.detail if isinstance(exc, DatabaseNotReadyError) else None
    return detail or ""


def _database_unusable(exc: BaseException, *, declared: bool = False) -> None:
    """Warn once per process that the database cannot be used, and drop the
    cached detector, so the next lookup builds (and checks) it again.

    With *declared* (a licence is stated, so only the licence-file second
    opinion needs the database) a missing database is said once at INFO: the
    stated value is recorded as it is. A declared licence text, which only
    the database can read, is no *declared* lookup: it warns, as does an
    empty, invalid or unreadable database. A declared name too short to be
    a licence text never gets here (:data:`_MIN_LICENSE_TEXT_LENGTH`)."""
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


_MIN_LICENSE_TEXT_LENGTH = 100
"""Below this length, *text* is a short label (e.g. ``"MIT License
(MIT)"``, seen in real-world ``[project.license].text`` values), not an
actual licence body -- similarity-matching it against LicenseID's
database is unreliable at this length and can score a coincidental
false positive above the match threshold. Every real SPDX license
text is well over this length (0BSD, the shortest, is ~500 characters),
so this only ever excludes non-license-body input, never a genuine
short license."""


#: Two matches this close are a tie. LicenseID ranks a near-variant of
#: a listed licence (``Pixar``, a modified Apache 2.0; ``JSON``, MIT plus one
#: sentence) a few thousandths above the licence itself for its verbatim
#: text; a different licence scores far lower. A *stated* licence wins a
#: tie; with none stated, a tie is no detection.
_STATED_TIE_MARGIN = 0.01

#: The highest score LicenseID (0.4 and later) gives: a capped score no
#: longer tells how far above the licence a near-variant scores.
_SCORE_CAP = 1.0

#: The ids an expression names; operators are not ids.
_EXPRESSION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+:-]*")
_EXPRESSION_OPERATORS = frozenset({"and", "or", "with"})


def _stated_ids(stated: str | None) -> frozenset[str]:
    """The licence ids *stated* names, case-folded, as LicenseID reads
    them (``MIT OR GPL-2.0+`` names ``MIT`` and ``GPL-2.0-or-later``), as
    written when it reads none; none for a licence text or name."""
    value = (stated or "").strip()
    if not (
        _looks_like_spdx_license_id(value) or _looks_like_spdx_license_expression(value)
    ):
        return frozenset()
    resolved = resolve_value(value)
    return frozenset(
        token.casefold()
        for token in _EXPRESSION_ID_RE.findall(
            resolved.expression if resolved else value
        )
        if token.casefold() not in _EXPRESSION_OPERATORS
    )


def _stated_among(results: Sequence[Detection], stated: frozenset[str]) -> str | None:
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
    """*value* as a number; ``None`` where LicenseID measured nothing
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
    cannot tell: LicenseID caps it to 1, where ``MIT`` verbatim and
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
    LicenseID's own ranking order."""
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
    too), without them: LicenseID uses a notice to place the licence in
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
    """Detect SPDX License ID from *text* using the LicenseID library.

    Returns the top-ranked SPDX License ID when its score meets *threshold*,
    or ``None`` when *text* is too short to be a real licence body (decided
    before the database is looked up, so nothing is said about it), the
    database cannot be used, or no match exceeds the threshold. *text* is
    read as written and without its copyright notice lines
    (:func:`_readings`); the better-scoring reading counts
    (:func:`_best_readings`). A licence *stated* (the manifest's declared
    licence) makes a missing database an ``INFO:`` line
    (:func:`_database_unusable`). An id or expression it names that *text*
    matches at *threshold* nearly as well as its top match, and fits the
    input as well, wins (:data:`_STATED_TIE_MARGIN`); else that reading
    decides (:func:`_best_reading_decides`), ``None`` when its top match is
    a near-tie with another licence family.
    """
    # A text too short to be a licence body is no detection: decided before
    # the database is looked up, so a short label never reports one missing.
    if len(text.strip()) < _MIN_LICENSE_TEXT_LENGTH:
        return None
    declared = bool(stated and stated.strip())
    detector = _detector(declared=declared)
    if detector is None:
        return None
    try:
        readings = _readings(detector, text)
        wanted = _stated_ids(stated)
        for results in _best_readings(readings):
            above = [r for r in results if r["score"] >= threshold]
            chosen = _stated_among(above, wanted)
            if chosen:
                return chosen
        return _best_reading_decides(readings, threshold)
    # The database failed after the detector was built (deleted, truncated,
    # corrupted): LicenseID raises this for any failed read.
    except DatabaseNotReadyError as exc:
        _database_unusable(exc, declared=declared)
        return None
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        _logger.debug("licenseid detection failed: %s", exc)
        return None
