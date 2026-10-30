# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A file Pitloom could not read and a directory it could not list:
``file-unreadable``, its variants ``file-unreadable/not-utf8`` and
``file-unreadable/outside-project``, and ``dir-unlistable``. A file or
directory that is absent is none of them: absent data is quiet.

The codes equal the evidence reasons of the same names
(:data:`pitloom.core.evidence.REASON_CODES`), which stay literals there, as
``over-cap`` does; ``tests/messages/test_drift_sources.py`` holds them equal.

See also: :mod:`pitloom.messages._file_unreadable_warning` (the helpers
every site warns through) and :data:`pitloom.messages._fields.READ_USES`
(what a file is read for).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The end of every advice an agent relays without acting on it.
_ASK: Final = "ask first, and with nobody to ask, report it only."
#: What every line ends in when the content is outside the project.
_OUTSIDE: Final = "outside the project directory"

#: A file read for a purpose of the closed table.
FILE_LINE: Final = Line(
    level="WARNING", template="FILE=%(file)s: could not read %(use)s; %(failure)s"
)
#: A file a project setting lists, read for that setting.
FIELD_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: could not read for %(field)s; %(failure)s",
)
#: A model candidate whose header could not be read to confirm its format.
HEADER_LINE: Final = Line(
    level="WARNING",
    template="FORMAT=%(format)s FILE=%(file)s: could not read header; %(failure)s",
)

FILE_UNREADABLE: Final = Message(
    code="file-unreadable",
    condition="unreadable",
    lines=(FILE_LINE, FIELD_LINE, HEADER_LINE),
    summary="A file Pitloom found or was named could not be read: the "
    "operating system refused it (no read permission, a directory above it "
    "without search permission, a file another program holds open on "
    "Windows) or the read failed (an I/O error, a file that is no regular "
    "file once opened).",
    did="Read nothing more of it and went on without what it holds, as the "
    "line says what it was read for: a file scan leaves the file out of the "
    "SBOM (loom embed-wheel keeps it, with the wheel's own hash); a hash "
    "leaves no verifiedUsing (a model's ID registry lookup is then not gated; "
    "a dataset's provenance says Evidence: not_measured | Reason: "
    "file-unreadable); a project setting's field is not set from the file; "
    "the usage scan records no model reference from it; ID registry indexing "
    "leaves it out of the index; no dependency pins are read from a lock "
    "file; a model whose header could not be read is not listed as an AI "
    "model.",
    effect="thinner",
    actor="user",
    advice="Tell the user which file could not be read and what the system "
    "reported, as the line says. They give the account Pitloom runs as read "
    "access to it (or close the program that holds it), or restore a damaged "
    "copy, and generate again. Do not change permissions or ownership, or "
    f"copy, move or replace the file, for them; {_ASK}",
    subject_key="FILE",
)

FILE_UNREADABLE_NOT_UTF8: Final = Message(
    code="file-unreadable/not-utf8",
    condition="unreadable",
    lines=(
        Line(
            level="WARNING",
            template="FILE=%(file)s: could not read %(use)s; not UTF-8: %(failure)s",
        ),
        Line(
            level="WARNING",
            template="FILE=%(file)s: could not read for %(field)s; not UTF-8: "
            "%(failure)s",
        ),
    ),
    summary="A text file Pitloom read is not UTF-8, the encoding it must be "
    "in: a requirements file or a file a setup.cfg directive lists, or a "
    "Python file read for the model usage scan.",
    did="Went on without what the file holds: the field is not set from it, "
    "or the usage scan records no model reference from it.",
    effect="thinner",
    actor="user",
    advice="Tell the user which file is not UTF-8 and what the decoder "
    "reported, as the line says. They save it as UTF-8 and generate again. Do "
    f"not convert, edit or replace the file for them; {_ASK}",
    subject_key="FILE",
)

FILE_UNREADABLE_OUTSIDE: Final = Message(
    code="file-unreadable/outside-project",
    condition="unreadable",
    lines=(
        Line(
            level="WARNING",
            template=f"FILE=%(file)s: could not read %(use)s; {_OUTSIDE}",
        ),
        Line(
            level="WARNING",
            template=f"FILE=%(file)s: could not read for %(field)s; {_OUTSIDE}",
        ),
    ),
    summary="A file a project setting names, or a licence file, leads outside "
    "the project directory (a .. or absolute path, or a symbolic link out), "
    "and Pitloom reads no file outside it: its content is no part of the "
    "project. For an installed dependency, the directory is its .dist-info.",
    did="Did not read it and went on without what it holds: the field is not "
    "set from it, or its licence text and copyright notices are not used.",
    effect="thinner",
    actor="user",
    advice="Tell the user which file lies outside the project and which "
    "setting or licence file names it, as the line says. They move or copy "
    "the file into the project, or point the setting at a file inside it, "
    "and generate again; for an installed dependency, only its maintainers "
    "can fix it. Do not move, copy or link files, or edit the setting, for "
    f"them; {_ASK}",
    subject_key="FILE",
)

DIR_UNLISTABLE: Final = Message(
    code="dir-unlistable",
    condition="unlistable",
    lines=(
        Line(
            level="WARNING",
            template="DIR=%(dir)s: could not list %(use)s; %(failure)s",
        ),
    ),
    summary="A directory could not be listed (no read or search permission): "
    "the files under it were not seen.",
    did="Went on without them: file discovery leaves them out of the SBOM (a "
    "build backend that lists before it excludes can name a directory it "
    "would leave out anyway); a dataset directory gets no hash (Evidence: "
    "not_measured | Reason: dir-unlistable); ID registry indexing leaves them "
    "out of the index.",
    effect="thinner",
    actor="user",
    advice="Tell the user which directory could not be listed and what the "
    "system reported, as the line says. They give the account Pitloom runs "
    "as read and search access to it and generate again. Do not change "
    f"permissions or ownership, or copy or move files, for them; {_ASK}",
    subject_key="DIR",
)

ENTRIES: Final = (
    FILE_UNREADABLE,
    FILE_UNREADABLE_NOT_UTF8,
    FILE_UNREADABLE_OUTSIDE,
    DIR_UNLISTABLE,
)
