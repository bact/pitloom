# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM generation for Python projects that use Hatchling metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from spdx_python_model import v3_0_1 as spdx3

from loom.core.models import generate_spdx_id
from loom.exporters.spdx3_json import Spdx3JsonExporter
from loom.extractors.metadata import extract_metadata_from_pyproject
from loom.generators.dependencies import add_dependencies
from loom.generators.fragments import merge_fragments


def generate_sbom(
    project_dir: Path,
    output_path: Path | None = None,
    pretty: bool | None = None,
    creator_name: str | None = None,
    creator_email: str | None = None,
) -> str:
    """Generate an SPDX 3.0 SBOM for a Python project.

    Reads project metadata from ``pyproject.toml``, constructs a complete
    SPDX 3.0 document including dependency relationships, and optionally
    merges pre-generated SBOM fragments (e.g., from ``loom.bom.track``).

    Args:
        project_dir: Path to the project directory containing ``pyproject.toml``.
        output_path: If given, the JSON-LD output is also written to this path.
        pretty: If ``True``, indent the JSON output with 2 spaces.
            If ``False``, produce compact output (no extra whitespace).
            If ``None`` (default), read the setting from ``[tool.loom] pretty``
            in ``pyproject.toml`` (which itself defaults to ``False``).
        creator_name: Name of the SBOM creator. Defaults to ``"Loom"``.
        creator_email: Email address of the SBOM creator. Optional.

    Returns:
        JSON-LD string of the generated SPDX 3.0 SBOM.

    Raises:
        FileNotFoundError: If ``pyproject.toml`` is not found in ``project_dir``.
        ValueError: If required project metadata (e.g., ``name``) is missing.
    """
    metadata = extract_metadata_from_pyproject(project_dir / "pyproject.toml")
    effective_pretty: bool = metadata.pretty if pretty is None else pretty

    exporter = Spdx3JsonExporter()
    doc_uuid = str(uuid4())

    # --- Creation info and creator agent ---
    creation_info = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime.now(timezone.utc),
    )
    creator = spdx3.Person(
        spdxId=generate_spdx_id("Person", doc_name=metadata.name, doc_uuid=doc_uuid),
        name=creator_name or "Loom",
        creationInfo=creation_info,
    )
    if creator_email:
        creator.externalIdentifier = [
            spdx3.ExternalIdentifier(
                externalIdentifierType=spdx3.ExternalIdentifierType.email,
                identifier=creator_email,
            )
        ]
    creation_info.createdBy = [creator.spdxId]

    # Unknown supplier organization for dependencies without explicit supplier info
    unknown_org = spdx3.Organization(
        spdxId=generate_spdx_id(
            "Organization", doc_name="UnknownSupplier", doc_uuid=doc_uuid
        ),
        name="NOASSERTION",
        creationInfo=creation_info,
    )

    exporter.add_creation_info(creation_info)
    exporter.add_person(creator)
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
        creationInfo=creation_info,
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
        creationInfo=creation_info,
        rootElement=[main_package.spdxId],
    )
    sbom.software_sbomType = [spdx3.software_SbomType.build]

    spdx_doc = spdx3.SpdxDocument(
        spdxId=generate_spdx_id(
            "SpdxDocument", doc_name=metadata.name, doc_uuid=doc_uuid
        ),
        creationInfo=creation_info,
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
        creation_info=creation_info,
        doc_uuid=doc_uuid,
        exporter=exporter,
    )

    # --- SBOM fragments ---
    merge_fragments(
        project_dir=project_dir,
        fragment_files=metadata.fragments,
        exporter=exporter,
    )

    sbom_json = exporter.to_json(pretty=effective_pretty)

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json
