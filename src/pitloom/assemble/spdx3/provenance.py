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

import base64
import logging
import math
from typing import Any, TypedDict, cast

import rfc8785
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._provenance_encoders import (
    _KEY_MAP,
    DEFAULT_SCHEMA_ID,
    TRANSPARENT_SOURCES,
    VALID_PROVENANCE_DETAIL,
    VALID_PROVENANCE_FORMATS,
    PitloomV1Encoder,
    ProvenanceEncoder,
    filter_high_signal,
    parse_provenance_value,
    resolve_encoder,
)
from pitloom.core.models import generate_spdx_id
from pitloom.core.provenance import (
    ProvenanceConfig,
    normalize_max_source_metadata_bytes,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

log = logging.getLogger(__name__)

#: Statement-schema URL for a fragment-unification process Annotation (A1).
UNIFICATION_SCHEMA_URL = "https://pitloom.dev/provenance/unification/1"

#: Statement-schema URL for a preserved verbatim artifact-metadata blob (P1).
ARTIFACT_METADATA_SCHEMA_URL = "https://pitloom.dev/provenance/artifact-metadata/1"

#: Statement-schema URL for a multi-source field-value disagreement (G2).
CONFLICT_SCHEMA_URL = "https://pitloom.dev/provenance/conflict/1"

#: Statement-schema URL for an enrichment run's field changes (E1/E2).
ENRICHMENT_SCHEMA_URL = "https://pitloom.dev/provenance/enrichment/1"

__all__ = [
    "ARTIFACT_METADATA_SCHEMA_URL",
    "CONFLICT_SCHEMA_URL",
    "DEFAULT_SCHEMA_ID",
    "ENRICHMENT_SCHEMA_URL",
    "TRANSPARENT_SOURCES",
    "UNIFICATION_SCHEMA_URL",
    "VALID_PROVENANCE_DETAIL",
    "VALID_PROVENANCE_FORMATS",
    "ConflictCandidate",
    "EnrichedFieldEntry",
    "PitloomV1Encoder",
    "ProvenanceEncoder",
    "_KEY_MAP",
    "build_conflict_annotation",
    "build_enrichment_annotation",
    "build_provenance_annotation",
    "build_provenance_comment",
    "build_source_metadata_annotation",
    "build_unification_annotation",
    "emit_provenance",
    "filter_high_signal",
    "parse_provenance_value",
    "resolve_encoder",
]


# pylint: disable=too-many-return-statements
def _sanitize_for_json(obj: object) -> object:
    """Recursively normalize preserved raw metadata into JSON-safe values."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, (bytes, bytearray)):
        return base64.b64encode(bytes(obj)).decode("ascii")
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        sanitized = [_sanitize_for_json(v) for v in obj]
        return sorted(sanitized, key=_canonical_bytes)
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    # RFC 8785 has no default=str-style hook for unrecognized types (unlike
    # plain json.dumps) -- stringify anything else here so it never reaches
    # the serializer, matching the previous default=str fallback.
    return str(obj)


def _canonical_bytes(obj: object) -> bytes:
    """Serialize obj via RFC 8785 (JSON Canonicalization Scheme), as bytes."""
    return rfc8785.dumps(cast(Any, _sanitize_for_json(obj)))


def _canonical_json(obj: object) -> str:
    """Serialize obj via RFC 8785 (JSON Canonicalization Scheme), as a str."""
    return _canonical_bytes(obj).decode("utf-8")


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
        statement=_canonical_json(statement_obj),
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
        "unified": sorted(unified_ids),
        "fragments": sorted(fragments),
    }
    return _build_json_annotation(
        subject_spdx_id, statement, creation_info, annotation_spdx_id
    )


class _ConflictCandidateRequired(TypedDict):
    value: str
    role: str
    source: str


class ConflictCandidate(_ConflictCandidateRequired, total=False):
    """One source's reported value for a field under dispute (G2)."""

    ref: str


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


def _artifact_metadata_envelope(
    source_format: str,
    kept_metadata: dict[str, Any],
    dropped_keys: list[str],
    max_metadata_bytes: int,
) -> dict[str, Any]:
    """Build the artifact-metadata ``statement`` envelope (P1)."""
    statement: dict[str, Any] = {
        "schema": ARTIFACT_METADATA_SCHEMA_URL,
        "kind": "artifact-metadata",
        "format": source_format,
        "metadata": kept_metadata,
    }
    if dropped_keys:
        statement["truncated"] = True
        statement["truncatedKeys"] = sorted(dropped_keys)
        statement["truncatedKeyCount"] = len(dropped_keys)
        statement["maxMetadataBytes"] = max_metadata_bytes
    return statement


def _truncate_metadata_for_budget(
    metadata: dict[str, Any],
    source_format: str,
    max_metadata_bytes: int,
) -> tuple[dict[str, Any], list[str]] | None:
    """Drop the largest metadata entries first until the artifact-metadata
    envelope's serialized size fits ``max_metadata_bytes``.

    Returns ``(kept_metadata, dropped_keys)`` -- ``dropped_keys`` is empty
    when nothing needed dropping. Returns ``None`` if even an empty
    ``metadata: {}`` (plus the marker fields) wouldn't fit the budget.

    Re-checks the real serialized size of the candidate envelope at every
    step rather than approximating it -- the realistic key count here (a
    single AI model's metadata table) is small enough (dozens of keys, not
    thousands) that this stays cheap even though it isn't asymptotically
    optimal.
    """
    sanitized = cast(dict[str, Any], _sanitize_for_json(metadata))

    def envelope_bytes(kept: dict[str, Any], dropped: list[str]) -> int:
        envelope = _artifact_metadata_envelope(
            source_format, kept, dropped, max_metadata_bytes
        )
        return len(_canonical_bytes(envelope))

    if envelope_bytes(sanitized, []) <= max_metadata_bytes:
        return sanitized, []

    entry_bytes = {
        key: len(_canonical_bytes(key)) + 1 + len(_canonical_bytes(value))
        for key, value in sanitized.items()
    }
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
) -> spdx3.Annotation | None:
    """Return an Annotation embedding verbatim original metadata (P1).

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

    max_metadata_bytes = normalize_max_source_metadata_bytes(max_metadata_bytes)
    dropped_keys: list[str] = []
    kept_metadata = metadata
    if max_metadata_bytes:
        result = _truncate_metadata_for_budget(
            metadata, source_format, max_metadata_bytes
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
        source_format, kept_metadata, dropped_keys, max_metadata_bytes
    )
    annotation_spdx_id = generate_spdx_id(
        "Annotation", doc_name=doc_name, doc_uuid=doc_uuid
    )
    return _build_json_annotation(
        subject_spdx_id, statement, creation_info, annotation_spdx_id
    )


def build_provenance_comment(provenance: dict[str, str]) -> str | None:
    """Return the human-readable ``"Metadata provenance: ..."`` comment form."""
    if not provenance:
        return None
    return "Metadata provenance: " + "; ".join(
        f"{field}: {source}" for field, source in provenance.items()
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
