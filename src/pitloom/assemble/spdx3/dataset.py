# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dataset package and relationship creation for SPDX 3 SBOM documents."""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

# Mapping from DatasetReference.role strings to SPDX 3.0.1 RelationshipType.
# finetunedOn, validatedOn, pretrainedOn do not exist in SPDX 3.0.1;
# they fall back to RelationshipType.other with a comment (see _role_to_rel).
# RelationshipType members are plain str NamedIndividual IRIs, not an enum type.
_ROLE_TO_RELATIONSHIP: dict[str, str] = {
    "trainedOn": spdx3.RelationshipType.trainedOn,
    "testedOn": spdx3.RelationshipType.testedOn,
}

# PresenceType mapping for has_sensitive_personal_information.
# PresenceType members are plain str NamedIndividual IRIs, not an enum type.
_PRESENCE_MAP: dict[str, str] = {
    "yes": spdx3.PresenceType.yes,
    "no": spdx3.PresenceType.no,
    "noAssertion": spdx3.PresenceType.noAssertion,
}


def _role_to_rel(role: str) -> tuple[str, str | None]:
    """Return the SPDX RelationshipType and optional fallback comment for *role*.

    Returns:
        A 2-tuple of ``(RelationshipType, comment_or_None)``.  ``comment``
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


def _resolve_dataset_types(dataset_types: list[str]) -> list[str]:
    """Map known dataset type string names to enum values or noAssertion."""
    type_values: list[str] = []
    for type_name in dataset_types:
        enum_val = getattr(spdx3.dataset_DatasetType, type_name, None)
        if enum_val is not None:
            type_values.append(enum_val)
    return type_values if type_values else [spdx3.dataset_DatasetType.noAssertion]


def _populate_dataset_profile_fields(
    dataset_pkg: spdx3.dataset_DatasetPackage, meta: DatasetMetadata
) -> None:
    """Populate optional dataset profile and privacy fields."""
    if meta.dataset_size is not None:
        dataset_pkg.dataset_datasetSize = meta.dataset_size
    if meta.data_collection_process:
        dataset_pkg.dataset_dataCollectionProcess = meta.data_collection_process
    if meta.data_preprocessing:
        dataset_pkg.dataset_dataPreprocessing = list(meta.data_preprocessing)
    if meta.known_bias:
        dataset_pkg.dataset_knownBias = list(meta.known_bias)
    if meta.intended_use:
        dataset_pkg.dataset_intendedUse = meta.intended_use
    if meta.has_sensitive_personal_information is not None:
        presence = _PRESENCE_MAP.get(meta.has_sensitive_personal_information)
        if presence is not None:
            dataset_pkg.dataset_hasSensitivePersonalInformation = presence
    if meta.anonymization_methods:
        dataset_pkg.dataset_anonymizationMethodUsed = list(meta.anonymization_methods)
    if meta.croissant_url:
        ext_ref = spdx3.ExternalRef(
            externalRefType=spdx3.ExternalRefType.other,
            locator=[meta.croissant_url],
            comment="Croissant metadata",
        )
        dataset_pkg.externalRef = [ext_ref]


def _build_dataset_package(
    meta: DatasetMetadata,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> spdx3.dataset_DatasetPackage:
    """Build a ``dataset_DatasetPackage`` SPDX 3 element from a
    :class:`~pitloom.core.dataset_metadata.DatasetMetadata`.
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

    dataset_pkg.dataset_datasetType = _resolve_dataset_types(meta.dataset_types)
    _populate_dataset_profile_fields(dataset_pkg, meta)
    return dataset_pkg


def _add_dataset_creator_agent(
    dataset_pkg_spdx_id: str,
    creator_name: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Create an Agent element for a dataset's creator and wire a publishedBy
    relationship linking the dataset to the Agent.
    """
    creator_agent = spdx3.Agent(
        spdxId=generate_spdx_id(
            f"Agent-{creator_name}", doc_name=doc_name, doc_uuid=doc_uuid
        ),
        name=creator_name,
        creationInfo=creation_info,
    )
    exporter.add_agent(creator_agent)
    rel_creator = build_relationship(
        from_id=dataset_pkg_spdx_id,
        to_ids=[require_spdx_id(creator_agent)],
        rel_type=spdx3.RelationshipType.publishedBy,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        creation_info=creation_info,
    )
    if rel_creator:
        exporter.add_relationship(rel_creator)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def add_datasets_for_model(
    ai_package_spdx_id: str,
    datasets: list[DatasetReference],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    dataset_creation_info: dict[str, spdx3.CreationInfo] | None = None,
) -> None:
    """Build ``dataset_DatasetPackage`` and relationship elements for each
    dataset reference.

    Args:
        dataset_creation_info: Optional override map, dataset name ->
            ``CreationInfo``, for datasets that came from an enrichment run
            rather than the model's own extraction (N3) -- see
            ``creation_info.build_enrichment_creation_info()``. A name not
            in the map (or when the map itself is ``None``) falls back to
            the shared *creation_info* param, unchanged behavior for every
            existing call site.
    """
    for dataset_ref in datasets:
        meta = dataset_ref.metadata
        element_creation_info = (
            dataset_creation_info.get(meta.name, creation_info)
            if dataset_creation_info
            else creation_info
        )
        dataset_pkg = _build_dataset_package(
            meta, element_creation_info, doc_name, doc_uuid
        )
        exporter.object_set.add(dataset_pkg)
        emit_provenance(
            subject=dataset_pkg,
            provenance=meta.provenance,
            creation_info=element_creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        if meta.creator:
            _add_dataset_creator_agent(
                dataset_pkg_spdx_id=require_spdx_id(dataset_pkg),
                creator_name=meta.creator,
                creation_info=element_creation_info,
                doc_name=doc_name,
                doc_uuid=doc_uuid,
                exporter=exporter,
            )

        rel_type, fallback_comment = _role_to_rel(dataset_ref.role)
        rel = build_relationship(
            from_id=ai_package_spdx_id,
            to_ids=[require_spdx_id(dataset_pkg)],
            rel_type=rel_type,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            creation_info=element_creation_info,
        )
        if rel:
            if fallback_comment and rel_type == spdx3.RelationshipType.other:
                rel.comment = fallback_comment
            exporter.add_relationship(rel)
