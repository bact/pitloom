# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Build SPDX 3 Core/Annotation elements recording metadata provenance.

See Also:
    :mod:`pitloom.assemble.spdx3._provenance_encoders` for schema encoders
    and value parsing.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, TypedDict, cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._provenance_encoders import (
    DEFAULT_SCHEMA_ID,
    DEPLOYED_PACKAGE_SOURCE,
    INSTALLED_DEPENDENCY_SOURCE,
    TRANSPARENT_SOURCES,
    VALID_PROVENANCE_DETAIL,
    VALID_PROVENANCE_FORMATS,
    PitloomV1Encoder,
    ProvenanceEncoder,
    filter_high_signal,
    is_license_concluded,
    resolve_encoder,
)
from pitloom.core.ai_metadata import MAX_MODEL_ENTRIES
from pitloom.core.canonical_json import (
    canonical_json,
    canonical_json_bytes,
    json_safe,
)
from pitloom.core.models import generate_spdx_id
from pitloom.core.project import ConflictCandidate
from pitloom.core.provenance import (
    ProvenanceConfig,
    escape_provenance_comment_part,
    parse_provenance_value,
    require_max_source_metadata_bytes,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

log = logging.getLogger(__name__)

#: Statement-schema URL for a fragment-unification process Annotation (A1).
UNIFICATION_SCHEMA_URL = "https://pitloom.dev/provenance/unification/1"

#: Statement-schema URL for a preserved verbatim artifact-metadata blob (P1).
#: A scalar is its :func:`~pitloom.core.scalar_text.scalar_text`;
#: ``valueTypes`` names the type of each non-string scalar.
ARTIFACT_METADATA_SCHEMA_URL = "https://pitloom.dev/provenance/artifact-metadata/2"

#: Statement-schema URL for a multi-source field-value disagreement (G2).
CONFLICT_SCHEMA_URL = "https://pitloom.dev/provenance/conflict/1"

#: Statement-schema URL for an enrichment run's field changes (E1/E2).
ENRICHMENT_SCHEMA_URL = "https://pitloom.dev/provenance/enrichment/1"

__all__ = [
    "ARTIFACT_METADATA_SCHEMA_URL",
    "CONFLICT_SCHEMA_URL",
    "DEFAULT_SCHEMA_ID",
    "DEPLOYED_PACKAGE_SOURCE",
    "ENRICHMENT_SCHEMA_URL",
    "INSTALLED_DEPENDENCY_SOURCE",
    "TRANSPARENT_SOURCES",
    "UNIFICATION_SCHEMA_URL",
    "VALID_PROVENANCE_DETAIL",
    "VALID_PROVENANCE_FORMATS",
    "ConflictCandidate",
    "EnrichedFieldEntry",
    "PitloomV1Encoder",
    "ProvenanceEncoder",
    "build_conflict_annotation",
    "build_enrichment_annotation",
    "build_provenance_annotation",
    "build_provenance_comment",
    "build_source_metadata_annotation",
    "build_unification_annotation",
    "emit_provenance",
    "filter_high_signal",
    "is_license_concluded",
    "parse_provenance_value",
    "resolve_encoder",
]


def _build_json_annotation(
    subject_spdx_id: str,
    statement_obj: dict[str, Any],
    creation_info: spdx3.CreationInfo,
    annotation_spdx_id: str,
) -> spdx3.Annotation:
    """Build an ``application/json`` Annotation with the given id."""
    return spdx3.Annotation(
        spdxId=annotation_spdx_id,
        creationInfo=creation_info,
        annotationType=spdx3.AnnotationType.other,
        contentType="application/json",
        subject=subject_spdx_id,
        statement=canonical_json(statement_obj),
    )


def build_unification_annotation(
    subject_spdx_id: str,
    criterion: str,
    unified_ids: list[str],
    fragments: list[str],
    creation_info: spdx3.CreationInfo,
    annotation_spdx_id: str,
) -> spdx3.Annotation:
    """Return an Annotation recording why fragment elements were unified (A1)."""
    statement = {
        "schema": UNIFICATION_SCHEMA_URL,
        "kind": "unification",
        "criterion": criterion,
        # Canonical: RFC 8785 (JCS) canonicalizes JSON *object* member
        # order but not *array* order, so these sorts are load-bearing
        # for output determinism, not redundant with canonical_json().
        "unified": sorted(unified_ids),
        "fragments": sorted(fragments),
    }
    return _build_json_annotation(
        subject_spdx_id, statement, creation_info, annotation_spdx_id
    )


def build_conflict_annotation(
    subject_spdx_id: str,
    field: str,
    candidates: list[ConflictCandidate],
    creation_info: spdx3.CreationInfo,
    annotation_spdx_id: str,
) -> spdx3.Annotation:
    """Return an Annotation recording multi-source disagreement (G2)."""
    statement = {
        "schema": CONFLICT_SCHEMA_URL,
        "kind": "conflict",
        "field": field,
        "candidates": candidates,
    }
    return _build_json_annotation(
        subject_spdx_id, statement, creation_info, annotation_spdx_id
    )


class EnrichedFieldEntry(TypedDict):
    """One field an enrichment run changed on a single element (E1/E2)."""

    field: str
    before: Any
    after: Any
    role: str
    source: str


def build_enrichment_annotation(
    subject_spdx_id: str,
    changes: list[EnrichedFieldEntry],
    creation_info: spdx3.CreationInfo,
    annotation_spdx_id: str,
) -> spdx3.Annotation:
    """Return an Annotation recording what an enrichment run changed."""
    statement = {
        "schema": ENRICHMENT_SCHEMA_URL,
        "kind": "enrichment",
        "changes": changes,
    }
    return _build_json_annotation(
        subject_spdx_id, statement, creation_info, annotation_spdx_id
    )


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _artifact_metadata_envelope(
    source_format: str,
    kept_metadata: dict[str, Any],
    dropped_keys: list[str],
    max_metadata_bytes: int,
    value_types: Mapping[str, str],
    capped_key_count: int,
) -> dict[str, Any]:
    """Build the artifact-metadata ``statement`` envelope (P1).

    ``valueTypes`` holds the *value_types* of the kept keys, and is left out
    when there are none. ``truncatedKeyCount`` counts both the *dropped_keys*
    (named in ``truncatedKeys``, cut to ``maxMetadataBytes``) and the
    *capped_key_count* keys the reader left out over ``maxEntries``
    (unnamed: listing them would cost what the cap saves).
    """
    statement: dict[str, Any] = {
        "schema": ARTIFACT_METADATA_SCHEMA_URL,
        "kind": "artifact-metadata",
        "format": source_format,
        "metadata": kept_metadata,
    }
    kept_types = {k: v for k, v in value_types.items() if k in kept_metadata}
    if kept_types:
        statement["valueTypes"] = kept_types  # RFC 8785 sorts the keys
    if dropped_keys or capped_key_count:
        statement["truncated"] = True
        statement["truncatedKeyCount"] = len(dropped_keys) + capped_key_count
    if dropped_keys:
        # Canonical: RFC 8785 doesn't reorder JSON arrays (see
        # build_unification_annotation above) -- this sort is load-bearing.
        statement["truncatedKeys"] = sorted(dropped_keys)
        statement["maxMetadataBytes"] = max_metadata_bytes
    if capped_key_count:
        statement["maxEntries"] = MAX_MODEL_ENTRIES
    return statement


def _truncate_metadata_for_budget(
    metadata: dict[str, Any],
    source_format: str,
    max_metadata_bytes: int,
    value_types: Mapping[str, str],
    capped_key_count: int,
) -> tuple[dict[str, Any], list[str]] | None:
    """Drop the largest metadata entries first until the artifact-metadata
    envelope's serialized size fits ``max_metadata_bytes``. A dropped key
    takes its ``valueTypes`` entry with it.

    Returns ``(kept_metadata, dropped_keys)`` -- ``dropped_keys`` is empty
    when nothing needed dropping. Returns ``None`` if even an empty
    ``metadata: {}`` (plus the marker fields) wouldn't fit the budget.

    Re-checks the real serialized size of the candidate envelope at every
    step rather than approximating it -- the realistic key count here (a
    single AI model's metadata table) is small enough (dozens of keys, not
    thousands) that this stays cheap even though it isn't asymptotically
    optimal.
    """
    sanitized = cast(dict[str, Any], json_safe(metadata))

    def envelope_bytes(kept: dict[str, Any], dropped: list[str]) -> int:
        envelope = _artifact_metadata_envelope(
            source_format,
            kept,
            dropped,
            max_metadata_bytes,
            value_types,
            capped_key_count,
        )
        return len(canonical_json_bytes(envelope))

    if envelope_bytes(sanitized, []) <= max_metadata_bytes:
        return sanitized, []

    entry_bytes = {
        key: len(canonical_json_bytes(key)) + 1 + len(canonical_json_bytes(value))
        for key, value in sanitized.items()
    }
    # Canonical: this order (largest entry first, key as tiebreak) decides
    # *which* keys get dropped when the budget is tight, not just their
    # order -- content-affecting, not cosmetic. Final truncatedKeys order
    # is re-sorted alphabetically above regardless.
    drop_order = sorted(sanitized, key=lambda key: (-entry_bytes[key], key))

    kept = dict(sanitized)
    dropped: list[str] = []
    for key in drop_order:
        del kept[key]
        dropped.append(key)
        if envelope_bytes(kept, dropped) <= max_metadata_bytes:
            return kept, dropped

    return None


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def build_source_metadata_annotation(
    subject_spdx_id: str,
    source_format: str,
    metadata: dict[str, Any],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    max_metadata_bytes: int = 0,
    value_types: Mapping[str, str] | None = None,
    capped_key_count: int = 0,
) -> spdx3.Annotation | None:
    """Return an Annotation embedding verbatim original metadata (P1).

    *value_types* (``AiModelMetadata.raw_metadata_types``) becomes the
    envelope's ``valueTypes``, cut to the keys kept.

    *capped_key_count* (``AiModelMetadata.raw_metadata_dropped``), the keys
    the reader left out over :data:`~pitloom.core.ai_metadata.MAX_MODEL_ENTRIES`,
    marks the result ``truncated`` with that ``truncatedKeyCount`` and
    ``maxEntries``, without naming the keys.

    ``max_metadata_bytes`` (0 = unlimited, the default) caps the serialized
    Annotation's size: when exceeded, the largest metadata entries are
    dropped first and the result is marked with
    ``truncated``/``truncatedKeys``/``truncatedKeyCount``/
    ``maxMetadataBytes`` so the reduction is visible rather than silent.
    If even an empty ``metadata: {}`` plus the marker fields wouldn't fit
    the budget, no Annotation is emitted at all.
    """
    if not metadata:
        return None

    max_metadata_bytes = require_max_source_metadata_bytes(max_metadata_bytes)
    types = value_types or {}
    dropped_keys: list[str] = []
    kept_metadata = metadata
    if max_metadata_bytes:
        result = _truncate_metadata_for_budget(
            metadata, source_format, max_metadata_bytes, types, capped_key_count
        )
        if result is None:
            log.warning(
                "Artifact-metadata Annotation for %r dropped entirely: "
                "max-source-metadata-bytes=%d is too small to hold even an "
                "empty metadata envelope.",
                subject_spdx_id,
                max_metadata_bytes,
            )
            return None
        kept_metadata, dropped_keys = result
        if dropped_keys and not kept_metadata:
            log.warning(
                "Artifact-metadata Annotation for %r had all %d metadata "
                "keys dropped to fit max-source-metadata-bytes=%d.",
                subject_spdx_id,
                len(dropped_keys),
                max_metadata_bytes,
            )

    statement = _artifact_metadata_envelope(
        source_format,
        kept_metadata,
        dropped_keys,
        max_metadata_bytes,
        types,
        capped_key_count,
    )
    annotation_spdx_id = generate_spdx_id(
        "Annotation", doc_name=doc_name, doc_uuid=doc_uuid
    )
    return _build_json_annotation(
        subject_spdx_id, statement, creation_info, annotation_spdx_id
    )


def build_provenance_comment(provenance: dict[str, str]) -> str | None:
    """Return the human-readable ``"Metadata provenance: ..."`` comment form,
    each part through
    :func:`~pitloom.core.provenance.escape_provenance_comment_part`."""
    if not provenance:
        return None
    return "Metadata provenance: " + "; ".join(
        f"{escape_provenance_comment_part(field, field=True)}: "
        f"{escape_provenance_comment_part(source)}"
        for field, source in provenance.items()
    )


def build_provenance_annotation(
    subject_spdx_id: str,
    provenance: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    encoder: ProvenanceEncoder | None = None,
) -> spdx3.Annotation | None:
    """Return an Annotation recording where each metadata field came from."""
    if not provenance:
        return None

    enc = encoder or resolve_encoder()

    try:
        return spdx3.Annotation(
            spdxId=generate_spdx_id("Annotation", doc_name=doc_name, doc_uuid=doc_uuid),
            creationInfo=creation_info,
            annotationType=spdx3.AnnotationType.other,
            contentType=enc.content_type,
            subject=subject_spdx_id,
            statement=enc.encode(provenance),
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid Annotation for provenance schema {enc.schema_id!r} "
            f"(content_type={enc.content_type!r}): {exc}"
        ) from exc


# pylint: disable=too-many-arguments,too-many-positional-arguments
def emit_provenance(
    subject: spdx3.Element,
    provenance: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Write provenance for *subject* as an Annotation, a ``.comment``, or both."""
    config = provenance_config or ProvenanceConfig()
    provenance_format = config.format
    provenance_detail = config.detail
    if provenance_format not in VALID_PROVENANCE_FORMATS:
        valid = ", ".join(sorted(VALID_PROVENANCE_FORMATS))
        raise ValueError(
            f"Unknown provenance_format {provenance_format!r}; expected one of {valid}"
        )
    if provenance_detail not in VALID_PROVENANCE_DETAIL:
        valid = ", ".join(sorted(VALID_PROVENANCE_DETAIL))
        raise ValueError(
            f"Unknown provenance_detail {provenance_detail!r}; expected one of {valid}"
        )

    if provenance_detail == "minimal":
        provenance = filter_high_signal(provenance)

    if not provenance:
        return

    if provenance_format in ("comment", "both"):
        comment = build_provenance_comment(provenance)
        if comment:
            subject.comment = (
                f"{subject.comment}\n{comment}" if subject.comment else comment
            )

    if provenance_format in ("annotation", "both"):
        annotation = build_provenance_annotation(
            subject_spdx_id=require_spdx_id(subject),
            provenance=provenance,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            encoder=encoder,
        )
        if annotation is not None:
            exporter.add_annotation(annotation)
