# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One entry of a lock file Pitloom records no pin for: a package entry, a
dependency reference or a ``requirements.txt`` line of the wrong shape, or
naming what the lock does not hold (``lock-entry-malformed``); one with no
exact registry pin to record (``lock-entry-unusable``); and a package the
lock states at several versions (``lock-entry-conflict``).

A ``requirements.txt`` is read as a lock only when every line is one exact
pin, so one line of it that is not ends ``no pins read from it``; a lock's
entry ends ``skipped``. A line of ``requirements.txt`` is named by its
number as pip counts it (``FILE=requirements.txt LINE=3``).

See also: :mod:`pitloom.messages._lock_file` (the file as a whole),
:mod:`pitloom.messages._lock_say` (the helpers that say them),
:mod:`pitloom.messages.lock_files` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._lock_file import LOCK_SURFACES, NOT_READ
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: What a lock entry's line ends in when its pin is left out.
SKIPPED: Final = "skipped"
#: What a lock entry's line ends in when its pin is recorded but something
#: it names is not followed.
PIN_KEPT: Final = "pin kept"


def _entry(text: str) -> Line:
    """A ``WARNING`` line naming the lock file, then *text*."""
    return Line(level="WARNING", template=f"FILE=%(file)s: {text}")


def _package(text: str) -> Line:
    """A ``WARNING`` line naming the lock file and the package, then
    *text*."""
    return Line(level="WARNING", template=f"FILE=%(file)s PACKAGE=%(package)s: {text}")


def _requirement_line(text: str) -> Line:
    """A ``WARNING`` line naming ``requirements.txt`` and the line, then
    *text*, then that no pins are read from the file."""
    return Line(
        level="WARNING",
        template=f"FILE=%(file)s LINE=%(line_number)s: {text}; {NOT_READ}",
    )


#: A ``requirements.txt`` line that is not a PEP 508 requirement; *why*:
#: the first line of the parser's message, a URL's credentials masked.
REQUIREMENT_LINE: Final = _requirement_line("not a PEP 508 requirement: %(why)s")
#: An entry of a list that is not a table (and so has no name).
NOT_TABLE_LINE: Final = _entry(
    f"an entry of %(lock_key)s is %(value_type)s, expected a table; {SKIPPED}"
)
#: An entry with no name, or one that is not a valid distribution name.
NAME_LINE: Final = _entry(
    "an entry of %(lock_key)s has name %(lock_value)s, not a valid package "
    f"name; {SKIPPED}"
)
#: A ``Pipfile.lock`` entry (keyed by its name) that is not a table.
PACKAGE_NOT_TABLE_LINE: Final = _package(
    f"entry is %(value_type)s, expected a table; {SKIPPED}"
)
#: An entry with no ``version``, or one that is not a version.
VERSION_LINE: Final = _package(f"version missing or not a version; {SKIPPED}")
#: A ``Pipfile.lock`` version that is not a version specifier.
SPECIFIER_LINE: Final = _package(
    f"version %(lock_value)s is not a version specifier; {SKIPPED}"
)
#: A key of an entry that is not a list (``groups``): the entry is skipped.
KEY_LIST_LINE: Final = _package(
    f"%(lock_key)s is %(value_type)s, expected a list; {SKIPPED}"
)
#: An entry's own ``dependencies`` that is not a list: its pin is kept, its
#: dependencies are not followed.
DEPENDENCIES_LIST_LINE: Final = _package(
    "%(lock_key)s is %(value_type)s, expected a list; its dependencies not "
    f"followed, {PIN_KEPT}"
)
#: An entry's ``optional-dependencies`` that is not a table: the extras a
#: reference requests are not followed.
KEY_TABLE_LINE: Final = _package(
    "%(lock_key)s is %(value_type)s, expected a table; requested extras not "
    f"followed, {PIN_KEPT}"
)
#: A key of an entry that is not a string.
KEY_TEXT_LINE: Final = _package(
    f"%(lock_key)s is %(value_type)s, expected a string; {SKIPPED}"
)
#: A dependency reference's requested extras: neither a string nor a list.
KEY_TEXT_OR_LIST_LINE: Final = _package(
    "%(lock_key)s is %(value_type)s, expected a string or a list; requested "
    f"extras not followed, {PIN_KEPT}"
)
#: A dependency reference's requested extras holding a value that is not a
#: string: those values are skipped, the others read.
KEY_ITEMS_LINE: Final = _package(
    "%(lock_key)s holds a value that is not a string; that value not "
    f"followed, {PIN_KEPT}"
)
#: One extra's list of ``optional-dependencies`` that is not a list.
EXTRA_LIST_LINE: Final = _package(
    "%(lock_key)s of extra %(extra_name)s is %(value_type)s, expected a "
    f"list; extra not followed, {PIN_KEPT}"
)
#: A dependency reference naming a package the lock's table does not hold.
NOT_IN_TABLE_LINE: Final = _package(
    f"referenced but not in the lock's package table; {SKIPPED}"
)
#: A dependency reference requesting an extra the package does not have.
NO_EXTRA_LINE: Final = _package(
    "extra %(extra_name)s requested but not in its %(lock_key)s; extra not "
    f"followed, {PIN_KEPT}"
)
#: A marker that does not parse: the entry is kept, as if it held.
MARKER_LINE: Final = _package(
    "marker %(lock_value)s does not parse: %(failure)s; kept, its marker read as true"
)

LOCK_ENTRY_MALFORMED: Final = Message(
    code="lock-entry-malformed",
    condition="malformed",
    lines=(
        REQUIREMENT_LINE,
        NOT_TABLE_LINE,
        NAME_LINE,
        PACKAGE_NOT_TABLE_LINE,
        VERSION_LINE,
        SPECIFIER_LINE,
        KEY_LIST_LINE,
        DEPENDENCIES_LIST_LINE,
        KEY_TABLE_LINE,
        KEY_TEXT_LINE,
        KEY_TEXT_OR_LIST_LINE,
        KEY_ITEMS_LINE,
        EXTRA_LIST_LINE,
        NOT_IN_TABLE_LINE,
        NO_EXTRA_LINE,
        MARKER_LINE,
    ),
    summary="One entry of a lock file, one dependency reference in it or one "
    "line of requirements.txt has the wrong shape (no name, no version, a "
    "key of the wrong type, a marker that does not parse, a line that is "
    "not PEP 508), or names what the lock does not hold (a package missing "
    "from its table, an extra the package does not have). Most often a "
    "stale or hand-edited lock.",
    did=f"Said by {LOCK_SURFACES}. What the line's last clause says: "
    "'skipped' left the entry's pin out; 'pin kept' recorded the entry's "
    "pin but did not follow its dependencies, or the extras a reference "
    "requests, so pins reached only through them are missing; a "
    "pylock.toml marker that does not parse keeps its entry, as if the "
    "marker held; a requirements.txt line reads no pins from the file, and "
    "the next lock is tried. The rest of the lock is read. A uv.lock line "
    "about a package is said once per package and line in one run. The "
    "SBOM is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user which lock entry is malformed and what is wrong, "
    "as the line says, and what the SBOM lacks for it: the entry's pin "
    "('skipped'), or the pins reached only through what was not followed "
    "('pin kept'); a marker read as true may list a package the project's "
    "environments do not install. They regenerate "
    "the lock with its tool ('uv lock', 'poetry lock', 'pdm lock', 'pipenv "
    "lock', or pip-compile for requirements.txt) and run again. Do not "
    f"regenerate or edit the lock for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: A ``requirements.txt`` line that is a pip option (``-r``, ``-e``).
OPTION_LINE: Final = _requirement_line("pip option %(lock_value)s, not a pin")
#: A ``requirements.txt`` line that is a direct reference.
DIRECT_LINE: Final = _requirement_line("%(package)s is a direct reference, not a pin")
#: A ``requirements.txt`` line that is not one exact version.
RANGE_LINE: Final = _requirement_line("%(package)s is not one exact version")
#: An entry from a VCS, a path, a URL or an editable source.
SOURCE_LINE: Final = _package(
    f"a %(source_kind)s source, not a registry version; {SKIPPED}"
)
#: A dependency reference stating its own version (one per marker).
REFERENCE_VERSION_LINE: Final = _package(
    f"its reference states a version per marker; {SKIPPED}"
)
#: A ``Pipfile.lock`` version that is not one exact version.
NOT_EXACT_LINE: Final = _package(
    f"version %(lock_value)s is not one exact version; {SKIPPED}"
)

LOCK_ENTRY_UNUSABLE: Final = Message(
    code="lock-entry-unusable",
    condition="unusable",
    lines=(
        OPTION_LINE,
        DIRECT_LINE,
        RANGE_LINE,
        SOURCE_LINE,
        REFERENCE_VERSION_LINE,
        NOT_EXACT_LINE,
    ),
    summary="A well-formed lock entry or requirements.txt line has no exact "
    "registry version to record: a VCS, path, URL or editable source, a "
    "range, a version per marker (Pitloom evaluates no marker), or a pip "
    "option. A requirements.txt is read as a lock only when every line is "
    "one exact pin.",
    did=f"Said by {LOCK_SURFACES}. Skipped the entry and read the rest of "
    "the lock; for a requirements.txt line, read no pins from the file and "
    "tried the next lock. The direct dependency itself is still listed from "
    "its declaration. The SBOM is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user which entry has no pin in the SBOM and why, as "
    "the line says. Nothing in a lock needs fixing: a source that is not a "
    "registry has no version to pin. A requirements.txt meant as a lock "
    "pins every line to one exact version (pip-compile writes one; "
    "--generate-hashes output and -r includes are not read). Do not edit "
    f"the file for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: A package at several versions in one lock: left out.
VERSIONS_LINE: Final = _package(
    f"pinned to several versions; {SKIPPED}, dropped %(dropped)s"
)
#: A package at several versions in ``requirements.txt``: no pins read.
VERSIONS_FILE_LINE: Final = _package(
    f"pinned to several versions; {NOT_READ}, dropped %(dropped)s"
)

#: A package at several versions in the locked dependencies a document is
#: assembled from (two lock formats layered by hand): no lock file to name.
LOCKED_VERSIONS_LINE: Final = Line(
    level="WARNING",
    template="PACKAGE=%(package)s: pinned to several versions in the locked "
    f"dependencies; {SKIPPED}, dropped %(dropped)s",
)

LOCK_ENTRY_CONFLICT: Final = Message(
    code="lock-entry-conflict",
    condition="conflict",
    lines=(VERSIONS_LINE, VERSIONS_FILE_LINE, LOCKED_VERSIONS_LINE),
    summary="One lock file states one package at several versions; or (no "
    "FILE= on the line) the locked dependencies a document is assembled "
    "from do, as when two lock formats are layered by hand. Often "
    "legitimate: pylock.toml may hold one entry per marker, uv.lock one per "
    "Python version, and Pitloom evaluates no marker. Two spellings of one "
    "version (1.0 and 1.0.0) are one version and say nothing.",
    did=f"Said by {LOCK_SURFACES}. Recorded no pin for the package (the line "
    "lists the versions dropped); in requirements.txt, read no pins from "
    "the file and tried the next lock. A uv.lock line about a package is "
    "said once per package and line in one run. The SBOM is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user which package has no pin in the SBOM and the "
    "versions the line drops. When the versions are per environment "
    "(markers, Python versions), nothing is to fix. Otherwise the lock is "
    "stale or hand-edited; they regenerate it with its tool. Do not "
    f"regenerate or edit the lock for them; {ASK_FIRST}",
    subject_key="PACKAGE",
    since=_SINCE,
)

ENTRIES: Final = (LOCK_ENTRY_MALFORMED, LOCK_ENTRY_UNUSABLE, LOCK_ENTRY_CONFLICT)
