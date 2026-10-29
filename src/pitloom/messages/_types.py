# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One catalogue entry, :class:`Message`, and the closed vocabularies it
draws on.

See also: :mod:`pitloom.messages` (the catalogue).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pitloom.logging_config import CODE_PATTERN

#: The levels a catalogued message is printed at (``DEBUG`` lines carry no
#: code).
LEVELS: Final = frozenset({"ERROR", "WARNING", "INFO"})

#: The closed condition vocabulary: what happened, in one word.
CONDITIONS: Final = frozenset(
    {
        "build-failed",
        "conflict",
        "decision",
        "escaped",
        "fallback",
        "fetch-failed",
        "id-collision",
        "ignored",
        "interrupted",
        "invalid",
        "left-behind",
        "left-out",
        "lfs-pointer",
        "licence",
        "malformed",
        "mismatch",
        "missing-library",
        "moved",
        "new-id",
        "no-effect",
        "not-a-model",
        "not-found",
        "not-saved",
        "not-this-format",
        "over-cap",
        "refused",
        "rejected",
        "skipped",
        "split",
        "summary",
        "unknown-key",
        "unpinned",
        "unreadable",
        "unusable",
        "usage",
        "wrapper",
    }
)

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


@dataclass(frozen=True)
class Message:
    """A catalogued message: what Pitloom prints, what it means, what it did
    and what a reader (a person, or an agent relaying it) should do.

    Raises:
        ValueError: A field breaks the catalogue's rules (see
            :meth:`__post_init__`).
    """

    #: The stable code printed as `` [code]``: the family, or
    #: ``<family>/<variant>`` (:data:`CODE_GRAMMAR`).
    code: str
    #: The group of messages this one belongs to.
    family: str
    #: What happened, from :data:`CONDITIONS`.
    condition: str
    #: The levels it is printed at, from :data:`LEVELS`.
    levels: frozenset[str]
    #: What the line names (``FILE``, a model path).
    subject: str
    #: What the message means, in one sentence.
    summary: str
    #: What Pitloom did about it.
    did: str
    #: What an agent tells the user to do; never to run a fix itself.
    advice: str
    #: The message text as printed, after ``LEVEL: `` and before the code,
    #: with ``%s`` for each interpolated value.
    patterns: tuple[str, ...]

    def __post_init__(self) -> None:
        """Check the entry against the catalogue's rules."""
        problem = _code_problem(self.code)
        if problem is not None:
            raise ValueError(problem)
        if self.code.partition("/")[0] != self.family:
            raise ValueError(f"message code {self.code!r} is not in {self.family!r}")
        if self.condition not in CONDITIONS:
            raise ValueError(f"{self.code}: unknown condition {self.condition!r}")
        if not self.levels or not self.levels <= LEVELS:
            raise ValueError(f"{self.code}: levels {sorted(self.levels)} not in LEVELS")
        texts = (self.subject, self.summary, self.did, self.advice, *self.patterns)
        if not self.patterns or not all(text.strip() for text in texts):
            raise ValueError(f"{self.code}: an empty field")
