# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 document assembly for Python projects.

Public entry point / facade: the project-SBOM assembly (:func:`build`) and
its two shared helpers (:func:`_build_creation_bundle`,
:func:`_build_main_package`) live here; file-element assembly, single-model
assembly, deployed-environment assembly, and locked-dependency handling are
split into :mod:`pitloom.assemble.spdx3._document_files`,
:mod:`pitloom.assemble.spdx3._document_model`,
:mod:`pitloom.assemble.spdx3._document_deployed`, and
:mod:`pitloom.assemble.spdx3._document_locked_deps` respectively, and
re-exported below, so each name is importable from this module.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._dep_scope import is_self_reference
from pitloom.assemble.spdx3._document_conflicts import attach_metadata_field_conflicts
from pitloom.assemble.spdx3._document_deployed import build_deployed
from pitloom.assemble.spdx3._document_file_hits import resolve_file_hits
from pitloom.assemble.spdx3._document_files import (
    _add_package_files,
    _emit_file_header_metadata,
    _magika_version,
)
from pitloom.assemble.spdx3._document_locked_deps import (
    _dedup_and_locked_versions,
    _deduplicated_locked_dependencies,
    _extract_locked_version_map,
    _locked_dependencies_completeness,
    _locked_transitive_only_dependencies,
    _prefetch_combined_release_info,
)
from pitloom.assemble.spdx3._document_model import (
    _ai_model_identity,
    build_enrichment_fragment,
    build_model,
)
from pitloom.assemble.spdx3._licensing_profiles import apply_licensing_profiles
from pitloom.assemble.spdx3._main_authors import add_main_package_originators
from pitloom.assemble.spdx3._package_ids import resolve_project_package_ids
from pitloom.assemble.spdx3._reserved_ids import model_dataset_keys, reserve_held_ids
from pitloom.assemble.spdx3.ai import add_ai_models, resolve_ai_model_entity_hits
from pitloom.assemble.spdx3.creation_info import (
    build_creation_info,
    parse_iso_datetime,
    to_spdx3_datetime,
)
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.assemble.spdx3.deps_installed import _DEFAULT_LOCKED_PROVENANCE
from pitloom.assemble.spdx3.deps_license import attach_main_package_license
from pitloom.assemble.spdx3.deps_phantom import add_phantom_dependencies
from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    emit_provenance,
    resolve_encoder,
)
from pitloom.core.document import DocumentModel
from pitloom.core.models import (
    _clear_doc_counters,
    build_pypi_purl,
    compute_doc_uuid,
    generate_spdx_id,
)
from pitloom.core.provenance import ProvenanceConfig
from pitloom.core.requirements import normalize_dependency_specifier
from pitloom.enrich.base import EnrichmentResult
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash
from pitloom.extract.authors import dependency_author_splits
from pitloom.extract.copyright_notices import COPYRIGHT_NOASSERTION
from pitloom.id_registry import IdRegistry, IdRegistrySession, info_identity_unknown

__all__ = [
    "_ai_model_identity",
    "_add_package_files",
    "_deduplicated_locked_dependencies",
    "_emit_file_header_metadata",
    "_extract_locked_version_map",
    "_locked_dependencies_completeness",
    "_locked_transitive_only_dependencies",
    "_magika_version",
    "_prefetch_combined_release_info",
    "build",
    "build_deployed",
    "build_enrichment_fragment",
    "build_model",
]


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
    resolved_id: str | None = None,
) -> spdx3.software_Package:
    """Create the SPDX package representing the Python project.

    *resolved_id* is the pre-resolved registry id (see
    :func:`~pitloom.assemble.spdx3._package_ids.resolve_project_package_ids`);
    ``None`` mints one.
    """
    metadata = doc.project
    creation_metadata = doc.creation_metadata
    download_location = metadata.urls.get("Source") or metadata.urls.get("Homepage")
    main_package = spdx3.software_Package(
        spdxId=resolved_id
        or generate_spdx_id("Package", doc_name=metadata.name, doc_uuid=doc_uuid),
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
    # The notices found in its licence files; none found is no assertion.
    main_package.software_copyrightText = (
        metadata.copyright_text or COPYRIGHT_NOASSERTION
    )
    main_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
    if creation_metadata.build_datetime:
        # The same parse as CreationInfo.created: "Z" on every Python,
        # offsets converted to UTC, whole seconds.
        main_package.builtTime = to_spdx3_datetime(
            parse_iso_datetime(creation_metadata.build_datetime)
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
                    "SHA-256 Merkle root over the payload files; "
                    "not a hash of a single artifact"
                ),
            )
        ]

    return main_package


def _canonical(dependencies: list[str]) -> list[str]:
    """*dependencies* as the SBOM shows them, one rule whichever route
    read them (a setuptools wheel keeps ``Foo_Bar``, a ``[project]`` read
    gives ``foo-bar``): the PEP 503 name the ``pkg:pypi`` PURL uses, and
    ``packaging``'s spelling of the rest
    (:func:`~pitloom.core.requirements.normalize_dependency_specifier`)."""
    return [normalize_dependency_specifier(d, quiet=True) for d in dependencies]


def _with_canonical_dependencies(doc: DocumentModel) -> DocumentModel:
    """*doc* with its project's dependencies :func:`_canonical`."""
    project = dataclasses.replace(
        doc.project, dependencies=_canonical(doc.project.dependencies)
    )
    return dataclasses.replace(doc, project=project)


def _with_recorded_keys(
    exporter: Spdx3JsonExporter, session: IdRegistrySession
) -> Spdx3JsonExporter:
    """*exporter*, given the registry keys *session*'s lookups recorded
    (:attr:`~pitloom.export.spdx3_json.Spdx3JsonExporter.registry_keys`),
    after the one ``INFO:`` counting its layout-alias hits
    (:meth:`~pitloom.id_registry.IdRegistrySession.info_layout_alias_hits`)."""
    session.info_layout_alias_hits()
    exporter.registry_keys.update(session.recorded_keys())
    return exporter


# pylint: disable=too-many-locals
# pylint: disable-next=too-many-arguments
def build(
    doc: DocumentModel,
    merkle_root: str | None = None,
    *,
    sbom_type: Any = spdx3.software_SbomType.source,
    registry: IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrichment_results_by_model: list[list[EnrichmentResult]] | None = None,
    offline: bool = False,
    content_type_method: str = "auto",
    identity_info_due: Callable[[], bool] | None = None,
) -> Spdx3JsonExporter:
    """Assemble SPDX 3 elements from a :class:`~pitloom.core.document.DocumentModel`.

    ``enrichment_results_by_model``, when given, is one
    ``list[EnrichmentResult]`` per ``doc.ai_models`` element, same order --
    see :func:`~pitloom.assemble.spdx3.ai.add_ai_models`.

    ``offline``: when ``False`` (the default), each dependency package's
    supplier/license/copyright gaps left by installed metadata are given a
    best-effort PyPI JSON API lookup before the licence is left unstated and
    the copyright is ``NOASSERTION`` -- see
    :func:`~pitloom.assemble.spdx3.deps.add_dependencies`.
    """
    doc = _with_canonical_dependencies(doc)
    metadata = doc.project
    prov_cfg = provenance or ProvenanceConfig()
    encoder: ProvenanceEncoder = resolve_encoder(prov_cfg.schema)

    exporter = Spdx3JsonExporter()
    doc_uuid = compute_doc_uuid(
        name=metadata.name,
        version=metadata.version or "unknown",
        dependencies=metadata.dependencies,
        merkle_root=merkle_root,
        locked_dependencies=metadata.locked_dependencies,
        locked_dependencies_provenance=metadata.provenance.get("locked_dependencies"),
        identity_seed=doc.identity_seed,
    )
    _clear_doc_counters(doc_uuid)
    # Deduplicated once and shared below: a genuine name/version conflict
    # in metadata.locked_dependencies must warn exactly once per document,
    # not once per function that would otherwise recompute it, and each
    # entry's pin is parsed once, not once per consumer.
    deduplicated_locked, locked_versions = _dedup_and_locked_versions(
        metadata.locked_dependencies
    )
    transitive_only = _canonical(
        _locked_transitive_only_dependencies(
            metadata, deduplicated_locked=deduplicated_locked
        )
    )
    # One shared session across files, directories, AI models and packages:
    # a registry hit any of them resolves is claimed by whichever comes
    # first below, so two elements never reuse the same stale id -- see
    # IdRegistrySession's docstring. Every lookup precedes the reservation.
    session = IdRegistrySession(registry)
    file_hits = resolve_file_hits(doc, session)
    model_hits = resolve_ai_model_entity_hits(
        doc.ai_models,
        session,
        doc.project.files,
        keys=file_hits.keys,
        prefix=file_hits.prefix,
    )
    package_ids = resolve_project_package_ids(doc, transitive_only, session)
    reserve_held_ids(
        metadata.name, doc_uuid, session, unlooked=model_dataset_keys(doc.ai_models)
    )

    # --- Creation info, creator agents, and creation tools ---
    spdx_ci, agents, tools = _build_creation_bundle(doc, doc_uuid)

    exporter.add_creation_info(spdx_ci)
    for agent in agents:
        exporter.add_agent(agent)
    for tool in tools:
        exporter.object_set.add(tool)

    # --- Main package ---
    main_package = _build_main_package(
        doc, spdx_ci, agents, doc_uuid, merkle_root, package_ids.main
    )

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
    if not doc.identity_known:
        exporter.registry_non_readers.add(require_spdx_id(main_package))
        if registry is not None and (identity_info_due is None or identity_info_due()):
            info_identity_unknown()
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
    attach_main_package_license(
        metadata=metadata,
        main_package=main_package,
        spdx_ci=spdx_ci,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=prov_cfg,
        encoder=encoder,
    )

    # --- Metadata field conflicts (e.g. an in-tree .egg-info/.dist-info
    # disagreeing with the static source) ---
    attach_metadata_field_conflicts(
        metadata=metadata,
        main_package=main_package,
        creation_info=spdx_ci,
        doc_uuid=doc_uuid,
        exporter=exporter,
    )

    # --- Locked (e.g. poetry.lock-resolved) transitive-only dependencies ---
    release_info_cache = (
        None
        if offline
        else _prefetch_combined_release_info(
            [
                dep
                for dep in metadata.dependencies
                if not is_self_reference(dep, metadata.name)
            ],
            transitive_only,
            locked_versions=locked_versions,
        )
    )

    # --- Dependencies ---
    locked_dependencies_provenance = metadata.provenance.get(
        "locked_dependencies", _DEFAULT_LOCKED_PROVENANCE
    )
    # One author-split warning for every dependency of the document.
    with dependency_author_splits():
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
            content_type_method=content_type_method,
            release_info_cache=release_info_cache,
            locked_versions=locked_versions,
            locked_provenance=locked_dependencies_provenance,
            locked_hashes=metadata.locked_dependency_hashes,
            resolved_ids=package_ids.dependencies,
            project_name=metadata.name,
        )

        if transitive_only:
            add_dependencies(
                dependencies=transitive_only,
                dep_provenance=locked_dependencies_provenance,
                main_package_spdx_id=require_spdx_id(main_package),
                creation_info=spdx_ci,
                doc_name=metadata.name,
                doc_uuid=doc_uuid,
                exporter=exporter,
                offline=offline,
                provenance_config=prov_cfg,
                encoder=encoder,
                content_type_method=content_type_method,
                release_info_cache=release_info_cache,
                completeness=_locked_dependencies_completeness(metadata),
                locked_hashes=metadata.locked_dependency_hashes,
                resolved_ids=package_ids.dependencies,
                project_name=metadata.name,
            )

    # --- Files ---
    file_spdx_ids = _add_package_files(
        doc,
        main_package,
        spdx_ci,
        doc_uuid,
        exporter,
        file_hits,
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
            resolved_ids=package_ids.phantom,
            not_looked_up=package_ids.phantom_not_looked_up,
        )

    # --- AI models (and their associated datasets) ---
    if doc.ai_models:
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.ai)
        if any(m.datasets for m in doc.ai_models):
            spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.dataset)
        # Each model's key recorded for the id it got, as each file's is.
        model_hits.record(
            add_ai_models(
                ai_models=doc.ai_models,
                main_package_spdx_id=require_spdx_id(main_package),
                file_spdx_ids=file_spdx_ids,
                creation_info=spdx_ci,
                doc_name=metadata.name,
                doc_uuid=doc_uuid,
                exporter=exporter,
                resolved_entity_ids=model_hits.ids,
                provenance_config=prov_cfg,
                encoder=encoder,
                enrichment_results_by_model=enrichment_results_by_model,
            )
        )

    # --- Authors, last: no Agent minted earlier changes id ---
    add_main_package_originators(
        main_package,
        metadata,
        # A named creator per Agent; none: the one SoftwareAgent "Pitloom".
        (
            list(zip(doc.creation_metadata.creators, agents, strict=True))
            if doc.creation_metadata.creators
            else []
        ),
        spdx_ci,
        doc_uuid,
        exporter,
        offline=offline,
    )

    apply_licensing_profiles(spdx_doc, exporter.object_set.objects)
    # Last: after every lookup and record_key of this build.
    return _with_recorded_keys(exporter, session)
