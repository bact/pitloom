# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM generator for Python projects using Hatchling metadata."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as get_package_version
from pathlib import Path
from uuid import uuid4

from spdx_python_model import v3_0_1 as spdx3

from loom.core.models import generate_spdx_id
from loom.exporters.spdx3_json import Spdx3JsonExporter
from loom.extractors.metadata import extract_metadata_from_pyproject


def generate_sbom_from_project(
    project_dir: Path,
    creator_name: str | None = None,
    creator_email: str | None = None,
) -> str:
    """Generate an SPDX 3.0 SBOM from a Python project.

    Args:
        project_dir: Path to the project directory containing pyproject.toml
        creator_name: Name of the SBOM creator (defaults to "Loom")
        creator_email: Email of the SBOM creator (optional)

    Returns:
        str: JSON-LD representation of the SBOM

    Raises:
        FileNotFoundError: If pyproject.toml is not found
        ValueError: If required project metadata is missing
    """
    pyproject_path = project_dir / "pyproject.toml"
    metadata = extract_metadata_from_pyproject(pyproject_path)

    # Create SPDX document elements
    exporter = Spdx3JsonExporter()

    # Generate a single document UUID for the entire SBOM
    doc_uuid = str(uuid4())

    # Create creation info
    creation_info = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime.now(timezone.utc),
    )

    # Create creator person
    creator = spdx3.Person(
        spdxId=generate_spdx_id("Person", doc_name=metadata.name, doc_uuid=doc_uuid),
        name=creator_name or "Loom",
        creationInfo=creation_info,
    )
    if creator_email:
        creator_email_id = spdx3.ExternalIdentifier(
            externalIdentifierType=spdx3.ExternalIdentifierType.email,
            identifier=creator_email,
        )
        creator.externalIdentifier = [creator_email_id]

    creation_info.createdBy = [creator.spdxId]

    # Add creation info first
    exporter.add_creation_info(creation_info)

    # Add creator
    exporter.add_person(creator)

    # Create unknown organization for dependencies without supplier info
    unknown_org = spdx3.Organization(
        spdxId=generate_spdx_id("Organization", doc_name="UnknownSupplier", doc_uuid=doc_uuid),
        name="NOASSERTION",
        creationInfo=creation_info,
    )
    exporter.add_person(unknown_org)

    # Create main package
    package_version = metadata.version or "unknown"
    download_location = metadata.urls.get("Source") or metadata.urls.get("Homepage")

    # Extract copyright year from metadata if available, otherwise use current year
    copyright_year = datetime.now().year
    # Use first author if available, otherwise use package name
    copyright_holder = metadata.name
    if metadata.authors:
        copyright_holder = metadata.authors[0].get("name", metadata.name)

    # Build provenance comment for the main package
    provenance_parts = []
    for field, source in metadata.provenance.items():
        provenance_parts.append(f"{field}: {source}")

    comment = None
    if provenance_parts:
        comment = "Metadata provenance: " + "; ".join(provenance_parts)

    main_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name=metadata.name, doc_uuid=doc_uuid),
        name=metadata.name,
        creationInfo=creation_info,
    )
    # Populate Version (NTIA Minimum Element)
    if package_version:
        main_package.software_packageVersion = package_version
    # Populate Supplier (NTIA Minimum Element)
    main_package.suppliedBy = creator.spdxId

    if metadata.description:
        main_package.description = metadata.description
    if download_location:
        main_package.software_downloadLocation = download_location
    if metadata.urls.get("Homepage"):
        main_package.software_homePage = metadata.urls.get("Homepage")
    main_package.software_copyrightText = f"Copyright (c) {copyright_year} {copyright_holder}"
    main_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
    if comment:
        main_package.comment = comment

    # Create SBOM
    sbom = spdx3.software_Sbom(
        spdxId=generate_spdx_id("Sbom", doc_name=metadata.name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
        rootElement=[main_package.spdxId],
    )
    sbom.software_sbomType = [spdx3.software_SbomType.build]

    # Create SPDX document
    spdx_doc = spdx3.SpdxDocument(
        spdxId=generate_spdx_id("SpdxDocument", doc_name=metadata.name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
        rootElement=[sbom.spdxId],
    )
    spdx_doc.profileConformance = [spdx3.ProfileIdentifierType.core, spdx3.ProfileIdentifierType.software]

    # Add all elements to exporter
    exporter.add_document(spdx_doc)
    exporter.add_sbom(sbom)
    exporter.add_package(main_package)

    # Add dependency packages and relationships
    for dep in metadata.dependencies:
        # Parse dependency string (e.g., "fasttext==0.9.3", "requests>=2.28.0", "numpy")
        dep_name = dep
        for op in ["==", ">=", "<=", "~=", ">", "<", "!=", "==="]:
            if op in dep:
                dep_name = dep.split(op)[0].strip()
                break

        # Try to resolve actual installed version during this build
        resolved_version = None
        try:
            resolved_version = get_package_version(dep_name)
        except PackageNotFoundError:
            pass

        # Build provenance comment for dependency packages
        dep_parts = [f"dependencies: {metadata.provenance.get('dependencies', 'Unknown source')}"]
        dep_parts.append(f"Declared constraint: {dep}")

        if resolved_version:
            dep_parts.append("Version resolved: Build-time environment (importlib.metadata)")
            dep_version = resolved_version
        elif "==" in dep:
            dep_version = dep.split("==")[1].strip()
        else:
            dep_version = "unknown"

        dep_comment = "Metadata provenance: " + "; ".join(dep_parts)

        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name=metadata.name, doc_uuid=doc_uuid),
            name=dep_name,
            creationInfo=creation_info,
        )
        # Populate Version (NTIA Minimum Element)
        dep_package.software_packageVersion = dep_version
        # Populate Supplier (NTIA Minimum Element)
        dep_package.suppliedBy = unknown_org.spdxId

        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
        dep_package.comment = dep_comment

        exporter.add_package(dep_package)

        # Create dependency relationship
        rel_comment = f"Metadata provenance: dependencies: {metadata.provenance.get('dependencies', 'Unknown source')}"

        dep_rel = spdx3.Relationship(
            spdxId=generate_spdx_id("Relationship", doc_name=metadata.name, doc_uuid=doc_uuid),
            from_=main_package.spdxId,
            to=[dep_package.spdxId],
            relationshipType=spdx3.RelationshipType.dependsOn,
            creationInfo=creation_info,
        )
        if rel_comment:
            dep_rel.comment = rel_comment
        dep_rel.description = f"{metadata.name} depends on {dep_name}"

        exporter.add_relationship(dep_rel)

    # Ingest Generic SBOM Fragments if defined
    for fragment_file in metadata.fragments:
        fragment_path = project_dir / fragment_file
        if fragment_path.exists():
            try:
                with open(fragment_path, "rb") as f:
                    # In SPDX 3.0, JSON-LD fragments can be parsed back into object sets
                    fragment_set = spdx3.SHACLObjectSet()
                    parser = spdx3.JSONLDDeserializer()
                    parser.read(f, fragment_set)

                    # Merge fragment objects into our main exporter object set
                    for obj in fragment_set.foreach():
                        exporter.object_set.add(obj)
            except Exception as e:
                logging.warning(f"Failed to ingest SBOM fragment {fragment_path}: {e}")
        else:
            logging.warning(f"Configured SBOM fragment {fragment_path} not found.")

    return exporter.to_json()


def generate_sbom_to_file(
    project_dir: Path,
    output_path: Path,
    creator_name: str | None = None,
    creator_email: str | None = None,
) -> None:
    """Generate an SPDX 3.0 SBOM and write it to a file.

    Args:
        project_dir: Path to the project directory containing pyproject.toml
        output_path: Path where the SBOM JSON file will be written
        creator_name: Name of the SBOM creator (defaults to "Loom")
        creator_email: Email of the SBOM creator (optional)
    """
    sbom_json = generate_sbom_from_project(project_dir, creator_name, creator_email)
    output_path.write_text(sbom_json)
