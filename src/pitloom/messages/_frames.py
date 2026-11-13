# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The frames a surface puts before a catalogued message's text: the
``loom <command>: `` of every ``ERROR:`` line the command line prints
(``loom: `` where no command is known), the Hatchling build hook's, and the
``FORMAT=... FILE=...: `` a model scan puts before a model reader's own line
(:mod:`pitloom.extract.scanner`). A line is trusted with at most one frame
before one of its entry's shapes (:func:`pitloom.messages.trusted_message`),
never with any other text.

The library prints no ``ERROR:`` line and puts no frame on an exception's
text. A drift test holds the table and the surfaces together
(``tests/messages/test_frames.py``).

See also: :mod:`pitloom.messages._lines` (where frames are matched).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pitloom.messages._templates import render, shown, template_names
from pitloom.messages._types import LEVELS, template_problem


@dataclass(frozen=True, kw_only=True)
class Frame:
    """A prefix a surface puts before a message's text.

    Raises:
        ValueError: A level is not one of :data:`LEVELS`, the template does
            not end in ``": "`` or breaks a rule of
            :func:`~pitloom.messages._types.template_problem`.
    """

    #: The levels of the lines it comes before.
    levels: frozenset[str]
    #: Its text, ending in ``": "``, each value a ``%(name)s``.
    template: str
    #: What prints it.
    surface: str

    def __post_init__(self) -> None:
        """Check the frame against the catalogue's rules."""
        problem = template_problem(self.template)
        if not self.levels or not self.levels <= LEVELS:
            problem = f"{self.template!r}: levels {sorted(self.levels)} not in LEVELS"
        elif problem is None and not self.template.endswith(": "):
            problem = f"{self.template!r}: does not end in ': '"
        if problem is not None:
            raise ValueError(problem)

    @property
    def fields(self) -> frozenset[str]:
        """The names the template uses."""
        return frozenset(template_names(self.template))

    @property
    def shown(self) -> str:
        """The template as the reference shows it (``<file>``)."""
        return shown(self.template)

    def render(self, values: Mapping[str, object]) -> str:
        """The prefix printed for *values*, each written by its field."""
        return render(self.template, values)


#: What every ``ERROR:`` line of a ``loom`` command starts with, by the
#: command that printed it (``loom generate: ``, ``loom fragment validate: ``).
COMMAND_FRAME: Final = Frame(
    levels=frozenset({"ERROR"}),
    template="loom %(subcommand)s: ",
    surface="the command line, each subcommand",
)

#: What an ``ERROR:`` line starts with when no subcommand is known: a command
#: line that does not parse as one, or Ctrl-C before it did.
TOP_FRAME: Final = Frame(
    levels=frozenset({"ERROR"}),
    template="loom: ",
    surface="the command line, before a subcommand is known",
)

#: What the Hatchling build hook puts before an ``ERROR:`` line.
HOOK_FRAME: Final = Frame(
    levels=frozenset({"ERROR"}),
    template="Pitloom build hook: ",
    surface="the Hatchling build hook",
)

#: What a model scan puts before a model reader's own warning or error.
RELAY_FRAME: Final = Frame(
    levels=frozenset({"WARNING", "ERROR"}),
    template="FORMAT=%(format)s FILE=%(file)s: ",
    surface="a model scan, before a model reader's own line",
)

#: Every frame.
FRAMES: Final = (COMMAND_FRAME, TOP_FRAME, HOOK_FRAME, RELAY_FRAME)
