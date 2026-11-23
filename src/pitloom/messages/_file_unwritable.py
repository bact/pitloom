# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A file Pitloom could not write: ``file-unwritable``. The system refused
the write (no write permission, a read-only file system, a full disk, a
directory where the file should be): an ID registry file, a wheel an embed
rewrites, the ``-o`` copy of an embedded SBOM. A wheel an embed rewrote
whose file mode could not be set back is ``file-unwritable/mode``.

See also: :mod:`pitloom.messages._file_unreadable` (a file Pitloom could not
read), :mod:`pitloom.messages._registry_save` (an ID registry save, the one
writer that says it today).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._registry_file import SAVE_SURFACES
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"

#: A file written for a purpose of the closed table, where the write ends
#: the command (``loom id generate``, ``loom id import``, an embed).
WRITE_ERROR_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: could not write %(use)s; %(failure)s"
)
#: The same, where the run's own output is already built (a run saving the
#: ids it added to an ID registry).
WRITE_LINE: Final = Line(level="WARNING", template=WRITE_ERROR_LINE.template)

FILE_UNWRITABLE: Final = Message(
    code="file-unwritable",
    condition="unwritable",
    lines=(WRITE_ERROR_LINE, WRITE_LINE),
    summary="A file Pitloom writes could not be written: the operating "
    "system refused it (no write permission on the file or its directory, a "
    "read-only file system, a full disk, a directory where the file should "
    "be). The ID registry file, written 'for the ID registry'; a wheel an "
    "embed rewrites with its SBOM, or the '-o' copy of that SBOM, written "
    "'for the SBOM'.",
    did="Tried to write an ID registry file through a temporary file "
    "beside it, so a "
    "failed write leaves its old content; where the directory refuses a "
    "temporary file, the file is written in place and a failure (a full "
    "disk) can leave it part-written. A wheel is written as a new file "
    "beside it, put in its place once complete: a refused write leaves the "
    "wheel as it was; the '-o' copy is written in place, after the wheel. "
    "As an ERROR ('loom id generate', 'loom id import', "
    "'loom embed-wheel', 'loom wheel --embed'), the command exits 1 (an "
    "embed-wheel batch goes on with its other wheels). As a WARNING "
    f"({SAVE_SURFACES}, saving the ids a run added after its SBOM is "
    "built), the SBOM stands and the ids are not saved: the next run mints "
    "them again.",
    effect="none",
    actor="user",
    advice="Tell the user which file could not be written and what the "
    "system reported, as the line says. They give the account Pitloom runs "
    "as write access to the file and its directory, or free disk space, and "
    "run again. Do not change permissions or ownership, or delete files, for "
    f"them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: A wheel an embed rewrote whose file mode could not be set back.
MODE_NOT_RESTORED_LINE: Final = Line(
    level="WARNING", template="FILE=%(file)s: file mode not restored; %(failure)s"
)

FILE_UNWRITABLE_MODE: Final = Message(
    code="file-unwritable/mode",
    condition="unwritable",
    lines=(MODE_NOT_RESTORED_LINE,),
    summary="An embed wrote the wheel with its SBOM through a new file put "
    "in place of the old one, then could not give it the old file's mode "
    "(its permission bits): the operating system refused (a file system "
    "without POSIX modes, a file owned by another account).",
    did="Kept the new wheel, SBOM embedded, with the mode a new file gets "
    "(the umask's); the exit status does not change.",
    effect="none",
    actor="user",
    advice="Tell the user the wheel's permissions changed, as the line says, "
    "if they rely on them (an executable bit, a group's access). They set "
    f"the mode again. Do not change permissions for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

ENTRIES: Final = (FILE_UNWRITABLE, FILE_UNWRITABLE_MODE)
