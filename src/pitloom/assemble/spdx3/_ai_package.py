# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model package building and external references for SPDX 3.

See also: :mod:`pitloom.assemble.spdx3.ai` for model assembly into SBOM documents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import build_source_metadata_annotation
from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.ids import IdRegistry

# Valid SPDX 3 ai_safetyRiskAssessmentType enum values (lowercase).
_SAFETY_RISK_VALUES = {"high", "medium", "low", "serious"}


def _should_preserve_metadata(
    ai_model: AiModelMetadata,
    file_spdx_ids: dict[str, str],
    setting: str,
) -> bool:
    """Decide whether to embed *ai_model*'s verbatim original metadata (P1)."""
    if setting == "always":
        return True
    if setting == "never":
        return False
    rel = ai_model.format_info.file_path_relative
    shipped = bool(rel) and rel in file_spdx_ids
    return not shipped


def _source_metadata_blob(ai_model: AiModelMetadata) -> tuple[str, dict[str, Any]]:
    """Return ``(format_tag, metadata)`` for P1 preservation."""
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


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
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
    """Emit a verbatim artifact-metadata preservation Annotation for *ai_model*."""
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
    """Resolve a registered ``ai_AIPackage`` id for a scan-discovered model."""
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


def _add_external_identifiers_and_refs(
    ai_pkg: spdx3.ai_AIPackage,
    ai_model: AiModelMetadata,
) -> None:
    """Add ExternalIdentifier and ExternalRef elements to an ai_AIPackage."""
    doi = ai_model.doi or ai_model.extra_data.get("hf.doi")
    if doi:
        ai_pkg.externalIdentifier.append(
            spdx3.ExternalIdentifier(
                externalIdentifierType=spdx3.ExternalIdentifierType.other,
                identifier=str(doi),
                comment="DOI",
            )
        )

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

    url = ai_model.url or ai_model.extra_data.get("hf.url")
    if url:
        ai_pkg.externalRef.append(
            spdx3.ExternalRef(
                externalRefType=spdx3.ExternalRefType.altWebPage,
                locator=[str(url)],
                comment="Model page URL",
            )
        )


@dataclass(frozen=True)
class _LineageContext:
    creation_info: spdx3.CreationInfo
    doc_name: str
    doc_uuid: str
    exporter: Spdx3JsonExporter
    cache: dict[str, str] = field(default_factory=dict)


def _add_base_model_lineage(
    ai_pkg: spdx3.ai_AIPackage,
    ai_model: AiModelMetadata,
    ctx: _LineageContext,
) -> None:
    """Add native descendantOf Relationship linking ai_pkg to its base model."""
    base_model_id = ai_model.base_model or ai_model.extra_data.get("hf.base_model")
    if not base_model_id:
        return

    base_model_str = str(base_model_id)
    base_spdx_id = ctx.cache.get(base_model_str)
    if base_spdx_id is None:
        pkg_name = (
            base_model_str.rsplit("/", maxsplit=1)[-1]
            if "/" in base_model_str
            else base_model_str
        )
        existing_spdx_id = None
        for obj in ctx.exporter.object_set.objects:
            if isinstance(obj, spdx3.ai_AIPackage) and obj.name in (
                base_model_str,
                pkg_name,
            ):
                existing_spdx_id = require_spdx_id(obj)
                break

        if existing_spdx_id:
            base_spdx_id = existing_spdx_id
        else:
            base_spdx_id = generate_spdx_id(
                f"AIPackage-{pkg_name}", doc_name=ctx.doc_name, doc_uuid=ctx.doc_uuid
            )
            base_pkg = spdx3.ai_AIPackage(
                spdxId=base_spdx_id,
                name=pkg_name,
                creationInfo=ctx.creation_info,
            )
            url = (
                base_model_str
                if base_model_str.startswith(("http://", "https://"))
                else f"https://huggingface.co/{base_model_str}"
            )
            base_pkg.externalRef.append(
                spdx3.ExternalRef(
                    externalRefType=spdx3.ExternalRefType.altWebPage,
                    locator=[url],
                    comment="Base model repository",
                )
            )
            ctx.exporter.add_package(base_pkg)
        ctx.cache[base_model_str] = base_spdx_id

    rel_relation = ai_model.base_model_relation or ai_model.extra_data.get(
        "hf.base_model_relation"
    )

    rel = build_relationship(
        from_id=require_spdx_id(ai_pkg),
        to_ids=[base_spdx_id],
        rel_type=spdx3.RelationshipType.descendantOf,
        doc_name=ctx.doc_name,
        doc_uuid=ctx.doc_uuid,
        creation_info=ctx.creation_info,
        id_suffix="Relationship-lineage",
    )
    if rel:
        if rel_relation:
            rel.comment = f"base_model_relation:{rel_relation}"
        ctx.exporter.add_relationship(rel)


def _build_ai_package(
    ai_model: AiModelMetadata,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    entity_spdx_id: str | None = None,
) -> spdx3.ai_AIPackage:
    """Build an ``ai_AIPackage`` SPDX 3 element from an :class:`AiModelMetadata`."""
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

    type_of_model_values: list[str] = []
    if ai_model.type_of_model:
        type_of_model_values.append(ai_model.type_of_model)
    if ai_model.architecture:
        type_of_model_values.append(ai_model.architecture)
    if type_of_model_values:
        ai_pkg.ai_typeOfModel = type_of_model_values

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

    combined_domains: list[str] = []
    seen_domains: set[str] = set()
    for d in list(ai_model.domain) + list(ai_model.usage.domains):
        if d not in seen_domains:
            combined_domains.append(d)
            seen_domains.add(d)
    if combined_domains:
        ai_pkg.ai_domain = combined_domains

    if ai_model.usage.limitations:
        ai_pkg.ai_limitation = "; ".join(ai_model.usage.limitations)

    if ai_model.usage.safety_risk_assessment:
        risk_val = ai_model.usage.safety_risk_assessment.lower()
        if risk_val in _SAFETY_RISK_VALUES:
            ai_pkg.ai_safetyRiskAssessment = getattr(
                spdx3.ai_SafetyRiskAssessmentType, risk_val, None
            )

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

    _add_external_identifiers_and_refs(ai_pkg, ai_model)

    if ai_model.usage.known_biases:
        ai_pkg.comment = "Known biases: " + "; ".join(ai_model.usage.known_biases)

    return ai_pkg
