# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 single-model document assembly for
:mod:`pitloom.assemble.spdx3.document`.

See also: :mod:`pitloom.assemble.spdx3.document`, the public entry point
that re-exports :func:`build_enrichment_fragment` and :func:`build_model`.
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.ai import (
    _add_base_model_lineage,
    _build_ai_package,
    _emit_source_metadata,
    _LineageContext,
)
from pitloom.assemble.spdx3.creation_info import (
    build_creation_info,
    build_enrichment_elements,
)
from pitloom.assemble.spdx3.dataset import add_datasets_for_model
from pitloom.assemble.spdx3.deps_license import build_license_elements
from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    build_enrichment_annotation,
    emit_provenance,
    resolve_encoder,
)
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich.base import EnrichmentResult
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id


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


# pylint: disable-next=too-many-locals
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
        prov_cfg.max_source_metadata_bytes,
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
