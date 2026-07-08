# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 document assembly for Python projects."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.ai import _build_ai_package, add_ai_models
from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.assemble.spdx3.dataset import add_datasets_for_model
from pitloom.assemble.spdx3.deps import add_dependencies, build_license_elements
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import (
    _clear_doc_counters,
    build_pypi_purl,
    compute_doc_uuid,
    generate_spdx_id,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id


def _build_creation_bundle(
    doc: DocumentModel, doc_uuid: str
) -> tuple[spdx3.CreationInfo, spdx3.Agent, spdx3.Tool | None]:
    """Create shared SPDX creation objects for the document."""
    return build_creation_info(doc.creation_metadata, doc.project.name, doc_uuid)


def _build_provenance_comment(doc: DocumentModel) -> str | None:
    """Return a stable provenance summary for package metadata."""
    provenance = doc.project.provenance
    if not provenance:
        return None

    return "Metadata provenance: " + "; ".join(
        f"{field}: {source}" for field, source in provenance.items()
    )


def _build_main_package(
    doc: DocumentModel,
    spdx_ci: spdx3.CreationInfo,
    creator: spdx3.Agent,
    doc_uuid: str,
) -> spdx3.software_Package:
    """Create the SPDX package representing the Python project."""
    metadata = doc.project
    creation_metadata = doc.creation_metadata
    download_location = metadata.urls.get("Source") or metadata.urls.get("Homepage")
    main_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name=metadata.name, doc_uuid=doc_uuid),
        name=metadata.name,
        creationInfo=spdx_ci,
    )
    main_package.software_packageVersion = metadata.version or "unknown"
    # suppliedBy names who supplied the package, so only assert it for a real
    # named creator -- not for the default SoftwareAgent "Pitloom", which is
    # the SBOM tool, not the package's supplier.
    if creation_metadata.creator_name:
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
    if creation_metadata.build_datetime:
        main_package.builtTime = datetime.fromisoformat(
            creation_metadata.build_datetime
        )

    # packageUrl -- PyPI PURL (pkg:pypi/<name>@<version>), only when a real
    # version is known.  Mirrors the dependency PURL logic in deps.py.
    if metadata.version and metadata.version != "unknown":
        main_package.software_packageUrl = build_pypi_purl(
            metadata.name, metadata.version
        )

    provenance_comment = _build_provenance_comment(doc)
    if provenance_comment:
        main_package.comment = provenance_comment
    return main_package


def _add_package_files(
    doc: DocumentModel,
    main_package: spdx3.software_Package,
    spdx_ci: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> dict[str, str]:
    """Add package files and directory containment relationships."""
    metadata = doc.project
    file_spdx_ids: dict[str, str] = {}
    dir_spdx_ids: dict[str, str] = {}

    for package_file in metadata.files:
        dist_path = Path(package_file.distribution_path)
        parent_paths = [p for p in list(dist_path.parents)[::-1] if p.name]

        for index, directory_path in enumerate(parent_paths):
            directory_name = directory_path.as_posix()
            if directory_name in dir_spdx_ids:
                continue

            directory_file = spdx3.software_File(
                spdxId=generate_spdx_id(
                    "File", doc_name=metadata.name, doc_uuid=doc_uuid
                ),
                name=directory_name,
                creationInfo=spdx_ci,
            )
            directory_file.software_fileKind = spdx3.software_FileKindType.directory
            exporter.add_file(directory_file)
            dir_spdx_ids[directory_name] = require_spdx_id(directory_file)

            parent_id = (
                main_package.spdxId
                if index == 0
                else dir_spdx_ids[parent_paths[index - 1].as_posix()]
            )
            exporter.add_relationship(
                spdx3.Relationship(
                    spdxId=generate_spdx_id(
                        "Relationship", doc_name=metadata.name, doc_uuid=doc_uuid
                    ),
                    from_=parent_id,
                    to=[require_spdx_id(directory_file)],
                    relationshipType=spdx3.RelationshipType.contains,
                    creationInfo=spdx_ci,
                )
            )

        package_entry = spdx3.software_File(
            spdxId=generate_spdx_id("File", doc_name=metadata.name, doc_uuid=doc_uuid),
            name=package_file.distribution_path,
            creationInfo=spdx_ci,
        )
        package_entry.software_fileKind = spdx3.software_FileKindType.file
        package_entry.verifiedUsing = [
            spdx3.Hash(
                algorithm=spdx3.HashAlgorithm.sha256,
                hashValue=package_file.digest_sha256,
            )
        ]
        exporter.add_file(package_entry)
        file_spdx_ids[package_file.distribution_path] = require_spdx_id(package_entry)

        parent_id = (
            dir_spdx_ids[parent_paths[-1].as_posix()]
            if parent_paths
            else main_package.spdxId
        )
        exporter.add_relationship(
            spdx3.Relationship(
                spdxId=generate_spdx_id(
                    "Relationship", doc_name=metadata.name, doc_uuid=doc_uuid
                ),
                from_=parent_id,
                to=[require_spdx_id(package_entry)],
                relationshipType=spdx3.RelationshipType.contains,
                creationInfo=spdx_ci,
            )
        )

    return file_spdx_ids


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

    exporter = Spdx3JsonExporter()
    doc_uuid = compute_doc_uuid(
        name=metadata.name,
        version=metadata.version or "unknown",
        dependencies=metadata.dependencies,
        merkle_root=merkle_root,
    )
    _clear_doc_counters(doc_uuid)

    # --- Creation info, creator agent, and creation tool ---
    spdx_ci, creator, tool = _build_creation_bundle(doc, doc_uuid)

    exporter.add_creation_info(spdx_ci)
    exporter.add_agent(creator)
    if tool is not None:
        exporter.object_set.add(tool)

    # --- Main package ---
    main_package = _build_main_package(doc, spdx_ci, creator, doc_uuid)

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
            package_spdx_id=require_spdx_id(main_package),
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
        main_package_spdx_id=require_spdx_id(main_package),
        creation_info=spdx_ci,
        doc_name=metadata.name,
        doc_uuid=doc_uuid,
        exporter=exporter,
    )

    # --- Files ---
    file_spdx_ids = _add_package_files(doc, main_package, spdx_ci, doc_uuid, exporter)

    # --- AI models (and their associated datasets) ---
    if doc.ai_models:
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.ai)
        if any(m.datasets for m in doc.ai_models):
            spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.dataset)
        if (
            any(m.license for m in doc.ai_models)
            and spdx3.ProfileIdentifierType.simpleLicensing
            not in spdx_doc.profileConformance
        ):
            spdx_doc.profileConformance.append(
                spdx3.ProfileIdentifierType.simpleLicensing
            )
        add_ai_models(
            ai_models=doc.ai_models,
            main_package_spdx_id=require_spdx_id(main_package),
            file_spdx_ids=file_spdx_ids,
            creation_info=spdx_ci,
            doc_name=metadata.name,
            doc_uuid=doc_uuid,
            exporter=exporter,
        )

    return exporter


def build_model(
    model: AiModelMetadata,
    creation_metadata: CreationMetadata,
) -> Spdx3JsonExporter:
    """Assemble a standalone SPDX 3 SBOM for a single AI model file.

    Produces a minimal document containing only the ``ai_AIPackage`` element
    derived from *model*.  There is no parent Python package -- the AI package
    is itself the root element of the ``software_Sbom``.

    Args:
        model: Extracted AI model metadata.
        creation_metadata: Creator and timestamp metadata for the SBOM document.

    Returns:
        A populated :class:`~pitloom.export.spdx3_json.Spdx3JsonExporter`.
    """
    doc_name: str = model.name or model.format_info.file_name or "model"

    exporter = Spdx3JsonExporter()
    doc_uuid = compute_doc_uuid(
        name=doc_name,
        version=model.version or "unknown",
        dependencies=[],
        merkle_root=None,
    )
    _clear_doc_counters(doc_uuid)

    spdx_ci, creator, tool = build_creation_info(creation_metadata, doc_name, doc_uuid)

    exporter.add_creation_info(spdx_ci)
    exporter.add_agent(creator)
    if tool is not None:
        exporter.object_set.add(tool)

    ai_pkg = _build_ai_package(model, spdx_ci, doc_name, doc_uuid)
    exporter.add_package(ai_pkg)

    if model.license:
        rel_declared, rel_concluded = build_license_elements(
            license_id=model.license,
            package_spdx_id=require_spdx_id(ai_pkg),
            license_provenance=model.provenance.get(
                "license",
                "Source: model file / Hugging Face Hub",
            ),
            creation_info=spdx_ci,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
        )
        exporter.add_relationship(rel_declared)
        exporter.add_relationship(rel_concluded)

    if model.datasets:
        add_datasets_for_model(
            ai_package_spdx_id=require_spdx_id(ai_pkg),
            datasets=model.datasets,
            creation_info=spdx_ci,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
        )

    sbom = spdx3.software_Sbom(
        spdxId=generate_spdx_id("Sbom", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=spdx_ci,
        rootElement=[ai_pkg.spdxId],
    )
    sbom.software_sbomType = [spdx3.software_SbomType.build]

    spdx_doc = spdx3.SpdxDocument(
        spdxId=generate_spdx_id("SpdxDocument", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=spdx_ci,
        rootElement=[sbom.spdxId],
    )
    spdx_doc.profileConformance = [
        spdx3.ProfileIdentifierType.core,
        spdx3.ProfileIdentifierType.software,
        spdx3.ProfileIdentifierType.ai,
    ]
    if model.license:
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.simpleLicensing)
    if model.datasets:
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.dataset)

    exporter.add_document(spdx_doc)
    exporter.add_sbom(sbom)

    return exporter
