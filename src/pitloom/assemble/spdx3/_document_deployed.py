# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 deployed-environment document assembly for
:mod:`pitloom.assemble.spdx3.document`.

See also: :mod:`pitloom.assemble.spdx3.document`, the public entry point
that re-exports :func:`build_deployed`.
"""

from __future__ import annotations

from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps import _finish_dependency_enrichment
from pitloom.assemble.spdx3.deps_pypi import _prefetch_pypi_release_infos
from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    emit_provenance,
    resolve_encoder,
)
from pitloom.core.document import DocumentModel
from pitloom.core.models import (
    _clear_doc_counters,
    build_relationship,
    compute_doc_uuid,
    generate_spdx_id,
)
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.ids import IdRegistry


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
    # Local import to avoid a circular import at module-load time --
    # document.py imports build_deployed from this module, so importing
    # its own _build_creation_bundle/_build_main_package back at this
    # module's top level would run before those names exist in document.py.
    # By the time build_deployed() is actually called, document.py has
    # finished loading, so this resolves cleanly.
    # pylint: disable=import-outside-toplevel,cyclic-import
    from pitloom.assemble.spdx3.document import (
        _build_creation_bundle,
        _build_main_package,
    )

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
                dep_rel = build_relationship(
                    from_id=parent_spdx_id,
                    to_ids=[child_spdx_id],
                    rel_type=spdx3.RelationshipType.dependsOn,
                    doc_name=metadata.name,
                    doc_uuid=doc_uuid,
                    creation_info=spdx_ci,
                )
                if dep_rel:
                    exporter.add_relationship(dep_rel)

    # Third pass: Link top-level packages to the environment root
    for node in env_tree:
        pkg_key = node.get("package", {}).get("key")
        if pkg_key not in dep_keys_with_parents:
            child_spdx_id = package_spdx_ids.get(pkg_key)
            if child_spdx_id:
                dep_rel = build_relationship(
                    from_id=require_spdx_id(main_package),
                    to_ids=[child_spdx_id],
                    rel_type=spdx3.RelationshipType.dependsOn,
                    doc_name=metadata.name,
                    doc_uuid=doc_uuid,
                    creation_info=spdx_ci,
                )
                if dep_rel:
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
