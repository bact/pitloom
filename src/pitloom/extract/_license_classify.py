# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Classify a licence value as an SPDX expression, licence text,
``NOASSERTION`` or ``NONE``, in canonical form, with the provenance notes
that record a rewrite. ``licenseid`` reads every expression; this module
keeps Pitloom's own rules around it: the named individuals, the values too
long or on several lines to read, the warnings.

See also: :mod:`pitloom.extract._license` (detection, re-exports these
names), :mod:`pitloom.extract._license_resolve` (the reading) and
:mod:`pitloom.assemble.spdx3._license_elements` (the element builder).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from pitloom.core.provenance import provenance_segment
from pitloom.extract._license_resolve import (
    is_licence_id,
    refusal_reason,
    resolution_notes,
    resolve_value,
    say_resolved,
)
from pitloom.logging_config import excerpt, warn_once

_logger = logging.getLogger(__name__)


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


#: Longer or multi-line values are licence text; they are not read (a
#: licence body is text, not an expression to resolve).
_MAX_EXPRESSION_LENGTH = 200

#: One line, one reason; ``%r`` keeps control characters out of the log.
_NOT_AN_EXPRESSION_MESSAGE = (
    "LICENSE=%r: not a valid SPDX license expression (%s); recorded as license text"
)

#: A field that holds an SPDX expression only, recorded as text. The value
#: through :func:`~pitloom.logging_config.excerpt`: one line, cut.
_UNREAD_SPDX_FIELD_MESSAGE = (
    "FIELD=%s LICENSE=%s: not read as an SPDX license expression (%s); "
    "recorded as license text"
)

_EXPRESSION_OPERATOR_RE = re.compile(r"(?<![\w-])(?:AND|OR|WITH|NOT)(?![\w-])")
_EXPRESSION_TOKEN_RE = re.compile(r"[A-Za-z0-9.+:\-]+")
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


def _replace_surrogates(raw: str, warn: bool) -> str:
    """*raw* with each lone surrogate replaced by U+FFFD: it cannot be
    encoded, so it would fail the serialisation of the SBOM."""
    cleaned = _SURROGATE_RE.sub("\ufffd", raw)
    if warn:
        warn_once(_logger, raw, _SURROGATE_MESSAGE, raw)
    return cleaned


def _looks_like_expression(stripped: str) -> bool:
    """Whether *stripped* has an operator (any case) or parenthesis and a
    word ``licenseid`` reads as a licence id (:func:`~pitloom.extract.\
_license_resolve.is_licence_id`; a ``+`` after it left out)."""
    cased = _SPDX_OPERATOR_CASING_RE.sub(lambda m: m.group(1).upper(), stripped)
    if not ("(" in cased or ")" in cased or _EXPRESSION_OPERATOR_RE.search(cased)):
        return False
    return any(
        is_licence_id(token.removesuffix("+"))
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
    single-line value of at most :data:`_MAX_EXPRESSION_LENGTH` characters
    in which ``licenseid`` reads an expression is recorded as that
    expression, in its canonical form (``mit and apache-2.0`` ->
    ``Apache-2.0 AND MIT``, ``LGPL-2.0+`` -> ``LGPL-2.0-or-later``,
    ``Apache2`` -> ``Apache-2.0``, ``MIT License`` -> ``MIT``; see
    :func:`~pitloom.extract._license_resolve.resolve_value`).
    Anything else is text, stripped, its lines of
    blank space emptied (:func:`empty_blank_lines`); text that
    has an operator or parenthesis and a known id, so looks like a broken
    expression, also gets one ``WARNING:`` per value per process, unless
    *warn* is false (a comparison, not a record of the value).
    """
    return _classify(raw, warn)[0]


def _classify(
    raw: str | None, warn: bool, field: str | None = None
) -> tuple[ClassifiedLicense | None, str]:
    """:func:`classify_license` and, for text, why it is not an expression
    (one line); ``""`` for any other kind. A value ``licenseid`` re-spells
    is said once (:func:`~pitloom.extract._license_resolve.say_resolved`)
    when it is recorded: *warn*, or the *field* it was read from is given."""
    if raw and _SURROGATE_RE.search(raw):
        raw = _replace_surrogates(raw, warn)
    stripped = (raw or "").strip()
    word = stripped.upper()
    if not stripped:
        return None, ""
    if word in _INDIVIDUAL_WORDS:
        kind, value = _INDIVIDUAL_WORDS[word]
        return ClassifiedLicense(kind, value, raw or ""), ""
    if "\n" in stripped or len(stripped) > _MAX_EXPRESSION_LENGTH:
        reason = (
            "more than one line"
            if "\n" in stripped
            else f"longer than {_MAX_EXPRESSION_LENGTH} characters, not parsed"
        )
        text = ClassifiedLicense("text", empty_blank_lines(stripped), raw or "")
        return text, reason
    return _expression_or_text(stripped, raw or "", warn, field)


def _expression_or_text(
    stripped: str, raw: str, warn: bool, field: str | None
) -> tuple[ClassifiedLicense, str]:
    """The reading of the single-line *stripped* value: the expression
    ``licenseid`` reads in it (said once when it differs from *stripped* and
    the value is recorded: *warn*, or a *field* is given), else text with
    why it is not one."""
    resolved = resolve_value(stripped)
    if resolved is not None:
        if (warn or field is not None) and resolved.expression != stripped:
            say_resolved(stripped, resolved, field)
        return ClassifiedLicense("expression", resolved.expression, raw), ""
    reason = refusal_reason(stripped)
    if warn and _looks_like_expression(stripped):
        warn_once(_logger, stripped, _NOT_AN_EXPRESSION_MESSAGE, stripped, reason)
    return ClassifiedLicense("text", stripped, raw), reason


def warn_unless_expression(value: str | None, field: str) -> None:
    """One ``WARNING:`` per value per process when *value*, read from
    *field*, a field that holds an SPDX license expression only (PEP 639
    ``project.license``, Core Metadata ``License-Expression``, a file's
    ``SPDX-License-Identifier`` tag, GGUF ``general.license``, a PyPI
    record's ``license_expression``), is not one
    that Pitloom reads (``Acme-Terms``, ``MIT OR Foo``, a licence text), so is
    recorded as licence text. An expression, ``NOASSERTION``/``UNKNOWN``,
    ``NONE`` and a blank value are quiet. A field that may hold free text
    (Core Metadata ``License``, ``project.license.text``) never calls this.

    The key is the one :func:`classify_license`'s broken-expression warning
    uses, so a value is said once, by whichever comes first."""
    classified, reason = _classify(value, False, field)
    if classified is None or classified.kind != "text":
        return
    warn_once(
        _logger,
        classified.value,
        _UNREAD_SPDX_FIELD_MESSAGE,
        field,
        excerpt(classified.value),
        reason,
    )


#: What a model card or file puts in a licence field for "a licence, not
#: named here" (the name is in another field): a placeholder, not a claim.
VAGUE_LICENSE_VALUES: frozenset[str] = frozenset(
    {"other", "custom", "proprietary", "unknown", "unlicensed"}
)


def is_vague_license_value(value: str | None) -> bool:
    """Whether *value* is one of :data:`VAGUE_LICENSE_VALUES`, in any case."""
    return value is not None and value.strip().lower() in VAGUE_LICENSE_VALUES


def is_weak_licence(value: str | None) -> bool:
    """Whether *value* is a placeholder (``NOASSERTION``/``UNKNOWN``, any
    case), not a claim. ``NONE`` is a statement, not weak."""
    classified = classify_license(value, warn=False)
    return classified is not None and classified.kind == "noassertion"


def tag_license_normalization(
    provenance: str, raw: str, normalized: str, *, resolver: bool = True
) -> str:
    """Append a note to *provenance* when normalization changed the value:
    ``Normalized-From``, and the resolver's keys
    (:func:`~pitloom.extract._license_resolve.resolution_notes`) unless
    *resolver* is false (no reading was involved, as for ``UNKNOWN`` ->
    ``NOASSERTION``)."""
    if raw.strip() == normalized:
        return provenance
    note = provenance_segment(provenance, "Normalized-From", raw.strip())
    return note + resolution_notes(raw, normalized) if resolver else note


def tag_deprecated_license_ids(provenance: str, expression: str) -> str:
    """Append a note to *provenance* for each deprecated id of *expression*
    whose successors are ambiguous (``GPL-2.0 (GPL-2.0-only or
    GPL-2.0-or-later)``, as ``licenseid`` names them). The id itself is kept
    as written."""
    resolved = resolve_value(expression)
    if resolved is None or not resolved.deprecated:
        return provenance
    return provenance_segment(
        provenance, "Deprecated-License-Id", "; ".join(resolved.deprecated)
    )
