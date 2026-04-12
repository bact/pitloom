# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dataset package and relationship creation for SPDX 3 SBOM documents."""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter

# Mapping from DatasetReference.role strings to SPDX 3.0.1 RelationshipType.
# finetunedOn, validatedOn, pretrainedOn do not exist in SPDX 3.0.1;
# they fall back to RelationshipType.other with a comment (see _role_to_rel).
_ROLE_TO_RELATIONSHIP: dict[str, str] = {
    "trainedOn": spdx3.RelationshipType.trainedOn,
    "testedOn": spdx3.RelationshipType.testedOn,
}

# PresenceType mapping for has_sensitive_personal_information.
_PRESENCE_MAP: dict[str, str] = {
    "yes": spdx3.PresenceType.yes,
    "no": spdx3.PresenceType.no,
    "noAssertion": spdx3.PresenceType.noAssertion,
}


def _role_to_rel(role: str) -> tuple[str, str | None]:
    """Return the SPDX RelationshipType and optional fallback comment for *role*.

    Returns:
        A 2-tuple of ``(relationship_type_str, comment_or_None)``.  ``comment``
        is non-``None`` only when *role* has no direct SPDX 3.0.1 equivalent
        and ``RelationshipType.other`` is used as a stand-in.
    """
    rel_type = _ROLE_TO_RELATIONSHIP.get(role)
    if rel_type is not None:
        return rel_type, None
    return (
        spdx3.RelationshipType.other,
        f"Intended relationship role '{role}' is not available in SPDX 3.0.1; "
        f"upgrade to SPDX 3.1 for native support.",
    )


def _build_dataset_package(
    meta: DatasetMetadata,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> spdx3.dataset_DatasetPackage:
    """Build a ``dataset_DatasetPackage`` SPDX 3 element from a
    :class:`~pitloom.core.dataset_metadata.DatasetMetadata`.

    Field mapping:

    **Core identification**

    - ``name`` → ``name``
    - ``version`` → ``software_packageVersion``
    - ``description`` → ``description``
    - ``download_url`` → ``software_downloadLocation``

    **Dataset profile**

    - ``dataset_types`` → ``dataset_datasetType`` (list of enum values)
    - ``dataset_size`` → ``dataset_datasetSize``
    - ``data_collection_process`` → ``dataset_dataCollectionProcess``
    - ``data_preprocessing`` → ``dataset_dataPreprocessing``
    - ``known_bias`` → ``dataset_knownBias``
    - ``intended_use`` → ``dataset_intendedUse``
    - ``has_sensitive_personal_information``
      → ``dataset_hasSensitivePersonalInformation`` (``PresenceType`` enum)
    - ``anonymization_methods`` → ``dataset_anonymizationMethodUsed``

    **External reference**

    - ``croissant_url`` → ``externalRef`` with type ``other`` and comment
      ``"Croissant metadata"``

    **Provenance**

    - ``provenance`` → ``comment``

    Args:
        meta: Extracted dataset metadata.
        creation_info: The shared CreationInfo node.
        doc_name: The parent document/package name (for deterministic spdxId).
        doc_uuid: The document UUID (for deterministic spdxId).

    Returns:
        A populated :class:`spdx3.dataset_DatasetPackage` instance.
    """
    dataset_pkg = spdx3.dataset_DatasetPackage(
        spdxId=generate_spdx_id("DatasetPackage", doc_name=doc_name, doc_uuid=doc_uuid),
        name=meta.name,
        creationInfo=creation_info,
    )

    if meta.version:
        dataset_pkg.software_packageVersion = meta.version

    if meta.description:
        dataset_pkg.description = meta.description

    if meta.download_url:
        dataset_pkg.software_downloadLocation = meta.download_url

    # dataset_datasetType is required by the SPDX model; always set it.
    # Map known string names to enum values, skip unknowns silently.
    # Fall back to [noAssertion] when no type information is available.
    # dataset_DatasetType named individuals are str at runtime;
    # stubs type them as str.
    type_values: list[str] = []
    for type_name in meta.dataset_types:
        enum_val = getattr(spdx3.dataset_DatasetType, type_name, None)
        if enum_val is not None:
            type_values.append(enum_val)
    if not type_values:
        type_values = [spdx3.dataset_DatasetType.noAssertion]
    dataset_pkg.dataset_datasetType = type_values  # type: ignore[assignment]

    if meta.dataset_size is not None:
        dataset_pkg.dataset_datasetSize = meta.dataset_size

    if meta.data_collection_process:
        dataset_pkg.dataset_dataCollectionProcess = meta.data_collection_process

    if meta.data_preprocessing:
        dataset_pkg.dataset_dataPreprocessing = (
            meta.data_preprocessing  # type: ignore[assignment]
        )

    if meta.known_bias:
        dataset_pkg.dataset_knownBias = meta.known_bias  # type: ignore[assignment]

    if meta.intended_use:
        dataset_pkg.dataset_intendedUse = meta.intended_use

    if meta.has_sensitive_personal_information is not None:
        presence = _PRESENCE_MAP.get(meta.has_sensitive_personal_information)
        if presence is not None:
            dataset_pkg.dataset_hasSensitivePersonalInformation = presence

    if meta.anonymization_methods:
        dataset_pkg.dataset_anonymizationMethodUsed = (
            meta.anonymization_methods  # type: ignore[assignment]
        )

    # ExternalRef pointing to the Croissant document for full provenance.
    if meta.croissant_url:
        ext_ref = spdx3.ExternalRef(
            externalRefType=spdx3.ExternalRefType.other,
            locator=[meta.croissant_url],
            comment="Croissant metadata",
        )
        dataset_pkg.externalRef = [ext_ref]  # type: ignore[assignment]

    # comment: provenance
    if meta.provenance:
        prov_str = "; ".join(
            f"{field_name}: {src}" for field_name, src in meta.provenance.items()
        )
        dataset_pkg.comment = f"Metadata provenance: {prov_str}"

    return dataset_pkg


def add_datasets_for_model(
    ai_package_spdx_id: str,
    datasets: list[DatasetReference],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Build ``dataset_DatasetPackage`` and relationship elements for each
    dataset reference and add them to the exporter.

    For each entry in ``datasets``:

    - A ``dataset_DatasetPackage`` element is built from the extracted metadata.
    - A relationship element links the AI package (``from_``) to the dataset
      (``to``), using the role to select the relationship type.
    - Roles ``"trainedOn"`` and ``"testedOn"`` map to the corresponding SPDX 3.0.1
      relationship types directly.
    - Other roles (``"finetunedOn"``, ``"validatedOn"``, ``"pretrainedOn"``)
      use ``RelationshipType.other`` with an explanatory comment.

    The caller is responsible for appending ``ProfileIdentifierType.dataset``
    to the document's ``profileConformance`` when at least one dataset is present.

    Args:
        ai_package_spdx_id: SPDX ID of the ``ai_AIPackage`` element that this
            dataset is associated with.
        datasets: List of :class:`~pitloom.core.dataset_metadata.DatasetReference`
            objects, each carrying a role and extracted metadata.
        creation_info: Shared ``CreationInfo`` for all new elements.
        doc_name: Document name (project name) for SPDX ID generation.
        doc_uuid: Document-scoped UUID used in SPDX ID generation.
        exporter: Receives the new dataset package and relationship elements.
    """
    for dataset_ref in datasets:
        meta = dataset_ref.metadata
        dataset_pkg = _build_dataset_package(meta, creation_info, doc_name, doc_uuid)
        # dataset_DatasetPackage is not a software_Package so add via object_set.
        exporter.object_set.add(dataset_pkg)

        rel_type, fallback_comment = _role_to_rel(dataset_ref.role)
        rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
            ),
            creationInfo=creation_info,
            from_=ai_package_spdx_id,
            to=[dataset_pkg.spdxId],  # type: ignore[attr-defined]
            relationshipType=rel_type,
        )
        if fallback_comment:
            rel.comment = fallback_comment
        exporter.add_relationship(rel)
