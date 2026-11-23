# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An SBOM fragment Pitloom was to merge and did not, and what a merge that
needed it does then: a fragment that could not be read
(``fragment-unreadable``), is not one Pitloom can merge
(``fragment-invalid``) or is the document being built
(``fragment-unusable``); a merge left without a fragment it needed
(``fragment-missing``); a configured digest the fragment's bytes do not
have (``fragment-digest-invalid``); and an element the merged document
names but does not hold (``reference-not-found``).

Each ``WARNING`` about one fragment has two lines that differ only in their
outcome: ``not merged``, or, for a fragment marked ``required = true``,
that the merge will fail (it then raises ``fragment-missing``). A fragment
is named as configured (``[tool.pitloom.fragment]``), or, for ``loom
merge``, by the directory as given joined with its file name.

See also: :mod:`pitloom.messages._fragments_merge` (what folding fragments
together says), :mod:`pitloom.messages._fragments_say` (the helpers) and
:mod:`pitloom.messages._input_not_found` (``input-not-found/fragment``,
which shares the outcomes).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: The outcome of a fragment left out of the merge.
NOT_MERGED: Final = "not merged"
#: The outcome of a required fragment left out: the merge raises
#: ``fragment-missing`` after the last fragment.
MERGE_WILL_FAIL: Final = "required, so the merge will fail"
#: Where a fragment line's advice sends a reader for what to do next.
_EACH_WARNING: Final = "fix each as its WARNING says"


def fragment_lines(text: str) -> tuple[Line, Line]:
    """The two ``WARNING`` lines of a fragment left out: ``FILE=<file>: ``,
    *text*, then :data:`NOT_MERGED`, or :data:`MERGE_WILL_FAIL` for a
    required one."""
    return (
        Line(level="WARNING", template=f"FILE=%(file)s: {text}; {NOT_MERGED}"),
        Line(level="WARNING", template=f"FILE=%(file)s: {text}; {MERGE_WILL_FAIL}"),
    )


#: What a merge without the fragment does, for each entry's ``did``.
_LEFT_OUT: Final = (
    "Merged the SBOM without it and wrote it (the build hook builds the "
    "wheel). For a fragment marked required = true (the line says so), the "
    "merge then fails with fragment-missing and no SBOM is written. 'loom "
    "fragment list' lists the fragment, and exits 1 for a required one."
)

UNREADABLE_LINE, REQUIRED_UNREADABLE_LINE = fragment_lines(
    "SBOM fragment could not be read (%(failure)s)"
)

FRAGMENT_UNREADABLE: Final = Message(
    code="fragment-unreadable",
    condition="unreadable",
    lines=(UNREADABLE_LINE, REQUIRED_UNREADABLE_LINE),
    summary="An SBOM fragment Pitloom was to merge (one configured under "
    "[tool.pitloom.fragment], or a *.json file of the directory 'loom merge' "
    "reads) is there but could not be read: the operating system refused "
    "it (no read permission, a directory where a file was expected, an I/O "
    "error). 'loom fragment list' says the same of a configured fragment.",
    did=_LEFT_OUT,
    effect="thinner",
    actor="user",
    advice="Tell the user which fragment could not be read and why, as the "
    "line says. They fix its permissions or its path and run again. Do not "
    f"change permissions or the configuration for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

NOT_JSON_LINE, REQUIRED_NOT_JSON_LINE = fragment_lines(
    "SBOM fragment is not valid JSON (%(failure)s)"
)
NOT_SPDX_LINE, REQUIRED_NOT_SPDX_LINE = fragment_lines(
    "SBOM fragment is not SPDX 3 JSON-LD Pitloom can merge (%(failure)s)"
)

FRAGMENT_INVALID: Final = Message(
    code="fragment-invalid",
    condition="invalid",
    lines=(
        NOT_JSON_LINE,
        REQUIRED_NOT_JSON_LINE,
        NOT_SPDX_LINE,
        REQUIRED_NOT_SPDX_LINE,
    ),
    summary="An SBOM fragment was read but is not one Pitloom can merge. "
    "Not valid JSON: a syntax error, bytes that are not UTF-8, UTF-16 or "
    "UTF-32, or nesting too deep to parse. Not SPDX 3 JSON-LD Pitloom can "
    "merge: JSON the SPDX 3.0.1 bindings do not read (not an object, an "
    "unknown property or type, a value of the wrong type), or a number with "
    "no RFC 8785 spelling (an integer beyond +-(2**53 - 1), a number past "
    "a double), which the merged document could not be written with.",
    did=_LEFT_OUT,
    effect="thinner",
    actor="user",
    advice="Tell the user which fragment is not usable and why, as the line "
    "says. They fix the fragment or write it again (run the enrichment that "
    "wrote it); for a configured fragment, 'loom fragment list' reads it as "
    "the merge does, so they can check it before the next build. Do not "
    f"edit the fragment for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

SAME_DOCUMENT_LINE, REQUIRED_SAME_DOCUMENT_LINE = fragment_lines(
    "SBOM fragment is the document being merged into (%(spdx_id)s)"
)

FRAGMENT_UNUSABLE: Final = Message(
    code="fragment-unusable",
    condition="unusable",
    lines=(SAME_DOCUMENT_LINE, REQUIRED_SAME_DOCUMENT_LINE),
    summary="A configured SBOM fragment is the document Pitloom is "
    "building: its SpdxDocument has the id the project's own SBOM gets, so "
    "it is an earlier SBOM of the same project, not a fragment written to "
    "enrich it. Merging it would fold the project into itself.",
    did=_LEFT_OUT,
    effect="thinner",
    actor="user",
    advice="Tell the user the configured path names an SBOM of the project "
    "itself, as the line says. They point the entry at the fragment the "
    "enrichment wrote, not at a generated SBOM of the project, and run "
    f"again. Do not edit the configuration for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: Required fragments left out of a project's merge.
REQUIRED_MISSING_LINE: Final = Line(
    level="ERROR",
    template="%(number)s required SBOM fragment(s) not merged: %(files)s; "
    f"{_EACH_WARNING}",
)
#: ``loom merge`` (:func:`pitloom.assemble.generate_merged_sbom`) of a
#: directory none of whose fragments could be merged.
NONE_MERGED_LINE: Final = Line(
    level="ERROR",
    template=f"no SBOM fragment in %(path)s could be merged; {_EACH_WARNING}",
)

FRAGMENT_MISSING: Final = Message(
    code="fragment-missing",
    condition="missing",
    lines=(REQUIRED_MISSING_LINE, NONE_MERGED_LINE),
    summary="A merge went without a fragment it needed: configured "
    "fragments marked required = true were not merged (not found, not "
    "readable, not mergeable, or the project's own document), or 'loom "
    "merge' merged none of the *.json files of its directory. A WARNING "
    "line before it names each fragment and why.",
    did="Wrote nothing: no SBOM is written, the command exits 1 (the "
    "Action step fails), the build hook fails the build, and the library "
    "raises pitloom.assemble.FragmentMergeError (a ValueError) carrying the "
    "code.",
    effect="not-written",
    actor="user",
    advice="Tell the user which fragments were not merged, as the line "
    "names them, and why, as each one's WARNING says. They fix each "
    "fragment as that WARNING advises, or, for a required fragment no "
    "longer wanted, remove its entry or its required = true, and run "
    f"again. Do not edit the fragments or the configuration for them; {ASK_FIRST}",
    since=_SINCE,
)

#: A configured fragment whose bytes do not have its configured SHA-256.
DIGEST_MISMATCH_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: SHA-256 %(measured)s does not match the "
    "configured %(declared)s",
)

FRAGMENT_DIGEST_INVALID: Final = Message(
    code="fragment-digest-invalid",
    condition="invalid",
    lines=(DIGEST_MISMATCH_LINE,),
    summary="The bytes of a configured SBOM fragment do not have the "
    "SHA-256 its sha256 setting in [tool.pitloom.fragment] states: the "
    "file changed after the digest was configured, or the digest is of "
    "another file. Only 'loom fragment list' checks it; the merge does not.",
    did="Listed the fragment with SHA256=mismatch; the listing goes on, and "
    "its exit status does not change.",
    effect="none",
    actor="user",
    advice="Tell the user the fragment's bytes differ from the configured "
    "digest, as the line says. If the change is expected, they set sha256 "
    "to the new value; else they restore the fragment that was pinned. Do "
    f"not change the setting or the file for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: The prefix of every line said while fragments are folded together
#: (:mod:`pitloom.messages._fragments_merge`).
MERGE_PREFIX: Final = "Merge: "
#: What a reader does about a reference to nothing.
_REGENERATE: Final = "regenerate the base SBOM, then run the enrichment again"

#: One reference to an element the merged document does not hold.
REFERENCE_LINE: Final = Line(
    level="WARNING",
    template=f"{MERGE_PREFIX}ELEMENT=%(spdx_id)s: %(property)s names "
    f"%(reference)s, which is not in the merged document; {_REGENERATE}",
)
#: The merge that left one or more of them.
REFERENCES_LINE: Final = Line(
    level="ERROR",
    template="%(number)s reference(s) to elements not in the merged "
    f"document; {_REGENERATE}",
)

REFERENCE_NOT_FOUND: Final = Message(
    code="reference-not-found",
    condition="not-found",
    lines=(REFERENCE_LINE, REFERENCES_LINE),
    summary="After the fragments merged, an element of the merged document "
    "names an element that is neither in it nor declared external (an "
    "import of its SpdxDocument): a relationship's from or to, an "
    "annotation's subject, a collection's rootElement, or a licence "
    "expression's customIdToUri in the document's own namespace. Usually a "
    "fragment written against an older SBOM of the project, whose element "
    "ids have changed since (a Pitloom upgrade, a change to the project's "
    "files or name), or one naming an element a fragment left out was to "
    "supply.",
    did="Said each reference as a WARNING, then wrote nothing: no SBOM is "
    "written, the command exits 1, the build hook fails the build and the "
    "library raises pitloom.assemble.FragmentMergeError carrying the code.",
    effect="not-written",
    actor="user",
    advice="Tell the user which references name nothing, as the WARNING "
    "lines say. They regenerate the base SBOM, run the enrichment again "
    "against it, and merge again; the same merge run again fails the same "
    "way. Do not write or change an ID registry to make the ids match, and "
    f"do not edit the fragments for them; {ASK_FIRST}",
    subject_key="ELEMENT",
    since=_SINCE,
)

#: A merged document no fragment gives a creation time to.
NO_CREATED_LINE: Final = Line(
    level="WARNING",
    template=f"{MERGE_PREFIX}no fragment states a creation time; created set "
    "to %(datetime)s",
)

DATETIME_MISSING: Final = Message(
    code="datetime-missing",
    condition="missing",
    lines=(NO_CREATED_LINE,),
    summary="'loom merge' (pitloom.assemble.generate_merged_sbom) dates the "
    "merged SBOM by SOURCE_DATE_EPOCH, else by the latest created of the "
    "fragments' creation info, never by the clock. Neither was there: "
    "SOURCE_DATE_EPOCH is not set and every fragment merged states no "
    "creation info (an empty @graph, or a file holding []).",
    did="Wrote the SBOM with created set to the date the line names, the "
    "start of 1970, which says nothing of when it was made.",
    effect="weaker",
    actor="user",
    advice="Tell the user the merged SBOM's creation time is a placeholder, "
    "as the line says. They state created in a fragment's CreationInfo (the "
    "enrichment that writes it does), or set SOURCE_DATE_EPOCH for the "
    "merge, and merge again. Do not edit the fragments or set the "
    f"environment for them; {ASK_FIRST}",
    since=_SINCE,
)

ENTRIES: Final = (
    FRAGMENT_UNREADABLE,
    FRAGMENT_INVALID,
    FRAGMENT_UNUSABLE,
    FRAGMENT_MISSING,
    FRAGMENT_DIGEST_INVALID,
    REFERENCE_NOT_FOUND,
    DATETIME_MISSING,
)
