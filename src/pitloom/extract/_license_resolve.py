# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A declared licence value read through ``licenseid.resolve``: which of its
answers Pitloom accepts, and how each is said in the log and the provenance.

``licenseid`` decides what a value names (``Apache2`` is ``Apache-2.0``); this
module decides what Pitloom does with the answer. A resolution that rewrites
more than the form of the text (a re-spelling, a listed name, a stated "or
later", a renamed id) is the resolver's decision, not the author's words: one
``INFO:`` line per value, and ``Resolution-1`` in the provenance.

See also: :mod:`pitloom.extract._license_classify` (the caller) and
:mod:`pitloom.extract._license` (the database access).
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any

from pitloom.logging_config import excerpt, log_once, loggable

_logger = logging.getLogger(__name__)

try:
    _LICENSEID_VERSION: str | None = _pkg_version("licenseid")
except PackageNotFoundError:
    _LICENSEID_VERSION = None

#: The categories that give an expression Pitloom records. ``assumed_only``
#: and ``deprecated_ambiguous`` come back as written (the listed id, never
#: narrowed); ``expression``, ``malformed`` and ``unresolved`` give none.
_ACCEPTED = frozenset(
    {
        "exact",
        "lexical",
        "listed_name",
        "deprecated_equal_successor",
        "plus_to_or_later",
        "stated_qualifier",
        "separator",
        "version_spelling",
    }
)
#: What the resolver may fold away or respell: letters, digits, white space,
#: ``_ . , + ( )`` and the hyphens. Any other character (``?``, ``*``, U+FFFD)
#: it would drop is the author's, so such a value is not read.
_FOLDABLE = re.compile(r"[\w\s.,+()\u2010-\u2015\u2212-]+")
#: Only the form of the text changed, or ``+`` was written as ``-or-later``
#: (its own key): the author's id stands, so nothing is said above ``DEBUG:``.
_FORM_ONLY = frozenset({"exact", "lexical", "plus_to_or_later"})


@dataclass(frozen=True)
class DeclaredResolution:
    """What ``licenseid`` read in a declared value: the *expression* to record,
    its *category*, and the *steps* it took (``separator``, ``version_spelling``,
    ...), the qualifier steps (*expansions*) apart."""

    expression: str
    category: str
    steps: tuple[str, ...]
    expansions: tuple[str, ...]

    @property
    def decided(self) -> bool:
        """Whether the resolver decided something beyond form and ``+``."""
        return self.category not in _FORM_ONLY


def _kinds(steps: list[Any]) -> tuple[str, ...]:
    """The kinds of the applied *steps*, in order, each once."""
    return tuple(dict.fromkeys(s["kind"] for s in steps if s["applied"]))


def resolve_value(value: str) -> DeclaredResolution | None:
    """The accepted reading of the single-line licence *value*, or ``None``
    when ``licenseid`` names no one licence for it (or cannot be asked)."""
    if not _FOLDABLE.fullmatch(value):
        return None
    licence = importlib.import_module("pitloom.extract._license")
    found = licence.resolve_declared_value(value)
    if found is None or found["expression"] is None:
        return None
    if found["category"] not in _ACCEPTED:
        return None
    return DeclaredResolution(
        found["expression"],
        found["category"],
        _kinds(found["steps"]),
        _kinds(found["expansions"]),
    )


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
    """The provenance keys that name the resolver's decision on *raw*, each
    led by `` | ``; empty when it decided nothing (``mit`` -> ``MIT``).

    ``Method: licenseid_resolution`` and ``Resolution-1`` (value, result and
    steps) when it re-spelled or renamed; ``Expansion-1`` for a qualifier
    (``+`` to ``-or-later``, a stated "or later") apart; ``Tool`` names it."""
    resolved = resolve_value(raw.strip())
    if resolved is None:
        return ""
    notes = ""
    if resolved.decided:
        steps = ", ".join(resolved.steps) or resolved.category
        notes += (
            f" | Method: licenseid_resolution | Resolution-1: "
            f"{raw.strip()} -> {expression} ({steps})"
        )
    if resolved.expansions:
        notes += f" | Expansion-1: {', '.join(resolved.expansions)}"
    if notes and _LICENSEID_VERSION is not None:
        notes += f" | Tool: licenseid=={_LICENSEID_VERSION}"
    return notes
