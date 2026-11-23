# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An SBOM embedded in a wheel (PEP 770, ``.dist-info/sboms/``) or to be
embedded: none there (``wheel-sbom-missing``), several and none named
(``wheel-sbom-ambiguous``), a name without its format's recommended
extension (``wheel-sbom-wrong-format``), a check that could not be made
(``wheel-sbom-unusable``), an SBOM whose subject is not the wheel's
(``wheel-sbom-conflict``) or another SBOM an embed keeps or removes
(``wheel-sbom-conflict/held``); an entry dated before a ZIP archive can
record (``datetime-not-recordable``); and the build hook's SBOM named like
an ``sbom-files`` entry (``sbom-name-conflict``). Also the summaries of
``verify-wheel`` and ``validate-wheel``.

``verify-wheel`` is structural (where the SBOM is, its name, its subject);
``validate-wheel`` checks its content (``sbom-invalid``, page "Targets").

See also: :mod:`pitloom.messages._wheel_sboms_say` (the helpers),
:mod:`pitloom._sbom_format` (the cross-check),
:mod:`pitloom._wheel_sbom_location` (finding the SBOM).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._summary import Summary
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
_TOPIC: Final = "wheel-sboms"
_ARCHIVE: Final = "ARCHIVE=%(archive)s"
_MEMBER: Final = "ARCHIVE=%(archive)s ENTRY=%(member)s"
_SBOMS: Final = ".dist-info/sboms/"

NO_SBOM_LINE: Final = Line(
    level="ERROR", template=f"{_ARCHIVE}: no SBOM under {_SBOMS}"
)
NO_NAMED_SBOM_LINE: Final = Line(
    level="ERROR",
    template=f"{_ARCHIVE}: no SBOM under {_SBOMS} named %(sbom_filename)s",
)

WHEEL_SBOM_MISSING: Final = Message(
    code="wheel-sbom-missing",
    condition="missing",
    lines=(NO_SBOM_LINE, NO_NAMED_SBOM_LINE),
    summary="A wheel to verify or validate has no SBOM under its own "
    ".dist-info/sboms/ (PEP 770), or none of the file name given as "
    "--sbom-filename. Only a direct child of sboms/ is an embedded SBOM.",
    did="Reported the wheel as failed (STATUS=failed); a batch goes on with "
    "the next wheel and the command exits 1.",
    effect="none",
    actor="user",
    advice="Tell the user the wheel carries no SBOM where PEP 770 puts it, "
    "as the line says. They embed one ('loom embed-wheel', 'loom wheel "
    "--embed', or the build hook) and check again, or give the right "
    f"--sbom-filename. Do not embed for them; {ASK_FIRST}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

SEVERAL_SBOMS_LINE: Final = Line(
    level="ERROR",
    template=f"{_ARCHIVE}: %(number)s SBOMs under {_SBOMS} (%(members)s); pass "
    "--sbom-filename",
)

WHEEL_SBOM_AMBIGUOUS: Final = Message(
    code="wheel-sbom-ambiguous",
    condition="ambiguous",
    lines=(SEVERAL_SBOMS_LINE,),
    summary="A wheel holds several SBOMs under its own .dist-info/sboms/ "
    "(PEP 770 allows any number) and the command was not told which one to "
    "check.",
    did="Checked none of them: the wheel is reported failed and the command "
    "exits 1; the library (find_embedded_sbom) raises ValueError carrying "
    "the code.",
    effect="none",
    actor="caller",
    advice="The caller may run again with --sbom-filename naming one of the "
    "files the line lists, once for each SBOM to check.",
    subject_key="ARCHIVE",
    since=_SINCE,
)

WRONG_EXTENSION_LINE: Final = Line(
    level="WARNING",
    template=f"{_MEMBER}: SBOM does not end in %(extension)s, its format's "
    "recommended extension",
)

WHEEL_SBOM_WRONG_FORMAT: Final = Message(
    code="wheel-sbom-wrong-format",
    condition="wrong-format",
    lines=(WRONG_EXTENSION_LINE,),
    summary="An SBOM embedded in a wheel is in a format Pitloom recognises "
    "(SPDX 3 JSON-LD) but its file name does not end in that format's "
    "recommended extension (.spdx3.json), which tools that look for an SBOM "
    "by name go by.",
    did="Verified the rest; the wheel's status and the exit status do not change.",
    effect="none",
    actor="user",
    advice="Tell the user the embedded SBOM's name lacks its recommended "
    "extension, as the line says. They embed it again under a name ending "
    "in that extension (embed-wheel --sbom-basename), if tools that read it "
    f"need one. Do not re-embed for them; {ASK_FIRST}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

UNKNOWN_FORMAT_LINE: Final = Line(
    level="WARNING",
    template=f"{_MEMBER}: SBOM format not recognised; extension not checked",
)
NO_VALIDATOR_LINE: Final = Line(
    level="WARNING",
    template=f"{_MEMBER}: no validator for the SBOM's format; not validated",
)


def unchecked_line(part: str, why: str) -> Line:
    """The ``WARNING`` line of a cross-check not made: ``SBOM <part> not
    cross-checked: <why>``."""
    return Line(
        level="WARNING", template=f"{_ARCHIVE}: SBOM {part} not cross-checked: {why}"
    )


_BOTH: Final = "name and version"
_PART: Final = "%(identity_part)s"
NO_WHEEL_IDENTITY_LINE: Final = unchecked_line(
    _BOTH, "the wheel's METADATA states neither"
)
WHEEL_PART_MISSING_LINE: Final = unchecked_line(
    _PART, "the wheel's METADATA states none"
)
SBOM_PART_MISSING_LINE: Final = unchecked_line(_PART, "the SBOM's subject states none")
BOTH_PART_MISSING_LINE: Final = unchecked_line(
    _PART, "neither the wheel's METADATA nor the SBOM's subject states one"
)
WHEEL_VERSION_INVALID_LINE: Final = unchecked_line(
    "version",
    "the wheel's METADATA version %(wheel_value)s is not a PEP 440 version",
)
SBOM_VERSION_INVALID_LINE: Final = unchecked_line(
    "version", "the SBOM's version %(sbom_value)s is not a PEP 440 version"
)
NOT_SPDX3_LINE: Final = unchecked_line(_BOTH, "the SBOM is not SPDX 3 JSON-LD")
NO_DOCUMENT_LINE: Final = unchecked_line(_BOTH, "the SBOM has no SpdxDocument")
NO_DOCUMENT_ROOT_LINE: Final = unchecked_line(
    _BOTH, "the SpdxDocument has no usable rootElement"
)
NO_SBOM_ROOT_LINE: Final = unchecked_line(
    _BOTH, "the software_Sbom has no usable rootElement"
)
SUBJECT_NOT_PACKAGE_LINE: Final = unchecked_line(
    _BOTH, "the SBOM's subject is of type %(sbom_value)s, not a package"
)

WHEEL_SBOM_UNUSABLE: Final = Message(
    code="wheel-sbom-unusable",
    condition="unusable",
    lines=(
        UNKNOWN_FORMAT_LINE,
        NO_VALIDATOR_LINE,
        NO_WHEEL_IDENTITY_LINE,
        WHEEL_PART_MISSING_LINE,
        SBOM_PART_MISSING_LINE,
        BOTH_PART_MISSING_LINE,
        WHEEL_VERSION_INVALID_LINE,
        SBOM_VERSION_INVALID_LINE,
        NOT_SPDX3_LINE,
        NO_DOCUMENT_LINE,
        NO_DOCUMENT_ROOT_LINE,
        NO_SBOM_ROOT_LINE,
        SUBJECT_NOT_PACKAGE_LINE,
    ),
    summary="A check of an embedded SBOM, or of one given to embed, could "
    "not be made: its format is not one Pitloom recognises (only SPDX 3 "
    "JSON-LD is; a CycloneDX file is not), so its extension is not checked "
    "or no validator runs; or its subject's name and version cannot be "
    "compared with the wheel's METADATA (PEP 503 names, PEP 440 versions): "
    "a side states none, a version is not a PEP 440 version, or the SBOM "
    "has no SpdxDocument whose rootElement leads (through a software_Sbom) "
    "to a software_Package or ai_AIPackage. Only the first rootElement is "
    "followed.",
    did="Skipped that check, never counting it as a mismatch: verify-wheel "
    "and embed-wheel go on, validate-wheel reports the wheel as skipped "
    "(STATUS=skipped), and no exit status changes.",
    effect="weaker",
    actor="user",
    advice="Tell the user which check was not made and why, as the line "
    "says; the wheel and its SBOM may still disagree. If the SBOM is "
    "theirs, they regenerate it in SPDX 3 JSON-LD with the package as its "
    f"subject. Do not edit the SBOM for them; {ASK_FIRST}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

MISMATCH_TEXT: Final = (
    f"{_ARCHIVE}: SBOM {_PART} %(sbom_value)s differs from the wheel's "
    "METADATA %(wheel_value)s"
)
MISMATCH_LINE: Final = Line(level="WARNING", template=MISMATCH_TEXT)
MISMATCH_ERROR_LINE: Final = Line(level="ERROR", template=MISMATCH_TEXT)

WHEEL_SBOM_CONFLICT: Final = Message(
    code="wheel-sbom-conflict",
    condition="conflict",
    lines=(MISMATCH_LINE, MISMATCH_ERROR_LINE),
    summary="An SBOM embedded in a wheel, or given to embed (embed-wheel "
    "--sbom), names a subject whose name or version differs from the "
    "wheel's own METADATA, compared as the ecosystem compares them (PEP 503 "
    "names, PEP 440 versions): an SBOM of another package or release. One "
    "line per part that differs.",
    did="As a WARNING (verify-wheel; embed-wheel with --allow-mismatch), "
    "went on: the status and exit status do not change. As an ERROR "
    "(verify-wheel --fail-on-mismatch: the wheel is reported failed and the "
    "command exits 1; embed-wheel --sbom: nothing is written, the command "
    "exits 1 and the library raises ValueError carrying the code).",
    effect="weaker",
    actor="user",
    advice="Tell the user the SBOM is not of this wheel, as the line says. "
    "They regenerate the SBOM for this wheel (or embed the right one) and "
    "run again; in CI, verify-wheel --fail-on-mismatch keeps a mismatch "
    "from passing. Do not pass --allow-mismatch or regenerate the SBOM for "
    f"them; {ASK_FIRST}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

KEPT_LINE: Final = Line(
    level="WARNING",
    template=f"{_MEMBER}: a Pitloom SBOM, not a build or analyzed one of this "
    "wheel's name and version; kept",
)
REMOVED_LINE: Final = Line(
    level="INFO", template=f"{_MEMBER}: an earlier Pitloom SBOM of this wheel; removed"
)

WHEEL_SBOM_CONFLICT_HELD: Final = Message(
    code="wheel-sbom-conflict/held",
    condition="conflict",
    lines=(KEPT_LINE, REMOVED_LINE),
    summary="An embed found another Pitloom SBOM already under the wheel's "
    ".dist-info/sboms/. One of type build or analyzed for the wheel's own "
    "name and version is the one the new embed supersedes; any other (a "
    "design or source SBOM, or one of another release) was shipped on "
    "purpose.",
    did="The INFO line: removed the earlier SBOM from the rewritten wheel "
    "(and from RECORD). The WARNING: kept the other SBOM beside the new "
    "one; the wheel now holds both.",
    effect="none",
    actor="user",
    advice="Tell the user, after a WARNING only, that the wheel holds another "
    "SBOM, as the line says; if it is stale, they remove it and embed "
    "again. After the INFO line there is nothing to do. Do not remove an "
    f"SBOM for them; {ASK_FIRST}",
    subject_key="ARCHIVE",
    since=_SINCE,
)

FLOORED_LINE: Final = Line(
    level="INFO",
    template=f"{_ARCHIVE}: SBOM entry dated 1980-01-01, the earliest a ZIP "
    "archive can record; the SBOM's created keeps the true date",
)

DATETIME_NOT_RECORDABLE: Final = Message(
    code="datetime-not-recordable",
    condition="not-recordable",
    lines=(FLOORED_LINE,),
    summary="The SBOM's creation time (--creation-datetime, else "
    "SOURCE_DATE_EPOCH) is before 1980, which a ZIP archive cannot record "
    "as a member's date (SOURCE_DATE_EPOCH=0 is the usual case).",
    did="Dated the embedded SBOM's ZIP entry 1980-01-01; the SBOM's own "
    "created keeps the date given, so the wheel is still reproducible.",
    effect="none",
    actor="none",
    advice="The line says why the entry's date and the SBOM's created "
    "differ; mention it only when the user asks about the dates.",
    subject_key="ARCHIVE",
    since=_SINCE,
)

NAME_CLASH_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: also the name, ignoring case, of sbom-files entry "
    "%(path)s; set another sbom-basename in [tool.pitloom] or drop the entry",
)

SBOM_NAME_CONFLICT: Final = Message(
    code="sbom-name-conflict",
    condition="conflict",
    lines=(NAME_CLASH_LINE,),
    summary="The build hook's SBOM file name is also, ignoring letter case, "
    "the name of an SBOM Hatchling already places under .dist-info/sboms/ "
    "(an sbom-files entry, often a 'loom project' output of the same "
    "default name): one would overwrite the other, on a case-insensitive "
    "file system too.",
    did="Wrote nothing: the build hook fails the build.",
    effect="not-written",
    actor="user",
    advice="Tell the user the two SBOM names collide, as the line says. They "
    "set [tool.pitloom] sbom-basename to another name, or drop the "
    "sbom-files entry, and build again. Do not edit the configuration for "
    f"them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: ``loom verify-wheel``: every wheel passed.
VERIFY_WHEEL_OK: Final = Summary(
    template="verify-wheel: %(number)s wheel(s) OK",
    meaning="loom verify-wheel found every wheel's SBOM where PEP 770 puts "
    "it; the WARNING lines before it, if any, say what else it found.",
    topic=_TOPIC,
)
#: ``loom validate-wheel``: every wheel's SBOM valid.
VALIDATE_WHEEL_VALID: Final = Summary(
    template="validate-wheel: %(number)s wheel(s) valid",
    meaning="loom validate-wheel found every wheel's embedded SBOM valid "
    "(schema and SHACL).",
    topic=_TOPIC,
)
#: ``loom validate-wheel``: some wheels' SBOMs in a format with no validator.
VALIDATE_WHEEL_SKIPPED: Final = Summary(
    template="validate-wheel: %(number)s wheel(s) valid, %(skipped)s skipped "
    "(no validator for their format)",
    meaning="loom validate-wheel found no invalid SBOM, but could not "
    "validate some, their format having no validator (a wheel-sbom-unusable "
    "WARNING names each).",
    topic=_TOPIC,
)

ENTRIES: Final = (
    WHEEL_SBOM_MISSING,
    WHEEL_SBOM_AMBIGUOUS,
    WHEEL_SBOM_WRONG_FORMAT,
    WHEEL_SBOM_UNUSABLE,
    WHEEL_SBOM_CONFLICT,
    WHEEL_SBOM_CONFLICT_HELD,
    DATETIME_NOT_RECORDABLE,
    SBOM_NAME_CONFLICT,
)

SUMMARIES: Final = (VERIFY_WHEEL_OK, VALIDATE_WHEEL_VALID, VALIDATE_WHEEL_SKIPPED)
