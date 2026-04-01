# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 document assembly for Python projects."""

from __future__ import annotations

from datetime import datetime, timezone

from spdx_python_model import v3_0_1 as spdx3

from pitloom.assemble.spdx3.ai import add_ai_models
from pitloom.assemble.spdx3.deps import add_dependencies, build_license_elements
from pitloom.core.document import DocumentModel
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter


def build(doc: DocumentModel, merkle_root: str | None = None) -> Spdx3JsonExporter:
    """Assemble SPDX 3 elements from a :class:`~pitloom.core.document.DocumentModel`.

    Args:
        doc: Format-neutral document model with project metadata, creation
            metadata, and any AI model metadata.
        merkle_root: Optional hex-encoded SHA-256 Merkle root of the wheel
            source files (see :func:`~pitloom.core.models.compute_wheel_merkle_root`).
            When provided, any change to the packaged source causes a new document UUID.

    Returns:
        A populated :class:`~pitloom.export.spdx3_json.Spdx3JsonExporter`
        containing all SPDX 3 elements for the project and its dependencies.
    """
    metadata = doc.project
    ci = doc.creation
    created_at = (
        datetime.fromisoformat(ci.creation_datetime)
        if ci.creation_datetime
        else datetime.now(timezone.utc)
    )

    exporter = Spdx3JsonExporter()
    doc_uuid = compute_doc_uuid(
        name=metadata.name,
        version=metadata.version or "unknown",
        dependencies=metadata.dependencies,
        merkle_root=merkle_root,
    )
    _clear_doc_counters(doc_uuid)

    # --- Creation info, creator agent, and creation tool ---
    spdx_ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=created_at,
    )
    creator = spdx3.Person(
        spdxId=generate_spdx_id("Person", doc_name=metadata.name, doc_uuid=doc_uuid),
        name=ci.creator_name,
        creationInfo=spdx_ci,
    )
    if ci.creator_email:
        creator.externalIdentifier = [
            spdx3.ExternalIdentifier(
                externalIdentifierType=spdx3.ExternalIdentifierType.email,
                identifier=ci.creator_email,
            )
        ]
    tool = spdx3.Tool(
        spdxId=generate_spdx_id("Tool", doc_name=metadata.name, doc_uuid=doc_uuid),
        name=ci.creation_tool,
        creationInfo=spdx_ci,
    )
    spdx_ci.createdBy = [creator.spdxId]
    spdx_ci.createdUsing = [tool.spdxId]

    exporter.add_creation_info(spdx_ci)
    exporter.add_person(creator)
    exporter.object_set.add(tool)

    # --- Main package ---
    provenance_comment: str | None = None
    if metadata.provenance:
        provenance_comment = "Metadata provenance: " + "; ".join(
            f"{field}: {source}" for field, source in metadata.provenance.items()
        )

    download_location = metadata.urls.get("Source") or metadata.urls.get("Homepage")

    main_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name=metadata.name, doc_uuid=doc_uuid),
        name=metadata.name,
        creationInfo=spdx_ci,
    )
    main_package.software_packageVersion = metadata.version or "unknown"
    main_package.suppliedBy = creator.spdxId
    if metadata.description:
        main_package.description = metadata.description
    if download_location:
        main_package.software_downloadLocation = download_location
    if metadata.urls.get("Homepage"):
        main_package.software_homePage = metadata.urls.get("Homepage")
    main_package.software_copyrightText = f"Copyright (c) {datetime.now().year} " + (
        metadata.authors[0].get("name", metadata.name)
        if metadata.authors
        else metadata.name
    )
    main_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
    if ci.build_datetime:
        main_package.builtTime = datetime.fromisoformat(ci.build_datetime)
    if provenance_comment:
        main_package.comment = provenance_comment

    # --- SBOM and document envelope ---
    sbom = spdx3.software_Sbom(
        spdxId=generate_spdx_id("Sbom", doc_name=metadata.name, doc_uuid=doc_uuid),
        creationInfo=spdx_ci,
        rootElement=[main_package.spdxId],
    )
    sbom.software_sbomType = [spdx3.software_SbomType.build]

    spdx_doc = spdx3.SpdxDocument(
        spdxId=generate_spdx_id(
            "SpdxDocument", doc_name=metadata.name, doc_uuid=doc_uuid
        ),
        creationInfo=spdx_ci,
        rootElement=[sbom.spdxId],
    )
    spdx_doc.profileConformance = [
        spdx3.ProfileIdentifierType.core,
        spdx3.ProfileIdentifierType.software,
    ]

    exporter.add_document(spdx_doc)
    exporter.add_sbom(sbom)
    exporter.add_package(main_package)

    # --- License ---
    if metadata.license_name:
        rel_declared, rel_concluded = build_license_elements(
            license_id=metadata.license_name,
            package_spdx_id=main_package.spdxId,
            license_provenance=metadata.provenance.get(
                "license", "Source: pyproject.toml | Field: project.license"
            ),
            creation_info=spdx_ci,
            doc_name=metadata.name,
            doc_uuid=doc_uuid,
            exporter=exporter,
        )
        exporter.add_relationship(rel_declared)
        exporter.add_relationship(rel_concluded)
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.simpleLicensing)

    # --- Dependencies ---
    add_dependencies(
        dependencies=metadata.dependencies,
        dep_provenance=metadata.provenance.get("dependencies", "Unknown source"),
        main_package_spdx_id=main_package.spdxId,
        creation_info=spdx_ci,
        doc_name=metadata.name,
        doc_uuid=doc_uuid,
        exporter=exporter,
    )

    # --- AI models (and their associated datasets) ---
    if doc.ai_models:
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.ai)
        if any(m.datasets for m in doc.ai_models):
            spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.dataset)
        add_ai_models(
            ai_models=doc.ai_models,
            main_package_spdx_id=main_package.spdxId,
            creation_info=spdx_ci,
            doc_name=metadata.name,
            doc_uuid=doc_uuid,
            exporter=exporter,
        )

    return exporter
