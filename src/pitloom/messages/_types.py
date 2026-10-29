# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One catalogue entry, :class:`Message`, the shapes it is printed in,
:class:`Line`, and the closed vocabularies they draw on.

See also: :mod:`pitloom.messages` (the catalogue) and
:mod:`pitloom.messages._fields` (the values a line names).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pitloom.logging_config import CODE_PATTERN
from pitloom.messages._fields import (
    FIELDS,
    PLACEHOLDER,
    render,
    shown,
    template_names,
)

#: The levels a catalogued message is printed at (``DEBUG`` lines carry no
#: code).
LEVELS: Final = frozenset({"ERROR", "WARNING", "INFO"})

#: The closed condition vocabulary: the cause, in one word, never Pitloom's
#: response to it (``skipped``, ``ignored``): ``[subject-]condition`` names
#: a family (``file-unreadable``), a bare condition one whose cause does not
#: depend on its subject (``over-cap``). What kind of message it is (a
#: decision, a summary, a usage error), who acts and the frame around it are
#: not conditions; nor is a domain (licences).
CONDITIONS: Final = frozenset(
    {
        "ambiguous",
        "build-failed",
        "conflict",
        "interrupted",
        "invalid",
        "lfs-pointer",
        "malformed",
        "missing",
        "moved",
        "needs-build",
        "network-failed",
        "no-effect",
        "not-found",
        "not-recordable",
        "over-cap",
        "timeout",
        "unknown-key",
        "unlistable",
        "unpinned",
        "unreadable",
        "unsafe",
        "unusable",
        "wrong-format",
    }
)

#: What the condition does to the SBOM, as a ``WARNING:``, and what each
#: effect means.
EFFECT_MEANINGS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "none": "the SBOM states what the input holds",
        "thinner": "the SBOM says less than reading the input would",
        "weaker": "what the SBOM says is less sure",
        "not-written": "no SBOM is written for the input",
    }
)
EFFECTS: Final = frozenset(EFFECT_MEANINGS)

#: Who acts on the advice: the ``user`` (an agent relays it and does not
#: act), the ``caller`` (the program or agent that ran the command may fix
#: its own command), or ``none``; with the heading the reference gives it.
ACTOR_HEADINGS: Final[Mapping[str, str]] = MappingProxyType(
    {"user": "Tell the user", "caller": "The caller may fix", "none": "Nothing to do"}
)
ACTORS: Final = frozenset(ACTOR_HEADINGS)

#: One part of a code: lower-case ASCII words joined by single hyphens.
_PART: Final = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
#: A catalogued code: a family, optionally ``/`` and a variant.
CODE_GRAMMAR: Final = rf"{_PART}(?:/{_PART})?"
#: The longest code.
LONGEST_CODE: Final = 40
#: Names no family takes: they name tools and formats, kept free for a
#: producer namespace (no printed code carries one).
RESERVED_FAMILIES: Final = frozenset(
    {"bom", "licenseid", "lumina", "pitloom", "sarif", "sbom", "spdx"}
)

_CODE_RE: Final = re.compile(CODE_GRAMMAR)
_READ_RE: Final = re.compile(CODE_PATTERN)
_CODE_LIKE_END: Final = re.compile(rf" \[{CODE_PATTERN}\]\Z")
_KEY_RE: Final = re.compile(r"[A-Z][A-Z0-9_]*")
_RELEASE_RE: Final = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}")


def _code_problem(code: str) -> str | None:
    """Why *code* is not a catalogued code, or ``None``."""
    if (
        len(code) > LONGEST_CODE
        or _CODE_RE.fullmatch(code) is None
        or _READ_RE.fullmatch(code) is None
    ):
        return f"message code {code!r} is not a code"
    if code.partition("/")[0] in RESERVED_FAMILIES:
        return f"message code {code!r} takes a reserved family name"
    return None


def template_problem(template: str) -> str | None:
    """Why *template* cannot be a line's or a frame's text, or ``None``: it
    names an unknown field, holds a stray ``%`` or a line break, has white
    space at its start, ends in what reads as a code, or puts a field that
    takes any text first or next to another field (it would take in what
    lies beside it)."""
    try:
        template_names(template)
    except ValueError as exc:
        return str(exc)
    if not template.strip() or template != template.lstrip():
        return f"{template!r}: empty, or white space at its start"
    if "\n" in template or "\r" in template:
        return f"{template!r}: a line break"
    if _CODE_LIKE_END.search(template):
        return f"{template!r}: ends in what reads as a code"
    spans = [(m.start(), m.end(), m.group(1)) for m in PLACEHOLDER.finditer(template)]
    for i, (start, end, name) in enumerate(spans):
        beside = (i > 0 and spans[i - 1][1] == start) or (
            i + 1 < len(spans) and spans[i + 1][0] == end
        )
        if FIELDS[name].free and (start == 0 or beside):
            return f"{template!r}: {name!r} takes any text, first or beside a field"
    return None


@dataclass(frozen=True, kw_only=True)
class Line:
    """One shape a message is printed in.

    Raises:
        ValueError: The level is not one of :data:`LEVELS`, or the
            template breaks a rule of :func:`template_problem`, or ends in
            white space.
    """

    #: ``ERROR``, ``WARNING`` or ``INFO``.
    level: str
    #: The text between ``LEVEL: `` and `` [code]``, each value
    #: ``%(name)s`` of a field of :data:`~pitloom.messages._fields.FIELDS`.
    template: str

    def __post_init__(self) -> None:
        """Check the line against the catalogue's rules."""
        if self.level not in LEVELS:
            raise ValueError(f"{self.template!r}: level {self.level!r} not in LEVELS")
        problem = template_problem(self.template)
        if problem is None and self.template != self.template.rstrip():
            problem = f"{self.template!r}: white space at its end"
        if problem is not None:
            raise ValueError(problem)

    @property
    def fields(self) -> frozenset[str]:
        """The names the template uses."""
        return frozenset(template_names(self.template))

    @property
    def shown(self) -> str:
        """The template as the reference shows it, each value as
        :attr:`~pitloom.messages._fields.Field.shown` (``<file>``)."""
        return shown(self.template)

    def render(self, values: Mapping[str, object]) -> str:
        """The text printed for *values*, each written by its field.

        Raises:
            ValueError: *values* names other fields, or a value does not
                have its field's shape.
        """
        return render(self.template, values)


@dataclass(frozen=True, kw_only=True)
class Message:
    """A catalogued message: what Pitloom prints, what it means, what it did
    and what a reader (a person, or an agent relaying it) should do.

    Raises:
        ValueError: A field breaks the catalogue's rules (see
            :meth:`__post_init__`).
    """

    #: The stable code printed as `` [code]``: the family, or
    #: ``<family>/<variant>`` (:data:`CODE_GRAMMAR`), named by the cause.
    code: str
    #: What happened, from :data:`CONDITIONS`; one per family.
    condition: str
    #: Every shape it is printed in.
    lines: tuple[Line, ...]
    #: What the message means.
    summary: str
    #: What Pitloom did about it, as a ``WARNING:``.
    did: str
    #: What it does to the SBOM, from :data:`EFFECTS`.
    effect: str
    #: Who acts on :attr:`advice`, from :data:`ACTORS`.
    actor: str
    #: What an agent tells the user, or what the caller may fix.
    advice: str
    #: The key of the ``KEY=value`` its lines name the subject by (``FILE``).
    subject_key: str | None = None
    #: The release that first prints the code.
    since: str = "0.22.0"

    def __post_init__(self) -> None:
        """Check the entry against the catalogue's rules."""
        problem = _code_problem(self.code)
        if problem is None:
            problem = self._field_problem()
        if problem is not None:
            raise ValueError(problem)

    def _field_problem(self) -> str | None:
        """Why a field other than the code breaks a rule, or ``None``."""
        checks = (
            (self.condition in CONDITIONS, f"unknown condition {self.condition!r}"),
            (self.effect in EFFECTS, f"unknown effect {self.effect!r}"),
            (self.actor in ACTORS, f"unknown actor {self.actor!r}"),
            (
                bool(self.lines) and len(set(self.lines)) == len(self.lines),
                "no lines, or one line twice",
            ),
            (
                all(t.strip() for t in (self.summary, self.did, self.advice)),
                "an empty field",
            ),
            (
                self.subject_key is None
                or (
                    _KEY_RE.fullmatch(self.subject_key) is not None
                    and any(f"{self.subject_key}=" in ln.template for ln in self.lines)
                ),
                f"subject key {self.subject_key!r} names no line's subject",
            ),
            (
                _RELEASE_RE.fullmatch(self.since) is not None,
                f"since {self.since!r}",
            ),
        )
        return next((f"{self.code}: {why}" for ok, why in checks if not ok), None)

    @property
    def family(self) -> str:
        """The code before any ``/``: the group of messages of one
        condition."""
        return self.code.partition("/")[0]

    @property
    def levels(self) -> frozenset[str]:
        """The levels its lines are printed at."""
        return frozenset(line.level for line in self.lines)

    def line_for(
        self, level: str, names: Collection[str], line: Line | None = None
    ) -> Line:
        """Its line at *level* that names exactly *names*: *line*, which
        must be one of them, else the only one.

        Raises:
            ValueError: No line does, *line* is not one, or several do and
                *line* does not say which.
        """
        wanted = frozenset(names)
        found = [ln for ln in self.lines if ln.level == level and ln.fields == wanted]
        if line is not None and line in found:
            return line
        if line is None and len(found) == 1:
            return found[0]
        what = "that line is not one" if line is not None else f"{len(found)} name"
        raise ValueError(f"{self.code}: {what} of its {level} lines {sorted(wanted)}")
