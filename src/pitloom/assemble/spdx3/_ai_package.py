# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model package building and external references for SPDX 3.

See also: :mod:`pitloom.assemble.spdx3.ai` for model assembly into SBOM documents.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._display_text import (
    BASE_MODEL,
    BASE_MODEL_RELATIONSHIP,
    escape_element_display_text,
)
from pitloom.assemble.spdx3.provenance import build_source_metadata_annotation
from pitloom.core.ai_metadata import (
    MAX_MODEL_NAME_CHARS,
    AiModelFormat,
    AiModelMetadata,
    SourceMetadata,
    cap_model_name,
    source_metadata,
    value_text,
)
from pitloom.core.canonical_json import canonical_json
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.project import project_relative_or_fallback
from pitloom.core.untrusted_text import escape_display_controls
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.logging_config import NAME_CUT_WARNING, loggable

log = logging.getLogger(__name__)

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


def _source_metadata_blob(ai_model: AiModelMetadata) -> tuple[str, SourceMetadata]:
    """Return ``(format_tag, source metadata)`` for P1 preservation.

    A model file's metadata is its reader's ``raw_metadata`` and
    ``raw_metadata_types``. Only a model of no file format (a Hugging Face
    model) falls back to ``properties`` and the ``extra_data``/
    ``extra_lists`` slots, through the same
    :func:`~pitloom.core.ai_metadata.source_metadata` as a reader: scalars
    as text, typed in ``valueTypes``.
    """
    fmt = str(ai_model.format_info.model_format)
    if ai_model.raw_metadata or fmt != str(AiModelFormat.UNKNOWN):
        return fmt, SourceMetadata(
            raw_metadata=dict(ai_model.raw_metadata),
            raw_metadata_types=dict(ai_model.raw_metadata_types),
        )
    blob: dict[str, Any] = {}
    blob.update(ai_model.properties)
    blob.update(ai_model.extra_data)
    blob.update(ai_model.extra_lists)
    if ai_model.extra_data or ai_model.extra_lists:
        fmt = "huggingface"
    return fmt, source_metadata(blob)


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _emit_source_metadata(
    ai_model: AiModelMetadata,
    ai_pkg: spdx3.ai_AIPackage,
    file_spdx_ids: dict[str, str],
    preserve_source_metadata: str,
    max_source_metadata_bytes: int,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Emit a verbatim artifact-metadata preservation Annotation for *ai_model*."""
    if not _should_preserve_metadata(ai_model, file_spdx_ids, preserve_source_metadata):
        return
    source_format, source = _source_metadata_blob(ai_model)
    annotation = build_source_metadata_annotation(
        subject_spdx_id=require_spdx_id(ai_pkg),
        source_format=source_format,
        metadata=source["raw_metadata"],
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        max_metadata_bytes=max_source_metadata_bytes,
        value_types=source["raw_metadata_types"],
        capped_key_count=ai_model.raw_metadata_dropped,
    )
    if annotation is not None:
        exporter.add_annotation(annotation)


def _ai_model_entity_candidates(ai_model: AiModelMetadata) -> list[str]:
    """Candidate ``ai_AIPackage`` registry lookup names for a
    scan-discovered model, in preference order.

    Returns the candidate names only -- no registry lookup here; a
    caller passes this list to
    :meth:`~pitloom.id_registry.IdRegistrySession.entity_id`, which tries
    each in order and claims the first hit.
    """
    candidates: list[str] = []
    if ai_model.own_name:
        candidates.append(ai_model.own_name)
    if ai_model.format_info.physical_path:
        # The scanner already stores a stable path; this guard is
        # defensive for a hand-built AiModelMetadata whose physical_path is
        # an absolute (e.g. --allow-build temporary) path that could never
        # match a project-relative registry key. Fall back to
        # file_path_relative.
        resolved = project_relative_or_fallback(
            ai_model.format_info.physical_path,
            ai_model.format_info.file_path_relative or "",
        )
        if resolved:
            candidates.append(resolved)
    if ai_model.file_name_stem:
        candidates.append(ai_model.file_name_stem)
    return candidates


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


def _model_where(ai_model: AiModelMetadata) -> tuple[str, str]:
    """The ``FORMAT=``/``FILE=`` values naming *ai_model* in a warning."""
    info = ai_model.format_info
    where = info.physical_path or info.file_path_relative or info.file_name
    return (
        _source_metadata_blob(ai_model)[0],  # "huggingface" for a Hub model
        loggable(where or ai_model.url or ai_model.resolve_name()[0]),
    )


def cap_related_name(name: str, label: str, ai_model: AiModelMetadata) -> str:
    """*name*, of an element *ai_model* brings in (its *label*, e.g.
    ``"dataset name"``), cut as a model's own name is
    (:func:`~pitloom.core.ai_metadata.cap_model_name`), and said so."""
    capped = cap_model_name(name)
    if capped != name:
        log.warning(
            NAME_CUT_WARNING,
            *_model_where(ai_model),
            label,
            len(name),
            MAX_MODEL_NAME_CHARS,
        )
    return capped


def _find_or_create_base_pkg(
    base_model_str: str, ctx: _LineageContext, ai_model: AiModelMetadata
) -> tuple[str, spdx3.ai_AIPackage | None]:
    """Find an existing base model package, or create a new external
    reference node; return its spdxId and the package when created."""
    pkg_name = cap_related_name(
        base_model_str.rsplit("/", maxsplit=1)[-1], "base model name", ai_model
    )
    # A package already finished has its name escaped.
    names = {base_model_str, pkg_name}
    names |= {escape_display_controls(name) for name in names}
    for obj in ctx.exporter.object_set.objects:
        if isinstance(obj, spdx3.ai_AIPackage) and obj.name in names:
            return require_spdx_id(obj), None

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
    return base_spdx_id, base_pkg


def _add_base_model_lineage(
    ai_pkg: spdx3.ai_AIPackage,
    ai_model: AiModelMetadata,
    ctx: _LineageContext,
) -> list[tuple[str, spdx3.Element]]:
    """Add native descendantOf Relationship linking ai_pkg to its base model;
    return the elements created, labelled for :func:`finish_ai_package`."""
    base_model_id = ai_model.base_model or ai_model.extra_data.get("hf.base_model")
    if not base_model_id:
        return []

    created: list[tuple[str, spdx3.Element]] = []
    base_model_str = str(base_model_id)
    base_spdx_id = ctx.cache.get(base_model_str)
    if base_spdx_id is None:
        base_spdx_id, base_pkg = _find_or_create_base_pkg(base_model_str, ctx, ai_model)
        ctx.cache[base_model_str] = base_spdx_id
        if base_pkg is not None:
            created.append((BASE_MODEL, base_pkg))

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
        created.append((BASE_MODEL_RELATIONSHIP, rel))
    return created


def _populate_ai_pkg_hyperparameters(
    ai_pkg: spdx3.ai_AIPackage, ai_model: AiModelMetadata
) -> None:
    """Populate hyperparameters dictionary entries on ai_AIPackage."""
    hyperparameter_entries: list[spdx3.DictionaryEntry] = []
    if ai_model.quantization:
        hyperparameter_entries.append(
            spdx3.DictionaryEntry(key="quantization", value=ai_model.quantization)
        )
    # Sorted by key: the source's own order must not change the output.
    for key, val in sorted(
        ai_model.hyperparameters.items(), key=lambda item: str(item[0])
    ):
        hyperparameter_entries.append(
            spdx3.DictionaryEntry(key=str(key), value=value_text(val))
        )
    if hyperparameter_entries:
        ai_pkg.ai_hyperparameter = hyperparameter_entries


def _populate_ai_pkg_domains_and_safety(
    ai_pkg: spdx3.ai_AIPackage, ai_model: AiModelMetadata
) -> None:
    """Populate domain, limitations, and safety risk assessment fields."""
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


def _populate_ai_pkg_io_application(
    ai_pkg: spdx3.ai_AIPackage, ai_model: AiModelMetadata
) -> None:
    """Populate informationAboutApplication JSON structure on ai_AIPackage."""
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
        ai_pkg.ai_informationAboutApplication = canonical_json(io_parts)


def finish_display_text(
    ai_model: AiModelMetadata, elements: Iterable[tuple[str, spdx3.Element]]
) -> None:
    """Escape the invisible and bidi controls in the display text of each
    of *elements*, built from *ai_model* and each labelled for the warning
    (``""`` for the model's own package), and say once which properties had
    one; quiet when none had."""
    changed = sorted(
        {
            f"{label} {prop}" if label else prop
            for label, element in elements
            for prop in escape_element_display_text(element)
        }
    )
    if not changed:
        return
    log.warning(
        "FORMAT=%s FILE=%s: invisible or bidi control characters written as "
        "\\uXXXX in %s",
        *_model_where(ai_model),
        ", ".join(changed),
    )


def finish_ai_package(
    ai_pkg: spdx3.ai_AIPackage,
    ai_model: AiModelMetadata,
    related: Iterable[tuple[str, spdx3.Element]] = (),
) -> None:
    """:func:`finish_display_text` for *ai_pkg*, built from *ai_model*, and
    the *related* elements the model brought in (its base model, its
    datasets). Called by every surface once the last of them is written (the
    provenance ``comment`` included), so one model gives one warning. The
    ``spdxId`` keeps the name as resolved (its IRI percent-encodes these
    controls), so it still agrees with the registry; the artifact-metadata
    annotation keeps the model's metadata as read."""
    finish_display_text(ai_model, [("", ai_pkg), *related])


def _build_ai_package(
    ai_model: AiModelMetadata,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    entity_spdx_id: str | None = None,
) -> spdx3.ai_AIPackage:
    """Build an ``ai_AIPackage`` SPDX 3 element from an :class:`AiModelMetadata`.

    Its display text is escaped by :func:`finish_ai_package`, once its
    provenance comment is written too."""
    pkg_name, _ = ai_model.resolve_name()
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

    _populate_ai_pkg_hyperparameters(ai_pkg, ai_model)
    _populate_ai_pkg_domains_and_safety(ai_pkg, ai_model)
    _populate_ai_pkg_io_application(ai_pkg, ai_model)
    _add_external_identifiers_and_refs(ai_pkg, ai_model)

    if ai_model.usage.known_biases:
        ai_pkg.comment = "Known biases: " + "; ".join(ai_model.usage.known_biases)

    return ai_pkg
