# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model package and relationship creation for SPDX 3 SBOM documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.dataset import add_datasets_for_model
from pitloom.assemble.spdx3.deps import build_license_elements
from pitloom.assemble.spdx3.provenance import (
    ProvenanceEncoder,
    build_source_metadata_annotation,
    emit_provenance,
)
from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.ids import IdRegistry

# Valid SPDX 3 ai_safetyRiskAssessmentType enum values (lowercase).
_SAFETY_RISK_VALUES = {"high", "medium", "low", "serious"}


def _should_preserve_metadata(
    ai_model: AiModelMetadata,
    file_spdx_ids: dict[str, str],
    setting: str,
) -> bool:
    """Decide whether to embed *ai_model*'s verbatim original metadata (P1).

    ``"always"``/``"never"`` are explicit. ``"auto"`` preserves only when the
    artifact is **not shipped** with the distribution -- i.e. it cannot be
    re-extracted from the SBOM's own package later. A model whose file is in
    the packaged file set (*file_spdx_ids*) is shipped; a Hugging Face / URL
    model with no local packaged file is not.
    """
    if setting == "always":
        return True
    if setting == "never":
        return False
    rel = ai_model.format_info.file_path_relative
    shipped = bool(rel) and rel in file_spdx_ids
    return not shipped


def _source_metadata_blob(ai_model: AiModelMetadata) -> tuple[str, dict[str, Any]]:
    """Return ``(format_tag, metadata)`` for P1 preservation.

    Prefers the verbatim, type-preserving ``raw_metadata`` an extractor captured
    (GGUF kv-store, safetensors ``__metadata__``); falls back to the retained
    ``properties`` + Hugging Face ``extra_data``/``extra_lists`` so a
    hub-sourced model still preserves what was collected.
    """
    fmt = str(ai_model.format_info.model_format)
    if ai_model.raw_metadata:
        return fmt, dict(ai_model.raw_metadata)
    blob: dict[str, Any] = {}
    blob.update(ai_model.properties)
    blob.update(ai_model.extra_data)
    blob.update(ai_model.extra_lists)
    if fmt == str(AiModelFormat.UNKNOWN) and (
        ai_model.extra_data or ai_model.extra_lists
    ):
        fmt = "huggingface"
    return fmt, blob


def _emit_source_metadata(
    ai_model: AiModelMetadata,
    ai_pkg: spdx3.ai_AIPackage,
    file_spdx_ids: dict[str, str],
    preserve_source_metadata: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Emit a verbatim artifact-metadata preservation Annotation for *ai_model*
    when the P1 gate says so (see :func:`_should_preserve_metadata`)."""
    if not _should_preserve_metadata(ai_model, file_spdx_ids, preserve_source_metadata):
        return
    source_format, metadata = _source_metadata_blob(ai_model)
    annotation = build_source_metadata_annotation(
        subject_spdx_id=require_spdx_id(ai_pkg),
        source_format=source_format,
        metadata=metadata,
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
    )
    if annotation is not None:
        exporter.add_annotation(annotation)


def _lookup_ai_model_entity(
    ai_model: AiModelMetadata, registry: IdRegistry | None
) -> str | None:
    """Resolve a registered ``ai_AIPackage`` id for a scan-discovered model.

    Tries, in order, every name a producer might plausibly have registered
    this model under:

    1. ``ai_model.name``, when the extractor set one.
    2. ``format_info.physical_path`` -- the project-root-relative path (e.g.
       ``"src/pkg/model.bin"``), i.e. the exact string a
       ``pitloom.loom`` fragment's ``run.set_model(model_file_path, ...)``
       call would have used as both the model's name and the registry
       lookup key when invoked with that same path.
    3. The file stem of ``format_info.file_name`` (e.g. ``"model"`` for
       ``"model.bin"``) -- mirrors the lookup
       :func:`pitloom.assemble.generate_ai_model_sbom` performs for
       ``loom model``/``--registry``.

    Returns ``None`` (mint a fresh id, unchanged behaviour) when no registry
    is given or none of the candidates are registered.
    """
    if registry is None:
        return None

    candidates: list[str] = []
    if ai_model.name:
        candidates.append(ai_model.name)
    if ai_model.format_info.physical_path:
        candidates.append(ai_model.format_info.physical_path)
    if ai_model.format_info.file_name:
        candidates.append(Path(ai_model.format_info.file_name).stem)

    for candidate in candidates:
        registered_id = registry.lookup_entity(candidate, "ai_AIPackage")
        if registered_id is not None:
            return registered_id
    return None


def _build_ai_package(
    ai_model: AiModelMetadata,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    entity_spdx_id: str | None = None,
) -> spdx3.ai_AIPackage:
    """Build an ``ai_AIPackage`` SPDX 3 element from an :class:`AiModelMetadata`.

    Field mapping:

    **Core identification**

    - ``name`` -> ``name`` (falls back to ``format_info.model_format`` string)
    - ``version`` -> ``software_packageVersion``
    - ``description`` -> ``description``

    **Technical model metadata**

    - ``type_of_model`` and/or ``architecture`` -> ``ai_typeOfModel`` (list)
    - ``quantization`` -> ``ai_hyperparameter`` (key="quantization")
    - ``hyperparameters`` -> ``ai_hyperparameter`` (list of DictionaryEntry)
    - ``inputs`` / ``outputs`` -> ``ai_informationAboutApplication`` (JSON)

    **Use-case and safety** (from ``usage`` sub-object)

    - ``domain`` + ``usage.domains`` -> ``ai_domain`` (merged, de-duplicated)
    - ``usage.limitations`` -> ``ai_limitation`` (joined with "; ")
    - ``usage.safety_risk_assessment`` -> ``ai_safetyRiskAssessment``
      (enum: high | medium | low | serious)
    - ``usage.intended_use`` + ``usage.unintended_use``
      -> merged into ``ai_informationAboutApplication`` JSON
    - ``usage.known_biases`` -> appended to ``comment``

    **Provenance**

    - ``provenance`` is emitted separately by :func:`add_ai_models` via
      :func:`~pitloom.assemble.spdx3.provenance.emit_provenance` (Core
      Annotation and/or legacy ``comment``, per config) once this package
      has been added to the exporter.

    Args:
        ai_model: Extracted AI model metadata.
        creation_info: The shared CreationInfo node.
        doc_name: The parent document/package name (for deterministic spdxId).
        doc_uuid: The document UUID (for deterministic spdxId).
        entity_spdx_id: When given, overrides the freshly minted ``spdxId``
            with this one -- used when a stable file/entity id registry
            already has an id for this model (see
            :func:`_lookup_ai_model_entity`), so this element and one built
            from an independently generated ``pitloom.loom`` fragment become
            literally the same element once merged.

    Returns:
        A populated :class:`spdx3.ai_AIPackage` instance.
    """
    pkg_name = ai_model.name or str(ai_model.format_info.model_format)
    ai_pkg = spdx3.ai_AIPackage(
        spdxId=entity_spdx_id
        or generate_spdx_id(
            f"AIPackage-{pkg_name}", doc_name=doc_name, doc_uuid=doc_uuid
        ),
        name=pkg_name,
        creationInfo=creation_info,
    )

    if ai_model.version:
        ai_pkg.software_packageVersion = ai_model.version

    if ai_model.description:
        ai_pkg.description = ai_model.description

    # ai_typeOfModel: collect both the general type and the specific architecture.
    type_of_model_values: list[str] = []
    if ai_model.type_of_model:
        type_of_model_values.append(ai_model.type_of_model)
    if ai_model.architecture:
        type_of_model_values.append(ai_model.architecture)
    if type_of_model_values:
        ai_pkg.ai_typeOfModel = type_of_model_values

    # ai_hyperparameter: quantization first (if present), then training hyperparams.
    hyperparameter_entries: list[spdx3.DictionaryEntry] = []
    if ai_model.quantization:
        hyperparameter_entries.append(
            spdx3.DictionaryEntry(key="quantization", value=ai_model.quantization)
        )
    for key, val in ai_model.hyperparameters.items():
        hyperparameter_entries.append(
            spdx3.DictionaryEntry(key=str(key), value=str(val))
        )
    if hyperparameter_entries:
        ai_pkg.ai_hyperparameter = hyperparameter_entries

    # ai_domain: merge top-level domain list with usage.domains (de-duplicated).
    combined_domains: list[str] = []
    seen_domains: set[str] = set()
    for d in list(ai_model.domain) + list(ai_model.usage.domains):
        if d not in seen_domains:
            combined_domains.append(d)
            seen_domains.add(d)
    if combined_domains:
        ai_pkg.ai_domain = combined_domains

    # ai_limitation: SPDX 3 field is a single String; join list with "; ".
    if ai_model.usage.limitations:
        ai_pkg.ai_limitation = "; ".join(ai_model.usage.limitations)

    # ai_safetyRiskAssessment: enum (high | medium | low | serious).
    if ai_model.usage.safety_risk_assessment:
        risk_val = ai_model.usage.safety_risk_assessment.lower()
        if risk_val in _SAFETY_RISK_VALUES:
            ai_pkg.ai_safetyRiskAssessment = getattr(
                spdx3.ai_SafetyRiskAssessmentType, risk_val, None
            )

    # ai_informationAboutApplication: JSON dict combining I/O specs and use-case info.
    io_parts: dict[str, Any] = {}
    if ai_model.inputs:
        io_parts["inputs"] = ai_model.inputs
    if ai_model.outputs:
        io_parts["outputs"] = ai_model.outputs
    if ai_model.usage.intended_use:
        io_parts["intended_use"] = ai_model.usage.intended_use
    if ai_model.usage.unintended_use:
        io_parts["unintended_use"] = ai_model.usage.unintended_use
    if io_parts:
        ai_pkg.ai_informationAboutApplication = json.dumps(io_parts, ensure_ascii=False)

    # ExternalIdentifier: DOI (uses type 'other' with comment 'DOI' in SPDX 3.0.1;
    # 'doi' enum member is introduced in SPDX 3.1-dev).
    doi = ai_model.doi or ai_model.extra_data.get("hf.doi")
    if doi:
        ai_pkg.externalIdentifier.append(
            spdx3.ExternalIdentifier(
                externalIdentifierType=spdx3.ExternalIdentifierType.other,
                identifier=str(doi),
                comment="DOI",
            )
        )

    # ExternalRef: arXiv papers
    arxiv_ids = ai_model.arxiv_ids or ai_model.extra_lists.get("hf.arxiv") or []
    for arxiv_id in arxiv_ids:
        arxiv_str = str(arxiv_id)
        loc = (
            arxiv_str
            if arxiv_str.startswith(("http://", "https://"))
            else f"https://arxiv.org/abs/{arxiv_str}"
        )
        ai_pkg.externalRef.append(
            spdx3.ExternalRef(
                externalRefType=spdx3.ExternalRefType.documentation,
                locator=[loc],
                comment=f"arXiv:{arxiv_str}",
            )
        )

    # ExternalRef: Model page / repository URL
    url = ai_model.url or ai_model.extra_data.get("hf.url")
    if url:
        ai_pkg.externalRef.append(
            spdx3.ExternalRef(
                externalRefType=spdx3.ExternalRefType.altWebPage,
                locator=[str(url)],
                comment="Model page URL",
            )
        )

    # comment: known_biases. Provenance is emitted separately by the caller
    # (see the docstring's Provenance section above).
    if ai_model.usage.known_biases:
        ai_pkg.comment = "Known biases: " + "; ".join(ai_model.usage.known_biases)

    return ai_pkg


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def add_ai_models(
    ai_models: list[AiModelMetadata],
    main_package_spdx_id: str,
    file_spdx_ids: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    registry: IdRegistry | None = None,
    provenance_format: str = "both",
    encoder: ProvenanceEncoder | None = None,
    provenance_detail: str = "minimal",
    preserve_source_metadata: str = "auto",
) -> None:
    """Build ``ai_AIPackage`` and ``contains`` relationship elements for each
    AI model and add them to the exporter.

    For each entry in ``ai_models``:

    - An ``ai_AIPackage`` element is built from the extracted metadata.
    - A ``contains`` relationship links the main Python package to the AI model.
    - ``type_of_model`` and ``architecture`` are both stored in
      ``ai_typeOfModel``.
    - ``quantization`` and hyperparameters are stored as ``ai_hyperparameter``
      DictionaryEntry list (quantization first).
    - ``domain`` + ``usage.domains`` -> ``ai_domain`` (merged, de-duplicated).
    - ``usage.limitations`` -> ``ai_limitation`` (joined string).
    - ``usage.safety_risk_assessment`` -> ``ai_safetyRiskAssessment`` enum.
    - ``usage.intended_use`` / ``usage.unintended_use`` -> merged into
      ``ai_informationAboutApplication`` JSON alongside I/O specs.
    - ``usage.known_biases`` -> SPDX ``comment``; ``provenance`` -> a Core
      ``Annotation`` and/or legacy ``comment``, per *provenance_format*.

    The caller is responsible for appending
    ``ProfileIdentifierType.ai`` to the document's ``profileConformance``
    when at least one AI model is present.

    Args:
        ai_models: List of extracted :class:`~pitloom.core.ai_metadata.AiModelMetadata`.
        main_package_spdx_id: SPDX ID of the parent Python package.
        creation_info: Shared ``CreationInfo`` for all new elements.
        doc_name: Document name (project name) for SPDX ID generation.
        doc_uuid: Document-scoped UUID used in SPDX ID generation.
        exporter: Receives the new package and relationship elements.
        registry: Optional stable file/entity id registry (see
            :mod:`pitloom.ids`). When given, each model is looked up via
            :func:`_lookup_ai_model_entity` (by name, physical path, then
            file stem); a match reuses that registered ``spdxId`` instead of
            minting a fresh one -- unifying a scan-discovered model (e.g. the
            wheel's own packaged model file) with the ``ai_AIPackage`` a
            ``pitloom.loom`` fragment already registered for the same model.
        provenance_format: How to record metadata provenance -- see
            :func:`~pitloom.assemble.spdx3.provenance.emit_provenance`.
        encoder: Provenance statement encoder; defaults to the registered
            default schema.
        provenance_detail: ``"minimal"`` (default) keeps only high-signal
            field sources; ``"full"`` records every field.
        preserve_source_metadata: Whether to embed each model's verbatim
            original metadata blob (P1) -- ``"auto"`` (default) only when the
            model file is not shipped in the distribution, else ``"always"``/
            ``"never"``. See :func:`_should_preserve_metadata`.
    """
    for ai_model in ai_models:
        entity_spdx_id = _lookup_ai_model_entity(ai_model, registry)
        ai_pkg = _build_ai_package(
            ai_model, creation_info, doc_name, doc_uuid, entity_spdx_id=entity_spdx_id
        )
        exporter.add_package(ai_pkg)
        emit_provenance(
            subject=ai_pkg,
            provenance=ai_model.provenance,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_format=provenance_format,
            encoder=encoder,
            provenance_detail=provenance_detail,
        )
        _emit_source_metadata(
            ai_model,
            ai_pkg,
            file_spdx_ids,
            preserve_source_metadata,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
        )

        if ai_model.datasets:
            add_datasets_for_model(
                ai_package_spdx_id=require_spdx_id(ai_pkg),
                datasets=ai_model.datasets,
                creation_info=creation_info,
                doc_name=doc_name,
                doc_uuid=doc_uuid,
                exporter=exporter,
                provenance_format=provenance_format,
                encoder=encoder,
                provenance_detail=provenance_detail,
            )

        if ai_model.license:
            rel_declared, rel_concluded = build_license_elements(
                license_id=ai_model.license,
                package_spdx_id=require_spdx_id(ai_pkg),
                license_provenance=ai_model.provenance.get(
                    "license",
                    "Source: model file / Hugging Face Hub",
                ),
                creation_info=creation_info,
                doc_name=doc_name,
                doc_uuid=doc_uuid,
                exporter=exporter,
                provenance_format=provenance_format,
                encoder=encoder,
                provenance_detail=provenance_detail,
            )
            if rel_declared:
                exporter.add_relationship(rel_declared)
            if rel_concluded:
                exporter.add_relationship(rel_concluded)

        rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                "Relationship",
                doc_name=doc_name,
                doc_uuid=doc_uuid,
            ),
            from_=main_package_spdx_id,
            to=[require_spdx_id(ai_pkg)],
            relationshipType=spdx3.RelationshipType.contains,
            creationInfo=creation_info,
        )
        exporter.add_relationship(rel)

        model_file_id = (
            file_spdx_ids.get(ai_model.format_info.file_path_relative)
            if ai_model.format_info.file_path_relative
            else None
        )
        if model_file_id:
            rel_contains_file = spdx3.Relationship(
                spdxId=generate_spdx_id(
                    "Relationship",
                    doc_name=doc_name,
                    doc_uuid=doc_uuid,
                ),
                from_=ai_pkg.spdxId,
                to=[model_file_id],
                relationshipType=spdx3.RelationshipType.contains,
                creationInfo=creation_info,
            )
            exporter.add_relationship(rel_contains_file)

            for usage_path in ai_model.usage_files:
                usage_file_id = file_spdx_ids.get(usage_path)
                if usage_file_id:
                    # Scoped `runtime`: the usage file (e.g. predict.py) loads
                    # the model as part of the shipped artifact's execution --
                    # contrast with the `generates` relationships loom.run
                    # emits for a build-time training/preprocessing script,
                    # which are scoped `build` (see pitloom.loom).
                    rel_usage = spdx3.LifecycleScopedRelationship(
                        spdxId=generate_spdx_id(
                            "Relationship",
                            doc_name=doc_name,
                            doc_uuid=doc_uuid,
                        ),
                        from_=usage_file_id,
                        to=[model_file_id],
                        relationshipType=spdx3.RelationshipType.hasDataFile,
                        scope=spdx3.LifecycleScopeType.runtime,
                        creationInfo=creation_info,
                    )
                    exporter.add_relationship(rel_usage)
