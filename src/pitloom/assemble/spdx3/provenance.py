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

import json
from typing import Protocol

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


class ProvenanceEncoder(Protocol):
    """Turns Pitloom's ``field -> source string`` map into an SPDX statement."""

    schema_id: str
    """Short id used in config/registry lookup, e.g. ``"pitloom/1"``."""

    content_type: str
    """Value for ``Annotation.contentType`` (must match ``^[^/]+/[^/]+$``)."""

    def encode(self, provenance: dict[str, str]) -> str:
        """Return the serialized ``Annotation.statement`` body."""
        ...


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


def build_provenance_comment(provenance: dict[str, str]) -> str | None:
    """Return the legacy human-readable ``"Metadata provenance: ..."`` comment.

    Mirrors the string format extractors and assemblers used before
    Annotation support was added. Returns ``None`` when *provenance* is empty.
    """
    if not provenance:
        return None
    return "Metadata provenance: " + "; ".join(
        f"{field}: {source}" for field, source in provenance.items()
    )


def emit_provenance(
    subject: spdx3.Element,
    provenance: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    provenance_format: str = "both",
    encoder: ProvenanceEncoder | None = None,
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

    Raises:
        ValueError: If *provenance_format* is not one of
            :data:`VALID_PROVENANCE_FORMATS`. Rejected rather than silently
            dropped, since neither branch below would otherwise fire and the
            provenance would be lost without any error or warning.
    """
    if provenance_format not in VALID_PROVENANCE_FORMATS:
        valid = ", ".join(sorted(VALID_PROVENANCE_FORMATS))
        raise ValueError(
            f"Unknown provenance_format {provenance_format!r}; expected one of {valid}"
        )

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
    "DEFAULT_SCHEMA_ID",
    "VALID_PROVENANCE_FORMATS",
    "PitloomV1Encoder",
    "ProvenanceEncoder",
    "build_provenance_annotation",
    "build_provenance_comment",
    "emit_provenance",
    "parse_provenance_value",
    "resolve_encoder",
]
