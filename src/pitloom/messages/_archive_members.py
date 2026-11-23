# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An archive member (of a wheel or an sdist) Pitloom does not list, or
lists under another name: a name with no safe install location
(``archive-member-unsafe``), a member another one overwrites or shadows, or
members that share a project path (``archive-member-conflict``), and a
non-conforming name or a directory entry with data
(``archive-member-invalid``).

A read of a wheel or an sdist leaves such a member out of the SBOM: ``;
not listed``. ``--allow-build`` (its lines after ``Build: ``) does not copy
it out of the wheel it built: ``; not copied``. Neither changes the
archive: an embed rewrites the wheel with every member it had.

See also: :mod:`pitloom.messages._archive_members_say` (the helpers),
:mod:`pitloom.core.archive_member_names` (the reader).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: The outcome of a member a read leaves out of the SBOM.
NOT_LISTED: Final = "not listed"
#: The outcome of a member the ``--allow-build`` route does not extract.
NOT_COPIED: Final = "not copied"
_MEMBER: Final = "ARCHIVE=%(archive)s ENTRY=%(member)s"


def member_lines(text: str) -> tuple[Line, Line]:
    """The two ``WARNING`` lines of a member left out: *text*, then
    :data:`NOT_LISTED` (a read), or :data:`NOT_COPIED` (the build route)."""
    return (
        Line(level="WARNING", template=f"{_MEMBER}: {text}; {NOT_LISTED}"),
        Line(level="WARNING", template=f"{_MEMBER}: {text}; {NOT_COPIED}"),
    )


#: What a member left out does, for each entry's ``did``.
_LEFT_OUT: Final = (
    "Left the member out of the SBOM (not listed); on the --allow-build "
    "route, did not extract it from the built wheel (not copied), so no "
    "file of the SBOM comes from it. The archive is not changed: an embed "
    "rewrites the wheel with every member it had."
)
_NOTHING_TO_DO: Final = (
    "If the archive is theirs, they rebuild it with a conforming build "
    "tool; else they ask whoever published it. Do not repack the archive "
    f"for them; {ASK_FIRST}"
)

UNSAFE_LINE, UNSAFE_COPY_LINE = member_lines("no safe install location")
OUTSIDE_LINE: Final = Line(
    level="WARNING",
    template=f"{_MEMBER}: resolves outside the extraction directory; {NOT_COPIED}",
)

ARCHIVE_MEMBER_UNSAFE: Final = Message(
    code="archive-member-unsafe",
    condition="unsafe",
    lines=(UNSAFE_LINE, UNSAFE_COPY_LINE, OUTSIDE_LINE),
    summary="An archive member's name has no install location an installer "
    "could write it to: absolute (a leading / or a drive such as C:), with a "
    "'..' segment, holding a NUL, or empty once normalised; or, on the "
    "--allow-build route, it resolves outside the directory Pitloom extracts "
    "the built wheel into (a link on the way).",
    did=_LEFT_OUT,
    effect="thinner",
    actor="user",
    advice="Tell the user which member was left out and why, as the line "
    "says: such a name can write outside an install directory, and a "
    f"conforming build tool does not write one. {_NOTHING_TO_DO}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

OVERWRITTEN_LINE, OVERWRITTEN_COPY_LINE = member_lines(
    "overwritten by later entry %(later_member)s"
)
SHADOWED_LINE, SHADOWED_COPY_LINE = member_lines("also a directory of other entries")
SHARED_PATHS_LINE: Final = Line(
    level="WARNING",
    template="ARCHIVE=%(archive)s: members share a project path "
    "(%(project_paths)s); they would share one ID registry key",
)

ARCHIVE_MEMBER_CONFLICT: Final = Message(
    code="archive-member-conflict",
    condition="conflict",
    lines=(
        OVERWRITTEN_LINE,
        OVERWRITTEN_COPY_LINE,
        SHADOWED_LINE,
        SHADOWED_COPY_LINE,
        SHARED_PATHS_LINE,
    ),
    summary="Archive members collide where they install: a later member has "
    "the same install name (read with \\ as a separator, as an installer on "
    "Windows reads it), so an installer extracting in order keeps only the "
    "later one; a file member's name is also a directory of other members, "
    "and no installer can write both; or, in an sdist, members inside and "
    "outside its top directory map to one project path, so they would share "
    "one ID registry key.",
    did=f"{_LEFT_OUT} Members sharing a project path are all listed, under "
    "that path; an ID registry would give them one id.",
    effect="thinner",
    actor="user",
    advice="Tell the user which members collide, as the line says; a "
    f"conforming build tool does not write such an archive. {_NOTHING_TO_DO}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

NORMALISED_LINE: Final = Line(
    level="WARNING",
    template=f"{_MEMBER}: non-conforming name; listed as %(install_name)s",
)
NORMALISED_COPY_LINE: Final = Line(
    level="WARNING",
    template=f"{_MEMBER}: non-conforming name; copied as %(install_name)s",
)
DIRECTORY_DATA_LINE, DIRECTORY_DATA_COPY_LINE = member_lines(
    "directory entry carries data"
)

ARCHIVE_MEMBER_INVALID: Final = Message(
    code="archive-member-invalid",
    condition="invalid",
    lines=(
        NORMALISED_LINE,
        NORMALISED_COPY_LINE,
        DIRECTORY_DATA_LINE,
        DIRECTORY_DATA_COPY_LINE,
    ),
    summary="An archive member is stored under a name that is not its "
    "install name (a backslash separator, an empty or '.' segment, a ./ in a "
    "wheel), so it is listed under the name an installer writes it to; or a "
    "member named as a directory (ending in /) carries bytes, which no "
    "installer writes.",
    did="Listed a non-conforming member under its install name (on the "
    "--allow-build route, copied it there), as the line says. Left a "
    "directory entry's bytes out (not listed, not copied). The archive is "
    "not changed.",
    effect="none",
    actor="user",
    advice="Tell the user what the line says only if they asked about the "
    "archive's members: the SBOM names each file as it installs. "
    f"{_NOTHING_TO_DO}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

ENTRIES: Final = (
    ARCHIVE_MEMBER_UNSAFE,
    ARCHIVE_MEMBER_CONFLICT,
    ARCHIVE_MEMBER_INVALID,
)
