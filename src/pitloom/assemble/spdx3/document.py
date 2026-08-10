# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 document assembly for Python projects."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.ai import (
    _add_base_model_lineage,
    _build_ai_package,
    _emit_source_metadata,
    _LineageContext,
    add_ai_models,
)
from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.assemble.spdx3.dataset import add_datasets_for_model
from pitloom.assemble.spdx3.deps import (
    _enrich_from_installed,
    add_dependencies,
    add_phantom_dependencies,
    build_license_elements,
)
from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    emit_provenance,
    resolve_encoder,
)
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import (
    _clear_doc_counters,
    build_pypi_purl,
    compute_doc_uuid,
    generate_spdx_id,
)
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.ids import IdRegistry


def _build_creation_bundle(
    doc: DocumentModel, doc_uuid: str
) -> tuple[spdx3.CreationInfo, list[spdx3.Agent], list[spdx3.Tool]]:
    """Create shared SPDX creation objects for the document."""
    return build_creation_info(doc.creation_metadata, doc.project.name, doc_uuid)


def _build_main_package(
    doc: DocumentModel,
    spdx_ci: spdx3.CreationInfo,
    agents: list[spdx3.Agent],
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
    # the SBOM tool, not the package's supplier.  suppliedBy is single-valued
    # in SPDX 3, so when multiple creators are named, the *first* one is used.
    if creation_metadata.creators:
        main_package.suppliedBy = agents[0].spdxId
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

    return main_package


def _add_package_files(
    doc: DocumentModel,
    main_package: spdx3.software_Package,
    spdx_ci: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    registry: IdRegistry | None = None,
) -> dict[str, str]:
    """Add package files and directory containment relationships.

    When *registry* is given, each wheel file's id is looked up by its
    physical (project-root-relative) path and content hash
    (:meth:`~pitloom.ids.IdRegistry.lookup_file`); a match reuses the
    registered ``spdxId`` instead of minting a fresh one, so this element and
    the ``software_File`` a ``pitloom.loom`` fragment emits for the same
    script become literally the same element once merged (see
    :func:`pitloom.assemble.spdx3.fragments.merge_fragments`). A miss (not
    registered, or a stale/mismatched hash) falls back to the existing
    deterministic minting -- unchanged behaviour when no registry applies.
    """
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

        registered_id = (
            registry.lookup_file(package_file.physical_path, package_file.digest_sha256)
            if registry is not None
            else None
        )
        package_entry = spdx3.software_File(
            spdxId=registered_id
            or generate_spdx_id("File", doc_name=metadata.name, doc_uuid=doc_uuid),
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


# pylint: disable=too-many-locals
def build(
    doc: DocumentModel,
    merkle_root: str | None = None,
    *,
    sbom_type: Any = spdx3.software_SbomType.source,
    registry: IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
) -> Spdx3JsonExporter:
    """Assemble SPDX 3 elements from a :class:`~pitloom.core.document.DocumentModel`."""
    metadata = doc.project
    prov_cfg = provenance or ProvenanceConfig()
    encoder: ProvenanceEncoder = resolve_encoder(prov_cfg.schema)

    exporter = Spdx3JsonExporter()
    doc_uuid = compute_doc_uuid(
        name=metadata.name,
        version=metadata.version or "unknown",
        dependencies=metadata.dependencies,
        merkle_root=merkle_root,
    )
    _clear_doc_counters(doc_uuid)

    # --- Creation info, creator agents, and creation tools ---
    spdx_ci, agents, tools = _build_creation_bundle(doc, doc_uuid)

    exporter.add_creation_info(spdx_ci)
    for agent in agents:
        exporter.add_agent(agent)
    for tool in tools:
        exporter.object_set.add(tool)

    # --- Main package ---
    main_package = _build_main_package(doc, spdx_ci, agents, doc_uuid)

    # --- SBOM and document envelope ---
    sbom = spdx3.software_Sbom(
        spdxId=generate_spdx_id("Sbom", doc_name=metadata.name, doc_uuid=doc_uuid),
        creationInfo=spdx_ci,
        rootElement=[main_package.spdxId],
    )
    sbom.software_sbomType = [sbom_type]

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
    emit_provenance(
        subject=main_package,
        provenance=metadata.provenance,
        creation_info=spdx_ci,
        doc_name=metadata.name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=prov_cfg,
        encoder=encoder,
    )

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
            # G2: only the pyproject.toml [project]-path extractor populates
            # license_concluded (independent directory scan) -- None here for
            # any other backend, which keeps this the original single-value
            # behavior unchanged.
            concluded_license_id=metadata.license_concluded,
            concluded_license_provenance=metadata.provenance.get("license_concluded"),
            provenance_config=prov_cfg,
            encoder=encoder,
        )
        if rel_declared:
            exporter.add_relationship(rel_declared)
        if rel_concluded:
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
        provenance_config=prov_cfg,
        encoder=encoder,
    )

    # --- Files ---
    file_spdx_ids = _add_package_files(
        doc, main_package, spdx_ci, doc_uuid, exporter, registry
    )

    # --- Phantom Dependencies ---
    if doc.phantom_dependencies:
        add_phantom_dependencies(
            phantom_deps=doc.phantom_dependencies,
            main_package_spdx_id=require_spdx_id(main_package),
            file_spdx_ids=file_spdx_ids,
            creation_info=spdx_ci,
            doc_name=metadata.name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=prov_cfg,
            encoder=encoder,
        )

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
            registry=registry,
            provenance_config=prov_cfg,
            encoder=encoder,
        )

    return exporter


# # pylint: disable=too-many-locals
def build_model(
    model: AiModelMetadata,
    creation_metadata: CreationMetadata,
    *,
    entity_spdx_id: str | None = None,
    provenance: ProvenanceConfig | None = None,
) -> Spdx3JsonExporter:
    """Assemble a standalone SPDX 3 SBOM for a single AI model file."""
    doc_name: str = model.name or model.format_info.file_name or "model"
    prov_cfg = provenance or ProvenanceConfig()
    encoder: ProvenanceEncoder = resolve_encoder(prov_cfg.schema)

    exporter = Spdx3JsonExporter()
    doc_uuid = compute_doc_uuid(
        name=doc_name,
        version=model.version or "unknown",
        dependencies=[],
        merkle_root=None,
    )
    _clear_doc_counters(doc_uuid)

    spdx_ci, agents, tools = build_creation_info(creation_metadata, doc_name, doc_uuid)

    exporter.add_creation_info(spdx_ci)
    for agent in agents:
        exporter.add_agent(agent)
    for tool in tools:
        exporter.object_set.add(tool)

    ai_pkg = _build_ai_package(model, spdx_ci, doc_name, doc_uuid)
    if entity_spdx_id is not None:
        ai_pkg.spdxId = entity_spdx_id
    exporter.add_package(ai_pkg)
    lineage_ctx = _LineageContext(
        creation_info=spdx_ci,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
    )
    _add_base_model_lineage(ai_pkg, model, lineage_ctx)
    emit_provenance(
        subject=ai_pkg,
        provenance=model.provenance,
        creation_info=spdx_ci,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=prov_cfg,
        encoder=encoder,
    )
    _emit_source_metadata(
        model,
        ai_pkg,
        {},
        prov_cfg.preserve_source_metadata,
        spdx_ci,
        doc_name,
        doc_uuid,
        exporter,
    )

    if model.datasets:
        add_datasets_for_model(
            ai_package_spdx_id=require_spdx_id(ai_pkg),
            datasets=model.datasets,
            creation_info=spdx_ci,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=prov_cfg,
            encoder=encoder,
        )

    if model.license:
        rel_declared, rel_concluded = build_license_elements(
            license_id=model.license,
            package_spdx_id=require_spdx_id(ai_pkg),
            license_provenance=model.provenance.get(
                "license", "Source: AI model metadata"
            ),
            creation_info=spdx_ci,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=prov_cfg,
            encoder=encoder,
        )
        if rel_declared:
            exporter.add_relationship(rel_declared)
        if rel_concluded:
            exporter.add_relationship(rel_concluded)

    sbom = spdx3.software_Sbom(
        spdxId=generate_spdx_id("Sbom", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=spdx_ci,
        rootElement=[ai_pkg.spdxId],
    )
    sbom.software_sbomType = [spdx3.software_SbomType.analyzed]

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


# pylint: disable=too-many-locals
def build_deployed(
    doc: DocumentModel,
    env_tree: list[dict[str, Any]],
    *,
    registry: IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
) -> Spdx3JsonExporter:
    """Assemble SPDX 3 elements for a deployed environment."""
    metadata = doc.project
    prov_cfg = provenance or ProvenanceConfig()
    encoder: ProvenanceEncoder = resolve_encoder(prov_cfg.schema)
    exporter = Spdx3JsonExporter()
    doc_uuid = compute_doc_uuid(
        name=metadata.name,
        version=metadata.version or "unknown",
        dependencies=[],
        merkle_root=None,
    )
    _clear_doc_counters(doc_uuid)

    # --- Creation info ---
    spdx_ci, agents, tools = _build_creation_bundle(doc, doc_uuid)
    exporter.add_creation_info(spdx_ci)
    for agent in agents:
        exporter.add_agent(agent)
    for tool in tools:
        exporter.object_set.add(tool)

    # --- Synthetic Main package representing the environment ---
    main_package = _build_main_package(doc, spdx_ci, agents, doc_uuid)
    exporter.add_package(main_package)
    emit_provenance(
        subject=main_package,
        provenance=metadata.provenance,
        creation_info=spdx_ci,
        doc_name=metadata.name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=prov_cfg,
        encoder=encoder,
    )

    # --- First pass: Create software_Package elements ---
    package_spdx_ids: dict[str, str] = {}
    for node in env_tree:
        pkg_info = node.get("package", {})
        dep_name = pkg_info.get("package_name") or pkg_info.get("key", "unknown")
        dep_version = pkg_info.get("installed_version", "unknown")

        lookup_key = pkg_info.get("key", dep_name.lower())
        spdx_id = (
            registry.lookup_entity(lookup_key, "software_Package")
            if registry is not None
            else None
        )
        if spdx_id is None:
            spdx_id = generate_spdx_id(
                "Package", doc_name=metadata.name, doc_uuid=doc_uuid
            )

        dep_package = spdx3.software_Package(
            spdxId=spdx_id,
            name=dep_name,
            creationInfo=spdx_ci,
        )
        dep_package.software_packageVersion = dep_version
        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library

        _enrich_from_installed(
            dep_name,
            dep_package,
            spdx_ci,
            metadata.name,
            doc_uuid,
            exporter,
            provenance_config=prov_cfg,
            encoder=encoder,
        )

        exporter.add_package(dep_package)
        emit_provenance(
            subject=dep_package,
            provenance={"package": "Source: pipdeptree (deployed environment)"},
            creation_info=spdx_ci,
            doc_name=metadata.name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=prov_cfg,
            encoder=encoder,
        )
        package_spdx_ids[pkg_info.get("key", dep_name.lower())] = require_spdx_id(
            dep_package
        )

    # Second pass: Create relationships
    dep_keys_with_parents = set()
    for node in env_tree:
        parent_key = node.get("package", {}).get("key")
        parent_spdx_id = package_spdx_ids.get(parent_key)
        if not parent_spdx_id:
            continue

        for dep in node.get("dependencies", []):
            child_key = dep.get("key")
            dep_keys_with_parents.add(child_key)
            child_spdx_id = package_spdx_ids.get(child_key)
            if child_spdx_id:
                dep_rel = spdx3.Relationship(
                    spdxId=generate_spdx_id(
                        "Relationship", doc_name=metadata.name, doc_uuid=doc_uuid
                    ),
                    from_=parent_spdx_id,
                    to=[child_spdx_id],
                    relationshipType=spdx3.RelationshipType.dependsOn,
                    creationInfo=spdx_ci,
                )
                # No provenance Annotation on the dependsOn edge: the
                # relationship is itself the native record (extraction-source
                # is on the packages). Annotating it would shadow native.
                exporter.add_relationship(dep_rel)

    # Third pass: Link top-level packages to the environment root
    for node in env_tree:
        pkg_key = node.get("package", {}).get("key")
        if pkg_key not in dep_keys_with_parents:
            child_spdx_id = package_spdx_ids.get(pkg_key)
            if child_spdx_id:
                dep_rel = spdx3.Relationship(
                    spdxId=generate_spdx_id(
                        "Relationship", doc_name=metadata.name, doc_uuid=doc_uuid
                    ),
                    from_=require_spdx_id(main_package),
                    to=[child_spdx_id],
                    relationshipType=spdx3.RelationshipType.dependsOn,
                    creationInfo=spdx_ci,
                )
                exporter.add_relationship(dep_rel)

    # --- SBOM and document envelope ---
    sbom = spdx3.software_Sbom(
        spdxId=generate_spdx_id("Sbom", doc_name=metadata.name, doc_uuid=doc_uuid),
        creationInfo=spdx_ci,
        rootElement=[main_package.spdxId],
    )
    sbom.software_sbomType = [spdx3.software_SbomType.deployed]

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
    if exporter.find_license("dummy") is not None or any(
        isinstance(obj, spdx3.simplelicensing_SimpleLicensingText)
        for obj in exporter.object_set.objects
    ):
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.simpleLicensing)

    exporter.add_document(spdx_doc)
    exporter.add_sbom(sbom)

    return exporter
