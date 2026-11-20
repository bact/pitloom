# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The frames a surface puts before a catalogued message's text: the
``loom <command>: `` of every ``ERROR:`` line the command line prints
(``loom: `` where no command is known), the Hatchling build hook's, and the
``FORMAT=... FILE=...: `` a model scan puts before a model reader's own line
(:mod:`pitloom.extract.scanner`), the ``Git source: `` of a Git URL
fetch's warnings and notes, the ``Build: `` of ``--allow-build``'s, and the
prefix of each surface that removes a temporary directory of its own (the
Hugging Face and PyPI fetches, the model scan of a wheel, the build hook).
A line is trusted with at most one frame before
one of its entry's shapes (:func:`pitloom.messages.trusted_message`), never
with any other text; a frame before a ``WARNING`` or ``INFO`` line names the
codes it may come before (exact codes: a variant is not its family), so a
line of any other code after it is not trusted.

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
            :func:`~pitloom.messages._types.template_problem`, or a frame
            of a ``WARNING`` or ``INFO`` line names no codes, or the set of
            codes is empty.
    """

    #: The levels of the lines it comes before.
    levels: frozenset[str]
    #: Its text, ending in ``": "``, each value a ``%(name)s``.
    template: str
    #: What prints it.
    surface: str
    #: The codes whose lines it comes before, each exact (a variant's
    #: siblings are not named by it); ``None``: every code's (an
    #: ``ERROR``-only frame, which a surface puts before any error).
    codes: frozenset[str] | None = None

    def __post_init__(self) -> None:
        """Check the frame against the catalogue's rules."""
        problem = template_problem(self.template)
        if not self.levels or not self.levels <= LEVELS:
            problem = f"{self.template!r}: levels {sorted(self.levels)} not in LEVELS"
        elif problem is None and not self.template.endswith(": "):
            problem = f"{self.template!r}: does not end in ': '"
        elif self.codes is None and self.levels != {"ERROR"}:
            problem = f"{self.template!r}: a WARNING or INFO frame names no codes"
        elif self.codes is not None and not self.codes:
            problem = f"{self.template!r}: an empty set of codes"
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

    def allows(self, code: str, level: str) -> bool:
        """Whether a line of the message *code* at *level* may follow it."""
        return level in self.levels and (self.codes is None or code in self.codes)


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

#: What a model scan puts before a model reader's own warning: the codes a
#: reader under :mod:`pitloom.extract.ai_model` says (a drift test walks
#: those modules and holds the set equal to them; no reader logs at
#: ``ERROR``).
RELAY_FRAME: Final = Frame(
    levels=frozenset({"WARNING"}),
    template="FORMAT=%(format)s FILE=%(file)s: ",
    surface="a model scan, before a model reader's own line",
    codes=frozenset(
        {
            "model-field-conflict",
            "model-field-unreadable",
            "parameter-count-invalid",
            "text-malformed",
        }
    ),
)

#: What every warning and note of a Git URL fetch starts with, and the git
#: command echo (:data:`pitloom.messages.git.GIT_COMMAND`) too.
GIT_PREFIX: Final = "Git source: "

#: What a Git URL fetch puts before its own warnings and notes; never before
#: an ``ERROR`` line (an exception's text).
GIT_FRAME: Final = Frame(
    levels=frozenset({"WARNING", "INFO"}),
    template=GIT_PREFIX,
    surface="a Git URL fetch",
    codes=frozenset(
        {
            "config-unsafe",
            "git-filter-unusable",
            "git-link-unsafe",
            "git-redirect-unusable",
            "query-no-effect",
            "target-ambiguous/git-page",
            "temp-dir-unwritable",
            "url-moved",
            "url-unsafe",
        }
    ),
)

#: What every warning and note about ``--allow-build`` and the build it
#: runs starts with (``option-no-effect``'s build line is built from it too,
#: as a literal: the frame does not come before that code).
BUILD_PREFIX: Final = "Build: "

#: What ``--allow-build`` puts before its warnings and notes: the build, its
#: temporary directories and a signal while it runs; never before an
#: ``ERROR`` line (an exception's text).
BUILD_FRAME: Final = Frame(
    levels=frozenset({"WARNING", "INFO"}),
    template=BUILD_PREFIX,
    surface="--allow-build: the build and its temporary directories",
    codes=frozenset(
        {
            "build-code-unsafe",
            "build-failed",
            "build-processes-unsafe",
            "build-timeout",
            "interrupted",
            "library-missing",
            "temp-dir-unwritable",
        }
    ),
)

#: What a Hugging Face model fetch puts before the line about its temporary
#: directory.
HF_FRAME: Final = Frame(
    levels=frozenset({"WARNING"}),
    template="Hugging Face source: ",
    surface="a Hugging Face model fetch, its temporary directory",
    codes=frozenset({"temp-dir-unwritable"}),
)

#: What a PyPI URL download puts before the line about its temporary
#: directory.
PYPI_FRAME: Final = Frame(
    levels=frozenset({"WARNING"}),
    template="PyPI source: ",
    surface="a PyPI URL download, its temporary directory",
    codes=frozenset({"temp-dir-unwritable"}),
)

#: What the model scan of a wheel puts before the lines about the temporary
#: copy of a model file.
SCAN_FRAME: Final = Frame(
    levels=frozenset({"WARNING"}),
    template="AI model scan: ",
    surface="the AI model scan of a wheel, its temporary copy",
    codes=frozenset({"interrupted", "temp-dir-unwritable"}),
)

#: What the Hatchling build hook puts before its own warnings (the same text
#: as :data:`HOOK_FRAME`, which comes before its ``ERROR`` line).
HOOK_STEP_FRAME: Final = Frame(
    levels=frozenset({"WARNING"}),
    template=HOOK_FRAME.template,
    surface="the Hatchling build hook, its own warnings",
    codes=frozenset({"temp-dir-unwritable"}),
)

#: Every frame.
FRAMES: Final = (
    COMMAND_FRAME,
    TOP_FRAME,
    HOOK_FRAME,
    RELAY_FRAME,
    GIT_FRAME,
    BUILD_FRAME,
    HF_FRAME,
    PYPI_FRAME,
    SCAN_FRAME,
    HOOK_STEP_FRAME,
)
