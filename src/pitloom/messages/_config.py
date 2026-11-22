# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom's own configuration (``[tool.pitloom]`` in ``pyproject.toml``,
``[tool:pitloom]`` in ``setup.cfg``, a ``--config`` file, the build hook's
``[tool.hatch.build.hooks.pitloom]``): a value of the wrong type or shape
(``config-invalid``), a key that moved (``config-moved``), a key Pitloom
does not know (``config-unknown-key``), a file that does not parse
(``config-malformed``), and the build's time sources: a
``SOURCE_DATE_EPOCH`` that is no time (``source-date-epoch-invalid``) and
an SBOM date taken from the clock (``datetime-unpinned``).

A line names where the value sits by its ``config_key``
(:class:`~pitloom.messages._config_place.ConfigPlace`), after ``FILE=``
when the file is known; a library caller's own value is
``option-invalid`` (:data:`~pitloom.messages._options.OPTION_VALUE_LINE`).
A configuration file the system does not let Pitloom read, or that is not
UTF-8, says ``file-unreadable`` (``/not-utf8``) ``for the configuration``.

See also: :mod:`pitloom.messages._config_say` (the error and the helpers),
:mod:`pitloom.messages.config` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._frames import HOOK_PREFIX
from pitloom.messages._types import ASK_FIRST, Line, Message, warning_twins

_SINCE: Final = "0.25.0"
#: Every run that reads a project's configuration.
_SURFACES: Final = (
    "the command line (a project's pyproject.toml or setup.cfg, an sdist's, "
    "or a --config file), the build hook, the library (generate_project_sbom, "
    "loom.run's pitloom_config, load_config_file) and the GitHub Action"
)


def _error(text: str) -> tuple[Line, Line]:
    """An ``ERROR`` line naming the file then where the value sits, then
    *text*; and its twin for a configuration of no file (a library
    dictionary)."""
    return (
        Line(level="ERROR", template=f"FILE=%(file)s: %(config_key)s: {text}"),
        Line(level="ERROR", template=f"%(config_key)s: {text}"),
    )


#: A value of the wrong type or shape: ``must be X, got Y``.
INVALID_FILE_LINE, INVALID_LINE = _error("must be %(expected)s, got %(got)s")

CONFIG_INVALID: Final = Message(
    code="config-invalid",
    condition="invalid",
    lines=(INVALID_FILE_LINE, INVALID_LINE),
    summary="A setting of Pitloom's configuration holds a value of the "
    "wrong type or shape: a string where true or false goes, 0 for a byte "
    "cap, a path where a file name goes, a table missing its name, an "
    "unknown choice. The line names the file, the setting (a table, a key, "
    "an array's entry counted from 0) and what it must be, then what it "
    "holds: its TOML type, and a short value (a string masked, escaped and "
    "cut to 40 characters). A URL credential fingerprint or a "
    "url-credentials mode is named by its type only: it may be the "
    "credential, pasted by mistake. A setup.cfg setting is named as "
    "setup.cfg spells it ([tool:pitloom]). The build hook's own "
    "[tool.hatch.build.hooks.pitloom] is named without a file: Hatchling "
    "may read it from hatch.toml.",
    did=f"Said by {_SURFACES}. Read no setting and wrote nothing: the command "
    "exits 1, the build fails, the library raises ValueError carrying the "
    "code.",
    effect="not-written",
    actor="user",
    advice="Tell the user the file, the setting, what it must be and what it "
    "holds, as the line says; they fix the value and run again (the "
    "configuration reference lists every setting). Do not edit their "
    f"configuration for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: A key or table that moved; the line names where it goes now.
MOVED_FILE_LINE, MOVED_LINE = _error("moved to %(destination)s")

CONFIG_MOVED: Final = Message(
    code="config-moved",
    condition="moved",
    lines=(MOVED_FILE_LINE, MOVED_LINE),
    summary="A configuration holds a key or table of an earlier release that "
    "now lives elsewhere: a single creator's creator-name in "
    "[tool.pitloom.creation] (now an entry of [[tool.pitloom.creator]]), "
    "ids-file (now id-registry), a [tool.pitloom.fragments] table, a build "
    "hook setting that moved to [tool.pitloom]. The line names where it "
    "goes now, as pyproject.toml spells it.",
    did=f"Said by {_SURFACES}. Read no setting and wrote nothing: the command "
    "exits 1, the build fails, the library raises ValueError carrying the "
    "code. Pitloom never reads a moved key in its old place.",
    effect="not-written",
    actor="user",
    advice="Tell the user which key moved and where it goes now, as the line "
    "says; they move it (a single value becomes an entry of an array of "
    "tables where the line names one) and run again. Do not edit their "
    f"configuration for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)


def _unknown(prefix: str, hint: str) -> Line:
    """A ``WARNING`` line naming an unknown key of a table, after *prefix*,
    then *hint*."""
    return Line(
        level="WARNING",
        template=f"{prefix}%(config_key)s: unknown key %(entry)s{hint}",
    )


_FILE: Final = "FILE=%(file)s: "
_CLOSE: Final = "; did you mean %(setting)s?"
_ELSEWHERE: Final = "; it belongs in %(tables)s"

#: An unknown key close to a known one.
UNKNOWN_CLOSE_FILE_LINE: Final = _unknown(_FILE, _CLOSE)
UNKNOWN_CLOSE_LINE: Final = _unknown("", _CLOSE)
#: An unknown key that another table knows.
UNKNOWN_ELSEWHERE_FILE_LINE: Final = _unknown(_FILE, _ELSEWHERE)
UNKNOWN_ELSEWHERE_LINE: Final = _unknown("", _ELSEWHERE)
#: An unknown key, no hint.
UNKNOWN_FILE_LINE: Final = _unknown(_FILE, "")
UNKNOWN_LINE: Final = _unknown("", "")
#: The build hook's table holds keys it does not take: an error.
HOOK_UNKNOWN_LINE: Final = Line(
    level="ERROR",
    template="%(config_key)s: unknown keys %(entries)s; only enabled and "
    "Hatchling's own hook keys go here, other settings go in [tool.pitloom]",
)

CONFIG_UNKNOWN_KEY: Final = Message(
    code="config-unknown-key",
    condition="unknown-key",
    lines=(
        UNKNOWN_CLOSE_FILE_LINE,
        UNKNOWN_ELSEWHERE_FILE_LINE,
        UNKNOWN_FILE_LINE,
        UNKNOWN_CLOSE_LINE,
        UNKNOWN_ELSEWHERE_LINE,
        UNKNOWN_LINE,
        HOOK_UNKNOWN_LINE,
    ),
    summary="A configuration table holds a key Pitloom does not know: most "
    "often a misspelt one (the line names the known key it is closest to, "
    "never its opposite: no-creation-tool is not creation-tool), or one "
    "that belongs in another table (the line names it). As an ERROR, the "
    "build hook's [tool.hatch.build.hooks.pitloom] holds keys other than "
    "enabled and Hatchling's own hook keys.",
    did=f"Said by {_SURFACES}, once per file and key in a run. As a "
    "WARNING, ignored the key: the run goes on with the setting's default, "
    "so the setting the user meant is not applied. As an ERROR, the build "
    "fails.",
    effect="none",
    actor="user",
    advice="Tell the user which key is unknown and the hint the line gives; "
    "the setting they meant is not applied until they rename or move it. "
    "Do not edit their configuration for them; " + ASK_FIRST,
    subject_key="FILE",
    since=_SINCE,
)

#: A TOML configuration (``pyproject.toml``, a ``--config`` file) that does
#: not parse; the failure names its line and column.
TOML_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: not valid TOML; %(failure)s"
)
#: A ``setup.cfg`` that does not parse.
INI_FILE_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: not valid INI; %(failure)s"
)
INI_LINE: Final = Line(level="ERROR", template="not valid INI; %(failure)s")
#: A ``[tool:pitloom]`` value with a bad ``%``: the error names the section,
#: the key and the fix.
INTERPOLATION_FILE_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: not valid INI interpolation; %(error)s",
)
INTERPOLATION_LINE: Final = Line(
    level="ERROR", template="not valid INI interpolation; %(error)s"
)

CONFIG_MALFORMED: Final = Message(
    code="config-malformed",
    condition="malformed",
    lines=(
        *warning_twins((TOML_LINE, INI_FILE_LINE, INTERPOLATION_FILE_LINE)),
        INI_LINE,
        INTERPOLATION_LINE,
    ),
    summary="A configuration or project metadata file is not valid TOML (a "
    "--config file, a project's or an sdist's pyproject.toml) or INI (a "
    "setup.cfg): the parser's failure, with its line and column where it "
    "gives them. The interpolation line is a setup.cfg value holding a % "
    "that is not a %% or a valid %(name)s reference.",
    did="Said by the command line, the build hook, the library "
    "(load_config_file, loom.run's pitloom_config, read_project, read_sdist) "
    "and the GitHub Action. As an ERROR, read no setting and no project "
    "metadata and wrote nothing: the command exits 1, the build hook fails "
    "the build, the library raises ValueError carrying the code. As a "
    "WARNING, read the project without that file: a setup.cfg read for "
    "pyproject.toml's dynamic fields fills none of them; an sdist's "
    "pyproject.toml gives none of its fields: PKG-INFO's are read when there "
    "is one, else the package is named unknown, with no version, description "
    "or dependencies.",
    effect="not-written",
    actor="user",
    advice="Tell the user which file does not parse and where, as the line "
    "says; they fix the syntax there (a % in a setup.cfg value is written "
    "%%) and run again. Do not edit their configuration for them; " + ASK_FIRST,
    subject_key="FILE",
    since=_SINCE,
)

_EPOCH: Final = "SOURCE_DATE_EPOCH=%(value)s: "
#: ``SOURCE_DATE_EPOCH`` is not a whole number.
EPOCH_NOT_INTEGER_LINE: Final = Line(
    level="ERROR",
    template=f"{_EPOCH}not an integer number of seconds since the Unix epoch",
)
#: ``SOURCE_DATE_EPOCH`` is a number no date has.
EPOCH_OUT_OF_RANGE_LINE: Final = Line(
    level="ERROR", template=f"{_EPOCH}out of range for a date"
)

SOURCE_DATE_EPOCH_INVALID: Final = Message(
    code="source-date-epoch-invalid",
    condition="invalid",
    lines=(EPOCH_NOT_INTEGER_LINE, EPOCH_OUT_OF_RANGE_LINE),
    summary="The SOURCE_DATE_EPOCH environment variable, which pins the "
    "dates of a reproducible build, is set to something that is not a whole "
    "number of seconds since 1970-01-01 UTC, or to a number no date has. "
    "The specification says a build should fail on it, as Hatchling does.",
    did="Read whether or not a date is pinned otherwise; wrote nothing: the "
    "command exits 1, the build fails, the library raises ValueError "
    "carrying the code.",
    effect="not-written",
    actor="user",
    advice="Tell the user the value is not a time, as the line says. They "
    "unset it, or set it to whole seconds since 1970 (the build environment "
    "most often sets it: a CI step, a packaging tool). Do not change their "
    f"environment for them; {ASK_FIRST}",
    subject_key="SOURCE_DATE_EPOCH",
    since=_SINCE,
)

#: The build hook dates its SBOM by the clock.
CLOCK_LINE: Final = Line(
    level="INFO",
    template=f"{HOOK_PREFIX}created and builtTime come from the clock; "
    "set SOURCE_DATE_EPOCH or creation-datetime to pin them",
)

DATETIME_UNPINNED: Final = Message(
    code="datetime-unpinned",
    condition="unpinned",
    lines=(CLOCK_LINE,),
    summary="The build hook found neither SOURCE_DATE_EPOCH nor "
    "creation-datetime in [tool.pitloom.creation], so the SBOM's created "
    "and the package's builtTime are the time of the build: two builds of "
    "the same sources give SBOMs (and wheels) that differ in those dates.",
    did="Dated the SBOM by the clock; the build goes on.",
    effect="none",
    actor="none",
    advice="Nothing to fix. For byte-identical builds, the user sets "
    "SOURCE_DATE_EPOCH in the build environment or creation-datetime in "
    "[tool.pitloom.creation]; mention it only when they ask about "
    "reproducible builds.",
    since=_SINCE,
)

ENTRIES: Final = (
    CONFIG_INVALID,
    CONFIG_MOVED,
    CONFIG_UNKNOWN_KEY,
    CONFIG_MALFORMED,
    SOURCE_DATE_EPOCH_INVALID,
    DATETIME_UNPINNED,
)
