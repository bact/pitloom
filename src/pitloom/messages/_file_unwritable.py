# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A file Pitloom could not write: ``file-unwritable``. The system refused
the write (no write permission, a read-only file system, a full disk, a
directory where the file should be).

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
#: the command (``loom id generate``, ``loom id import``).
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
    "be). Today the ID registry file, written 'for the ID registry'.",
    did="Wrote the file through a temporary file beside it, so it keeps its "
    "old content when the write fails; where the directory refuses a "
    "temporary file, the file is written in place and a failure (a full "
    "disk) can leave it part-written. As an ERROR ('loom id generate', "
    "'loom id import'), the command exits 1. As a WARNING "
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

ENTRIES: Final = (FILE_UNWRITABLE,)
