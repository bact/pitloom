# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 assembler for Python projects."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from spdx_python_model import v3_0_1 as spdx3

from loom.core.document import DocumentModel
from loom.core.models import generate_spdx_id
from loom.export.spdx3_json import Spdx3JsonExporter
from loom.assemble.spdx3.deps import add_dependencies


def build(doc: DocumentModel) -> Spdx3JsonExporter:
    """Assemble SPDX 3 elements from a :class:`~loom.core.document.DocumentModel`.

    Args:
        doc: Format-neutral document model with project metadata, creation
            metadata, and any AI model metadata.

    Returns:
        A populated :class:`~loom.export.spdx3_json.Spdx3JsonExporter`
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
    doc_uuid = str(uuid4())

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
        spdxId=generate_spdx_id("Tool", doc_name=ci.creation_tool, doc_uuid=doc_uuid),
        name=ci.creation_tool,
        creationInfo=spdx_ci,
    )
    spdx_ci.createdBy = [creator.spdxId]
    spdx_ci.createdUsing = [tool.spdxId]

    # Unknown supplier organization for dependencies without explicit supplier info
    unknown_org = spdx3.Organization(
        spdxId=generate_spdx_id(
            "Organization", doc_name="UnknownSupplier", doc_uuid=doc_uuid
        ),
        name="NOASSERTION",
        creationInfo=spdx_ci,
    )

    exporter.add_creation_info(spdx_ci)
    exporter.add_person(creator)
    exporter.object_set.add(tool)
    exporter.add_person(unknown_org)

    # --- Main package ---
    copyright_holder = (
        metadata.authors[0].get("name", metadata.name)
        if metadata.authors
        else metadata.name
    )
    provenance_comment: str | None = None
    if metadata.provenance:
        parts = [f"{field}: {source}" for field, source in metadata.provenance.items()]
        provenance_comment = "Metadata provenance: " + "; ".join(parts)

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
    main_package.software_copyrightText = (
        f"Copyright (c) {datetime.now().year} {copyright_holder}"
    )
    main_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
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

    # --- Dependencies ---
    add_dependencies(
        dependencies=metadata.dependencies,
        dep_provenance=metadata.provenance.get("dependencies", "Unknown source"),
        main_package_spdx_id=main_package.spdxId,
        unknown_org_spdx_id=unknown_org.spdxId,
        creation_info=spdx_ci,
        doc_uuid=doc_uuid,
        exporter=exporter,
    )

    return exporter
