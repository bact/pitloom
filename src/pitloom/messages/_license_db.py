# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""LicenseID's licence database, which matching a licence text needs:
``license-db-missing`` (not built) and ``license-db-unusable`` (there but
not usable, or no home directory to look in). ``licenseid database`` is the
literal subject of both.

See also: :mod:`pitloom.messages._license_say` (the helpers) and
:mod:`pitloom.extract._license_text_match` (the detection).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: The literal subject of every line.
_SUBJECT: Final = "licenseid database"
#: What every line says was skipped.
_SKIPPED: Final = "licence text detection skipped"
#: What a skipped detection leaves in the SBOM.
_NOT_MATCHED: Final = (
    "Skipped licence text detection: a licence file or text is recorded as "
    "text, not matched to an SPDX id."
)

_MISSING: Final = (
    f"{_SUBJECT} not found: %(path)s; {_SKIPPED}; run "
    "'licenseid update --source packaged'"
)
#: A licence is stated: only the licence-file second opinion is lost.
DB_MISSING_INFO_LINE: Final = Line(level="INFO", template=_MISSING)
#: No licence is stated, or only the database can read the stated one.
DB_MISSING_LINE: Final = Line(level="WARNING", template=_MISSING)

LICENSE_DB_MISSING: Final = Message(
    code="license-db-missing",
    condition="missing",
    lines=(DB_MISSING_INFO_LINE, DB_MISSING_LINE),
    summary="LicenseID's licence database is not built at the path it looks "
    "in (~/.local/share/licenseid/licenses.db). Matching a licence text to "
    "an SPDX id needs it; reading a declared expression does not. INFO when "
    "the package states a licence (only the licence-file second opinion is "
    "lost), WARNING when it states none or states a licence text, which only "
    "the database can read.",
    did=f"{_NOT_MATCHED} A stated licence is recorded as stated. Said once "
    "per process at each level; every later lookup looks for the database "
    "again.",
    effect="thinner",
    actor="user",
    advice="Tell the user that licence texts were not matched to SPDX ids "
    "because LicenseID's database is not built. They build it once with "
    "'licenseid update --source packaged' (offline: the licence list "
    "packaged with LicenseID) and generate again; loom has no --db option. "
    f"Do not run the command for them; {ASK_FIRST}",
    since=_SINCE,
)

#: The database is there but not usable, or there is no home directory.
DB_UNUSABLE_LINE: Final = Line(
    level="WARNING",
    template=f"{_SUBJECT} cannot be used: %(failure)s; {_SKIPPED}",
)

LICENSE_DB_UNUSABLE: Final = Message(
    code="license-db-unusable",
    condition="unusable",
    lines=(DB_UNUSABLE_LINE,),
    summary="LicenseID's licence database cannot be used: it is empty, "
    "invalid or unreadable, or LicenseID finds no home directory to look in "
    "(HOME, or USERPROFILE on Windows, set to nothing, or no home for the "
    "account). The detail is LicenseID's; its 'pass --db' is an option of "
    "the licenseid command, not of loom.",
    did=f"{_NOT_MATCHED} Said once per process; every later lookup tries the "
    "database again.",
    effect="thinner",
    actor="user",
    advice="Tell the user that licence texts were not matched to SPDX ids, "
    "with LicenseID's reason as the line gives it. With no home directory, "
    "they set HOME (USERPROFILE on Windows) to the account's home "
    "directory; loom has no --db option. An empty or invalid database they "
    "rebuild with 'licenseid update --source packaged --force'; an "
    "unreadable one is a file permission they fix. Do not run commands or "
    f"change the environment for them; {ASK_FIRST}",
    since=_SINCE,
)

ENTRIES: Final = (LICENSE_DB_MISSING, LICENSE_DB_UNUSABLE)
