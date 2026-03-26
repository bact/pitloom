# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 assembler for Python projects."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from spdx_python_model import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.core.document import DocumentModel
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter


def _build_license_elements(
    license_id: str,
    package_spdx_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> tuple[
    spdx3.simplelicensing_SimpleLicensingText,
    spdx3.Relationship,
    spdx3.Relationship,
]:
    """Build a SimpleLicensingText element and its hasDeclaredLicense /
    hasConcludedLicense relationships for a given package.

    Args:
        license_id: SPDX license identifier string (e.g. ``"Apache-2.0"``)
                    (the "to" in a relationship).
        package_spdx_id: SPDX ID of the package the license applies to
                         (the "from" in a relationship).
        license_provenance: Human-readable provenance note for the comment field.
        creation_info: Shared CreationInfo for all new elements.
        doc_name: Document name used in SPDX ID generation.
        doc_uuid: Document UUID used in SPDX ID generation.

    Returns:
        A 3-tuple of ``(SimpleLicensingText, hasDeclaredLicense Relationship,
        hasConcludedLicense Relationship)``.
    """
    license_text = spdx3.simplelicensing_SimpleLicensingText(
        spdxId=generate_spdx_id("License", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
    )
    license_text.name = license_id
    license_text.simplelicensing_licenseText = license_id
    license_text.comment = f"Metadata provenance: license: {license_provenance}"

    # The license actually found in the Software Artifact.
    rel_has_declared_license = spdx3.Relationship(
        spdxId=generate_spdx_id(
            "Relationship", doc_name=f"{doc_name}-declared-license", doc_uuid=doc_uuid
        ),
        creationInfo=creation_info,
        from_=package_spdx_id,
        relationshipType=spdx3.RelationshipType.hasDeclaredLicense,
        to=[license_text.spdxId],
    )

    # The license identified by the SPDX data creator.
    # This can be more complicated.
    # For example, if there are mulitple declared licenses,
    # or if there is no declared licenes but a license
    # can be concluded from other evidence.
    # See https://spdx.github.io/spdx-spec/v3.0/model/Licensing/Licensing/
    # Sort this out in future versions.
    # Eventually we may need to create the relationships separately,
    # as hasDeclaredLicense and hasConcludedLicense can be different and
    # the value of having this helper function will be less clear.
    rel_has_concluded_license = spdx3.Relationship(
        spdxId=generate_spdx_id(
            "Relationship", doc_name=f"{doc_name}-concluded-license", doc_uuid=doc_uuid
        ),
        creationInfo=creation_info,
        from_=package_spdx_id,
        relationshipType=spdx3.RelationshipType.hasConcludedLicense,
        to=[license_text.spdxId],
    )

    return license_text, rel_has_declared_license, rel_has_concluded_license


def build(doc: DocumentModel) -> Spdx3JsonExporter:
    """Assemble SPDX 3 elements from a :class:`~pitloom.core.document.DocumentModel`.

    Args:
        doc: Format-neutral document model with project metadata, creation
            metadata, and any AI model metadata.

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

    # --- License ---
    if metadata.license_name:
        license_elements = _build_license_elements(
            license_id=metadata.license_name,
            package_spdx_id=main_package.spdxId,
            license_provenance=metadata.provenance.get(
                "license", "Source: pyproject.toml | Field: project.license"
            ),
            creation_info=spdx_ci,
            doc_name=metadata.name,
            doc_uuid=doc_uuid,
        )
        license_text, rel_declared, rel_concluded = license_elements
        exporter.add_license(license_text)
        exporter.add_relationship(rel_declared)
        exporter.add_relationship(rel_concluded)
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.simpleLicensing)

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
