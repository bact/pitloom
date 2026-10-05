# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Classify a licence value as an SPDX expression, licence text,
``NOASSERTION`` or ``NONE``, in canonical form, with the provenance notes
that record a rewrite.

See also: :mod:`pitloom.extract._license` (detection, re-exports these
names) and :mod:`pitloom.assemble.spdx3._license_elements` (the element
builder).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any, Literal

from py_spdx_license import ExceptionId as SpdxExceptionId
from py_spdx_license import ParseError as SpdxExpressionParseError
from py_spdx_license import get_exception as get_spdx_exception
from py_spdx_license import get_license as get_spdx_license
from py_spdx_license import parse as parse_spdx_expression

from pitloom.logging_config import warn_once

_logger = logging.getLogger(__name__)


try:
    _PY_SPDX_LICENSE_VERSION: str | None = _pkg_version("py-spdx-license")
except PackageNotFoundError:
    _PY_SPDX_LICENSE_VERSION = None


#: Matches AND/OR/WITH/NOT only when they stand alone as their own token
_SPDX_OPERATOR_CASING_RE = re.compile(
    r"(?<![\w-])(and|or|with|not)(?![\w-])", re.IGNORECASE
)


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
#: Valid in SPDX but outside ``py-spdx-license``'s grammar: an id with the
#: "or later" ``+`` suffix (a listed licence id only), and/or a ``WITH``
#: addition that is an ``AdditionRef-`` (an exception is in the grammar, but
#: not after a ``+``). Matches one such term: id, ``+``, addition.
_GAP_TERM_RE = re.compile(
    r"(?<![A-Za-z0-9.:+\-])([A-Za-z0-9.:\-]+)(\+)?"
    r"(?:\s+WITH\s+([A-Za-z0-9.:\-]+))?(?![A-Za-z0-9.+\-])"
)
_NO_OR_LATER = ("-only", "-or-later")
#: Stands in for a term the parser cannot read while the rest is
#: canonicalised; lengthened until the input does not contain it.
_GAP_PLACEHOLDER = "LicenseRef-pitloom-gap-"
_GAP_MARK_RE = re.compile("\x00(.*?)\x00")
#: Words standing for a named individual; ``UNKNOWN`` is a source saying it
#: does not know: ``NOASSERTION``. Value: ``(kind, canonical value)``.
_INDIVIDUAL_WORDS: dict[str, tuple[LicenseKind, str]] = {
    "NOASSERTION": ("noassertion", "NOASSERTION"),
    "UNKNOWN": ("noassertion", "NOASSERTION"),
    "NONE": ("none", "NONE"),
}
#: A lone surrogate (not UTF-8 encodable) in a licence value.
_SURROGATE_RE = re.compile("[\ud800-\udfff]")
_SURROGATE_MESSAGE = (
    "LICENSE=%a: has characters that cannot be encoded; each replaced with U+FFFD"
)
#: A deprecated licence id is replaced by its successor, found in the SPDX
#: License List bundled with ``py-spdx-license``: ``(deprecated suffix,
#: successor suffix)``, so ``LGPL-2.0+`` -> ``LGPL-2.0-or-later``. A bare
#: ``GPL-2.0`` is left as written: its holder's intent (``-only`` or
#: ``-or-later``) is unknown (see :func:`tag_deprecated_license_ids`).
_DEPRECATED_SUCCESSORS = (("+", "-or-later"),)


def _canonical_string(node: Any) -> str:
    """The canonical form of a parsed *node*: terms sorted, repeats removed.

    ``py-spdx-license`` 0.0.1 raises ``TypeError`` from ``sort()`` on some
    repeated terms (``MIT OR ISC OR MIT OR ISC``), so a flat chain of one
    operator is deduplicated first; any other shape that fails to sort keeps
    the parser's own (case- and space-canonical) spelling. A valid expression
    is never refused for want of a canonical order.
    """
    try:
        return str(node.sort().to_string())
    except TypeError:
        pass
    text = str(node.to_string())
    operators = set(re.findall(r"\b(AND|OR)\b", text))
    if "(" not in text and len(operators) == 1:
        operator = operators.pop()
        terms = list(dict.fromkeys(text.split(f" {operator} ")))
        deduped = parse_spdx_expression(f" {operator} ".join(terms))
        return str(deduped.sort().to_string())
    return text


def _strict_parse(expression: str) -> tuple[str | None, str]:
    """``(canonical form, "")`` of *expression*, else ``(None, reason)`` in
    one line. An unknown id is a failure, not a node."""
    try:
        node = parse_spdx_expression(expression)
        if isinstance(node, SpdxExceptionId):
            return None, "an exception is not a license"
        return _canonical_string(node), ""
    except SpdxExpressionParseError as exc:
        # The message quotes the input, so escape what could break a log line.
        return None, str(exc).encode("unicode_escape").decode("ascii")
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


def _gap_term(base: str, plus: bool, addition: str) -> str | None:
    """The canonical spelling of one gap term, or ``None`` when it is not
    valid SPDX: a listed id (no ``+`` after ``-only``/``-or-later``) or a
    ``LicenseRef-``/``DocumentRef-`` (no ``+`` at all), and a listed
    exception (or an ``AdditionRef-``) after ``WITH``."""
    listed = get_spdx_license(base)
    if listed:
        if plus and base.endswith(_NO_OR_LATER):
            return None
        spelled = str(listed["licenseId"]) + ("+" if plus else "")
    elif not plus and _strict_parse(base)[0] == base:
        spelled = base  # a user-defined reference, which the parser checks
    else:
        return None
    if not addition:
        return spelled
    exception = get_spdx_exception(addition)
    if exception:
        return f"{spelled} WITH {exception['licenseExceptionId']}"
    if addition.startswith("AdditionRef-"):
        return f"{spelled} WITH {addition}"
    return None


def _gap_expression(cased: str) -> str | None:
    """The canonical form of *cased* when it is valid SPDX that only the
    ``+``/``AdditionRef-`` gap keeps the parser from reading, else ``None``.

    Each gap term (``Apache-2.0+``, ``MIT WITH AdditionRef-x``) is checked
    (see :func:`_gap_term`) and stands in as a placeholder while the rest is
    parsed and sorted, so the order, spacing and repeats are canonical as for
    any expression. Placeholders sort by their term, whatever the input order,
    and use a prefix the input does not contain, so a user's own
    ``LicenseRef-pitloom-gap-...`` is never taken for one.
    """
    if "\x00" in cased:
        return None
    prefix = _GAP_PLACEHOLDER
    while prefix in cased:  # the parser keeps a reference's case
        prefix += "x-"
    ok = True

    def mark(match: re.Match[str]) -> str:
        nonlocal ok
        base, plus, addition = match.groups()
        if not (plus or (addition or "").startswith("AdditionRef-")):
            return match.group(0)
        spelled = _gap_term(base, bool(plus), addition or "")
        if spelled is None:
            ok = False
            return match.group(0)
        return f"\x00{spelled}\x00"

    marked = _GAP_TERM_RE.sub(mark, cased)
    terms = sorted(set(_GAP_MARK_RE.findall(marked)))
    if not ok or not terms:
        return None
    placeholders = {t: f"{prefix}{i:03d}" for i, t in enumerate(terms)}
    canonical, _ = _strict_parse(
        _GAP_MARK_RE.sub(lambda m: placeholders[m.group(1)], marked)
    )
    if canonical is None:
        return None
    return re.sub(
        re.escape(prefix) + r"(\d+)(?!\d)",
        lambda m: terms[int(m.group(1))],
        canonical,
    )


def _replace_surrogates(raw: str, warn: bool) -> str:
    """*raw* with each lone surrogate replaced by U+FFFD: it cannot be
    encoded, so it would fail the serialisation of the SBOM."""
    cleaned = _SURROGATE_RE.sub("\ufffd", raw)
    if warn:
        warn_once(_logger, raw, _SURROGATE_MESSAGE, raw)
    return cleaned


def _looks_like_expression(cased: str) -> bool:
    """Whether *cased* has an operator or parenthesis and a known id."""
    if not ("(" in cased or ")" in cased or _EXPRESSION_OPERATOR_RE.search(cased)):
        return False
    return any(
        _strict_parse(token.removesuffix("+"))[0] is not None
        for token in _EXPRESSION_TOKEN_RE.findall(cased)
        if not _EXPRESSION_OPERATOR_RE.fullmatch(token)
    )


#: A line of spaces and tabs only, after any line break (CR, LF, CRLF): a
#: Core Metadata writer folding with more than 8 spaces (numpy's 9) leaves
#: one on every blank line; a file may have them too.
_BLANK_LINE_RE = re.compile(r"(?<![^\r\n])[ \t]+(?![^\r\n])")


def empty_blank_lines(text: str) -> str:
    """*text* with each line of only spaces and tabs emptied, so a licence
    text compares and records alike from a file and from Core Metadata."""
    return _BLANK_LINE_RE.sub("", text)


def classify_license(raw: str | None, *, warn: bool = True) -> ClassifiedLicense | None:
    """Sort *raw* into an SPDX expression, licence text, ``NOASSERTION`` or
    ``NONE``; ``None`` when it states no licence (absent, blank).

    The words ``UNKNOWN``, ``NOASSERTION`` and ``NONE`` match in any case. A
    value that parses as an expression of known ids is recorded in its
    canonical form (``mit and apache-2.0`` -> ``Apache-2.0 AND MIT``). A
    deprecated id with a listed successor is replaced by it
    (``LGPL-2.0+`` -> ``LGPL-2.0-or-later``; see :data:`_DEPRECATED_SUCCESSORS`).
    One that is valid SPDX but outside the parser's grammar (``Apache-2.0+``,
    ``WITH AdditionRef-...``) is kept as written, ids in their listed case
    and operators upper-cased. Anything else is text, stripped, its lines of
    blank space emptied (:func:`empty_blank_lines`); text that
    has an operator or parenthesis and a known id, so looks like a broken
    expression, also gets one ``WARNING:`` per value per process, unless
    *warn* is false (a comparison, not a record of the value).
    """
    if raw and _SURROGATE_RE.search(raw):
        raw = _replace_surrogates(raw, warn)
    stripped = (raw or "").strip()
    word = stripped.upper()
    if not stripped:
        return None
    if word in _INDIVIDUAL_WORDS:
        kind, value = _INDIVIDUAL_WORDS[word]
        return ClassifiedLicense(kind, value, raw or "")
    if "\n" in stripped or len(stripped) > _MAX_EXPRESSION_LENGTH:
        return ClassifiedLicense("text", empty_blank_lines(stripped), raw or "")
    cased = _SPDX_OPERATOR_CASING_RE.sub(lambda m: m.group(1).upper(), stripped)
    cased = _ID_TOKEN_RE.sub(_replace_deprecated, cased)
    canonical, reason = _strict_parse(cased)
    if canonical is not None:
        return ClassifiedLicense("expression", canonical, raw or "")
    gap = _gap_expression(cased)
    if gap is not None:
        return ClassifiedLicense("expression", gap, raw or "")
    if warn and _looks_like_expression(cased):
        warn_once(_logger, stripped, _NOT_AN_EXPRESSION_MESSAGE, stripped, reason)
    return ClassifiedLicense("text", stripped, raw or "")


def is_listed_name(name: str, license_id: str) -> bool:
    """Whether *name* is the SPDX License List name of the listed id
    *license_id* (``MIT License`` for ``MIT``): the same licence spelled by
    name, as a ``License ::`` classifier does. Case-insensitive."""
    listed = get_spdx_license(license_id)
    return bool(listed) and name.strip().casefold() == str(listed["name"]).casefold()


def same_licence(first: str, second: str) -> bool:
    """Whether two classified licence values name one licence: equal, or one
    is the SPDX List name of the other's id (``MIT License`` and ``MIT``)."""
    return (
        first == second
        or is_listed_name(first, second)
        or is_listed_name(second, first)
    )


def tag_license_normalization(
    provenance: str, raw: str, normalized: str, *, normalizer: bool = True
) -> str:
    """Append a note to *provenance* when normalization changed the value;
    *normalizer* false leaves out the parser's version (no parse was
    involved, as for ``UNKNOWN`` -> ``NOASSERTION``)."""
    if raw.strip() == normalized:
        return provenance
    note = f"{provenance} | Normalized-From: {raw.strip()}"
    if not normalizer or _PY_SPDX_LICENSE_VERSION is None:
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
