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
import logging
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Literal

from licenseid import AggregatedLicenseMatcher
from py_spdx_license import ExceptionId as SpdxExceptionId
from py_spdx_license import ParseError as SpdxExpressionParseError
from py_spdx_license import get_exception as get_spdx_exception
from py_spdx_license import get_license as get_spdx_license
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
from pitloom.logging_config import warn_once

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
    "ClassifiedLicense",
    "canonicalize_license_id",
    "classify_license",
    "collect_license_candidates",
    "detect_independent_license",
    "detect_license_for_project",
    "detect_license_from_text",
    "find_license_files",
    "resolve_license_concluded",
    "tag_deprecated_license_ids",
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


LicenseKind = Literal["expression", "text", "noassertion", "none"]


@dataclass(frozen=True)
class ClassifiedLicense:
    """A licence value sorted by what it is. *value* is what to record
    (the canonical expression, the stripped text, or ``NOASSERTION``/``NONE``);
    *raw* is the input, for provenance."""

    kind: LicenseKind
    value: str
    raw: str


#: Longer or multi-line values are licence text; they are not parsed (a
#: 48 KB body costs seconds in the expression parser).
_MAX_EXPRESSION_LENGTH = 200

#: One line, one reason; ``%r`` keeps control characters out of the log.
_NOT_AN_EXPRESSION_MESSAGE = (
    "LICENSE=%r: not a valid SPDX license expression (%s); recorded as license text"
)

_EXPRESSION_OPERATOR_RE = re.compile(r"(?<![\w-])(?:AND|OR|WITH|NOT)(?![\w-])")
_EXPRESSION_TOKEN_RE = re.compile(r"[A-Za-z0-9.+:\-]+")
#: One id, ``+`` included: ``GPL-2.0+`` (a listed, deprecated id) is one token.
_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9.:\-]+\+?")
#: Valid in SPDX but outside ``py-spdx-license``'s grammar: the "or later"
#: ``+`` suffix (on a listed licence id only) and an ``AdditionRef-``
#: addition after ``WITH``.
_OR_LATER_RE = re.compile(r"([A-Za-z0-9.:\-]+)\+(?=$|[\s)])")
#: Not followed by ``+``: an addition takes no "or later".
_ADDITION_REF_RE = re.compile(
    r"(\bWITH\s+)AdditionRef-[A-Za-z0-9.\-]+(?![A-Za-z0-9.+\-])"
)
#: Ids that already say "only" or "or later" take no ``+``.
_NO_OR_LATER = ("-only", "-or-later")
_USER_DEFINED_PREFIXES = ("LicenseRef-", "DocumentRef-")
#: Stands in for an addition when checking the rest of the expression.
_PLACEHOLDER_EXCEPTION = "Classpath-exception-2.0"
#: A deprecated licence id is replaced by its successor, found in the SPDX
#: License List bundled with ``py-spdx-license``: ``(deprecated suffix,
#: successor suffix)``, so ``LGPL-2.0+`` -> ``LGPL-2.0-or-later``. A bare
#: ``GPL-2.0`` is left as written: its holder's intent (``-only`` or
#: ``-or-later``) is unknown (see :func:`tag_deprecated_license_ids`).
_DEPRECATED_SUCCESSORS = (("+", "-or-later"),)


def _strict_parse(expression: str) -> tuple[str | None, str]:
    """``(canonical form, "")`` of *expression*, else ``(None, reason)`` in
    one line. An unknown id is a failure, not a node."""
    try:
        node = parse_spdx_expression(expression)
        if isinstance(node, SpdxExceptionId):
            return None, "an exception is not a license"
        return str(node.sort().to_string()), ""
    except SpdxExpressionParseError as exc:
        # The message quotes the input, so escape what could break a log line.
        reason = (str(exc).splitlines() or ["unparsable"])[0]
        return None, reason.encode("unicode_escape").decode("ascii")
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:  # the parser can raise IndexError and the like
        return None, type(exc).__name__


def _successor_id(token: str) -> str | None:
    """The current id for a listed, deprecated id *token* (case-insensitive),
    in its canonical case; ``None`` when *token* is not one or has no
    non-deprecated successor on the list."""
    deprecated = get_spdx_license(token)
    if not deprecated or not deprecated["isDeprecatedLicenseId"]:
        return None
    for old, new in _DEPRECATED_SUCCESSORS:
        if token.endswith(old):
            successor = get_spdx_license(token[: len(token) - len(old)] + new)
            if successor and not successor["isDeprecatedLicenseId"]:
                return str(successor["licenseId"])
    return None


def _replace_deprecated(match: re.Match[str]) -> str:
    """The successor of a deprecated id token, unless another ``+`` follows
    (``GPL-2.0++`` is no id)."""
    token = match.group(0)
    if match.string[match.end() : match.end() + 1] == "+":
        return token
    return _successor_id(token) or token


def _canonical_case(match: re.Match[str]) -> str:
    """The id in *match* in the case the SPDX lists spell it; a token that is
    no licence or exception id (an operator, ``LicenseRef-x``) is unchanged."""
    token = match.group(0)
    base = token.removesuffix("+")
    listed = get_spdx_license(base) or get_spdx_exception(base)
    if not listed:
        return token
    spelled = str(listed.get("licenseId") or listed["licenseExceptionId"])
    return spelled + token[len(base) :]


def _strip_or_later(match: re.Match[str]) -> str:
    """Drop a ``+``, except after ``LicenseRef-``/``DocumentRef-`` or an id
    ending ``-only``/``-or-later`` (not valid SPDX): the parse of what is left
    then fails for a ``+`` after anything but a listed licence id."""
    token = match.group(1)
    if token.startswith(_USER_DEFINED_PREFIXES) or token.endswith(_NO_OR_LATER):
        return match.group(0)
    return token


def _looks_like_expression(cased: str) -> bool:
    """Whether *cased* has an operator or parenthesis and a known id."""
    if not ("(" in cased or ")" in cased or _EXPRESSION_OPERATOR_RE.search(cased)):
        return False
    return any(
        _strict_parse(token.removesuffix("+"))[0] is not None
        for token in _EXPRESSION_TOKEN_RE.findall(cased)
        if not _EXPRESSION_OPERATOR_RE.fullmatch(token)
    )


def classify_license(raw: str | None, *, warn: bool = True) -> ClassifiedLicense | None:
    """Sort *raw* into an SPDX expression, licence text, ``NOASSERTION`` or
    ``NONE``; ``None`` when it states no licence (absent, blank, ``UNKNOWN``).

    The words ``UNKNOWN``, ``NOASSERTION`` and ``NONE`` match in any case. A
    value that parses as an expression of known ids is recorded in its
    canonical form (``mit and apache-2.0`` -> ``Apache-2.0 AND MIT``). A
    deprecated id with a listed successor is replaced by it
    (``LGPL-2.0+`` -> ``LGPL-2.0-or-later``; see :data:`_DEPRECATED_SUCCESSORS`).
    One that is valid SPDX but outside the parser's grammar (``Apache-2.0+``,
    ``WITH AdditionRef-...``) is kept as written, ids in their listed case
    and operators upper-cased. Anything else is text, stripped; text that
    has an operator or parenthesis and a known id, so looks like a broken
    expression, also gets one ``WARNING:`` per value per process, unless
    *warn* is false (a comparison, not a record of the value).
    """
    stripped = (raw or "").strip()
    word = stripped.upper()
    if not stripped or word == "UNKNOWN":
        return None
    if word in ("NOASSERTION", "NONE"):
        return ClassifiedLicense(
            "noassertion" if word == "NOASSERTION" else "none", word, raw or ""
        )
    if "\n" in stripped or len(stripped) > _MAX_EXPRESSION_LENGTH:
        return ClassifiedLicense("text", stripped, raw or "")
    cased = _SPDX_OPERATOR_CASING_RE.sub(lambda m: m.group(1).upper(), stripped)
    cased = _ID_TOKEN_RE.sub(_replace_deprecated, cased)
    canonical, reason = _strict_parse(cased)
    if canonical is not None:
        return ClassifiedLicense("expression", canonical, raw or "")
    gapless = _ADDITION_REF_RE.sub(rf"\1{_PLACEHOLDER_EXCEPTION}", cased)
    gapless = _OR_LATER_RE.sub(_strip_or_later, gapless)
    if gapless != cased and _strict_parse(gapless)[0] is not None:
        return ClassifiedLicense(
            "expression", _ID_TOKEN_RE.sub(_canonical_case, cased), raw or ""
        )
    if warn and _looks_like_expression(cased):
        warn_once(_logger, stripped, _NOT_AN_EXPRESSION_MESSAGE, stripped, reason)
    return ClassifiedLicense("text", stripped, raw or "")


def tag_license_normalization(provenance: str, raw: str, normalized: str) -> str:
    """Append a note to *provenance* when normalization changed the value."""
    if raw.strip() == normalized:
        return provenance
    note = f"{provenance} | Normalized-From: {raw.strip()}"
    if _PY_SPDX_LICENSE_VERSION is None:
        return note
    return f"{note} | Normalizer: py-spdx-license=={_PY_SPDX_LICENSE_VERSION}"


def _ambiguous_deprecated_ids(expression: str) -> list[str]:
    """Each deprecated id of *expression*, once, as ``ID (ID-only or
    ID-or-later)`` when the list has both successors, so which was meant
    cannot be told (``GPL-2.0``)."""
    found: dict[str, str] = {}
    for token in _ID_TOKEN_RE.findall(expression):
        listed = get_spdx_license(token)
        only = get_spdx_license(token + "-only")
        later = get_spdx_license(token + "-or-later")
        if listed and listed["isDeprecatedLicenseId"] and only and later:
            found[token] = (
                f"{listed['licenseId']} ({only['licenseId']} or {later['licenseId']})"
            )
    return list(found.values())


def tag_deprecated_license_ids(provenance: str, expression: str) -> str:
    """Append a note to *provenance* for each deprecated id of *expression*
    whose successors are ambiguous. The id itself is kept as written."""
    ambiguous = _ambiguous_deprecated_ids(expression)
    if not ambiguous:
        return provenance
    return f"{provenance} | Deprecated-License-Id: {'; '.join(ambiguous)}"


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
