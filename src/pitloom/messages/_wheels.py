# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel Pitloom refuses as a whole, and a wheel whose own ``.dist-info``
directory it cannot tell: an archive or a member that cannot be read
(``wheel-unreadable``), member names no installer can tell apart
(``wheel-invalid``), a wheel an embed cannot rewrite (``wheel-unusable``,
``wheel-unusable/signed``), and no top-level ``.dist-info``, several, or
one the file name does not name (``dist-info-missing``,
``dist-info-ambiguous``, ``dist-info-conflict``).

Every refusal ends ``; wheel refused``. A ``.dist-info`` line is an
``ERROR`` where the command needs the directory (verify, validate, embed),
ending ``; wheel refused``, and a ``WARNING`` where it only names the
package (``loom wheel``, ``generate``), ending ``; identity unknown``.

See also: :mod:`pitloom.messages._wheels_say` (the helpers),
:mod:`pitloom.core.wheel_dist_info` (the reader).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._surface import SURFACE_CLI, SURFACE_LIBRARY
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: The outcome of every refusal.
WHEEL_REFUSED: Final = "wheel refused"
#: The outcome of a ``.dist-info`` line where the read goes on.
IDENTITY_UNKNOWN: Final = "identity unknown"
#: The subject of a line about a wheel as a whole.
_ARCHIVE: Final = "ARCHIVE=%(archive)s"
#: The subject of a line about one member of a wheel.
_MEMBER: Final = "ARCHIVE=%(archive)s ENTRY=%(member)s"

#: What a refusal does.
_REFUSED: Final = (
    "Refused the wheel as a whole: no SBOM is written and no wheel is "
    "changed; the command exits 1 (a batch goes on with the next wheel and "
    "exits 1 at the end), and the library raises WheelRefused, a ValueError "
    "carrying the code. The model scan of a wheel lists no file of it."
)
_REBUILD: Final = (
    "They rebuild the wheel with a conforming build tool, or ask whoever "
    "published it for a good copy, and run again. Do not repair or rename "
    f"the wheel's members for them; {ASK_FIRST}"
)


def _refusal(subject: str, text: str) -> Line:
    """An ``ERROR`` line of *subject*, *text*, then ``; wheel refused``."""
    return Line(level="ERROR", template=f"{subject}: {text}; {WHEEL_REFUSED}")


UNOPENABLE_LINE: Final = _refusal(
    _ARCHIVE, "could not open as a ZIP archive (%(exception_type)s)"
)
MEMBER_UNREADABLE_LINE: Final = _refusal(_MEMBER, "could not read (%(exception_type)s)")

WHEEL_UNREADABLE: Final = Message(
    code="wheel-unreadable",
    condition="unreadable",
    lines=(UNOPENABLE_LINE, MEMBER_UNREADABLE_LINE),
    summary="A wheel could not be read: the file is not a ZIP archive Python "
    "can open (damaged, cut short, another format named .whl, a member name "
    "flagged UTF-8 that is not), or one of its members could not be read "
    "(damaged, encrypted, a compression Python cannot read, a RECORD that "
    "is not UTF-8). The line names the exception's type only, never its "
    "text, which quotes member names.",
    did=_REFUSED,
    effect="not-written",
    actor="user",
    advice=f"Tell the user the wheel is damaged, as the line says. {_REBUILD}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

NUL_NAME_LINE: Final = _refusal(_MEMBER, "NUL in member name")
DUPLICATE_NAME_LINE: Final = _refusal(_MEMBER, "duplicate member name")

WHEEL_INVALID: Final = Message(
    code="wheel-invalid",
    condition="invalid",
    lines=(NUL_NAME_LINE, DUPLICATE_NAME_LINE),
    summary="A wheel's member names do not let an installer tell its files "
    "apart: two members have one name, exactly or once read as an installer "
    "on Windows reads it (a/M and a\\M), or a name holds a NUL, where Python's "
    "zipfile cuts the name, so the member installs under a shorter name that "
    "may be another member's. No reader can tell which member is meant.",
    did=_REFUSED,
    effect="not-written",
    actor="user",
    advice="Tell the user the wheel's member names collide, as the line says; "
    f"a conforming build tool does not write such a wheel. {_REBUILD}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

NON_CONFORMING_LINE: Final = _refusal(
    _MEMBER, ".dist-info member under a non-conforming name"
)

WHEEL_UNUSABLE: Final = Message(
    code="wheel-unusable",
    condition="unusable",
    lines=(NON_CONFORMING_LINE,),
    summary="A wheel to embed an SBOM in stores a member of its own "
    ".dist-info directory under a name that is not its install name (a "
    "backslash, a ./ or an empty segment): the embed rewrites RECORD by "
    "install name, so it could not tell which entry it rewrites. Only an "
    "embed refuses it ('embed-wheel', 'wheel --embed'); a read lists the "
    "member under its install name.",
    did=_REFUSED,
    effect="not-written",
    actor="user",
    advice=f"Tell the user the wheel cannot take an SBOM, as the line says. {_REBUILD}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

#: How each surface lets an embed remove a ``RECORD`` signature (the hook
#: never embeds into a wheel).
ALLOW_SIGNED_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {SURFACE_CLI: "--allow-signed-wheel", SURFACE_LIBRARY: "allow_signed_wheel=True"}
)
SIGNED_LINE: Final = _refusal(
    _MEMBER,
    "signs the RECORD the embed rewrites; %(option)s removes it (re-sign "
    "the wheel after)",
)
SIGNATURE_REMOVED_LINE: Final = Line(
    level="INFO", template=f"{_MEMBER}: signature removed; re-sign the wheel"
)

WHEEL_UNUSABLE_SIGNED: Final = Message(
    code="wheel-unusable/signed",
    condition="unusable",
    lines=(SIGNED_LINE, SIGNATURE_REMOVED_LINE),
    summary="A wheel to embed an SBOM in carries a signature of its RECORD "
    "(RECORD.jws or RECORD.p7s, PEP 427). The embed rewrites RECORD, so the "
    "signature would no longer verify. The ERROR line names "
    "--allow-signed-wheel on the command line, allow_signed_wheel=True in "
    "the library. As an INFO line, it was given and the embed removed the "
    "signature.",
    did="As an ERROR, refused the wheel: no wheel is changed, the command "
    "exits 1 and the library raises WheelRefused, a ValueError carrying the "
    "code. As an INFO line, embedded the SBOM, rewrote RECORD and removed "
    "the signature: the wheel is unsigned.",
    effect="not-written",
    actor="user",
    advice="Tell the user the wheel is signed and an embed would break the "
    "signature, as the line says. Only with their say: run again with "
    "--allow-signed-wheel, which removes the signature, then they re-sign "
    "the wheel with their own key; after an INFO line, they re-sign it "
    "before publishing. Do not pass --allow-signed-wheel or sign for them; "
    f"{ASK_FIRST}",
    subject_key="ARCHIVE",
    since=_SINCE,
)


def _dist_info_lines(text: str) -> tuple[Line, Line]:
    """The ``ERROR`` line of a ``.dist-info`` problem *text*, ending ``;
    wheel refused``, and its ``WARNING`` line, ending ``; identity
    unknown``."""
    return (
        _refusal(_ARCHIVE, text),
        Line(level="WARNING", template=f"{_ARCHIVE}: {text}; {IDENTITY_UNKNOWN}"),
    )


#: What a ``.dist-info`` line's outcome means, for each entry's ``did``.
_DIST_INFO_DID: Final = (
    "As an ERROR (verify-wheel, validate-wheel, embed-wheel, wheel --embed), "
    "refused the wheel: nothing is written or changed, the command exits 1 "
    "and the library raises WheelRefused, a ValueError carrying the code. "
    "As a WARNING (loom wheel, generate of a wheel), wrote the SBOM with the "
    "wheel's files and no name, version or other METADATA of the package "
    "(named unknown)."
)
_DIST_INFO_ADVICE: Final = (
    "They rebuild the wheel with a conforming build tool, or rename the "
    "file to the PEP 427 name of its own .dist-info directory, and run "
    f"again. Do not rename or repack the wheel for them; {ASK_FIRST}"
)

NO_DIST_INFO_LINE, NO_DIST_INFO_WARNING_LINE = _dist_info_lines(
    "no top-level .dist-info directory"
)
METADATA_MISSING_LINE: Final = Line(
    level="WARNING", template=f"{_MEMBER}: not in the wheel; {IDENTITY_UNKNOWN}"
)

DIST_INFO_MISSING: Final = Message(
    code="dist-info-missing",
    condition="missing",
    lines=(NO_DIST_INFO_LINE, NO_DIST_INFO_WARNING_LINE, METADATA_MISSING_LINE),
    summary="A wheel has no top-level .dist-info directory (one vendored "
    "under a package is never the wheel's own), or its own .dist-info has no "
    "METADATA member (the line names the member looked for). A conforming "
    "wheel has both.",
    did=_DIST_INFO_DID,
    effect="thinner",
    actor="user",
    advice="Tell the user the wheel lacks the metadata a wheel must carry, as "
    f"the line says. {_DIST_INFO_ADVICE}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

SEVERAL_MATCH_LINE, SEVERAL_MATCH_WARNING_LINE = _dist_info_lines(
    "several top-level .dist-info directories match the file name"
)
NOT_A_WHEEL_NAME_LINE, NOT_A_WHEEL_NAME_WARNING_LINE = _dist_info_lines(
    "the file name is not a wheel name and several top-level .dist-info "
    "directories exist"
)
SEVERAL_NONE_MATCH_LINE, SEVERAL_NONE_MATCH_WARNING_LINE = _dist_info_lines(
    "several top-level .dist-info directories, none the one the file name names"
)

DIST_INFO_AMBIGUOUS: Final = Message(
    code="dist-info-ambiguous",
    condition="ambiguous",
    lines=(
        SEVERAL_MATCH_LINE,
        SEVERAL_MATCH_WARNING_LINE,
        NOT_A_WHEEL_NAME_LINE,
        NOT_A_WHEEL_NAME_WARNING_LINE,
        SEVERAL_NONE_MATCH_LINE,
        SEVERAL_NONE_MATCH_WARNING_LINE,
    ),
    summary="A wheel has several top-level .dist-info directories and its "
    "file name does not pick one: several match the name and version it "
    "names (PEP 503 names, PEP 440 versions), the file name is not a PEP "
    "427 wheel name, or none matches it. Pitloom does not guess which is the "
    "wheel's own.",
    did=_DIST_INFO_DID,
    effect="thinner",
    actor="user",
    advice="Tell the user Pitloom cannot tell the wheel's own .dist-info, as "
    f"the line says. {_DIST_INFO_ADVICE}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

OTHER_DIST_INFO_LINE: Final = Line(
    level="WARNING",
    template=f"{_ARCHIVE}: the file name names no top-level .dist-info; using "
    "%(member)s",
)

DIST_INFO_CONFLICT: Final = Message(
    code="dist-info-conflict",
    condition="conflict",
    lines=(OTHER_DIST_INFO_LINE,),
    summary="A wheel's PEP 427 file name names a package and version whose "
    ".dist-info directory the wheel does not hold; it holds exactly one "
    "other top-level .dist-info, which Pitloom reads as the wheel's own (a "
    "renamed file, or a wheel built under another name).",
    did="Read the one .dist-info the line names as the wheel's own; the "
    "command goes on and its exit status does not change.",
    effect="weaker",
    actor="user",
    advice="Tell the user the file name and the wheel's metadata disagree, as "
    "the line says. If the file was renamed, they give it back its PEP 427 "
    f"name; else they rebuild the wheel. Do not rename it for them; {ASK_FIRST}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

ENTRIES: Final = (
    WHEEL_UNREADABLE,
    WHEEL_INVALID,
    WHEEL_UNUSABLE,
    WHEEL_UNUSABLE_SIGNED,
    DIST_INFO_MISSING,
    DIST_INFO_AMBIGUOUS,
    DIST_INFO_CONFLICT,
)
