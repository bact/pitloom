# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model package and relationship creation for SPDX 3 SBOM documents.

See also: :mod:`pitloom.assemble.spdx3._ai_package` for AIPackage node construction.
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._ai_package import (
    _SAFETY_RISK_VALUES,
    _add_base_model_lineage,
    _add_external_identifiers_and_refs,
    _ai_model_entity_candidates,
    _build_ai_package,
    _emit_source_metadata,
    _LineageContext,
    _should_preserve_metadata,
    _source_metadata_blob,
    finish_ai_package,
    finish_display_text,
)
from pitloom.assemble.spdx3._display_text import LICENSE
from pitloom.assemble.spdx3.creation_info import build_enrichment_elements
from pitloom.assemble.spdx3.dataset import add_datasets_for_model
from pitloom.assemble.spdx3.deps_license import build_license_elements
from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    build_enrichment_annotation,
    emit_provenance,
)
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich.base import EnrichmentResult
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.id_registry import IdRegistrySession

__all__ = [
    "_LineageContext",
    "_SAFETY_RISK_VALUES",
    "_add_base_model_lineage",
    "_add_external_identifiers_and_refs",
    "_build_ai_package",
    "_emit_source_metadata",
    "_should_preserve_metadata",
    "_source_metadata_blob",
    "add_ai_models",
    "add_model_license",
    "finish_ai_package",
    "finish_display_text",
    "resolve_ai_model_entity_hits",
]


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def add_model_license(
    ai_model: AiModelMetadata,
    package_spdx_id: str,
    default_source: str,
    doc: tuple[spdx3.CreationInfo, str, str],
    exporter: Spdx3JsonExporter,
    config: ProvenanceConfig | None,
    encoder: ProvenanceEncoder | None,
) -> list[tuple[str, spdx3.Element]]:
    """Build *ai_model*'s licence element and its declared or concluded
    relationship, when it states a licence; return the licence elements,
    labelled :data:`~pitloom.assemble.spdx3._display_text.LICENSE` for
    :func:`finish_ai_package`, whose text came
    from the model. *doc* is the creation info, document name and uuid;
    *default_source* is the provenance when the model records none."""
    if not ai_model.license:
        return []
    creation_info, doc_name, doc_uuid = doc
    relationships = build_license_elements(
        license_id=ai_model.license,
        package_spdx_id=package_spdx_id,
        license_provenance=ai_model.provenance.get("license", default_source),
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=config,
        encoder=encoder,
    )
    licenses: dict[str, spdx3.Element] = {}
    for rel in relationships:
        if rel is None:
            continue
        exporter.add_relationship(rel)
        for target in rel.to:
            target_id = target if isinstance(target, str) else require_spdx_id(target)
            element = exporter.object_set.find_by_id(target_id)
            if isinstance(element, spdx3.Element):
                licenses[target_id] = element
    return [(LICENSE, licenses[key]) for key in sorted(licenses)]


def _ai_model_label(ai_model: AiModelMetadata, index: int) -> str:
    """A short, human-readable identifier for *ai_model* in an
    :class:`~pitloom.id_registry.IdRegistrySession` collision warning --
    never used as a lookup key, only for the message."""
    return (
        ai_model.own_name
        or ai_model.format_info.file_path_relative
        or ai_model.format_info.file_name
        or f"ai_models[{index}]"
    )


def resolve_ai_model_entity_hits(
    ai_models: list[AiModelMetadata],
    session: IdRegistrySession,
) -> list[str | None]:
    """Pre-resolve each of *ai_models*' ``ai_AIPackage`` registry hit, in
    list order (the scanner's order: sorted by distribution path, see
    :func:`pitloom.extract.scanner.discover_ai_models`), before any minting
    starts.

    One entry per model (``None`` on a miss) via
    :meth:`~pitloom.id_registry.IdRegistrySession.entity_id` over
    :func:`_ai_model_entity_candidates`. The caller must reserve every
    non-``None`` value (:func:`~pitloom.core.models.reserve_spdx_ids`)
    before minting, then pass this list to :func:`add_ai_models` instead
    of the registry -- pre-resolution is the single source of truth for
    what was reserved, so the actual build must never look the registry
    up a second time.

    Two models can legitimately hit the same entity -- e.g. two models
    sharing a file stem, the only lookup candidate left when neither has a
    name/``physical_path`` -- in which case only the first (in list
    order, or the first hit across files/directories/AI models together
    in *session*) reuses it; every later one gets its own fresh id
    instead of silently losing its element to the first, with one
    ``WARNING: ID registry: ...`` naming both.
    """
    hits: list[str | None] = []
    for index, ai_model in enumerate(ai_models):
        hit = session.entity_id(
            _ai_model_label(ai_model, index),
            _ai_model_entity_candidates(ai_model),
            "ai_AIPackage",
        )
        hits.append(hit)
    return hits


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _add_ai_model_file_relationships(
    ai_model: AiModelMetadata,
    ai_pkg_id: str,
    file_spdx_ids: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Build contains and hasDataFile relationships for model files."""
    model_file_id = (
        file_spdx_ids.get(ai_model.format_info.file_path_relative)
        if ai_model.format_info.file_path_relative
        else None
    )
    if not model_file_id:
        return

    rel_contains_file = build_relationship(
        from_id=ai_pkg_id,
        to_ids=[model_file_id],
        rel_type=spdx3.RelationshipType.contains,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        creation_info=creation_info,
    )
    if rel_contains_file:
        exporter.add_relationship(rel_contains_file)

    for usage_path in ai_model.usage_files:
        usage_file_id = file_spdx_ids.get(usage_path)
        if usage_file_id:
            rel_usage = build_relationship(
                from_id=usage_file_id,
                to_ids=[model_file_id],
                rel_type=spdx3.RelationshipType.hasDataFile,
                doc_name=doc_name,
                doc_uuid=doc_uuid,
                creation_info=creation_info,
                rel_class=spdx3.LifecycleScopedRelationship,
                scope=spdx3.LifecycleScopeType.runtime,
            )
            if rel_usage:
                exporter.add_relationship(rel_usage)


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def _add_single_ai_model(
    ai_model: AiModelMetadata,
    model_enrichment_results: list[EnrichmentResult],
    main_package_spdx_id: str,
    file_spdx_ids: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    entity_spdx_id: str | None,
    config: ProvenanceConfig,
    encoder: ProvenanceEncoder | None,
    lineage_ctx: _LineageContext,
) -> None:
    """Assemble elements and relationships for a single AI model.

    *entity_spdx_id* is the pre-resolved registry hit from
    :func:`resolve_ai_model_entity_hits` (or ``None`` on a miss) -- never
    looked up here."""
    ai_pkg = _build_ai_package(
        ai_model, creation_info, doc_name, doc_uuid, entity_spdx_id=entity_spdx_id
    )
    exporter.add_package(ai_pkg)
    ai_pkg_id = require_spdx_id(ai_pkg)
    related = _add_base_model_lineage(ai_pkg, ai_model, lineage_ctx)

    emit_provenance(
        subject=ai_pkg,
        provenance=ai_model.resolve_name()[1],
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=config,
        encoder=encoder,
    )
    _emit_source_metadata(
        ai_model,
        ai_pkg,
        file_spdx_ids,
        config.preserve_source_metadata,
        config.max_source_metadata_bytes,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
    )

    dataset_creation_info, annotation_groups = build_enrichment_elements(
        model_enrichment_results, creation_info, doc_name, doc_uuid, exporter
    )

    if ai_model.datasets:
        related += add_datasets_for_model(
            ai_package_spdx_id=ai_pkg_id,
            ai_model=ai_model,
            datasets=ai_model.datasets,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=config,
            encoder=encoder,
            dataset_creation_info=dataset_creation_info,
        )

    for enrich_ci, changes in annotation_groups:
        exporter.add_annotation(
            build_enrichment_annotation(
                subject_spdx_id=ai_pkg_id,
                changes=changes,
                creation_info=enrich_ci,
                annotation_spdx_id=generate_spdx_id(
                    "Annotation", doc_name=doc_name, doc_uuid=doc_uuid
                ),
            )
        )
    related += add_model_license(
        ai_model,
        ai_pkg_id,
        "Source: model file / Hugging Face Hub",
        (creation_info, doc_name, doc_uuid),
        exporter,
        config,
        encoder,
    )
    finish_ai_package(ai_pkg, ai_model, related)

    rel = build_relationship(
        from_id=main_package_spdx_id,
        to_ids=[ai_pkg_id],
        rel_type=spdx3.RelationshipType.contains,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        creation_info=creation_info,
    )
    if rel:
        exporter.add_relationship(rel)

    _add_ai_model_file_relationships(
        ai_model,
        ai_pkg_id,
        file_spdx_ids,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
    )


# pylint: disable=too-many-arguments,too-many-positional-arguments
def add_ai_models(
    ai_models: list[AiModelMetadata],
    main_package_spdx_id: str,
    file_spdx_ids: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    resolved_entity_ids: list[str | None] | None = None,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    enrichment_results_by_model: list[list[EnrichmentResult]] | None = None,
) -> None:
    """Build ``ai_AIPackage`` and ``contains`` relationship elements for AI models.

    *resolved_entity_ids*, when given, is one pre-resolved registry hit
    (or ``None``) per ``ai_models`` element, same order -- see
    :func:`resolve_ai_model_entity_hits`. Missing/``None`` list entries are
    treated as a miss, unchanged behaviour when no registry applies.
    """
    config = provenance_config or ProvenanceConfig()
    lineage_ctx = _LineageContext(
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
    )
    for index, ai_model in enumerate(ai_models):
        model_enrichment_results = (
            enrichment_results_by_model[index]
            if enrichment_results_by_model and index < len(enrichment_results_by_model)
            else []
        )
        entity_spdx_id = (
            resolved_entity_ids[index]
            if resolved_entity_ids and index < len(resolved_entity_ids)
            else None
        )
        _add_single_ai_model(
            ai_model,
            model_enrichment_results,
            main_package_spdx_id,
            file_spdx_ids,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            entity_spdx_id,
            config,
            encoder,
            lineage_ctx,
        )
