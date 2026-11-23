# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project's metadata files Pitloom cannot read as metadata: a
``setup.py`` that is no Python it can parse (``metadata-malformed``), a
value of the wrong type or shape (``metadata-invalid``) and no project
name anywhere (``project-name-missing``). As an ``ERROR`` no SBOM is
written. An ``ERROR`` line a reader may catch and go on past has a
``WARNING`` twin (:func:`~pitloom.messages._types.warning_twins`), said by
:func:`~pitloom.messages._metadata_say.relay_coded_warning`.

A ``pyproject.toml`` or ``setup.cfg`` that is not valid TOML or INI says
``config-malformed``; one that cannot be read, ``file-unreadable``, read
``for the project metadata``.

See also: :mod:`pitloom.messages.metadata` (the public names),
:mod:`pitloom.extract.project` (the readers).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message, warning_twins

_SINCE: Final = "0.25.0"
#: What the user does not let an agent do.
_NO_EDIT: Final = f"Do not edit the project for them; {ASK_FIRST}"
#: What every ERROR here does.
_NOT_WRITTEN: Final = (
    "As an ERROR, wrote nothing: the command exits 1 (the Action step "
    "fails), the library raises ValueError carrying the code."
)
#: The tail of a WARNING about a ``setup()`` keyword.
_UNDECLARED: Final = "; treated as undeclared"


def _setup_keyword(condition: str) -> Line:
    """The ``WARNING`` line naming a ``setup()`` keyword of a setup.py,
    then *condition*, then that it is treated as undeclared."""
    return Line(
        level="WARNING",
        template=f"FILE=%(file)s: setup() keyword %(name)s {condition}{_UNDECLARED}",
    )


#: A setup.py the parser refuses (a syntax error, a NUL byte, an expression
#: nested too deeply for it).
PYTHON_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: not valid Python; %(failure)s"
)
#: An attribute line of a ``file:``/``attr:`` directive's module nested
#: too deeply to parse.
NESTED_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: %(name)s line too deeply nested to parse; "
    "skipped for %(field)s",
)

METADATA_MALFORMED: Final = Message(
    code="metadata-malformed",
    condition="malformed",
    lines=(*warning_twins((PYTHON_LINE,)), NESTED_LINE),
    summary="A setup.py is not Python the parser of the Python Pitloom runs on "
    "can read: a syntax error, a NUL byte, or an expression nested too deeply "
    "for it. The failure is the parser's. The nested line is the line of a "
    "module that a setup.cfg attr: directive names, too deeply nested to "
    "parse alone.",
    did=f"{_NOT_WRITTEN} As a WARNING, read the project without it: a "
    "setup.py that does not parse while setup.cfg names the project leaves "
    "setup.cfg read alone; one read for pyproject.toml's dynamic fields fills "
    "none of them; a nested attr: line leaves the field it was read for "
    "unset, said once per file and field per process.",
    effect="not-written",
    actor="user",
    advice="Tell the user which file does not parse and the parser's failure, "
    "as the line says. They fix the syntax (setup.py runs as Python 3) or "
    f"write the value as a literal, and generate again. {_NO_EDIT}",
    subject_key="FILE",
    since=_SINCE,
)

#: What a value read as project metadata must be and is not. The ERROR is
#: refused (a [project] or [tool.poetry] that is no table, a name that is
#: no string); the WARNING twin is the same refusal relayed.
TYPE_ERROR_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: %(field)s is %(got)s, expected %(expected)s",
)
#: The same, for a value left out and the read going on.
TYPE_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: %(field)s is %(got)s, expected %(expected)s; ignored",
)
#: [project] that pyproject-metadata refuses; the failure is its own.
PROJECT_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: not valid [project] metadata; %(failure)s",
)
#: A [project] version or requires-python with a number too long to parse.
NUMBER_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: %(field)s has a number over %(number)s digits",
)
#: [project] present with no name, or a blank one.
PROJECT_NO_NAME_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: [project] has no name; read setup.cfg and "
    "setup.py instead",
)
#: A ``setup()`` keyword read from a ``**`` unpack.
KEYWORD_UNPACKED_LINE: Final = _setup_keyword("is not read")
#: A ``setup()`` keyword whose value is no literal.
KEYWORD_NOT_LITERAL_LINE: Final = _setup_keyword("is not a literal")
#: A ``setup()`` keyword whose literal Pitloom does not read.
KEYWORD_UNREAD_LINE: Final = _setup_keyword(
    "has a value Pitloom does not read (%(value)s)"
)
#: A ``setup()`` keyword given a blank string.
KEYWORD_BLANK_LINE: Final = _setup_keyword("is blank")
#: A ``tool.setuptools.dynamic`` requirements entry that is not a
#: ``{file = ...}`` table.
DIRECTIVE_NOT_FILE_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: %(field)s is not a table with 'file'; ignored",
)
#: A ``tool.setuptools.dynamic`` requirements entry given as ``attr``.
DIRECTIVE_ATTR_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: %(field)s has 'attr', not supported for "
    "requirements; ignored",
)
#: A requirements file a setting lists that is not there.
LISTED_NOT_FOUND_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: listed by %(field)s, not found; skipped",
)
#: A requirements file a setting lists by a name no file can have (a NUL).
LISTED_NO_FILE_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: listed by %(field)s, not a file name; skipped",
)

METADATA_INVALID: Final = Message(
    code="metadata-invalid",
    condition="invalid",
    lines=(
        TYPE_ERROR_LINE,
        Line(level="WARNING", template=TYPE_ERROR_LINE.template),
        TYPE_LINE,
        # Twinned: 'loom fragment list' says them as a WARNING and goes on.
        *warning_twins((PROJECT_LINE, NUMBER_LINE)),
        PROJECT_NO_NAME_LINE,
        KEYWORD_UNPACKED_LINE,
        KEYWORD_NOT_LITERAL_LINE,
        KEYWORD_UNREAD_LINE,
        KEYWORD_BLANK_LINE,
        DIRECTIVE_NOT_FILE_LINE,
        DIRECTIVE_ATTR_LINE,
        LISTED_NOT_FOUND_LINE,
        LISTED_NO_FILE_LINE,
    ),
    summary="A project metadata value is not what its format allows: a "
    "[project] that pyproject-metadata refuses (its words), a [project] or "
    "[tool.poetry] that is no table, a name that is no string, a version with "
    "a number too long to parse, a [project] with no name, a value of the "
    "wrong type, a setup() keyword Pitloom cannot read statically, a "
    "tool.setuptools.dynamic entry that is no {file = ...} table, or a "
    "requirements file a setting lists that is not there.",
    did=f"{_NOT_WRITTEN} As a WARNING, read on without the value: a wrong "
    "type is ignored; a setup() keyword is treated as undeclared, so a "
    "lower-priority source may give the field; a [project] with no name "
    "leaves setup.cfg and setup.py to name the project; a listed file not "
    "there gives no requirements; a [tool.poetry] relayed from a Poetry read "
    "skips Poetry's gap-fill, while poetry.lock's pins still apply. 'loom "
    "fragment list' says a refused [project] or too long a number as a "
    "WARNING too, and lists the fragments with SAME_DOCUMENT=-.",
    effect="not-written",
    actor="user",
    advice="Tell the user which value is refused or ignored and what was "
    "expected, as the line says; a WARNING leaves the field out of the SBOM "
    "or takes it from another source. They fix the value in the file named "
    f"and generate again. {_NO_EDIT}",
    subject_key="FILE",
    since=_SINCE,
)

#: No name in a Poetry project.
POETRY_NAME_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: neither [tool.poetry] nor [project] has a project name",
)
#: No name in a setuptools project's setup.cfg nor its setup.py.
SETUPTOOLS_NAME_LINE: Final = Line(
    level="ERROR",
    template="DIR=%(dir)s: no project name in setup.cfg [metadata] or a "
    "literal setup(name=...)",
)
#: No name in setup.cfg [metadata], read alone.
SETUP_CFG_NAME_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: [metadata] has no project name"
)
#: No literal name in setup.py, read alone.
SETUP_PY_NAME_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: no project name: setup(name=...) is not a string literal",
)

PROJECT_NAME_MISSING: Final = Message(
    code="project-name-missing",
    condition="missing",
    lines=(
        *warning_twins((POETRY_NAME_LINE,)),
        # Twinned: 'loom fragment list' says them as a WARNING and goes on.
        *warning_twins((SETUPTOOLS_NAME_LINE, SETUP_CFG_NAME_LINE, SETUP_PY_NAME_LINE)),
    ),
    summary="No project name is found where the project's build backend "
    "reads it: a Poetry project names it in neither [tool.poetry] nor "
    "[project]; a setuptools project in neither setup.cfg [metadata] nor a "
    "setup(name=...) string literal (a name computed by code is not read). "
    "A setup.py that does not parse says metadata-malformed first.",
    did=f"{_NOT_WRITTEN} The setuptools line raises FileNotFoundError, also "
    "carrying the code. As a WARNING, a Poetry read for poetry.lock's pins "
    "skipped Poetry's gap-fill and still applied the pins; 'loom fragment "
    "list' says any of them and lists the fragments with SAME_DOCUMENT=-.",
    effect="not-written",
    actor="user",
    advice="Tell the user that the project has no name Pitloom can read, and "
    "where it looked, as the line says. They declare name in [project] (or "
    "[tool.poetry], setup.cfg [metadata], or setup() as a string literal) "
    f"and generate again. {_NO_EDIT}",
    since=_SINCE,
)

ENTRIES: Final = (METADATA_MALFORMED, METADATA_INVALID, PROJECT_NAME_MISSING)
