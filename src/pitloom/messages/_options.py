# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The options a command was run with: one that has no effect for its
target (``option-no-effect``, a ``WARNING:``, or an ``INFO:`` for a setting
the surface never acts on), and one the command refuses: a value it cannot
take (``option-invalid``), two it cannot take together
(``option-conflict``) or one it needs (``option-missing``). The refusals
are the caller's to fix: the program or agent that ran the command may
correct its own command line.

See also: :mod:`pitloom.messages._options_say` (the helpers) and
:mod:`pitloom.core.no_effect` (the no-effect lines).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._registry_file import REGISTRY_PREFIX
from pitloom.messages._types import Line, Message

_SINCE: Final = "0.24.1"

#: The sub-prefix of every line about an option the target or command cannot
#: act on (``option-no-effect``'s own lines and the other ``Options:`` lines).
OPTIONS_PREFIX: Final = "Options: "
#: The sub-prefix of every line about ``--allow-build`` and the build it
#: runs (:data:`pitloom.core._models_wheel_types.BUILD_LOG_PREFIX` is this).
BUILD_PREFIX: Final = "Build: "

#: An option given that the target or command cannot act on.
OPTIONS_NO_EFFECT_LINE: Final = Line(
    level="WARNING",
    template=f"{OPTIONS_PREFIX}%(name)s: %(option)s has no effect %(when)s",
)
#: A setting the surface never acts on (``INFO:``: the user did not type it
#: for this run).
OPTIONS_NO_EFFECT_INFO_LINE: Final = Line(
    level="INFO", template=OPTIONS_NO_EFFECT_LINE.template
)
#: A build flag given without ``--allow-build``, or for a target no build
#: applies to.
BUILD_NO_EFFECT_LINE: Final = Line(
    level="WARNING",
    template=f"{BUILD_PREFIX}%(name)s: %(option)s has no effect %(when)s",
)

OPTION_NO_EFFECT: Final = Message(
    code="option-no-effect",
    condition="no-effect",
    lines=(OPTIONS_NO_EFFECT_LINE, OPTIONS_NO_EFFECT_INFO_LINE, BUILD_NO_EFFECT_LINE),
    summary="An option or setting was given that the target or command cannot "
    "act on (a build flag without --allow-build, --use-lockfile for a wheel "
    "given to 'loom generate', a library parameter a URL target ignores); "
    "the line says why. The INFO: line is a [tool.pitloom] setting the "
    "build hook or 'embed-wheel' never acts on, named by its flag.",
    did="Ran as if it were not given; the run goes on.",
    effect="none",
    actor="caller",
    advice="The caller may drop the option from its command, or pick the "
    "target or companion option it needs (the line says which). Nothing to "
    "tell the user unless they asked for the option; for the INFO: line, do "
    "not edit their configuration.",
    since=_SINCE,
)

#: ``argparse``'s refusal of an option's or argument's value (``argument
#: --build-timeout: invalid duration ...``, ``argument command: invalid
#: choice: ...``); a missing value (:data:`MISSING_VALUE_LINE`) and a
#: conflict (:data:`CONFLICT_ARGUMENT_LINE`) are not of its shape.
ARGUMENT_LINE: Final = Line(level="ERROR", template="argument %(option)s: %(refusal)s")
#: ``argparse``'s refusal of words it does not know.
UNRECOGNIZED_LINE: Final = Line(
    level="ERROR", template="unrecognized arguments: %(error)s"
)
#: ``argparse``'s refusal of an abbreviation that names several options.
AMBIGUOUS_LINE: Final = Line(level="ERROR", template="ambiguous option: %(error)s")
#: A ``--build-timeout`` out of range, from the command line or the library.
BUILD_TIMEOUT_LINE: Final = Line(
    level="ERROR",
    template="build timeout must be 1-%(limit)s seconds, got %(value)s",
)

#: An ``id generate`` PATH outside ``--project-dir``.
PATH_OUTSIDE_LINE: Final = Line(
    level="ERROR", template="PATH %(path)s is outside --project-dir %(root)s"
)
#: A path given to ``IdRegistry.generate`` outside its project root.
REGISTRY_PATH_OUTSIDE_LINE: Final = Line(
    level="ERROR",
    template=f"{REGISTRY_PREFIX}FILE=%(file)s: not inside the project root %(root)s",
)

OPTION_INVALID: Final = Message(
    code="option-invalid",
    condition="invalid",
    lines=(
        ARGUMENT_LINE,
        UNRECOGNIZED_LINE,
        AMBIGUOUS_LINE,
        BUILD_TIMEOUT_LINE,
        PATH_OUTSIDE_LINE,
        REGISTRY_PATH_OUTSIDE_LINE,
    ),
    summary="The command line holds an option or a value the command does not "
    "take: an unknown option, a value of the wrong form or out of range, an "
    "unknown subcommand, an option out of order (a creator's type or email "
    "before its name), or a 'loom id generate' PATH outside --project-dir "
    "(the library: a path outside the project root given to "
    "IdRegistry.generate). An option given without its value is "
    "option-missing; two options argparse refuses together are "
    "option-conflict.",
    did="Ran nothing: the command exits 2 (the Action step fails), 1 for a "
    "PATH outside --project-dir; the library raises ValueError carrying the "
    "code for a build timeout out of range (BuildOptions) and a path outside "
    "the project root (IdRegistry.generate).",
    effect="not-written",
    actor="caller",
    advice="The caller may fix the option or value the line names ('loom "
    "<command> --help' lists them) and run again. Tell the user only when the "
    "value came from them.",
    since=_SINCE,
)

#: Two options the command cannot take together.
CANNOT_BE_USED_LINE: Final = Line(
    level="ERROR", template="%(option)s cannot be used %(when)s"
)
#: ``argparse``'s refusal of two options of one mutually exclusive group.
#: Defensive: no command has such a group yet, so nothing prints it today;
#: it keeps the refusal coded once one is added.
CONFLICT_ARGUMENT_LINE: Final = Line(
    level="ERROR",
    template="argument %(option)s: not allowed with argument %(other)s",
)

#: ``loom id generate --namespace`` for a registry made with another one.
NAMESPACE_CONFLICT_LINE: Final = Line(
    level="ERROR",
    template=f"{REGISTRY_PREFIX}FILE=%(file)s: namespace %(namespace)s is not "
    "--namespace %(value)s; delete it to change the namespace",
)
#: ``loom id`` for a registry made for another project directory.
PROJECT_ROOT_CONFLICT_LINE: Final = Line(
    level="ERROR",
    template=f"{REGISTRY_PREFIX}FILE=%(file)s: project root %(path)s is not "
    "%(root)s; delete it to change the project root",
)

OPTION_CONFLICT: Final = Message(
    code="option-conflict",
    condition="conflict",
    lines=(
        CANNOT_BE_USED_LINE,
        CONFLICT_ARGUMENT_LINE,
        NAMESPACE_CONFLICT_LINE,
        PROJECT_ROOT_CONFLICT_LINE,
    ),
    summary="The command line holds an option the command cannot take in this "
    "case (-o/--output with several wheels), or one an existing ID registry "
    "contradicts: 'loom id generate --namespace' for a registry made with "
    "another namespace, or 'loom id' with a --project-dir (the current "
    "directory when not given) other than the one the registry was made for. "
    "The 'not allowed with' line is reserved for options of a mutually "
    "exclusive group; no command has one yet.",
    did="Ran nothing: the command exits 1, and an ID registry is left as it is.",
    effect="not-written",
    actor="caller",
    advice="The caller may drop the option, run the command once per input, "
    "or, for an ID registry, pass the namespace or project directory the "
    "registry holds (or name another registry file), and run again. "
    "Deleting a registry to change them loses every id it pins: that is the "
    "user's decision, never the caller's.",
    since=_SINCE,
)

#: ``argparse``'s refusal of a command line without a required argument.
REQUIRED_LINE: Final = Line(
    level="ERROR", template="the following arguments are required: %(error)s"
)
#: ``argparse``'s refusal of an option given without its value (``argument
#: -o/--output: expected one argument``).
MISSING_VALUE_LINE: Final = Line(
    level="ERROR", template="argument %(option)s: expected %(arity)s"
)
#: ``loom generate`` without ``-o``: a detected target has no default name.
OUTPUT_REQUIRED_LINE: Final = Line(
    level="ERROR",
    template="-o/--output is required: a detected target has no default file "
    "name; pass -o FILE, or use 'loom project', 'loom wheel', 'loom model' or "
    "'loom env' for that target's own default",
)
#: ``loom id`` with no registry named by a flag or the project.
REGISTRY_REQUIRED_LINE: Final = Line(
    level="ERROR",
    template="no ID registry declared: pass --id-registry FILE or set "
    "id-registry in %(table)s",
)

OPTION_MISSING: Final = Message(
    code="option-missing",
    condition="missing",
    lines=(
        REQUIRED_LINE,
        MISSING_VALUE_LINE,
        OUTPUT_REQUIRED_LINE,
        REGISTRY_REQUIRED_LINE,
    ),
    summary="The command line lacks an argument or option the command needs "
    "(a subcommand, -o/--output for 'loom generate', an ID registry for 'loom "
    "id'), or the value of an option given (-o with nothing after it).",
    did="Ran nothing: the command exits 2 (a parse error) or 1.",
    effect="not-written",
    actor="caller",
    advice="The caller may add what the line names and run again. Tell the "
    "user only when the value must come from them (an output file, a "
    "registry location).",
    since=_SINCE,
)

ENTRIES: Final = (OPTION_NO_EFFECT, OPTION_INVALID, OPTION_CONFLICT, OPTION_MISSING)
