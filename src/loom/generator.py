# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM generator for Python projects using Hatchling metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loom.core.models import (
    CreationInfo,
    Person,
    Relationship,
    Sbom,
    SoftwarePackage,
    SpdxDocument,
)
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

    # Create creation info
    creation_info = CreationInfo(
        created=datetime.now(timezone.utc),
        spec_version="3.0.1",
    )

    # Create creator person
    creator = Person(
        name=creator_name or "Loom",
        email=creator_email,
        creation_info=creation_info,
    )
    creation_info.created_by = [creator.spdx_id]

    # Add creation info first
    exporter.add_creation_info(creation_info)

    # Add creator
    exporter.add_person(creator)

    # Create main package
    package_version = metadata.version or "unknown"
    download_location = metadata.urls.get("Source") or metadata.urls.get("Homepage")

    # Extract copyright year from metadata if available, otherwise use current year
    copyright_year = datetime.now().year
    # Use first author if available, otherwise use package name
    copyright_holder = metadata.name
    if metadata.authors:
        copyright_holder = metadata.authors[0].get("name", metadata.name)

    main_package = SoftwarePackage(
        name=metadata.name,
        version=package_version,
        description=metadata.description,
        download_location=download_location,
        homepage=metadata.urls.get("Homepage"),
        copyright_text=f"Copyright (c) {copyright_year} {copyright_holder}",
        primary_purpose="library",
        creation_info=creation_info,
    )

    # Create SBOM
    sbom = Sbom(
        root_elements=[main_package.spdx_id],
        sbom_types=["build"],
        creation_info=creation_info,
    )

    # Create SPDX document
    spdx_doc = SpdxDocument(
        root_elements=[sbom.spdx_id],
        profile_conformance=["core", "software"],
        creation_info=creation_info,
    )

    # Add all elements to exporter
    exporter.add_document(spdx_doc)
    exporter.add_sbom(sbom)
    exporter.add_package(main_package)

    # Add dependency packages and relationships
    for dep in metadata.dependencies:
        # Parse dependency string (e.g., "fasttext==0.9.3" or "numpy>=1.20.0")
        dep_name = (
            dep.split("==")[0]
            .split(">=")[0]
            .split("<=")[0]
            .split(">")[0]
            .split("<")[0]
            .strip()
        )
        dep_version = None

        if "==" in dep:
            dep_version = dep.split("==")[1].strip()

        dep_package = SoftwarePackage(
            name=dep_name,
            version=dep_version,
            primary_purpose="library",
            creation_info=creation_info,
        )
        exporter.add_package(dep_package)

        # Create dependency relationship
        dep_rel = Relationship(
            from_element=main_package.spdx_id,
            to_elements=[dep_package.spdx_id],
            relationship_type="dependsOn",
            description=f"{metadata.name} depends on {dep_name}",
            creation_info=creation_info,
        )
        exporter.add_relationship(dep_rel)

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
