# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Phantom-dependency package and relationship creation for SPDX 3 SBOM
documents.

See also: :mod:`pitloom.assemble.spdx3.deps` for declared dependencies.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_license import _add_license_noassertion
from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.project import PhantomDependency
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash

__all__ = ["add_phantom_dependencies"]


def _add_relationship(
    exporter: Spdx3JsonExporter, relationship: spdx3.Relationship | None
) -> None:
    """Add *relationship* to *exporter* unless it was not built."""
    if relationship:
        exporter.add_relationship(relationship)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def add_phantom_dependencies(
    phantom_deps: list[PhantomDependency],
    main_package_spdx_id: str,
    file_spdx_ids: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    resolved_ids: Sequence[str | None] | None = None,
    not_looked_up: Collection[int] = frozenset(),
) -> None:
    """Build SPDX elements for bundled phantom binary dependencies.

    *resolved_ids*, when given, holds one pre-resolved registry id (or
    ``None``) per entry of *phantom_deps*, in order. *not_looked_up* holds
    the indices of the entries that never looked up; their ids are added to
    :attr:`~pitloom.export.spdx3_json.Spdx3JsonExporter.registry_non_readers`.
    """
    hits = resolved_ids if resolved_ids is not None else [None] * len(phantom_deps)
    for index, (dep, resolved_id) in enumerate(zip(phantom_deps, hits, strict=True)):
        dep_package = spdx3.software_Package(
            spdxId=resolved_id
            or generate_spdx_id("Package", doc_name=doc_name, doc_uuid=doc_uuid),
            name=dep.name,
            creationInfo=creation_info,
        )
        if index in not_looked_up:
            exporter.registry_non_readers.add(require_spdx_id(dep_package))
        if dep.version:
            dep_package.software_packageVersion = dep.version
        else:
            dep_package.software_packageVersion = "unknown"

        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
        dep_package.software_copyrightText = "NOASSERTION"
        if dep.digest_sha256:
            dep_package.verifiedUsing = [sha256_hash(dep.digest_sha256)]
        _add_license_noassertion(
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        exporter.add_package(dep_package)
        emit_provenance(
            subject=dep_package,
            provenance={
                "package": "Phantom dependency bundled in distribution artifact"
            },
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        _add_relationship(
            exporter,
            build_relationship(
                from_id=main_package_spdx_id,
                to_ids=[require_spdx_id(dep_package)],
                rel_type=spdx3.RelationshipType.dependsOn,
                doc_name=doc_name,
                doc_uuid=doc_uuid,
                creation_info=creation_info,
            ),
        )

        file_spdx_id = file_spdx_ids.get(dep.file_path)
        if file_spdx_id:
            _add_relationship(
                exporter,
                build_relationship(
                    from_id=require_spdx_id(dep_package),
                    to_ids=[file_spdx_id],
                    rel_type=spdx3.RelationshipType.contains,
                    doc_name=doc_name,
                    doc_uuid=doc_uuid,
                    creation_info=creation_info,
                ),
            )
