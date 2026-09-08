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
from pitloom.assemble.spdx3.ai import add_ai_models
from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.assemble.spdx3.deps import (
    _parse_dep_name,
    _resolve_version,
    add_dependencies,
    add_phantom_dependencies,
)
from pitloom.assemble.spdx3.deps_installed import _extract_exact_pin
from pitloom.assemble.spdx3.deps_license import attach_main_package_license
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
from pitloom.extract._lock_common import is_same_version, warn_conflicting_versions
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


def _deduplicated_locked_dependencies(
    locked_dependencies: list[str] | None,
) -> list[str]:
    """Collapse *locked_dependencies* to one entry per PEP 503-canonicalized
    name among its exact-pinned entries, preserving order.

    A canonical name whose *pinned* entries disagree on PEP 440 version is
    a genuine conflict (e.g. two lock formats layered by hand into the
    same ``ProjectMetadata``, or a future extractor that forgets to
    dedupe before returning) -- warned via :func:`warn_conflicting_versions`
    and excluded entirely, the same "skip the ambiguous name, don't guess"
    policy every extractor already applies to its own duplicate entries.
    Neither of this function's two callers (:func:`_extract_locked_version_map`,
    :func:`_locked_transitive_only_dependencies`) could otherwise safely
    pick a winner between two conflicting entries on its own -- and picking
    different winners in each would silently emit the ambiguous package
    twice, once per winner, into the assembled SPDX graph.

    An entry with no exact pin at all (unpinned, ranged, or unparseable --
    every shipped extractor always emits an exact pin, but this guards a
    future one that doesn't) has no version to compare and passes through
    unfiltered: only :func:`_extract_locked_version_map` needs a pin, and
    it already discards a pin-less entry on its own via
    :func:`_extract_exact_pin`'s own ``None`` return. A passthrough entry
    is dropped, though, when its canonical name also has a pinned entry
    elsewhere in *locked_dependencies* -- the pin is strictly more
    informative, and keeping both would double-emit the same package
    (one from the pinned entry, one from the passthrough one).
    """
    by_canonical: dict[str, list[tuple[str, str]]] = {}
    for dep in locked_dependencies or []:
        _req, pinned = _extract_exact_pin(dep)
        if pinned is None:
            continue
        canon = canonicalize_name(_parse_dep_name(dep))
        by_canonical.setdefault(canon, []).append((dep, pinned))

    excluded: set[str] = set()
    resolved: dict[str, str] = {}
    for group_canon, group in by_canonical.items():
        dep, version = group[0]
        conflicting_versions = {v for _, v in group if not is_same_version(v, version)}
        if conflicting_versions:
            warn_conflicting_versions(
                "locked dependencies", _parse_dep_name(dep), {v for _, v in group}
            )
            excluded.add(group_canon)
        else:
            resolved[group_canon] = dep

    deduplicated: list[str] = []
    emitted: set[str] = set()
    for dep in locked_dependencies or []:
        canon = canonicalize_name(_parse_dep_name(dep))
        if canon in excluded:
            continue
        if canon in resolved:
            if canon in emitted:
                continue
            emitted.add(canon)
            deduplicated.append(resolved[canon])
            continue
        # No pinned entry anywhere for this canonical name -- pass
        # through as-is, at its own original position.
        deduplicated.append(dep)
    return deduplicated


def _locked_transitive_only_dependencies(
    metadata: ProjectMetadata,
    *,
    deduplicated_locked: list[str] | None = None,
) -> list[str]:
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

    *deduplicated_locked*, when given, is used as-is instead of calling
    :func:`_deduplicated_locked_dependencies` again -- :func:`build` computes
    it once and shares it with :func:`_extract_locked_version_map` so a
    genuine name/version conflict in ``locked_dependencies`` only logs
    :func:`warn_conflicting_versions`'s warning once per document, not once
    per caller.
    """
    direct_names = {
        canonicalize_name(_parse_dep_name(dep)) for dep in metadata.dependencies
    }
    locked = (
        deduplicated_locked
        if deduplicated_locked is not None
        else _deduplicated_locked_dependencies(metadata.locked_dependencies)
    )
    return [
        dep
        for dep in locked
        if canonicalize_name(_parse_dep_name(dep)) not in direct_names
    ]


# pylint: disable=useless-return
def _locked_dependencies_completeness(metadata: ProjectMetadata) -> str | None:
    """Return the `RelationshipCompleteness` value for the locked-only
    `dependsOn` edges :func:`_locked_transitive_only_dependencies`
    produces, or `None` to leave it unset.

    Conservatively returns ``None`` (unset): while a resolver lock represents
    a resolved dependency graph, extractors may legitimately omit
    unrepresentable dependencies (such as VCS/path sources, non-default groups,
    or marker-ambiguous variants). Asserting ``complete`` would overstate
    completeness for partial closures, so leaving it unset makes no
    unverifiable claim.
    """
    del metadata
    return None


def _extract_locked_version_map(
    locked_dependencies: list[str] | None,
    *,
    deduplicated: list[str] | None = None,
) -> dict[str, str]:
    """Map canonical package names to their exact locked version string.

    Enables direct dependencies declared as ranges (e.g. ``requests>=2.0``)
    to resolve to their authoritative locked version rather than falling back
    to introspecting Pitloom's host environment.

    *deduplicated*, when given, is used as-is instead of calling
    :func:`_deduplicated_locked_dependencies` again -- see
    :func:`_locked_transitive_only_dependencies`'s matching parameter for why.
    """
    result: dict[str, str] = {}
    locked = (
        deduplicated
        if deduplicated is not None
        else _deduplicated_locked_dependencies(locked_dependencies)
    )
    for dep in locked:
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
            dep_name, dep, locked_version=locked_ver, warn=False
        )
        name_version_pairs.append((dep_name, dep_version))
    for dep in transitive_only:
        dep_name = _parse_dep_name(dep)
        dep_version, _version_note = _resolve_version(dep_name, dep, warn=False)
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
    attach_main_package_license(
        metadata=metadata,
        main_package=main_package,
        spdx_ci=spdx_ci,
        spdx_doc=spdx_doc,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=prov_cfg,
        encoder=encoder,
    )

    # --- Locked (e.g. poetry.lock-resolved) transitive-only dependencies ---
    # Deduplicated once and shared below: a genuine name/version conflict
    # in metadata.locked_dependencies must warn exactly once per document,
    # not once per function that would otherwise recompute it.
    deduplicated_locked = _deduplicated_locked_dependencies(
        metadata.locked_dependencies
    )
    transitive_only = _locked_transitive_only_dependencies(
        metadata, deduplicated_locked=deduplicated_locked
    )
    locked_versions = _extract_locked_version_map(
        metadata.locked_dependencies, deduplicated=deduplicated_locked
    )
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

    if (
        spdx3.ProfileIdentifierType.simpleLicensing not in spdx_doc.profileConformance
        and exporter.has_licenses
    ):
        spdx_doc.profileConformance.append(spdx3.ProfileIdentifierType.simpleLicensing)

    return exporter
