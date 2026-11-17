# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A lock file Pitloom reads no pins from, or reads with a doubt: one that
does not parse or lacks its top-level shape (``lock-file-malformed``), one
of another format or version (``lock-file-wrong-format``), one with no
entry for this project (``lock-file-unusable``), and two locks of which the
fixed order keeps one (``lock-file-conflict``).

The code goes by where the fault is: the file as a whole, a top-level key
or the project's own entry here; one package entry, one dependency
reference or one ``requirements.txt`` line in
:mod:`pitloom.messages._lock_entry`. A lock the system does not read, or
whose bytes are not in the encoding its format requires, says
``file-unreadable`` (``/not-utf8``) ``for dependency pins``; one over the
size cap ``over-cap``; an absent one nothing.

Every line names the lock by its file name (``FILE=uv.lock``): locks are
read at the project root only. No line has a frame or a prefix.

See also: :mod:`pitloom.messages._lock_say` (the helpers that say them),
:mod:`pitloom.messages.lock_files` (the public names),
:mod:`pitloom.extract.lock` (the readers).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"

#: What a line ends in when the next lock in the order is tried.
NOT_READ: Final = "no pins read from it"
#: The order Pitloom tries lock files in, for an advice.
LOCK_ORDER: Final = (
    "pylock.toml, uv.lock, poetry.lock, pdm.lock, Pipfile.lock, then a "
    "requirements.txt that pins every line"
)
#: Which runs read lock files.
LOCK_SURFACES: Final = (
    "loom project, loom generate on a project directory, loom enrich "
    "--project-dir, the library's generate_project_sbom and enrich_model, "
    "and a Git URL's checkout (never the build hook, loom wheel, loom env or "
    "an sdist)"
)


def _warning(text: str) -> Line:
    """A ``WARNING`` line naming the lock file, then *text*."""
    return Line(level="WARNING", template=f"FILE=%(file)s: {text}")


#: The file parses, but its top level is not an object (a TOML or JSON
#: array, a scalar).
TOP_LEVEL_LINE: Final = _warning(
    f"top-level value is %(value_type)s, expected an object; {NOT_READ}"
)
#: The file does not parse (``tomllib``'s or ``json``'s error, with its
#: position).
PARSE_LINE: Final = _warning(f"does not parse: %(failure)s; {NOT_READ}")
#: A top-level key the format needs is missing.
TOP_KEY_MISSING_LINE: Final = _warning(f"top-level %(lock_key)s missing; {NOT_READ}")
#: A top-level key that is not a list.
TOP_KEY_LIST_LINE: Final = _warning(
    f"top-level %(lock_key)s is %(value_type)s, expected a list; {NOT_READ}"
)
#: A top-level key that is not a table.
TOP_KEY_TABLE_LINE: Final = _warning(
    f"top-level %(lock_key)s is %(value_type)s, expected a table; {NOT_READ}"
)
#: A top-level key that is not a non-empty string.
TOP_KEY_TEXT_LINE: Final = _warning(
    f"top-level %(lock_key)s is %(value_type)s, expected a non-empty string; {NOT_READ}"
)
#: A top-level list of group names that is not one: no default group.
TOP_GROUPS_LINE: Final = _warning(
    "top-level %(lock_key)s is %(value_type)s, expected a list of strings; "
    "read as empty"
)
#: The project's own entry holds a key of the wrong shape.
ROOT_KEY_LINE: Final = _warning(
    "the project's own entry: %(lock_key)s is %(value_type)s, expected a "
    f"list; {NOT_READ}"
)

LOCK_FILE_MALFORMED: Final = Message(
    code="lock-file-malformed",
    condition="malformed",
    lines=(
        TOP_LEVEL_LINE,
        PARSE_LINE,
        TOP_KEY_MISSING_LINE,
        TOP_KEY_LIST_LINE,
        TOP_KEY_TABLE_LINE,
        TOP_KEY_TEXT_LINE,
        TOP_GROUPS_LINE,
        ROOT_KEY_LINE,
    ),
    summary="A lock file was read and decoded, but does not parse, or lacks "
    "the shape its format has at the top level or in the project's own "
    "entry: a key missing, or of the wrong type. Most often a hand edit, a "
    "merge of two versions, or a lock written by a tool's version Pitloom "
    "does not know.",
    did=f"Said by {LOCK_SURFACES}. Read no pins from the lock and tried the "
    "next lock in the order; with none, the SBOM lists the declared "
    "dependencies without lock pins. A pylock.toml whose default-groups is "
    "malformed is read with no default group. The SBOM is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user which lock file is malformed and what is wrong, "
    "as the line says, and that its pins are not in the SBOM. They "
    "regenerate it with its tool ('uv lock', 'poetry lock', 'pdm lock', "
    f"'pipenv lock') and run again; Pitloom tries locks in the order "
    f"{LOCK_ORDER}. Do not regenerate or edit the lock for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: No format marker (or one of the wrong type): not a lock of this format.
FORMAT_MARKER_LINE: Final = _warning(
    f"format marker %(lock_key)s missing or of the wrong type; {NOT_READ}"
)
#: A ``lock-version`` that is not ``major.minor``.
VERSION_SHAPE_LINE: Final = _warning(
    f"%(lock_key)s %(lock_value)s is not a major.minor version; {NOT_READ}"
)
#: A ``lock-version`` of a major version Pitloom does not read.
VERSION_MAJOR_LINE: Final = _warning(
    "%(lock_key)s %(lock_value)s is a major version Pitloom does not read "
    f"(it reads %(number)s); {NOT_READ}"
)
#: A ``lock-version`` of a newer minor version: read anyway.
VERSION_MINOR_LINE: Final = _warning(
    "%(lock_key)s %(lock_value)s is newer than the version Pitloom reads; "
    "read; newer keys not read"
)

LOCK_FILE_WRONG_FORMAT: Final = Message(
    code="lock-file-wrong-format",
    condition="wrong-format",
    lines=(
        FORMAT_MARKER_LINE,
        VERSION_SHAPE_LINE,
        VERSION_MAJOR_LINE,
        VERSION_MINOR_LINE,
    ),
    summary="A file named as a lock is not a lock of its format (no format "
    "marker, or one of the wrong type), or states a format version Pitloom "
    "does not read: not a major.minor version, or another major version. A "
    "newer minor version of pylock.toml is read anyway, since PEP 751 minor "
    "versions only add keys; the keys it adds are not read.",
    did=f"Said by {LOCK_SURFACES}. Read no pins from the lock and tried the "
    "next lock in the order; a newer minor version is read, its new keys "
    "left out. The SBOM is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user which lock file cannot be read and the version or "
    "marker the line names; what helps depends on it. No marker: the file "
    "is not a lock of that format (another tool's file of the same name, or "
    "a hand edit); they regenerate it with its tool. Another major version: "
    "the lock comes from a tool newer than Pitloom reads; a newer Pitloom "
    "may read it. A newer minor version: read, nothing to fix; a newer "
    "Pitloom reads its new keys. Not a major.minor version: most often a "
    "hand edit; they regenerate it. Do not regenerate the lock or upgrade "
    f"anything for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: A ``uv.lock`` with no editable or virtual entry.
NO_ROOT_LINE: Final = _warning(
    f"no entry for the project (no editable or virtual source); {NOT_READ}"
)
#: Workspace entries, none named as the project.
NO_MATCH_LINE: Final = _warning(
    f"workspace entries: %(number)s, none named %(package)s; {NOT_READ}"
)
#: Several workspace entries, and no project name to choose one.
NO_NAME_LINE: Final = _warning(
    f"workspace entries: %(number)s, no project name to choose one; {NOT_READ}"
)

LOCK_FILE_UNUSABLE: Final = Message(
    code="lock-file-unusable",
    condition="unusable",
    lines=(NO_ROOT_LINE, NO_MATCH_LINE, NO_NAME_LINE),
    summary="A well-formed uv.lock holds no entry Pitloom can tell is this "
    "project's own: no editable or virtual entry, or a workspace's entries "
    "of which none has the project's name, or several and no name to "
    "choose by. Taking another member's entry would credit its "
    "dependencies to this project.",
    did=f"Said by {LOCK_SURFACES}. Read no pins from the lock and tried the "
    "next lock in the order. The SBOM is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user that the lock holds no entry for this project, as "
    "the line says. In a workspace they run Pitloom on the member's own "
    "directory, or give the project a name in pyproject.toml that the lock "
    "holds; a lock from before the project was renamed is regenerated with "
    f"'uv lock'. Do not edit the project or the lock for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: A lock read while reading pyproject.toml, and a higher one found after.
LOCK_CONFLICT_LINE: Final = Line(
    level="WARNING",
    template="two lock files hold resolved dependencies; kept %(kept)s, "
    "dropped %(dropped)s",
)

LOCK_FILE_CONFLICT: Final = Message(
    code="lock-file-conflict",
    condition="conflict",
    lines=(LOCK_CONFLICT_LINE,),
    summary="Two lock files hold the project's resolved dependencies: a "
    "poetry.lock read with pyproject.toml, and a lock earlier in the fixed "
    f"order ({LOCK_ORDER}) found after it. Two locks where the first one "
    "tried applies say nothing.",
    did=f"Said by {LOCK_SURFACES}. Kept the pins of the lock earlier in the "
    "order; the other lock's pins are not recorded, and the provenance "
    "notes which lock it supersedes. The SBOM is written.",
    effect="none",
    actor="user",
    advice="Tell the user which lock the SBOM states and which is not "
    "recorded, as the line names them: the SBOM states the kept lock's "
    "pins; the dropped lock's pins are not recorded. If both locks are "
    "meant, one is stale; they remove it or regenerate both. Do not delete "
    f"or regenerate a lock for them; {ASK_FIRST}",
    since=_SINCE,
)

ENTRIES: Final = (
    LOCK_FILE_MALFORMED,
    LOCK_FILE_WRONG_FORMAT,
    LOCK_FILE_UNUSABLE,
    LOCK_FILE_CONFLICT,
)
