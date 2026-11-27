# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A summary: an ``INFO:`` line that reports what a run did under its own
rule (a count, the key it wrote, a hint), with no condition to name, so no
code. :func:`say_summary` writes it from its fields like a catalogued line,
and the message ratchet leaves its calls out by that kind
(``scripts/message_inventory/_scope.py``), never by its text.

See also: :mod:`pitloom.messages._types` (a coded :class:`Message`) and
:mod:`pitloom.messages._emit` (saying one).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pitloom.logging_config import KIND_ATTR, SUMMARY_KIND
from pitloom.messages._surface import Twins
from pitloom.messages._templates import shown, template_names, written
from pitloom.messages._topics import TOPIC_TITLES
from pitloom.messages._types import template_problem


@dataclass(frozen=True, kw_only=True)
class Summary:
    """An ``INFO:`` line of no condition, printed without a code.

    Raises:
        ValueError: The template breaks a rule of
            :func:`~pitloom.messages._types.template_problem` or ends in
            white space, the topic is not a page's, or the meaning is empty.
    """

    #: The text after ``INFO: ``, each value ``%(name)s`` of a field.
    template: str
    #: What the line reports, for the reference.
    meaning: str
    #: The page of the reference that lists it
    #: (:data:`~pitloom.messages.TOPIC_TITLES`).
    topic: str

    def __post_init__(self) -> None:
        """Check the summary against the catalogue's rules."""
        problem = template_problem(self.template)
        if problem is None and self.template != self.template.rstrip():
            problem = f"{self.template!r}: white space at its end"
        if problem is None and self.topic not in TOPIC_TITLES:
            problem = f"{self.template!r}: unknown topic {self.topic!r}"
        if problem is None and not self.meaning.strip():
            problem = f"{self.template!r}: an empty meaning"
        if problem is not None:
            raise ValueError(problem)

    @property
    def fields(self) -> frozenset[str]:
        """The names the template uses."""
        return frozenset(template_names(self.template))

    @property
    def shown(self) -> str:
        """The template as the reference shows it."""
        return shown(self.template)


def say_summary(
    log: logging.Logger, summary: Summary | Twins[Summary], **values: object
) -> None:
    """Log *summary* at ``INFO`` on *log*, each value written by its field,
    with no code on the record, its kind
    (:data:`~pitloom.logging_config.KIND_ATTR`) a summary. A
    :class:`~pitloom.messages._surface.Twins` says the wording of the
    surface that runs.

    Raises:
        ValueError: *values* names other fields than the template, or a
            value does not have its field's shape.
    """
    if isinstance(summary, Twins):
        summary = summary.current()
    texts = written(summary.template, values)
    args: tuple[object, ...] = (texts,) if texts else ()
    log.info(summary.template, *args, extra={KIND_ATTR: SUMMARY_KIND})
