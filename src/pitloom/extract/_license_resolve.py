# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A declared licence value read through ``licenseid.resolve``, the only
reader of one: what it reads, and how each answer is said in the log and the
provenance.

LicenseID decides what a value names (``Apache2`` is ``Apache-2.0``,
``mit and apache-2.0`` is ``Apache-2.0 AND MIT``) on the SPDX License List
packaged with it, so the reading needs no database and is the same whatever
database the user has. Every answer with an expression is recorded as that
expression; a value it names nothing in stays text, with its ``reason``.
A resolution that rewrites more than the form of the text (a re-spelling, a
listed name, a stated "or later", a renamed id) is the resolver's decision,
not the author's words: one ``INFO:`` line per value, and ``Resolution-1``
in the provenance.

See also: :mod:`pitloom.extract._license_classify` and
:func:`pitloom.extract._core_metadata.license_from_classifiers` (the callers)
and :mod:`pitloom.extract._licenseid_relay` (what LicenseID says).
"""

from __future__ import annotations

import copy
import functools
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from licenseid import DatabaseNotReadyError, Operand, Resolution, Step, resolve

from pitloom.core.provenance import provenance_segment
from pitloom.extract._licenseid_relay import relay_licenseid_warnings, say
from pitloom.logging_config import excerpt, log_once, loggable

_logger = logging.getLogger(__name__)

#: How many answers of :func:`_resolved` are kept: a value asked about by
#: several callers costs one lookup.
_MAX_RESOLUTIONS = 4096

#: Only the form of the text changed, or ``+`` was written as ``-or-later``
#: (its own key): the author's id stands, so nothing is said above ``DEBUG:``.
_FORM_ONLY = frozenset({"exact", "lexical", "plus_to_or_later"})
#: A deprecated id kept as written, its ``-only`` or ``-or-later`` unknown
#: (``GPL-2.0``): decided only where an operand was re-spelt to reach it
#: (``GPLv3``); the possible successors are noted
#: (:attr:`DeclaredResolution.deprecated`).
_KEPT_AS_WRITTEN = frozenset({"assumed_only", "deprecated_ambiguous"})
#: The categories of a word that is one licence id as written, case and a
#: listed deprecated id included (a deprecated id reached by a re-spelling,
#: ``GPLv3``, is not): what the broken-expression check counts.
_ID_CATEGORIES = _FORM_ONLY | _KEPT_AS_WRITTEN | {"deprecated_equal_successor"}


@functools.lru_cache(maxsize=_MAX_RESOLUTIONS)
def _resolved(value: str) -> Resolution:
    """LicenseID's reading of *value* on the SPDX License List packaged
    with it (``source="packaged"``: the same answer whatever database the
    user has, and with none). A failure raises and is not cached."""
    with relay_licenseid_warnings():
        return resolve(value, source="packaged")


def clear_resolution_cache() -> None:
    """Forget the answers of :func:`resolve_declared_value`."""
    _resolved.cache_clear()


def resolve_declared_value(value: str) -> Resolution | None:
    """LicenseID's reading of the declared licence *value*
    (:func:`licenseid.resolve` on its packaged SPDX License List), or
    ``None`` when there is no packaged list (a ``licenseid`` installed
    without it: its error relayed once per process, as LicenseID
    words it) or the resolver fails; a failure is not cached. Each caller
    gets its own copy."""
    try:
        return copy.deepcopy(_resolved(value))
    except DatabaseNotReadyError as exc:
        say(str(exc))
        return None
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        _logger.debug("Failed to resolve license value %r: %s", value, exc)
        return None


@dataclass(frozen=True)
class DeclaredResolution:
    """What LicenseID read in a declared value: the *expression* to record,
    its *category*, the *steps* it took (``separator``, ``version_spelling``,
    ...), the qualifier steps (*expansions*) apart, whether it *decided*
    something beyond form, the *tool* that read it (``licenseid==0.7.2``),
    and each *deprecated* id whose successors are ambiguous, as
    ``ID (ID-only or ID-or-later)``."""

    expression: str
    category: str
    steps: tuple[str, ...]
    expansions: tuple[str, ...]
    decided: bool
    tool: str
    deprecated: tuple[str, ...]


def _kinds(steps: Sequence[Step]) -> tuple[str, ...]:
    """The kinds of the applied *steps*, in order, each once."""
    return tuple(dict.fromkeys(s["kind"] for s in steps if s["applied"]))


#: A ``+`` right after an id (never after a space): what ``plus_to_or_later``
#: writes as ``-or-later``.
_PLUS_AFTER_ID = re.compile(r"(?<=[^\s+])\+(?=[\s)]|$)")


def _as_form(operand: Operand) -> str:
    """The text of *operand* with its form undone: case folded, runs of white
    space collapsed, and a ``+`` the resolver wrote as ``-or-later`` spelt
    so; what is left differs from the expression only where it was re-spelt."""
    text = " ".join(operand["text"].split())
    if "plus_to_or_later" in _kinds(operand["expansions"]):
        text = _PLUS_AFTER_ID.sub("-or-later", text)
    return text.casefold()


def _operand_decided(operand: Operand) -> bool:
    """Whether *operand* was read beyond its form: a category past
    :data:`_FORM_ONLY`, or a deprecated id kept as written but re-spelt to
    reach it (``GPLv3`` to ``GPL-3.0``; not ``gpl-3.0``, ``GPL-2.0+`` or
    a doubled space)."""
    category = operand["category"]
    if category in _FORM_ONLY:
        return False
    if category in _KEPT_AS_WRITTEN:
        return _as_form(operand) != (operand["expression"] or "").casefold()
    return True


def _decided(found: Resolution) -> bool:
    """Whether the resolver decided something beyond form and ``+`` in
    *found*: a deprecated id kept as written (``GPL-2.0``, also reordered in
    ``MIT OR GPL-2.0``) is the author's own id."""
    category = found["category"]
    if category not in _KEPT_AS_WRITTEN:
        return category not in _FORM_ONLY
    return any(_operand_decided(operand) for operand in found["operands"])


def _without_addition(expression: str) -> str:
    """The licence part of ``ID WITH EXCEPTION``: *expression* left of ``WITH``."""
    return expression.split(" WITH ", 1)[0]


def _ambiguous(operands: Sequence[Operand]) -> tuple[str, ...]:
    """Each deprecated id of *operands* whose possible successors LicenseID
    names (``GPL-2.0``: ``GPL-2.0-only`` or ``GPL-2.0-or-later``), once, as
    ``ID (FIRST or SECOND)``, an addition left out."""
    found: dict[str, None] = {}
    for operand in operands:
        if not operand["candidates"]:
            continue
        candidates = " or ".join(_without_addition(c) for c in operand["candidates"])
        licence = _without_addition(operand["expression"] or "")
        found[f"{licence} ({candidates})"] = None
    return tuple(found)


def resolve_value(value: str) -> DeclaredResolution | None:
    """The reading of the single-line licence *value*, or ``None`` when
    LicenseID names no expression for it (or cannot be asked)."""
    if len(value.splitlines()) > 1:  # \r, U+2028 ...: also a line break
        return None
    found = resolve_declared_value(value)
    if found is None or found["expression"] is None:
        return None
    resolver = found["resolver"]
    return DeclaredResolution(
        found["expression"],
        found["category"],
        _kinds(found["steps"]),
        _kinds(found["expansions"]),
        _decided(found),
        f"{resolver['name']}=={resolver['version']}",
        _ambiguous(found["operands"]),
    )


def refusal_reason(value: str) -> str:
    """Why LicenseID names no expression in the single-line *value*, in
    one loggable line: its ``reason`` (``not found: Acme-Terms``)."""
    if len(value.splitlines()) > 1:
        return "more than one line"
    found = resolve_declared_value(value)
    if found is None:
        return "not read by licenseid"
    return loggable(found["reason"] or found["category"])


def is_licence_id(token: str) -> bool:
    """Whether LicenseID reads the word *token* as one licence id as
    written, in any case (``mit``, ``GPL-2.0``, ``LicenseRef-a``), not a
    name or a re-spelling (``Apache2``, ``GPLv3``)."""
    found = resolve_declared_value(token)
    if found is None or found["expression"] is None:
        return False
    category = found["category"]
    if category in _KEPT_AS_WRITTEN:
        return not _decided(found)
    return category in _ID_CATEGORIES


def say_resolved(value: str, resolved: DeclaredResolution, field: str | None) -> None:
    """One line per value per process: ``INFO:`` when the resolver decided,
    ``DEBUG:`` for a change of form."""
    level = logging.INFO if resolved.decided else logging.DEBUG
    where = f"FIELD={field} " if field else ""
    log_once(
        _logger,
        level,
        f"resolved:{value}",
        "%sLICENSE=%s: read as %s (%s)",
        where,
        excerpt(value),
        loggable(resolved.expression),
        ", ".join(resolved.steps + resolved.expansions) or resolved.category,
    )


def resolution_notes(raw: str, expression: str) -> str:
    """The provenance keys that name the resolver's reading of *raw*, each
    led by `` | ``; empty when it reads no expression in *raw*.

    ``Method: licenseid_resolution`` and ``Resolution-1`` (value, result and
    steps) when it decided beyond form; ``Expansion-1`` for a qualifier
    (``+`` to ``-or-later``, a stated "or later") apart; ``Tool`` names the
    resolver, which did the rewrite (``mit`` -> ``MIT`` too)."""
    resolved = resolve_value(raw.strip())
    if resolved is None:
        return ""
    notes = ""
    if resolved.decided:
        steps = ", ".join(resolved.steps) or resolved.category
        notes = provenance_segment(notes, "Method", "licenseid_resolution")
        notes = provenance_segment(
            notes, "Resolution-1", f"{raw.strip()} -> {expression} ({steps})"
        )
    if resolved.expansions:
        notes = provenance_segment(notes, "Expansion-1", ", ".join(resolved.expansions))
    return provenance_segment(notes, "Tool", resolved.tool)
