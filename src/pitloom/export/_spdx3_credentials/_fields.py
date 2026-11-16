# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The fields the credential check reads and how
(:mod:`pitloom.export._spdx3_credentials`): the SPDX 3 field tables, the
detector's reading of each, and the separators and escapes of Pitloom's JSON
statements and provenance comment.

See also: :mod:`pitloom.export._spdx3_credentials._find` (the walk that
reads them) and :mod:`pitloom.export._spdx3_credentials._check` (the check).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pitloom.core.provenance import escape_provenance_comment_part

__all__ = [
    "ENTRY_SEPARATOR",
    "FIELD_SEPARATOR",
    "FIELD_UNESCAPES",
    "IDENTIFIER_READING",
    "JSON_CONTENT_TYPE",
    "NOTE_READING",
    "NOTE_SEPARATOR",
    "NOT_READ",
    "PITLOOM_SCHEMA_PREFIX",
    "PROVENANCE_COMMENT_PREFIX",
    "PROVENANCE_SCHEMA",
    "REFERENCE_FIELDS",
    "SOURCE_UNESCAPES",
    "UNESCAPE_RE",
    "URL_FIELDS",
    "URL_READING",
    "Reading",
]


@dataclass(frozen=True)
class Reading:
    """How the detector reads a field
    (:func:`~pitloom.core.url_masking.find_url_credentials`)."""

    scp: bool = True
    account: bool = True
    embedded: bool = False
    #: A string Pitloom wrote through
    #: :func:`~pitloom.core.provenance.sanitize_provenance_text`, which
    #: writes a format character as ``\uXXXX``: read with each such
    #: escape turned back into the character a reader of the original saw
    #: (``?to\u200bken=`` is ``?token=`` to a client that drops it).
    escaped: bool = False


#: An identifier Pitloom or a merged document stores: read for a URL or a
#: token anywhere in it, at each percent-decode depth (an id minted from a
#: name encodes it). An ``ssh`` or ``git`` account name alone (``git@``) is
#: weak, as in a URL field: a model named ``ssh://git@github.com/o/m``
#: names no credential. (The ID registry's key and id read it so too; its
#: namespace refuses it.)
IDENTIFIER_READING: Final = Reading(embedded=True)
#: A URL field of an SBOM.
URL_READING: Final = Reading()

#: Each reference field of the SPDX 3.0.1 model (an ``ObjectProp``: an
#: element, agent, tool, creation information or other object), read as an
#: id when it holds one (an IRI or a blank node) rather than the object
#: inline: a merged or given SBOM can name an IRI no element defines, which
#: is written as it stands. A drift test keeps the list whole.
REFERENCE_FIELDS: Final = frozenset(
    {
        *("ai_energyConsumption", "ai_finetuningEnergyConsumption"),
        *("ai_hyperparameter", "ai_inferenceEnergyConsumption", "ai_metric"),
        *("ai_metricDecisionThreshold", "ai_trainingEnergyConsumption"),
        *("build_configSourceDigest", "build_environment", "build_parameter"),
        *("createdBy", "createdUsing", "creationInfo", "dataLicense"),
        *("dataset_sensor", "definingArtifact", "element"),
        *("expandedlicensing_member", "expandedlicensing_subjectAddition"),
        "expandedlicensing_subjectExtendableLicense",
        *("expandedlicensing_subjectLicense", "extension"),
        *("extension_cdxProperty", "externalIdentifier", "externalRef", "from"),
        *("import", "namespaceMap", "originatedBy", "rootElement"),
        *("security_assessedElement", "simplelicensing_customIdToUri"),
        *("software_byteRange", "software_contentIdentifier"),
        *("software_lineRange", "software_snippetFromFile", "subject"),
        *("suppliedBy", "to", "verifiedUsing"),
    }
)

#: Each field read, by compact JSON-LD name, wherever it stands in an
#: element (a nested ``ExternalRef`` or ``NamespaceMap`` included), and how;
#: a reference field (:data:`REFERENCE_FIELDS`) is read when it holds a
#: string, the object inline is walked.
#: ``identifier`` is read whatever its ``externalIdentifierType``: a model's
#: DOI is ``other``, and no CPE, SWID, gitoid, SWHID, email address or
#: advisory id is a URL holding a credential as a whole value.
URL_FIELDS: Final[dict[str, Reading]] = {
    "spdxId": IDENTIFIER_READING,
    "@id": IDENTIFIER_READING,
    "externalSpdxId": IDENTIFIER_READING,
    "namespace": IDENTIFIER_READING,
    # A location hint may be a file path such as ``meet-10:30@ab:c.json``.
    "locationHint": Reading(scp=False),
    "software_downloadLocation": URL_READING,
    "software_homePage": URL_READING,
    "software_packageUrl": URL_READING,
    "software_contentIdentifierValue": URL_READING,
    "locator": URL_READING,
    "identifierLocator": URL_READING,
    "identifier": URL_READING,
    "expandedlicensing_seeAlso": URL_READING,
    "build_configSourceUri": URL_READING,
    "build_buildType": URL_READING,
    "security_locator": URL_READING,
    **dict.fromkeys(sorted(REFERENCE_FIELDS), IDENTIFIER_READING),
}

#: The ``anyURI`` fields of the SPDX 3.0.1 model not read, each with why.
#: Every ``anyURI`` field is in :data:`URL_FIELDS` or here (a drift test).
NOT_READ: Final[dict[str, str]] = {}

#: How every ``schema`` of a JSON statement Pitloom writes starts
#: (:mod:`pitloom.assemble.spdx3.provenance`,
#: :class:`pitloom.assemble.spdx3._provenance_encoders.PitloomV1Encoder`; a
#: test keeps them under it). A statement of another schema is not read.
PITLOOM_SCHEMA_PREFIX: Final = "https://pitloom.dev/"
JSON_CONTENT_TYPE: Final = "application/json"
#: Pitloom's field provenance statement, whose notes are joined
#: (:data:`NOTE_SEPARATOR`).
PROVENANCE_SCHEMA: Final = "https://pitloom.dev/provenance/fields/1"
#: A string of Pitloom's statement or provenance comment is read as a URL
#: field: a dependency's direct reference (``foo @ https://h/x``) is stated
#: whole in a note, a model's ``source_url`` in its artifact metadata.
NOTE_READING: Final = Reading(escaped=True)
#: How :func:`pitloom.core.provenance.parse_provenance_value` joins notes.
NOTE_SEPARATOR: Final = " | "

#: How Pitloom's provenance comment line starts
#: (:data:`pitloom.assemble.spdx3.provenance.PROVENANCE_COMMENT_PREFIX`; not
#: imported, since ``assemble`` imports this package; a test keeps the two
#: equal). A comment line that does not start with it is prose, never read.
PROVENANCE_COMMENT_PREFIX: Final = "Metadata provenance: "
#: How that line joins its ``field: source`` entries, and each field to its
#: source (:func:`pitloom.assemble.spdx3.provenance.provenance_comment_line`).
ENTRY_SEPARATOR: Final = "; "
FIELD_SEPARATOR: Final = ": "
#: The writer's escapes
#: (:func:`pitloom.core.provenance.escape_provenance_comment_part`), each
#: mapped back to its character: a ``;``, CR or LF in a source, and a ``:``
#: in a field name too, is written escaped, so each separator above and
#: each line break is the writer's own.
SOURCE_UNESCAPES: Final = {
    escape_provenance_comment_part(char): char for char in ";\r\n"
}
FIELD_UNESCAPES: Final = {
    escape_provenance_comment_part(char, field=True): char for char in ";\r\n:"
}
UNESCAPE_RE: Final = re.compile("|".join(map(re.escape, FIELD_UNESCAPES)))
