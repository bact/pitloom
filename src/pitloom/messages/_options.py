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

from pitloom.messages._config_place import FINGERPRINT_SHAPE
from pitloom.messages._field_writers import entity_text
from pitloom.messages._frames import BUILD_PREFIX
from pitloom.messages._registry_file import REGISTRY_PREFIX
from pitloom.messages._types import Line, Message

_SINCE: Final = "0.25.0"

#: The sub-prefix of every line about an option the target or command cannot
#: act on (``option-no-effect``'s own lines and the other ``Options:`` lines).
OPTIONS_PREFIX: Final = "Options: "

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
#: applies to: :data:`~pitloom.messages.BUILD_PREFIX` as a literal, since
#: :data:`~pitloom.messages.BUILD_FRAME` does not come before this code.
BUILD_NO_EFFECT_LINE: Final = Line(
    level="WARNING",
    template=f"{BUILD_PREFIX}%(name)s: %(option)s has no effect %(when)s",
)
#: A URL credential fingerprint accepted that no URL of the SBOM has.
STALE_FINGERPRINT_LINE: Final = Line(
    level="WARNING",
    template=f"{OPTIONS_PREFIX}FINGERPRINT=%(fingerprint)s: matches no URL of "
    "the SBOM %(element)s",
)
#: A ``--config`` file (``loom.run``'s ``pitloom_config``) with no
#: ``[tool.pitloom]`` table: the option set nothing.
CONFIG_NO_TABLE_LINE: Final = Line(
    level="WARNING",
    template=f"{OPTIONS_PREFIX}FILE=%(file)s: %(option)s has no [tool.pitloom] "
    "table; the defaults apply",
)
#: ``loom id`` with ``-o`` and ``--project-dir`` whose project config could
#: not be read: its ``url-credentials`` is not applied.
MODE_UNREAD_LINE: Final = Line(
    level="WARNING",
    template=f"{OPTIONS_PREFIX}DIR=%(dir)s: url-credentials not read: "
    "%(failure)s; the warn mode applies; add %(option)s to refuse",
)

OPTION_NO_EFFECT: Final = Message(
    code="option-no-effect",
    condition="no-effect",
    lines=(
        OPTIONS_NO_EFFECT_LINE,
        OPTIONS_NO_EFFECT_INFO_LINE,
        BUILD_NO_EFFECT_LINE,
        STALE_FINGERPRINT_LINE,
        MODE_UNREAD_LINE,
        CONFIG_NO_TABLE_LINE,
    ),
    summary="An option or setting was given that the target or command cannot "
    "act on (a build flag without --allow-build, --use-lockfile for a wheel "
    "given to 'loom generate', a library parameter a URL target ignores); "
    "the line says why. The INFO: line is a [tool.pitloom] setting the "
    "build hook or 'embed-wheel' never acts on, named by its flag. The "
    "FINGERPRINT= line is a fingerprint accepted (--accept-url-credential, "
    "accept-url-credentials in [tool.pitloom]) that no URL value of the "
    "SBOM it names (its document id) has: a value since removed, or a "
    "fingerprint mistyped. The DIR= line is 'loom id generate' or "
    "'loom id import' given -o and --project-dir, whose project config could "
    "not be read (a bare setup(), an invalid setting): its url-credentials "
    "is not applied. The FILE= line is a --config file (loom.run's "
    "pitloom_config) with no [tool.pitloom] table: a wrong file, most often.",
    did="Ran as if it were not given; the run goes on.",
    effect="none",
    actor="caller",
    advice="The caller may drop the option from its command, or pick the "
    "target or companion option it needs (the line says which). Nothing to "
    "tell the user unless they asked for the option; for the INFO: line, do "
    "not edit their configuration. For the FINGERPRINT= line, tell the "
    "user the acceptance accepts nothing here; they may drop it. For the "
    "DIR= line, tell the user the project's url-credentials was not "
    "applied and why; to refuse, the caller adds --refuse-url-credentials. "
    "For the FILE= line, the caller checks it named the file it meant.",
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
    template=f"{REGISTRY_PREFIX}PATH %(path)s is not inside the project root %(root)s",
)

#: A fingerprint given to the library (``CredentialPolicy``) that is none.
FINGERPRINT_LINE: Final = Line(
    level="ERROR", template=f"not a fingerprint ({FINGERPRINT_SHAPE})"
)
#: A ``PitloomConfig(url_credentials=...)`` that is no mode, given to the
#: library.
URL_CREDENTIALS_MODE_ARGUMENT_LINE: Final = Line(
    level="ERROR",
    template='PitloomConfig url_credentials: must be "warn" or "refuse"',
)
#: A value given to the library (a parameter, a ``PitloomConfig`` field) of
#: the wrong type or shape: ``must be X, got Y``, as ``config-invalid`` says
#: it of a configuration setting.
VALUE_LINE: Final = Line(
    level="ERROR", template="%(option)s: must be %(expected)s, got %(got)s"
)
#: A ``CredentialPolicy(refuse=...)`` that is no ``bool``.
REFUSE_ARGUMENT_LINE: Final = Line(
    level="ERROR",
    template="CredentialPolicy refuse: must be True or False",
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
        FINGERPRINT_LINE,
        URL_CREDENTIALS_MODE_ARGUMENT_LINE,
        REFUSE_ARGUMENT_LINE,
        VALUE_LINE,
    ),
    summary="The command line holds an option or a value the command does not "
    "take: an unknown option, a value of the wrong form or out of range, an "
    "unknown subcommand, an option out of order (a creator's type or email "
    "before its name), or a 'loom id generate' PATH outside --project-dir "
    "(the library: a path outside the project root given to "
    "IdRegistry.generate). Or a library caller gave a value of the wrong "
    "type or shape (the must-be line, as config-invalid says it of a "
    "setting: a byte cap of 0, a creation_datetime that is no ISO 8601 "
    "date). Or a URL credential fingerprint given to the library is not "
    "one; the line never shows the value, which may be a credential pasted "
    "by mistake. Or PitloomConfig.url_credentials is neither warn nor "
    "refuse, or CredentialPolicy(refuse=...) is no bool. The same faults "
    "in [tool.pitloom] are config-invalid. An option given without its "
    "value is option-missing; two options argparse refuses together are "
    "option-conflict.",
    did="Ran nothing: the command exits 2 (the Action step fails), 1 for a "
    "PATH outside --project-dir; the library raises ValueError carrying the "
    "code for a build timeout out of range (BuildOptions), a path outside "
    "the project root (IdRegistry.generate), a value of the wrong type or "
    "shape, a fingerprint that is none (CredentialPolicy) or a "
    "url-credentials that is no mode.",
    effect="not-written",
    actor="caller",
    advice="The caller may fix the option or value the line names ('loom "
    "<command> --help' lists them) and run again. Tell the user only when the "
    "value came from them. For a fingerprint, the user copies it from the "
    "credentials-unsafe/written or refused line that offers it; do not show the "
    "value they gave, and do not edit their configuration.",
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
    "--namespace %(given_namespace)s; delete it to change the namespace",
)
#: The same, when the two read alike once masked: a namespace holds no
#: credential, but a ``code`` or ``session`` value it keeps is masked in a
#: message (``?code=A`` and ``?code=B``).
NAMESPACE_CONFLICT_MASKED_LINE: Final = Line(
    level="ERROR",
    template=f"{REGISTRY_PREFIX}FILE=%(file)s: namespace %(namespace)s is not "
    "--namespace %(given_namespace)s (they differ in masked credentials); "
    "delete it to change the namespace",
)


def namespace_conflict_line(held: str, given: str) -> Line:
    """The line for a registry's namespace *held* that is not *given*:
    :data:`NAMESPACE_CONFLICT_MASKED_LINE` when the two print alike once a
    URL's credentials are masked, so the line never reads ``X is not X``."""
    alike = entity_text(held) == entity_text(given)
    return NAMESPACE_CONFLICT_MASKED_LINE if alike else NAMESPACE_CONFLICT_LINE


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
        NAMESPACE_CONFLICT_MASKED_LINE,
        PROJECT_ROOT_CONFLICT_LINE,
    ),
    summary="The command line holds an option the command cannot take in this "
    "case (-o/--output with several wheels), or one an existing ID registry "
    "contradicts: 'loom id generate --namespace' for a registry made with "
    "another namespace, or 'loom id generate' with a --project-dir (the "
    "current directory when not given), or 'loom id import' with an "
    "explicit one, other than the one the registry was made for. "
    "The 'not allowed with' line is reserved for options of a mutually "
    "exclusive group; no command has one yet.",
    did="Ran nothing: the command exits 1 (2 for the 'not allowed with' "
    "line), the library (IdRegistry) raises ValueError carrying the code, "
    "and an ID registry is left as it is.",
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

#: ``embed-wheel`` without ``--project-dir``, run where a project is.
PROJECT_DIR_NOT_GIVEN_LINE: Final = Line(
    level="INFO",
    template="--project-dir not given; the SBOM is built from the wheel alone, "
    "not from the project in the current directory",
)

OPTION_MISSING_PROJECT_DIR: Final = Message(
    code="option-missing/project-dir",
    condition="missing",
    lines=(PROJECT_DIR_NOT_GIVEN_LINE,),
    summary="'loom embed-wheel' ran without --project-dir in a directory "
    "holding a pyproject.toml: it never reads a project it is not given, so "
    "the SBOM it embeds is built from the wheel's own files and METADATA.",
    did="Built the SBOM from the wheel alone and embedded it; the exit "
    "status does not change.",
    effect="none",
    actor="caller",
    advice="The caller may run again with --project-dir naming the project "
    "the wheel was built from, for an SBOM that also states what the "
    "project declares (its lock file, its configuration).",
    since=_SINCE,
)

ENTRIES: Final = (
    OPTION_NO_EFFECT,
    OPTION_INVALID,
    OPTION_CONFLICT,
    OPTION_MISSING,
    OPTION_MISSING_PROJECT_DIR,
)
