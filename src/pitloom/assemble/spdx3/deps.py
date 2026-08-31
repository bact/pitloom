# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency package and relationship creation for SPDX 3 SBOM documents.

See also: :mod:`pitloom.assemble.spdx3.deps_installed` for local metadata parsing,
:mod:`pitloom.assemble.spdx3.deps_pypi` for the PyPI JSON API fallback,
:mod:`pitloom.assemble.spdx3.deps_license` for license element construction,
and :mod:`pitloom.assemble.spdx3.deps_originator` for originator resolution.
"""

from __future__ import annotations

from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_installed import (
    _DOWNLOAD_LABELS,
    _HOMEPAGE_LABELS,
    _VERSION_OPERATORS,
    _enrich_from_installed,
    _parse_dep_name,
    _resolve_version,
)
from pitloom.assemble.spdx3.deps_license import _add_license_noassertion, _apply_license
from pitloom.assemble.spdx3.deps_originator import (
    _apply_originator,
    _resolve_metadata_url,
)
from pitloom.assemble.spdx3.deps_pypi import (
    _extract_pypi_license,
    _extract_pypi_originator,
    _extract_release_hash,
    _fetch_pypi_release_info,
    _prefetch_pypi_release_infos,
)
from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.models import build_pypi_purl, build_relationship, generate_spdx_id
from pitloom.core.project import PhantomDependency
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash

__all__ = [
    "_DOWNLOAD_LABELS",
    "_HOMEPAGE_LABELS",
    "_VERSION_OPERATORS",
    "_enrich_from_installed",
    "_enrich_from_pypi",
    "_finish_dependency_enrichment",
    "_parse_dep_name",
    "_resolve_version",
    "add_dependencies",
    "add_phantom_dependencies",
]


# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals
def _enrich_from_pypi(
    dep_name: str,
    dep_version: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    already_filled: set[str],
    release_info_cache: dict[tuple[str, str | None], dict[str, Any] | None]
    | None = None,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    offline: bool = False,
    content_type_method: str = "auto",
) -> set[str]:
    """Best-effort PyPI JSON API fallback for originator, license, and hash."""
    version = dep_version if dep_version != "unknown" else None
    release_info = (
        release_info_cache.get((dep_name, version))
        if release_info_cache is not None
        else _fetch_pypi_release_info(dep_name, version)
    )
    if release_info is None:
        return set()

    filled: set[str] = set()
    info = release_info.get("info") or {}

    project_urls = info.get("project_urls") or {}
    lower_project_urls = {k.lower(): v for k, v in project_urls.items()}
    repo_url = _resolve_metadata_url(
        "", lower_project_urls, ("repository", "source", "source code")
    )
    if not repo_url:
        home_page = info.get("home_page") or _resolve_metadata_url(
            info.get("project_url") or "", lower_project_urls, _HOMEPAGE_LABELS
        )
        repo_url = home_page

    if "originator" not in already_filled:
        originators = _extract_pypi_originator(info)
        if _apply_originator(
            originators,
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            repo_url=repo_url,
            provenance_config=provenance_config,
            encoder=encoder,
            provenance_source=f"Source: PyPI JSON API | Package: {dep_name}",
            offline=offline,
            content_type_method=content_type_method,
        ):
            filled.add("originator")

    if "license" not in already_filled:
        license_id = _extract_pypi_license(info)
        if _apply_license(
            license_id,
            f"Source: PyPI JSON API | Package: {dep_name}",
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        ):
            filled.add("license")

    if version is not None:
        digest = _extract_release_hash(release_info)
        if digest:
            dep_package.verifiedUsing = [sha256_hash(digest)]
            filled.add("hash")

    return filled


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _finish_dependency_enrichment(
    dep_name: str,
    dep_version: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    offline: bool,
    release_info_cache: dict[tuple[str, str | None], dict[str, Any] | None]
    | None = None,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    content_type_method: str = "auto",
) -> None:
    """Apply the shared dependency-package completeness policy."""
    dep_package.software_packageUrl = build_pypi_purl(
        dep_name, dep_version if dep_version != "unknown" else None
    )

    filled = _enrich_from_installed(
        dep_name,
        dep_package,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
        offline=offline,
        content_type_method=content_type_method,
    )

    if not offline:
        filled |= _enrich_from_pypi(
            dep_name,
            dep_version,
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            already_filled=filled,
            release_info_cache=release_info_cache,
            provenance_config=provenance_config,
            encoder=encoder,
            offline=offline,
            content_type_method=content_type_method,
        )

    if "copyright" not in filled:
        dep_package.software_copyrightText = "NOASSERTION"
    if "license" not in filled:
        _add_license_noassertion(
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )


# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals
def add_dependencies(
    dependencies: list[str],
    dep_provenance: str,
    main_package_spdx_id: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    offline: bool = False,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    content_type_method: str = "auto",
    completeness: str | None = None,
    release_info_cache: dict[tuple[str, str | None], dict[str, Any] | None]
    | None = None,
) -> None:
    """Build SPDX ``software_Package`` and ``Relationship`` elements for
    dependencies.

    Multiple declared dependency strings that resolve to the same
    ``(name, version)`` -- e.g. the same package listed under more than one
    ``pyproject.toml`` extra, each split by a ``python_version`` marker --
    collapse into a single ``software_Package`` node. Their raw declared
    strings are preserved together in that node's provenance comment.

    *completeness*, when given (e.g. ``spdx3.RelationshipCompleteness.complete``
    for a lock-resolved transitive-dependency call), is set on every
    ``dependsOn`` relationship this call creates. Omitted (the default)
    leaves the relationship's ``completeness`` unset, unchanged from
    before this parameter existed.

    *release_info_cache*, when given, is used as-is instead of prefetching
    PyPI release info for this call's own *dependencies* -- callers that
    invoke :func:`add_dependencies` more than once for the same document
    (e.g. direct dependencies, then lock-resolved transitive-only ones)
    can prefetch a single combined batch up front and share it across
    every call, instead of paying for one PyPI network round-trip per
    call.
    """
    resolved = []
    for dep in dependencies:
        dep_name = _parse_dep_name(dep)
        dep_version, version_note = _resolve_version(dep_name, dep)
        resolved.append((dep, dep_name, dep_version, version_note))
    if release_info_cache is None and not offline:
        release_info_cache = _prefetch_pypi_release_infos(
            (dep_name, dep_version) for _dep, dep_name, dep_version, _note in resolved
        )

    grouped: dict[tuple[str, str], list[tuple[str, str | None]]] = {}
    for dep, dep_name, dep_version, version_note in resolved:
        grouped.setdefault((dep_name, dep_version), []).append((dep, version_note))

    for (dep_name, dep_version), declared in grouped.items():
        declared_constraints = [dep for dep, _note in declared]
        version_note = next((note for _dep, note in declared if note), None)
        dep_provenance_fields: dict[str, str] = {
            "dependencies": dep_provenance,
            "declared_constraint": " | ".join(declared_constraints),
        }
        if version_note:
            dep_provenance_fields["version"] = version_note

        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name=doc_name, doc_uuid=doc_uuid),
            name=dep_name,
            creationInfo=creation_info,
        )
        dep_package.software_packageVersion = dep_version
        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library

        _finish_dependency_enrichment(
            dep_name,
            dep_version,
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            offline=offline,
            release_info_cache=release_info_cache,
            provenance_config=provenance_config,
            encoder=encoder,
            content_type_method=content_type_method,
        )

        exporter.add_package(dep_package)
        emit_provenance(
            subject=dep_package,
            provenance=dep_provenance_fields,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        rel_kwargs: dict[str, Any] = {}
        if completeness is not None:
            rel_kwargs["completeness"] = completeness
        dep_rel = build_relationship(
            from_id=main_package_spdx_id,
            to_ids=[require_spdx_id(dep_package)],
            rel_type=spdx3.RelationshipType.dependsOn,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            creation_info=creation_info,
            **rel_kwargs,
        )
        if dep_rel:
            exporter.add_relationship(dep_rel)


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
) -> None:
    """Build SPDX elements for bundled phantom binary dependencies."""
    for dep in phantom_deps:
        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name=doc_name, doc_uuid=doc_uuid),
            name=dep.name,
            creationInfo=creation_info,
        )
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

        dep_rel = build_relationship(
            from_id=main_package_spdx_id,
            to_ids=[require_spdx_id(dep_package)],
            rel_type=spdx3.RelationshipType.dependsOn,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            creation_info=creation_info,
        )
        if dep_rel:
            exporter.add_relationship(dep_rel)

        file_spdx_id = file_spdx_ids.get(dep.file_path)
        if file_spdx_id:
            file_rel = build_relationship(
                from_id=require_spdx_id(dep_package),
                to_ids=[file_spdx_id],
                rel_type=spdx3.RelationshipType.contains,
                doc_name=doc_name,
                doc_uuid=doc_uuid,
                creation_info=creation_info,
            )
            if file_rel:
                exporter.add_relationship(file_rel)
