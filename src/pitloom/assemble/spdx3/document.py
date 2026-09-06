# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 document assembly for Python projects.

Public entry point / facade: the project-SBOM assembly (:func:`build`) and
its two shared helpers (:func:`_build_creation_bundle`,
:func:`_build_main_package`) live here; file-element assembly, single-model
assembly, and deployed-environment assembly are split into
:mod:`pitloom.assemble.spdx3._document_files`,
:mod:`pitloom.assemble.spdx3._document_model`, and
:mod:`pitloom.assemble.spdx3._document_deployed` respectively, and
re-exported below so every previously-public name is still importable from
this module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packaging.utils import canonicalize_name
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._document_deployed import build_deployed
from pitloom.assemble.spdx3._document_files import (
    _add_package_files,
    _emit_file_header_metadata,
    _magika_version,
)
from pitloom.assemble.spdx3._document_model import (
    _ai_model_identity,
    build_enrichment_fragment,
    build_model,
)
from pitloom.assemble.spdx3._provenance_encoders import parse_provenance_value
from pitloom.assemble.spdx3.ai import add_ai_models
from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.assemble.spdx3.deps import (
    _parse_dep_name,
    _resolve_version,
    add_dependencies,
    add_phantom_dependencies,
)
from pitloom.assemble.spdx3.deps_installed import _extract_exact_pin
from pitloom.assemble.spdx3.deps_license import (
    _add_license_noassertion,
    build_license_elements,
)
from pitloom.assemble.spdx3.deps_pypi import _prefetch_pypi_release_infos
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
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich.base import EnrichmentResult
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash
from pitloom.ids import IdRegistry

__all__ = [
    "_ai_model_identity",
    "_add_package_files",
    "_emit_file_header_metadata",
    "_magika_version",
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
    created = spdx_ci.created
    if isinstance(created, datetime):
        created_year = created.year
    else:
        created_year = datetime.now(timezone.utc).year
    main_package.software_copyrightText = f"Copyright (c) {created_year} " + (
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


def _locked_transitive_only_dependencies(metadata: ProjectMetadata) -> list[str]:
    """Return *metadata*'s locked (e.g. ``poetry.lock``-resolved) dependencies
    that aren't already a direct dependency, so a package declared both
    directly and in the lock gets one ``dependsOn`` edge, not two.

    Names are compared PEP 503-canonicalized (lowercased, ``-``/``_``/``.``
    folded to ``-``) since a lock file's resolved package names are
    normalized while the author's ``pyproject.toml`` spelling (e.g.
    ``"Django"``) may not be -- comparing raw, unnormalized names would
    treat those as different packages and double-emit the edge this
    function exists to avoid. See ``_try_read_poetry()`` in
    ``pitloom.extract._pyproject`` for why this is source-stage-only.
    """
    direct_names = {
        canonicalize_name(_parse_dep_name(dep)) for dep in metadata.dependencies
    }
    return [
        dep
        for dep in metadata.locked_dependencies
        if canonicalize_name(_parse_dep_name(dep)) not in direct_names
    ]


#: `locked_dependencies` provenance `Method` tags that represent a real
#: resolver's output -- a full, hash-verifiable transitive closure, not
#: just a list of exact pins someone happened to write down. Every
#: format in `pitloom.extract._locked_dependencies`'s cascade uses this
#: tag except pinned `requirements.txt`, whose own `"pinned_requirements"`
#: tag is deliberately excluded below.
_RESOLVED_LOCKFILE_METHOD = "resolved_lockfile"


def _locked_dependencies_completeness(metadata: ProjectMetadata) -> str | None:
    """Return the `RelationshipCompleteness` value for the locked-only
    `dependsOn` edges :func:`_locked_transitive_only_dependencies`
    produces, or `None` to leave it unset.

    A real resolver lock (`poetry.lock`, `pylock.toml`, `uv.lock`,
    `pdm.lock`, `Pipfile.lock` -- every cascade entry tagged
    `Method: resolved_lockfile`) genuinely proves the full transitive
    dependency closure, so its edges are marked `complete`. Every other
    case -- pinned `requirements.txt` (tagged `Method:
    pinned_requirements`, just a list of exact-pin lines a human or `pip
    freeze` wrote, with no resolver guarantee that every real transitive
    dependency is actually present), an unrecognized future `Method` tag,
    or no provenance recorded at all -- returns `None` (unset) instead:
    an inclusion check (only the one tag known to prove completeness
    claims it) rather than an exclusion check, so a future lock source
    that forgets to record its own `Method` tag fails safe to "unset"
    rather than silently defaulting to overstating completeness.
    """
    provenance = metadata.provenance.get("locked_dependencies")
    method = parse_provenance_value(provenance).get("method") if provenance else None
    if method == _RESOLVED_LOCKFILE_METHOD:
        return spdx3.RelationshipCompleteness.complete
    return None


def _extract_locked_version_map(locked_dependencies: list[str]) -> dict[str, str]:
    """Map canonical package names to their exact locked version string.

    Enables direct dependencies declared as ranges (e.g. ``requests>=2.0``)
    to resolve to their authoritative locked version rather than falling back
    to introspecting Pitloom's host environment.
    """
    result: dict[str, str] = {}
    for dep in locked_dependencies:
        dep_name = _parse_dep_name(dep)
        _req, pinned = _extract_exact_pin(dep)
        if pinned is not None:
            result[canonicalize_name(dep_name)] = pinned
    return result


def _prefetch_combined_release_info(
    dependencies: list[str],
    transitive_only: list[str],
    locked_versions: dict[str, str] | None = None,
) -> dict[tuple[str, str | None], dict[str, Any] | None]:
    """Prefetch PyPI release info once for every dependency a document will
    emit -- direct and lock-resolved-transitive alike -- so the result can
    be shared across both :func:`add_dependencies` calls in :func:`build`
    instead of each call paying for its own network round-trip."""
    name_version_pairs = []
    for dep in dependencies:
        dep_name = _parse_dep_name(dep)
        locked_ver = (
            locked_versions.get(canonicalize_name(dep_name))
            if locked_versions is not None
            else None
        )
        dep_version, _version_note = _resolve_version(
            dep_name, dep, locked_version=locked_ver
        )
        name_version_pairs.append((dep_name, dep_version))
    for dep in transitive_only:
        dep_name = _parse_dep_name(dep)
        dep_version, _version_note = _resolve_version(dep_name, dep)
        name_version_pairs.append((dep_name, dep_version))
    return _prefetch_pypi_release_infos(name_version_pairs)


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
        locked_dependencies=metadata.locked_dependencies,
        locked_dependencies_provenance=metadata.provenance.get("locked_dependencies"),
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
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.simpleLicensing)
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

    # --- Locked (e.g. poetry.lock-resolved) transitive-only dependencies ---
    transitive_only = _locked_transitive_only_dependencies(metadata)
    locked_versions = _extract_locked_version_map(metadata.locked_dependencies)
    release_info_cache = (
        None
        if offline
        else _prefetch_combined_release_info(
            metadata.dependencies, transitive_only, locked_versions=locked_versions
        )
    )

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
        content_type_method=content_type_method,
        release_info_cache=release_info_cache,
        locked_versions=locked_versions,
    )

    if transitive_only:
        add_dependencies(
            dependencies=transitive_only,
            dep_provenance=metadata.provenance.get(
                "locked_dependencies", "Source: lock file"
            ),
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
