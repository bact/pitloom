# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model package and relationship creation for SPDX 3 SBOM documents.

See also: :mod:`pitloom.assemble.spdx3._ai_package` for AIPackage node construction.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._ai_originators import add_model_originators
from pitloom.assemble.spdx3._ai_package import (
    _SAFETY_RISK_VALUES,
    _add_base_model_lineage,
    _add_external_identifiers_and_refs,
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
from pitloom.assemble.spdx3.deps_license import add_license_relationships
from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    build_enrichment_annotation,
    emit_provenance,
)
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.project import ProjectFile
from pitloom.core.provenance import ProvenanceConfig
from pitloom.core.untrusted_text import escape_display_controls
from pitloom.enrich.base import EnrichmentResult
from pitloom.export.hashes import file_digests_of
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    IdRegistry,
    IdRegistrySession,
    LookupKey,
    join_key,
)
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

_V = TypeVar("_V")

__all__ = [
    "MODEL_GATE_MISS_INFO",
    "ModelHits",
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
    "lookup_model_id",
    "model_lookup_key",
    "resolve_ai_model_entity_hits",
]

#: The one ``INFO:`` for a model whose lookup, gated by its file's SHA-256,
#: missed while an entry under its key exists: it records no SHA-256, or
#: another. Argument: the model's label.
MODEL_GATE_MISS_INFO = (
    "ID registry: model %s: no registry entry records its SHA-256; a new id is used"
)


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
    licenses = add_license_relationships(
        ai_model.license,
        package_spdx_id,
        ai_model.provenance.get("license", default_source),
        doc,
        exporter,
        config,
        encoder,
    )
    return [(LICENSE, element) for element in licenses]


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


def _info_gate_miss(registry: IdRegistry, claimant: str, key: str) -> None:
    """:data:`MODEL_GATE_MISS_INFO` for *claimant* when *registry* holds an
    entry under *key* (or its display-escaped spelling, as a session tries
    it), whatever its SHA-256. Read only: nothing is claimed."""
    spellings = (key, escape_display_controls(key))
    if any(registry.get(AI_PACKAGE_TYPE, name) is not None for name in spellings):
        log.info(MODEL_GATE_MISS_INFO, loggable(claimant))


def lookup_model_id(
    session: IdRegistrySession,
    claimant: str,
    lookup: LookupKey,
    digest: str | None,
) -> str | None:
    """*session*'s ``ai_AIPackage`` hit for *lookup*, claimed and its key
    recorded (:meth:`~pitloom.id_registry.IdRegistrySession.lookup_key`),
    gated by *digest*, the model file's SHA-256 (``None``: ungated): an
    entry recording no SHA-256, or another, never hits a gated lookup. Such
    a miss gives one :data:`MODEL_GATE_MISS_INFO`; every model lookup of
    every surface goes through here."""
    registry = session.registry
    if registry is None or digest is None:
        return session.lookup_key(claimant, AI_PACKAGE_TYPE, lookup)
    on_miss = functools.partial(_info_gate_miss, registry, claimant, lookup.key)
    return session.lookup_key(
        claimant, AI_PACKAGE_TYPE, lookup, sha256=digest, on_miss=on_miss
    )


def _of_model_file(ai_model: AiModelMetadata, by_path: Mapping[str, _V]) -> _V | None:
    """The value in *by_path* (by ``distribution_path``) for *ai_model*'s own
    file, or ``None`` when it has none there."""
    path = ai_model.format_info.file_path_relative
    return by_path.get(path) if path else None


def model_lookup_key(
    ai_model: AiModelMetadata,
    keys: Mapping[str, LookupKey],
    prefix: str | None,
) -> LookupKey:
    """The key *ai_model*'s ``ai_AIPackage`` is looked up and harvested
    under: the key of its own file among the document's *keys* (by
    ``distribution_path``: the one its ``software_File`` has, alias
    included); else, with a project *prefix*
    (:func:`~pitloom.id_registry.keys.project_prefix`), its project-relative
    ``physical_path`` joined to it; else its name as shown
    (:meth:`~pitloom.core.ai_metadata.AiModelMetadata.resolve_name`)."""
    own = _of_model_file(ai_model, keys)
    if own is not None:
        return own
    physical = ai_model.format_info.physical_path
    # join_key refuses an absolute (--allow-build temporary) path.
    key = None if prefix is None or not physical else join_key(prefix, physical)
    if key is not None:
        return LookupKey(key, path=True)
    return LookupKey(ai_model.resolve_name()[0])


@dataclass(frozen=True)
class ModelHits:
    """One document's ``ai_AIPackage`` registry hits (*ids*, one per model,
    ``None`` on a miss), each model's key (*keys*, same order) and the
    *session* they were claimed in."""

    session: IdRegistrySession
    ids: list[str | None]
    keys: list[LookupKey]

    def record(self, model_ids: Sequence[str]) -> None:
        """Record each model's key for the id it got (*model_ids*, model
        order), so a minted id is harvested under it; a hit's own recorded
        key wins (:meth:`~pitloom.id_registry.IdRegistrySession.record_key`)."""
        for spdx_id, lookup in zip(model_ids, self.keys, strict=True):
            self.session.record_key(spdx_id, AI_PACKAGE_TYPE, lookup.key)


def resolve_ai_model_entity_hits(
    ai_models: list[AiModelMetadata],
    session: IdRegistrySession,
    files: Iterable[ProjectFile] = (),
    *,
    keys: Mapping[str, LookupKey] | None = None,
    prefix: str | None = None,
) -> ModelHits:
    """Pre-resolve each of *ai_models*' ``ai_AIPackage`` registry hit, in
    list order (the scanner's order: sorted by distribution path, see
    :func:`pitloom.extract.scanner.discover_ai_models`), before any minting
    starts.

    Each model is looked up once, by :func:`model_lookup_key` over the
    document's file *keys* and project *prefix*, through
    :func:`lookup_model_id`, gated by the SHA-256 of its own file in
    *files*; a model with no file there, or one with no SHA-256, is looked
    up ungated. The caller must reserve every non-``None`` id
    (:func:`~pitloom.core.models.reserve_spdx_ids`) before minting, pass
    them to :func:`add_ai_models` instead of the registry (the build never
    looks the registry up a second time), then :meth:`ModelHits.record`
    the ids it returns.

    A stale registry can give two models one id: only the first (in list
    order, or the first claimant in *session*) reuses it; a later one gets
    its own fresh id, with one ``WARNING: ID registry: ...`` naming both.
    """
    keys = keys or {}
    digests = {pf.distribution_path: pf.digest_sha256 for pf in files}
    lookups = [model_lookup_key(model, keys, prefix) for model in ai_models]
    ids = [
        lookup_model_id(
            session,
            _ai_model_label(ai_model, index),
            lookup,
            _of_model_file(ai_model, digests),
        )
        for index, (ai_model, lookup) in enumerate(zip(ai_models, lookups, strict=True))
    ]
    return ModelHits(session, ids, lookups)


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
    model_file_id = _of_model_file(ai_model, file_spdx_ids)
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
) -> str:
    """Assemble elements and relationships for a single AI model; return
    its package's spdxId.

    *entity_spdx_id* is the pre-resolved registry hit from
    :func:`resolve_ai_model_entity_hits` (or ``None`` on a miss) -- never
    looked up here. The package's ``verifiedUsing`` is the SHA-256 and
    SHA-512 of the model's own ``software_File`` in the document, when it
    has one (new ``Hash`` elements, never shared with the file's)."""
    file_id = _of_model_file(ai_model, file_spdx_ids)
    ai_pkg = _build_ai_package(
        ai_model,
        creation_info,
        doc_name,
        doc_uuid,
        entity_spdx_id=entity_spdx_id,
        digest=(
            None
            if file_id is None
            else file_digests_of(exporter.object_set.find_by_id(file_id))
        ),
    )
    exporter.add_package(ai_pkg)
    ai_pkg_id = require_spdx_id(ai_pkg)
    related = _add_base_model_lineage(ai_pkg, ai_model, lineage_ctx)
    related += add_model_originators(
        ai_pkg, ai_model, (creation_info, doc_name, doc_uuid), exporter
    )

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
    return ai_pkg_id


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
) -> list[str]:
    """Build ``ai_AIPackage`` and ``contains`` relationship elements for AI
    models; return each package's spdxId, in *ai_models* order.

    *resolved_entity_ids*, when given, is one pre-resolved registry hit
    (or ``None``) per ``ai_models`` element, same order -- see
    :func:`resolve_ai_model_entity_hits`. A missing or ``None`` entry is a
    miss: a fresh id is minted.
    """
    config = provenance_config or ProvenanceConfig()
    lineage_ctx = _LineageContext(
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
    )
    ids: list[str] = []
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
        ids.append(
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
        )
    return ids
