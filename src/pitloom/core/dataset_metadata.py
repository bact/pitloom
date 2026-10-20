# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Format-neutral dataset metadata dataclasses.

These classes are the format-neutral internal representation of dataset
metadata. They have no dependency on any SBOM library, making them easy
to test and to consume from any serializer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Package comment for a dataset whose source lists several licences.
#: Argument: the source (``dataset card``, ``Croissant file``, ...).
SEVERAL_LICENCES_COMMENT = (
    "The %s lists several licences; it does not say whether they combine as AND or OR."
)


#: Text that fills a field without stating anything (compared in lower
#: case). ``NONE`` is not one: for a licence it is a statement.
_PLACEHOLDERS = frozenset({"unknown", "noassertion", "n/a"})


def is_placeholder(text: str) -> bool:
    """Whether *text* is ``unknown``, ``NOASSERTION`` or ``N/A`` (any case),
    a value that is not a claim."""
    return text.strip().casefold() in _PLACEHOLDERS


#: A field set and copied only together with the one it follows, from the
#: same source: :class:`DatasetMetadata` field -> its follower.
FOLLOWER_FIELDS: dict[str, str] = {"license": "further_licenses"}


@dataclass(frozen=True)
class FurtherLicences:
    """The licences a source lists after the first, in its order."""

    #: Each licence text, none repeating the first or another.
    texts: tuple[str, ...]
    #: The source that lists them, as :data:`SEVERAL_LICENCES_COMMENT`
    #: names it.
    lister: str

    @property
    def comment(self) -> str:
        """The note that the source does not say how the licences combine."""
        return SEVERAL_LICENCES_COMMENT % self.lister


@dataclass
# pylint: disable=too-many-instance-attributes
class DatasetMetadata:
    """Metadata describing a dataset.

    Fields align with the SPDX 3.0 Dataset profile where applicable.
    See: https://spdx.github.io/spdx-spec/v3.0/model/Dataset/Classes/DatasetPackage/

    Also draws on the Croissant RAI extension for responsible AI fields.
    See: https://docs.mlcommons.org/croissant/docs/croissant-rai-spec.html

    Attributes:
        name: Dataset name (required).
        version: Dataset version string.
        description: Human-readable description.
        download_url: URL where the dataset can be obtained.
            Maps to SPDX 3: ``software_downloadLocation``.
        license: SPDX license expression or license URL; of a source
            listing several, the first.
        further_licenses: The licences the same source lists after
            :attr:`license`; set and copied only together with it.
        keywords: Topic keywords.
        creator: Name of the individual or organisation that created the dataset.
        dataset_types: Dataset modality/type strings matching SPDX
            ``dataset_DatasetType`` enum names (e.g. ``["text", "numeric"]``).
            Valid values: ``audio``, ``categorical``, ``graph``, ``image``,
            ``numeric``, ``other``, ``sensor``, ``structured``, ``syntactic``,
            ``text``, ``timeseries``, ``timestamp``, ``video``.
            Maps to SPDX 3: ``dataset_datasetType``.
        dataset_size: Number of records or items.
            Maps to SPDX 3: ``dataset_datasetSize``.
        data_collection_process: Free-text description of how data was collected.
            Maps to SPDX 3: ``dataset_dataCollectionProcess``.
        data_preprocessing: List of preprocessing steps applied.
            Maps to SPDX 3: ``dataset_dataPreprocessing``.
        known_bias: Known biases present in the dataset.
            Maps to SPDX 3: ``dataset_knownBias``.
        intended_use: Description of intended use cases.
            Maps to SPDX 3: ``dataset_intendedUse``.
        has_sensitive_personal_information: One of ``"yes"``, ``"no"``,
            ``"noAssertion"``, or ``None`` when unknown.
            Maps to SPDX 3: ``dataset_hasSensitivePersonalInformation``
            (``PresenceType`` enum).
        anonymization_methods: Anonymisation techniques applied.
            Maps to SPDX 3: ``dataset_anonymizationMethodUsed``.
        croissant_url: URL of the Croissant JSON-LD metadata document.
            Stored as an ``ExternalRef`` in the SPDX element when present.
        provenance: Field-level provenance, keyed by field name.
    """

    name: str

    version: str | None = None
    description: str | None = None
    download_url: str | None = None
    license: str | None = None
    further_licenses: FurtherLicences | None = None
    keywords: list[str] = field(default_factory=list)
    creator: str | None = None

    # SPDX Dataset profile fields
    dataset_types: list[str] = field(default_factory=list)
    dataset_size: int | None = None
    data_collection_process: str | None = None
    data_preprocessing: list[str] = field(default_factory=list)
    known_bias: list[str] = field(default_factory=list)
    intended_use: str | None = None

    # "yes", "no", "noAssertion", or None (maps to PresenceType enum)
    has_sensitive_personal_information: str | None = None
    anonymization_methods: list[str] = field(default_factory=list)

    # URL of the Croissant JSON-LD source document; emitted as ExternalRef.
    croissant_url: str | None = None

    # Provenance tracking: field name -> source description
    provenance: dict[str, str] = field(default_factory=dict)


@dataclass
class DatasetReference:
    """A dataset linked to an AI model with a typed role.

    ``role`` is a provisional name, revised with the provenance taxonomy
    (roadmap: "Provenance and enrichment vocabulary"). It maps to an SPDX 3
    ``RelationshipType`` where supported.
    ``"trainedOn"`` and ``"testedOn"`` map directly to the corresponding
    SPDX 3.0.1 relationship types.  Other roles (``"finetunedOn"``,
    ``"validatedOn"``, ``"pretrainedOn"``) fall back to
    ``RelationshipType.other`` with a comment, pending SPDX 3.1 support.

    Attributes:
        role: Semantic role string.  Recognised values: ``"trainedOn"``,
            ``"testedOn"``, ``"finetunedOn"``, ``"validatedOn"``,
            ``"pretrainedOn"``.  Any other value falls back to ``other``.
        metadata: Extracted dataset metadata.
    """

    role: str
    metadata: DatasetMetadata


__all__ = [
    "FOLLOWER_FIELDS",
    "SEVERAL_LICENCES_COMMENT",
    "DatasetMetadata",
    "DatasetReference",
    "FurtherLicences",
    "is_placeholder",
]
