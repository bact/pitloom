# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 document assembly for Python projects."""

from __future__ import annotations

from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
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
from pitloom.assemble.spdx3.creation_info import (
    build_creation_info,
    build_enrichment_elements,
)
from pitloom.assemble.spdx3.dataset import add_datasets_for_model
from pitloom.assemble.spdx3.deps import (
    _add_license_noassertion,
    _finish_dependency_enrichment,
    _prefetch_pypi_release_infos,
    add_dependencies,
    add_phantom_dependencies,
    build_file_declared_license,
    build_license_elements,
)
from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    build_enrichment_annotation,
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
from pitloom.core.project import ProjectFile
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich.base import EnrichmentResult
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash
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
    merkle_root: str | None = None,
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

    # verifiedUsing -- the same Merkle root already folded into doc_uuid
    # (see compute_doc_uuid), asserted here as the package's own integrity
    # hash so NTIA/CISA "integrity hash" coverage extends to the main
    # package itself, not just its individual files.
    if merkle_root is not None:
        main_package.verifiedUsing = [
            sha256_hash(
                merkle_root,
                comment=(
                    "SHA-256 Merkle root over all files included in the wheel, "
                    "not a hash of a single artifact"
                ),
            )
        ]

    return main_package


# SPDX 2.x FileType -> SPDX 3 SoftwarePurpose: only the categories with a
# clean, identity-shaped equivalent. BINARY/AUDIO/IMAGE/TEXT/VIDEO
# (media-kind categories) and anything unrecognized have no
# SoftwarePurpose equivalent -- SPDX 3's own spec is explicit that
# SoftwarePurpose is "intrinsic to how the Element is being used rather
# than the content of the Element", a genuinely different axis from a
# file's content/media kind. Never derive a mapping from `contentType`
# for these -- see working-docs/design/file-headers.md.
_FILE_TYPE_TO_SOFTWARE_PURPOSE: dict[str, str] = {
    "SOURCE": spdx3.software_SoftwarePurpose.source,
    "ARCHIVE": spdx3.software_SoftwarePurpose.archive,
    "APPLICATION": spdx3.software_SoftwarePurpose.application,
    "DOCUMENTATION": spdx3.software_SoftwarePurpose.documentation,
    "OTHER": spdx3.software_SoftwarePurpose.other,
    "SPDX": spdx3.software_SoftwarePurpose.bom,
}


def _magika_version() -> str:
    """Best-effort ``magika`` package version for the ``detected``-role
    provenance ``Tool:`` segment. Falls back to ``"unknown"`` if the
    version can't be resolved -- shouldn't happen in practice, since
    ``content_type_method == "magika"`` is only ever set after ``magika``
    actually ran successfully earlier in this same process."""
    try:
        return _pkg_version("magika")
    except PackageNotFoundError:
        return "unknown"


def _emit_file_header_metadata(
    package_entry: spdx3.software_File,
    package_file: ProjectFile,
    spdx_ci: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None,
    encoder: ProvenanceEncoder | None,
) -> None:
    """Wire one file's SPDX-header-derived metadata onto *package_entry*.

    Native fields (``software_copyrightText``, ``software_primaryPurpose``,
    ``contentType``, a ``hasDeclaredLicense`` relationship) get their
    actual value set directly; the accompanying provenance Annotation
    records only *where* each came from -- role ``declared`` for
    everything read from the file's own header, ``detected`` for
    ``content_type`` (Pitloom's own detection, not the file's claim) --
    see ``working-docs/implementation/annotation-provenance.md``'s role
    vocabulary. ``file_type``/``file_contributors`` values with no native
    SPDX 3 slot go into ``package_entry.summary`` instead, as one sorted
    ``"Key: value; Key: value"`` string -- never onto
    ``software_primaryPurpose``/``software_additionalPurpose``, which the
    SPDX 3 spec defines as being about usage, not content.

    Nothing is emitted when *package_file* carries no header-derived data
    at all (every field checked here is falsy) -- a project can have
    thousands of files; only ones that actually said something get an
    entry, unlike the dependency-completeness ``NOASSERTION`` policy in
    :mod:`pitloom.assemble.spdx3.deps`, which applies to a handful of
    packages, not every source file.
    """
    file_path = package_file.physical_path
    field_provenance: dict[str, str] = {}
    summary_entries: list[tuple[str, str]] = []

    if package_file.copyright_text:
        package_entry.software_copyrightText = package_file.copyright_text
        field = (
            "SPDX-FileCopyrightText"
            if package_file.copyright_source == "spdx_tag"
            else "bare Copyright line"
        )
        field_provenance["copyright_text"] = f"Source: {file_path} | Field: {field}"

    if package_file.file_type:
        purpose = _FILE_TYPE_TO_SOFTWARE_PURPOSE.get(package_file.file_type)
        if purpose:
            package_entry.software_primaryPurpose = purpose
            field_provenance["file_type"] = (
                f"Source: {file_path} | Field: SPDX-FileType"
            )
        else:
            summary_entries.append(("FileType", package_file.file_type))

    if package_file.content_type:
        package_entry.contentType = package_file.content_type
        method = (
            f"Method: magika_content_detection | Tool: magika=={_magika_version()}"
            if package_file.content_type_method == "magika"
            else "Method: mimetype_extension_guess"
        )
        field_provenance["content_type"] = f"Source: {file_path} | {method}"

    if package_file.file_contributors:
        summary_entries.extend(
            ("Contributor", name) for name in package_file.file_contributors
        )
        field_provenance["file_contributors"] = (
            f"Source: {file_path} | Field: SPDX-FileContributor"
        )

    if summary_entries:
        summary_entries.sort()
        package_entry.summary = "; ".join(f"{k}: {v}" for k, v in summary_entries)

    if field_provenance:
        emit_provenance(
            subject=package_entry,
            provenance=field_provenance,
            creation_info=spdx_ci,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

    if package_file.spdx_license_identifier:
        exporter.add_relationship(
            build_file_declared_license(
                package_file.spdx_license_identifier,
                require_spdx_id(package_entry),
                f"Source: {file_path} | Field: SPDX-License-Identifier",
                spdx_ci,
                doc_name,
                doc_uuid,
                exporter,
                provenance_config=provenance_config,
                encoder=encoder,
            )
        )


# pylint: disable=too-many-locals
def _add_package_files(
    doc: DocumentModel,
    main_package: spdx3.software_Package,
    spdx_ci: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    registry: IdRegistry | None = None,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
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

    When a ``package_file`` carries SPDX-header-derived data (see
    :class:`pitloom.core.project.ProjectFile`), it's wired onto the
    resulting ``software_File`` element by
    :func:`_emit_file_header_metadata` -- *provenance_config*/*encoder*
    are forwarded there.
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
        package_entry.verifiedUsing = [sha256_hash(package_file.digest_sha256)]
        exporter.add_file(package_entry)
        _emit_file_header_metadata(
            package_entry,
            package_file,
            spdx_ci,
            metadata.name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
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
    enrichment_results_by_model: list[list[EnrichmentResult]] | None = None,
    offline: bool = False,
) -> Spdx3JsonExporter:
    """Assemble SPDX 3 elements from a :class:`~pitloom.core.document.DocumentModel`.

    ``enrichment_results_by_model``, when given, is one
    ``list[EnrichmentResult]`` per ``doc.ai_models`` element, same order --
    see :func:`~pitloom.assemble.spdx3.ai.add_ai_models`.

    ``offline``: when ``False`` (the default), each dependency package's
    supplier/license/copyright gaps left by installed metadata are given a
    best-effort PyPI JSON API lookup before falling back to ``NOASSERTION``
    -- see :func:`~pitloom.assemble.spdx3.deps.add_dependencies`.
    """
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
    main_package = _build_main_package(doc, spdx_ci, agents, doc_uuid, merkle_root)

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
    else:
        # No license declared anywhere pitloom looked -- assert that
        # explicitly rather than silently omitting the field; see
        # add_dependencies' identical NOASSERTION policy for dependencies.
        _add_license_noassertion(
            main_package,
            spdx_ci,
            metadata.name,
            doc_uuid,
            exporter,
            provenance_config=prov_cfg,
            encoder=encoder,
        )
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
        offline=offline,
        provenance_config=prov_cfg,
        encoder=encoder,
    )

    # --- Files ---
    file_spdx_ids = _add_package_files(
        doc,
        main_package,
        spdx_ci,
        doc_uuid,
        exporter,
        registry,
        provenance_config=prov_cfg,
        encoder=encoder,
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
            enrichment_results_by_model=enrichment_results_by_model,
        )

    return exporter


def _ai_model_identity(
    model: AiModelMetadata,
    *,
    doc_identity: tuple[str, str] | None = None,
    entity_spdx_id: str | None = None,
) -> tuple[str, str, str]:
    """Compute ``(doc_name, doc_uuid, ai_package_spdx_id)`` for a model file.

    By default, deterministic from the model's own name/version/format --
    identical to whatever :func:`build_model` computes for the same model
    when it stands alone as a single-model document, and to what
    :func:`~pitloom.assemble.spdx3.ai._build_ai_package` assigns as the
    ``ai_AIPackage`` spdxId in that case. Shared so a standalone
    enrichment fragment (:func:`build_enrichment_fragment`) always
    references the exact same subject id a full model SBOM would, letting
    the two merge cleanly.

    ``doc_identity``, when given, overrides ``(doc_name, doc_uuid)`` --
    e.g. a *project's* own identity (see
    :func:`~pitloom.assemble.enrich_model`'s ``project_target``
    parameter), for a model that will be embedded in a project-level
    document (``generate_project_sbom()``/the Hatchling build hook) rather
    than standing alone. The single-model and project-level identity
    schemes are **not interchangeable** -- a project-level document's
    ``doc_uuid`` is derived from the *project's* name/version/dependencies/
    Merkle root, not the model's, so a fragment built with the wrong one
    references an id that does not exist in the intended base document.

    ``entity_spdx_id``, when given, overrides the computed
    ``ai_package_spdx_id`` entirely -- e.g. one already resolved from an
    :class:`~pitloom.ids.IdRegistry`, matching what the base document
    (generated separately, with the same registry) will use.

    Clears the resolved ``doc_uuid``'s id counters immediately before
    minting ``ai_package_spdx_id`` (skipped when ``entity_spdx_id`` makes
    that unnecessary) -- ``generate_spdx_id``'s per-prefix counters are a
    process-wide side effect, so without this, a second call for the same
    model/project in the same process (e.g. an ``enrich_model()`` call
    followed by a ``generate_model_sbom()`` call, or simply two
    ``enrich_model()`` calls in a row) would silently mint a *different*,
    stale-incremented id instead of the deterministic first one. Callers
    that build a full document (:func:`build_model`) already re-clear
    right after calling this, so this is a safe no-op for them; callers
    that only need the identity tuple (:func:`build_enrichment_fragment`)
    depend on this clear to get the correct, reproducible id.
    """
    if doc_identity is not None:
        doc_name, doc_uuid = doc_identity
    else:
        doc_name = model.name or model.format_info.file_name or "model"
        doc_uuid = compute_doc_uuid(
            name=doc_name,
            version=model.version or "unknown",
            dependencies=[],
            merkle_root=None,
        )
    if entity_spdx_id is not None:
        return doc_name, doc_uuid, entity_spdx_id
    _clear_doc_counters(doc_uuid)
    pkg_name = model.name or str(model.format_info.model_format)
    ai_package_spdx_id = generate_spdx_id(
        f"AIPackage-{pkg_name}", doc_name=doc_name, doc_uuid=doc_uuid
    )
    return doc_name, doc_uuid, ai_package_spdx_id


def build_enrichment_fragment(
    model: AiModelMetadata,
    enrichment_results: list[EnrichmentResult],
    creation_metadata: CreationMetadata | None = None,
    *,
    entity_spdx_id: str | None = None,
    base_doc_identity: tuple[str, str] | None = None,
) -> Spdx3JsonExporter:
    """Assemble a standalone enrichment-only SPDX 3 fragment.

    Contains only what an enrichment run adds -- N3 CreationInfo(s)/Tool(s),
    any newly-created dataset elements, and the E1/E2 "enrichment" Annotation
    -- against the exact ``ai_AIPackage`` spdxId the intended base document
    would assign for the same model (see :func:`_ai_model_identity`). No
    ``ai_AIPackage``, ``software_Sbom``, or ``SpdxDocument`` element is
    included: this is a bare ``@graph`` fragment meant for
    ``merge_fragments()``, matching the wrapper-free shape
    ``working-docs/design/sbom-fragments.md`` documents and
    :mod:`pitloom.loom` already produces.

    ``entity_spdx_id``/``base_doc_identity`` are forwarded to
    :func:`_ai_model_identity` -- see that function's docstring for when
    each applies. Without either, this defaults to the single-model
    identity (correct when the fragment is meant to merge into a
    ``build_model()``-produced base document, e.g. from ``loom model``);
    pass ``base_doc_identity`` when the base document instead comes from
    ``generate_project_sbom()``/the Hatchling build hook, since those use
    a *different*, project-derived identity scheme for the same model's
    ``ai_AIPackage`` -- referencing the wrong one produces a fragment
    whose ``Annotation.subject``/dataset ``Relationship.from`` point at an
    id that does not exist in the merged result.

    Every element this function mints (CreationInfo(s), Tool(s), Agent(s),
    any new dataset package, the Annotation) is built under its own
    ``doc_uuid``, deliberately distinct from the base document's --
    ``generate_spdx_id``'s per-prefix counters are purely
    sequential-by-call-order within a single build, so reusing the base
    document's ``doc_uuid`` here would risk an accidental id collision
    with an unrelated base-document element once merged (e.g. this
    fragment's lone "enrichment" Annotation landing on ``Annotation-1``
    while the base document's own first annotation is something else
    entirely) -- ``merge_fragments()`` would then treat them as "the same
    element, conflicting content" and silently drop one, exactly the
    failure this separate namespace avoids. ``ai_package_spdx_id`` is the
    one exception: it is a *reference* to an element that already lives in
    the base document's namespace, so only it keeps using the base
    identity. ``merge_fragments()`` unifies ``Agent``/``Tool`` elements by
    structural equality (same name/type) when spdxIds don't match, so this
    fragment's own freshly-minted "Pitloom" Agent still collapses into the
    base document's real one after merge -- N3's "same createdBy identity"
    requirement (see :func:`build_enrichment_creation_info`) holds even
    though the ids themselves differ pre-merge.
    """
    doc_name, _base_doc_uuid, ai_package_spdx_id = _ai_model_identity(
        model, doc_identity=base_doc_identity, entity_spdx_id=entity_spdx_id
    )
    doc_uuid = compute_doc_uuid(
        name=f"{doc_name}-enrichment",
        version=model.version or "unknown",
        dependencies=[],
        merkle_root=None,
    )
    _clear_doc_counters(doc_uuid)

    exporter = Spdx3JsonExporter()
    spdx_ci, agents, tools = build_creation_info(
        creation_metadata or CreationMetadata(), doc_name, doc_uuid
    )
    exporter.add_creation_info(spdx_ci)
    for agent in agents:
        exporter.add_agent(agent)
    for tool in tools:
        exporter.object_set.add(tool)

    dataset_creation_info, annotation_groups = build_enrichment_elements(
        enrichment_results, spdx_ci, doc_name, doc_uuid, exporter
    )

    new_datasets = [
        dataset_ref
        for dataset_ref in model.datasets
        if dataset_ref.metadata.name in dataset_creation_info
    ]
    if new_datasets:
        add_datasets_for_model(
            ai_package_spdx_id=ai_package_spdx_id,
            datasets=new_datasets,
            creation_info=spdx_ci,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            dataset_creation_info=dataset_creation_info,
        )

    for enrich_ci, changes in annotation_groups:
        exporter.add_annotation(
            build_enrichment_annotation(
                subject_spdx_id=ai_package_spdx_id,
                changes=changes,
                creation_info=enrich_ci,
                annotation_spdx_id=generate_spdx_id(
                    "Annotation", doc_name=doc_name, doc_uuid=doc_uuid
                ),
            )
        )

    return exporter


# pylint: disable=too-many-locals
def build_model(
    model: AiModelMetadata,
    creation_metadata: CreationMetadata,
    *,
    entity_spdx_id: str | None = None,
    provenance: ProvenanceConfig | None = None,
    enrichment_results: list[EnrichmentResult] | None = None,
) -> Spdx3JsonExporter:
    """Assemble a standalone SPDX 3 SBOM for a single AI model file."""
    prov_cfg = provenance or ProvenanceConfig()
    encoder: ProvenanceEncoder = resolve_encoder(prov_cfg.schema)

    exporter = Spdx3JsonExporter()
    doc_name, doc_uuid, _ = _ai_model_identity(model)
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

    # N3 / E1 / E2: an enrichment run's newly-created dataset elements get
    # their own CreationInfo (N3); every changed field -- new datasets and
    # fields filled in place on the AI package itself -- becomes one entry
    # in an "enrichment" Annotation on the AI package (E1/E2), one per
    # source, each using that source's own CreationInfo (see
    # build_enrichment_elements()'s docstring for why -- the Annotation is
    # the only place an existing element's field-fill provenance can live,
    # so it must carry the enrichment tool/timestamp, not the document's).
    # See build_enrichment_creation_info()'s docstring for why N3 only
    # covers new elements, not in-place field fills.
    dataset_creation_info, annotation_groups = build_enrichment_elements(
        enrichment_results or [], spdx_ci, doc_name, doc_uuid, exporter
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
            dataset_creation_info=dataset_creation_info,
        )

    for enrich_ci, changes in annotation_groups:
        exporter.add_annotation(
            build_enrichment_annotation(
                subject_spdx_id=require_spdx_id(ai_pkg),
                changes=changes,
                creation_info=enrich_ci,
                annotation_spdx_id=generate_spdx_id(
                    "Annotation", doc_name=doc_name, doc_uuid=doc_uuid
                ),
            )
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
    offline: bool = False,
) -> Spdx3JsonExporter:
    """Assemble SPDX 3 elements for a deployed environment.

    ``offline``: forwarded to :func:`~pitloom.assemble.spdx3.deps.
    _finish_dependency_enrichment` for each installed package -- see
    :func:`~pitloom.assemble.spdx3.deps.add_dependencies` for what it
    controls.
    """
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

    # PyPI lookups for every installed package are fetched concurrently up
    # front -- see add_dependencies' identical rationale -- rather than
    # one-by-one inside the loop below, which would otherwise cost roughly
    # one blocking network round-trip per package in the environment.
    release_info_cache = (
        None
        if offline
        else _prefetch_pypi_release_infos(
            (
                node.get("package", {}).get("package_name")
                or node.get("package", {}).get("key", "unknown"),
                node.get("package", {}).get("installed_version", "unknown"),
            )
            for node in env_tree
        )
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

        _finish_dependency_enrichment(
            dep_name,
            dep_version,
            dep_package,
            spdx_ci,
            metadata.name,
            doc_uuid,
            exporter,
            offline=offline,
            release_info_cache=release_info_cache,
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
