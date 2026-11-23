# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What folding SBOM fragments into one document says, each line after
:data:`~pitloom.messages._fragments.MERGE_PREFIX` and the element it is
about (``ELEMENT=<spdxId>``): two values of one property
(``fragment-conflict``), an id held by another element
(``fragment-id-conflict``), one name with two SHA-256 digests
(``fragment-hash-conflict``) and a value Pitloom generated that a fragment
replaces (``generated-value-conflict``); and the summaries of the fragment
commands.

The values of a conflict are the merged ones: a text in quotes, any other
value as the caller described it
(:class:`~pitloom.messages._field_writers.DescribedValue`), each cut to
:data:`~pitloom.logging_config.EXCERPT_CHARS` characters.

See also: :mod:`pitloom.messages._fragments` (a fragment left out, a
reference to nothing) and :mod:`pitloom.messages._fragments_say` (the
helpers).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._fragments import MERGE_PREFIX
from pitloom.messages._summary import Summary
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
_TOPIC: Final = "fragments"
#: Every merge line's start: the prefix and the element.
_ELEMENT: Final = f"{MERGE_PREFIX}ELEMENT=%(spdx_id)s: "
#: The end of a line that kept one value and dropped another.
_KEPT_DROPPED: Final = "kept %(kept)s, dropped %(dropped)s"
#: The end of a line that kept both elements and renamed the later.
_BOTH_KEPT_RENAMED: Final = "both kept, the later is now %(new_id)s"


def _merge_line(level: str, text: str) -> Line:
    """A line at *level* about one merged element: the prefix, the
    element, then *text*."""
    return Line(level=level, template=f"{_ELEMENT}{text}")


#: Two values of a single-valued property.
PROPERTY_CONFLICT_LINE: Final = _merge_line(
    "WARNING", f"%(property)s differs; {_KEPT_DROPPED}"
)
#: Two values of one key of a dictionary property.
ENTRY_CONFLICT_LINE: Final = _merge_line(
    "WARNING", f"%(property)s key %(entry_key)s differs; {_KEPT_DROPPED}"
)

FRAGMENT_CONFLICT: Final = Message(
    code="fragment-conflict",
    condition="conflict",
    lines=(PROPERTY_CONFLICT_LINE, ENTRY_CONFLICT_LINE),
    summary="Two sources of one merged element state different values for "
    "a property that holds one value, or for one key of a dictionary "
    "property: the project's own element in a project build, or an earlier "
    "fragment in the merge order, against a later fragment. Neither value "
    "is a respelling of the other (the same JSON, or a path ending in the "
    "other).",
    did="Kept the value merged first (the project's, else the earlier "
    "fragment's) and dropped the other: the SBOM states the kept value; the "
    "dropped one is recorded nowhere.",
    effect="thinner",
    actor="user",
    advice="Tell the user the SBOM states the kept value and the dropped "
    "one is not recorded, as the line says. If the kept value is the wrong "
    "one, they fix whichever source is wrong (the project metadata or the "
    f"fragment) and generate again. Do not edit either for them; {ASK_FIRST}",
    subject_key="ELEMENT",
    since=_SINCE,
)

#: An element of another type holds the id.
ID_OTHER_TYPE_LINE: Final = _merge_line(
    "WARNING",
    "id held by a %(holder_type)s, also wanted by a %(element_type)s; "
    f"{_BOTH_KEPT_RENAMED}",
)
#: An element of the same type holds the id, with digests of one algorithm
#: that share no value.
ID_OTHER_CONTENT_LINE: Final = _merge_line(
    "WARNING",
    "id held by two %(element_type)s elements of different %(hash_algorithm)s "
    f"digests; {_BOTH_KEPT_RENAMED}",
)

FRAGMENT_ID_CONFLICT: Final = Message(
    code="fragment-id-conflict",
    condition="conflict",
    lines=(ID_OTHER_TYPE_LINE, ID_OTHER_CONTENT_LINE),
    summary="An element a fragment brings has the spdxId of an element "
    "already merged but is not that element: one of another type holds the "
    "id, or one of the same type whose digests of one algorithm share no "
    "value (two artefacts).",
    did="Kept both: the later element gets a new id in the document's "
    "namespace (the line names it), and every reference to it follows. The "
    "SBOM states both, but the later one's id is not the one its fragment "
    "stated.",
    effect="weaker",
    actor="user",
    advice="Tell the user a fragment reuses the id of another element, as "
    "the line says. They give the fragment's element an id of its own "
    "(write the fragment again against the current base SBOM), so the id "
    f"is stable across runs. Do not edit the fragment for them; {ASK_FIRST}",
    subject_key="ELEMENT",
    since=_SINCE,
)

#: Two elements of one type and name with different SHA-256 digests.
HASH_CONFLICT_LINE: Final = _merge_line(
    "WARNING",
    "a %(element_type)s named %(name)s has SHA-256 %(digest)s, another of "
    "that name %(other_digest)s; both kept",
)

FRAGMENT_HASH_CONFLICT: Final = Message(
    code="fragment-hash-conflict",
    condition="conflict",
    lines=(HASH_CONFLICT_LINE,),
    summary="Two elements of one type in the merged document share a name "
    "but state different SHA-256 digests: two files of one name with "
    "different content, or one artefact whose digest in one source is "
    "stale.",
    did="Kept both as separate elements, each with its own digest.",
    effect="none",
    actor="user",
    advice="Tell the user two elements share a name with different SHA-256 "
    "digests, as the line says. If they are one artefact, one source's "
    "digest is stale and they generate that source again; if they are two, "
    f"nothing needs fixing. Do not edit the sources for them; {ASK_FIRST}",
    subject_key="ELEMENT",
    since=_SINCE,
)

#: A value generated from the model file that a fragment replaces.
GENERATED_REPLACED_LINE: Final = _merge_line(
    "INFO",
    "%(property)s generated from the model file replaced by a fragment's; "
    f"{_KEPT_DROPPED}",
)
#: A base model's name replaced by the one the fragments agree on.
MODEL_NAME_REPLACED_LINE: Final = _merge_line(
    "INFO", f"name replaced by the one the fragments agree on; {_KEPT_DROPPED}"
)
#: A ``not_measured`` provenance entry of a property that now holds a value.
NOT_MEASURED_DROPPED_LINE: Final = _merge_line(
    "INFO",
    "%(property)s now holds a value; dropped its not_measured provenance of "
    "%(provenance_field)s",
)

GENERATED_VALUE_CONFLICT: Final = Message(
    code="generated-value-conflict",
    condition="conflict",
    lines=(
        GENERATED_REPLACED_LINE,
        MODEL_NAME_REPLACED_LINE,
        NOT_MEASURED_DROPPED_LINE,
    ),
    summary="A fragment states a value Pitloom generated itself, and the "
    "fragment's statement wins, by design: in a project build, a base "
    "model's value generated from the model file, or its name, replaced by "
    "the one the fragments agree on; or a merged element now holds a value "
    "its not_measured provenance entry says was not measured.",
    did="Kept the fragment's value and dropped the generated one, or "
    "dropped the not_measured provenance entry that no longer holds; the "
    "SBOM states what the fragments state.",
    effect="none",
    actor="none",
    advice="Nothing to fix: a fragment is how a user states what Pitloom "
    "cannot read, and the line reports the replacement. Mention it only "
    "when the user asks where a value came from.",
    subject_key="ELEMENT",
    since=_SINCE,
)

#: ``loom merge``: the number of fragments merged.
MERGE_MERGED: Final = Summary(
    template="merge: merged %(number)s fragment(s)",
    meaning="'loom merge' wrote the SBOM from this many fragments of the "
    "directory; one it could not merge is not counted (its WARNING line "
    "says why).",
    topic=_TOPIC,
)
#: ``loom fragment validate``: every document passed.
FRAGMENT_VALIDATE_VALID: Final = Summary(
    template="fragment validate: %(number)s document(s) valid",
    meaning="'loom fragment validate' found every document it was given "
    "valid against the SPDX 3 schema and SHACL shapes.",
    topic=_TOPIC,
)
#: ``loom fragment list``: no ``[tool.pitloom.fragment]`` entry.
FRAGMENT_LIST_NONE: Final = Summary(
    template="fragment list: no fragments configured",
    meaning="'loom fragment list' found no [tool.pitloom.fragment] entry in "
    "the project's pyproject.toml (none, or an empty list), so it lists "
    "nothing.",
    topic=_TOPIC,
)
#: ``loom enrich``: how to merge the fragment it wrote.
ENRICH_REGISTER_HINT: Final = Summary(
    template="enrich: register the fragment under [tool.pitloom.fragment] "
    "and re-run 'loom project'/'loom generate' to merge it into a base SBOM",
    meaning="'loom enrich' wrote a fragment, not an SBOM of the project: "
    "to merge it, the user adds it to [tool.pitloom.fragment] and builds "
    "the project's SBOM again.",
    topic=_TOPIC,
)

ENTRIES: Final = (
    FRAGMENT_CONFLICT,
    FRAGMENT_ID_CONFLICT,
    FRAGMENT_HASH_CONFLICT,
    GENERATED_VALUE_CONFLICT,
)

SUMMARIES: Final = (
    MERGE_MERGED,
    FRAGMENT_VALIDATE_VALID,
    FRAGMENT_LIST_NONE,
    ENRICH_REGISTER_HINT,
)
