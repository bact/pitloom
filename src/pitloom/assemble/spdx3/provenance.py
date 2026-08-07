# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Build SPDX 3 Core/Annotation elements recording metadata provenance.

Provenance answers "where did Pitloom collect this field from". The *who/when*
(pitloom Agent + Tool + timestamp) is carried by the Annotation's own
``creationInfo``. The *what/where* (per-field source) is carried by the
``statement``, whose shape and ``contentType`` are decided by a pluggable
:class:`ProvenanceEncoder` selected by schema id -- so an external AI-model
provenance schema can be adopted later without touching call sites.

See ``working-docs/implementation/annotation-provenance.md`` for the design.
"""

from __future__ import annotations

import base64
import json
import math
from typing import Any, Protocol

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

#: Segment-key normalization for the ``"Key: value | Key: value"`` strings
#: produced by extractors (e.g. ``"Source: pyproject.toml | Field: project.name"``).
_KEY_MAP = {
    "source": "source",
    "field": "location",
    "method": "method",
    "package": "package",
}

#: Statement-schema URL for a fragment-unification process Annotation (A1).
UNIFICATION_SCHEMA_URL = "https://pitloom.dev/provenance/unification/1"

#: Statement-schema URL for a preserved verbatim artifact-metadata blob (P1).
ARTIFACT_METADATA_SCHEMA_URL = "https://pitloom.dev/provenance/artifact-metadata/1"

#: Transparent, re-readable manifest sources. A field read verbatim from one of
#: these (no extraction ``method``) is *low* signal in minimal mode: its value
#: is already the native SPDX field and the source is trivially re-derivable by
#: the consumer. Anything else -- an inference, a scan (pipdeptree), a binary
#: artifact's internal key, a synthesized package -- is kept.
TRANSPARENT_SOURCES: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "hatchling build backend",  # same pyproject.toml data via the build hook
        "setup.cfg",
        "setup.py",
        "wheel metadata",
        "hugging face hub",
    }
)

#: Valid ``provenance_detail`` values for :func:`emit_provenance`. Mirrored
#: (not imported) in :mod:`pitloom.core.config`.
VALID_PROVENANCE_DETAIL: frozenset[str] = frozenset({"minimal", "full"})


def parse_provenance_value(value: str) -> dict[str, str]:
    """Parse ``"Source: X | Field: Y"`` into a structured dict.

    Segments without a ``:`` and segments with unrecognized keys are
    preserved (unrecognized keys pass through lower-cased) so that no
    information is silently dropped. Shared by any encoder that wants the
    pre-parsed form; encoders are free to consume the raw string instead.
    """
    parsed: dict[str, str] = {}
    notes: list[str] = []
    for raw in value.split("|"):
        segment = raw.strip()
        if not segment:
            continue
        key, sep, val = segment.partition(":")
        if sep:
            norm = _KEY_MAP.get(key.strip().lower(), key.strip().lower())
            parsed[norm] = val.strip()
        else:
            notes.append(segment)
    if notes:
        parsed.setdefault("note", " | ".join(notes))
    return parsed


def _is_high_signal(entry: dict[str, str]) -> bool:
    """Return whether a parsed field-provenance *entry* carries signal beyond
    the native SPDX value (the "minimal" detail boundary).

    Low-signal (dropped) only when the value was read *verbatim* from a
    transparent, re-readable manifest (:data:`TRANSPARENT_SOURCES`) with no
    extraction ``method`` -- e.g. ``name`` from ``project.name``, whose value
    is already the native ``Element.name`` and whose source the consumer can
    trivially re-read. Everything else is high-signal and kept:

    - any recorded ``method`` (inferred/detected/dynamic/caller/directive/
      inference) -- the native value can't convey it wasn't a plain read (G1);
    - a non-manifest ``source`` -- a scan (pipdeptree), a binary artifact's
      internal key (G4), a synthesized/phantom package, an enrichment;
    - the raw PEP 508 ``declared_constraint`` (parsed as a note, no manifest
      source), which has no native home (G3).
    """
    if entry.get("method"):
        return True
    source = entry.get("source", "").strip().lower()
    if " (" in source:
        source = source.split(" (", 1)[0].strip()
    return not source or source not in TRANSPARENT_SOURCES


def filter_high_signal(provenance: dict[str, str]) -> dict[str, str]:
    """Return the subset of *provenance* whose entries are high-signal.

    Used for ``detail == "minimal"``: drops trivial per-field source strings
    that merely restate where a natively-stored value was read from, keeping
    only those that add something the native value cannot convey. See
    :func:`_is_high_signal`.
    """
    return {
        field: src
        for field, src in provenance.items()
        if _is_high_signal(parse_provenance_value(src))
    }


# pylint: disable=too-few-public-methods
class ProvenanceEncoder(Protocol):
    """Turns Pitloom's ``field -> source string`` map into an SPDX statement."""

    schema_id: str
    """Short id used in config/registry lookup, e.g. ``"pitloom/1"``."""

    content_type: str
    """Value for ``Annotation.contentType`` (must match ``^[^/]+/[^/]+$``)."""

    def encode(self, provenance: dict[str, str]) -> str:
        """Return the serialized ``Annotation.statement`` body."""
        raise NotImplementedError


# pylint: disable=too-few-public-methods
class PitloomV1Encoder:
    """Pitloom's own simple JSON schema (the default)."""

    schema_id = "pitloom/1"
    schema_url = "https://pitloom.dev/provenance/1"
    content_type = "application/json"

    def encode(self, provenance: dict[str, str]) -> str:
        fields = {
            field: parse_provenance_value(src) for field, src in provenance.items()
        }
        envelope = {"schema": self.schema_url, "fields": fields}
        # sort_keys keeps output byte-stable for reproducible builds.
        return json.dumps(envelope, ensure_ascii=False, sort_keys=True)


#: Registry of available encoders, keyed by ``schema_id``. A future external
#: schema (see working-docs/implementation/annotation-provenance.md §8)
#: registers itself here alongside ``pitloom/1`` -- no call site changes.
_ENCODERS: dict[str, ProvenanceEncoder] = {
    PitloomV1Encoder.schema_id: PitloomV1Encoder(),
}

DEFAULT_SCHEMA_ID = PitloomV1Encoder.schema_id

#: Valid ``provenance_format`` values for :func:`emit_provenance`. Mirrored
#: (not imported) in :mod:`pitloom.core.config`, which validates the same
#: set at ``pyproject.toml`` parse time -- ``core`` must not import from
#: ``assemble``, so the two layers each fail fast independently rather than
#: sharing one source of truth.
VALID_PROVENANCE_FORMATS: frozenset[str] = frozenset({"annotation", "comment", "both"})


def resolve_encoder(schema_id: str | None = None) -> ProvenanceEncoder:
    """Return the encoder registered for *schema_id* (default when ``None``).

    An explicit empty string is treated as an (invalid) id, not as "use the
    default" -- only omitting *schema_id* (``None``) selects the default, so
    a mistakenly blank ``schema = ""`` in config fails loudly instead of
    silently resolving to :data:`DEFAULT_SCHEMA_ID`.

    Raises:
        ValueError: If *schema_id* is not a registered encoder.
    """
    key = DEFAULT_SCHEMA_ID if schema_id is None else schema_id
    try:
        return _ENCODERS[key]
    except KeyError:
        known = ", ".join(sorted(_ENCODERS))
        raise ValueError(f"Unknown provenance schema {key!r}; known: {known}") from None


def build_provenance_annotation(
    subject_spdx_id: str,
    provenance: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    encoder: ProvenanceEncoder | None = None,
) -> spdx3.Annotation | None:
    """Return an Annotation recording where each metadata field came from.

    Returns ``None`` when *provenance* is empty (nothing to record).
    *encoder* defaults to the configured/registered default schema.
    """
    if not provenance:
        return None

    enc = encoder or resolve_encoder()

    return spdx3.Annotation(
        spdxId=generate_spdx_id("Annotation", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
        annotationType=spdx3.AnnotationType.other,
        contentType=enc.content_type,
        subject=subject_spdx_id,
        statement=enc.encode(provenance),
    )


# pylint: disable=too-many-return-statements
def _sanitize_for_json(obj: object) -> object:
    """Recursively normalize preserved raw metadata into deterministic,
    RFC 8259-valid JSON-safe values before serialization.

    ``json.dumps`` cannot be trusted to do this on its own: a ``float`` is
    natively serializable, so its ``default=`` hook is never called for one --
    a NaN/Infinity value (reachable from a malformed binary model's float
    metadata) would otherwise round-trip straight into the non-standard
    ``NaN``/``Infinity`` JSON tokens. A ``set`` has no stable iteration order
    across processes (``PYTHONHASHSEED`` randomization), so leaving it to a
    generic ``str()`` fallback would break the byte-stable-SBOM guarantee.

    Extractors are expected to normalize numpy/library-native scalar types
    (e.g. via ``.tolist()``/``.item()``) to plain Python types before they
    reach ``raw_metadata`` -- see ``_gguf.py``'s ``_field_value`` -- so this
    function only needs to handle the plain-Python types below.
    """
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
        # Sanitize each element first, then order by its *canonical JSON
        # form* -- not by Python's native `<` (the fallback point of the
        # bug this replaces). `sorted()` on the raw elements can silently
        # "succeed" without raising TypeError yet still be order-dependent
        # on input iteration order for types with a non-total `<` (e.g.
        # frozenset, whose `<` means "is a proper subset of", not a total
        # order) -- a canonical-string sort key is well-defined for any
        # JSON-safe value, so it can't hit that trap.
        sanitized = [_sanitize_for_json(v) for v in obj]
        return sorted(sanitized, key=lambda v: json.dumps(v, sort_keys=True))
    return obj


def _build_json_annotation(
    subject_spdx_id: str,
    statement_obj: dict[str, Any],
    creation_info: spdx3.CreationInfo,
    annotation_spdx_id: str,
) -> spdx3.Annotation:
    """Build an ``application/json`` Annotation with the given *annotation_spdx_id*
    whose statement is *statement_obj* serialized byte-stably (``sort_keys``).
    Shared by the process-level and preservation builders below."""
    return spdx3.Annotation(
        spdxId=annotation_spdx_id,
        creationInfo=creation_info,
        annotationType=spdx3.AnnotationType.other,
        contentType="application/json",
        subject=subject_spdx_id,
        statement=json.dumps(
            _sanitize_for_json(statement_obj),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ),
    )


def build_unification_annotation(
    subject_spdx_id: str,
    criterion: str,
    unified_ids: list[str],
    fragments: list[str],
    creation_info: spdx3.CreationInfo,
    annotation_spdx_id: str,
) -> spdx3.Annotation:
    """Return an Annotation recording *why* fragment elements were unified into
    the survivor *subject_spdx_id* (A1).

    SPDX has no native home for this: the merged-away ids vanish from the graph
    and ``SpdxDocument.imports`` (a Phase-2 native anchor, see the design doc)
    can only say an element came from a fragment, not the matching *criterion*.

    Args:
        subject_spdx_id: The surviving element's id.
        criterion: Which rule matched. The merge currently records only
            ``"sha256"`` (content equality folds a distinct id); the field is
            kept general for future criteria.
        unified_ids: Dropped duplicate ids, distinct from the survivor, that
            were folded in (non-empty).
        fragments: Source fragment file paths that contributed.
        annotation_spdx_id: The Annotation's own id (minted by the caller in the
            document namespace, since fragment merge runs without a doc UUID).
    """
    statement = {
        "schema": UNIFICATION_SCHEMA_URL,
        "event": "unification",
        "criterion": criterion,
        "unified": sorted(unified_ids),
        "fragments": sorted(fragments),
    }
    return _build_json_annotation(
        subject_spdx_id, statement, creation_info, annotation_spdx_id
    )


def build_source_metadata_annotation(
    subject_spdx_id: str,
    source_format: str,
    metadata: dict[str, Any],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> spdx3.Annotation | None:
    """Return an Annotation embedding an artifact's verbatim original metadata
    *metadata* (P1), or ``None`` when there is nothing to preserve.

    Preserves the original as-is (in the model's own key vocabulary) so the SBOM
    stays a self-contained record when the artifact is not shipped and cannot be
    re-extracted later. Complements -- never replaces -- the native subset
    already mapped onto the ``ai_AIPackage``.

    Args:
        source_format: The artifact's metadata format tag -- the model file
            format's name (e.g. ``"gguf"``, ``"safetensors"``, ``"onnx"``), or
            ``"huggingface"`` for a hub-sourced model. Set by the caller (see
            :func:`~pitloom.assemble.spdx3.ai._source_metadata_blob`).
        metadata: The complete raw metadata map. Normalized for deterministic,
            valid JSON before serialization -- see :func:`_sanitize_for_json`.
    """
    if not metadata:
        return None
    statement = {
        "schema": ARTIFACT_METADATA_SCHEMA_URL,
        "format": source_format,
        "metadata": metadata,
    }
    annotation_spdx_id = generate_spdx_id(
        "Annotation", doc_name=doc_name, doc_uuid=doc_uuid
    )
    return _build_json_annotation(
        subject_spdx_id, statement, creation_info, annotation_spdx_id
    )


def build_provenance_comment(provenance: dict[str, str]) -> str | None:
    """Return the human-readable ``"Metadata provenance: ..."`` comment form.

    Returns ``None`` when *provenance* is empty.
    """
    if not provenance:
        return None
    return "Metadata provenance: " + "; ".join(
        f"{field}: {source}" for field, source in provenance.items()
    )


# pylint: disable=too-many-arguments,too-many-positional-arguments
def emit_provenance(
    subject: spdx3.Element,
    provenance: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    provenance_format: str = "both",
    encoder: ProvenanceEncoder | None = None,
    provenance_detail: str = "minimal",
) -> None:
    """Write provenance for *subject* as an Annotation, a ``.comment``, or both.

    Args:
        subject: The SPDX element the provenance describes. Must already
            have an ``spdxId`` (added to *exporter* beforehand).
        provenance: Field -> source-string map (see :func:`parse_provenance_value`).
        creation_info: Shared ``CreationInfo`` for the new Annotation, when built.
        doc_name: Document name (project name) for SPDX ID generation.
        doc_uuid: Document-scoped UUID used in SPDX ID generation.
        exporter: Receives the new Annotation element, when built.
        provenance_format: ``"annotation"``, ``"comment"``, or ``"both"``
            (default).
        encoder: Encoder used for the annotation path; defaults to the
            registered default schema.
        provenance_detail: ``"minimal"`` (default, matching the system/config
            default) first filters to high-signal fields only
            (:func:`filter_high_signal`) so trivial "came from pyproject.toml"
            noise is dropped; ``"full"`` records every field's source. Applies
            to both the comment and annotation paths.

    Raises:
        ValueError: If *provenance_format* or *provenance_detail* is not a valid
            value. Rejected rather than silently falling through -- an unknown
            *provenance_format* would fire neither branch (provenance lost), and
            an unknown *provenance_detail* would silently behave as ``"full"``.
    """
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


__all__ = [
    "ARTIFACT_METADATA_SCHEMA_URL",
    "DEFAULT_SCHEMA_ID",
    "UNIFICATION_SCHEMA_URL",
    "VALID_PROVENANCE_DETAIL",
    "VALID_PROVENANCE_FORMATS",
    "PitloomV1Encoder",
    "ProvenanceEncoder",
    "build_provenance_annotation",
    "build_provenance_comment",
    "build_source_metadata_annotation",
    "build_unification_annotation",
    "emit_provenance",
    "filter_high_signal",
    "parse_provenance_value",
    "resolve_encoder",
]
