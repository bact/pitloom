# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The frames a surface puts before a catalogued message's text: the
``<what> failed: `` of the CLI's error handler
(:func:`pitloom.cli.commands.utils.cli_error_handler`) and of the Hatchling
build hook, and the ``FORMAT=... FILE=...: `` a model scan puts before a
model reader's own line (:mod:`pitloom.extract.scanner`). A line is trusted
with at most one frame before one of its entry's shapes
(:func:`pitloom.messages.trusted_message`), never with any other text.

The table lists the strings the surfaces print today; a uniform
``loom <command>: `` frame is planned separately. A drift test holds the
table and the surfaces together (``tests/messages/test_frames.py``).

See also: :mod:`pitloom.messages._lines` (where frames are matched).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pitloom.messages._fields import render, shown, template_names
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


#: The text the CLI's error handler, or the build hook, puts before an
#: exception's text (then ``": "``), by what prints it.
HANDLER_FRAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "SBOM generation failed": (
            "loom generate, loom project and the Hatchling build hook"
        ),
        "deployed SBOM generation failed": "loom env",
        "enrichment fragment generation failed": "loom enrich",
        "fragment list failed": "loom fragment list",
        "fragment merge failed": "loom merge",
        "fragment validate failed": "loom fragment validate",
        "model command failed": "loom model",
        "wheel SBOM embedding failed": "loom embed-wheel",
        "wheel SBOM validation failed": "loom validate-wheel",
        "wheel SBOM verification failed": "loom verify-wheel",
        "wheel command failed": "loom wheel",
    }
)

#: What a model scan puts before a model reader's own warning or error.
RELAY_FRAME: Final = Frame(
    levels=frozenset({"WARNING", "ERROR"}),
    template="FORMAT=%(format)s FILE=%(file)s: ",
    surface="a model scan, before a model reader's own line",
)

#: Every frame.
FRAMES: Final = (
    *(
        Frame(levels=frozenset({"ERROR"}), template=f"{text}: ", surface=surface)
        for text, surface in HANDLER_FRAMES.items()
    ),
    RELAY_FRAME,
)
