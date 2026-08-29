# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclass for metadata provenance Annotations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import rfc8785

log = logging.getLogger(__name__)

DEFAULT_PROVENANCE_SCHEMA = "pitloom/1"

#: Smallest possible non-empty JCS-encoded JSON object (e.g. ``{"a":""}``),
#: computed from the real serializer so it can't silently drift from it.
_MIN_EFFECTIVE_MAX_SOURCE_METADATA_BYTES = len(rfc8785.dumps({"a": ""}))


def normalize_max_source_metadata_bytes(value: int) -> int:
    """Collapse a too-small-to-be-useful metadata byte budget to 0.

    ``0`` means "no cap" (embed the full artifact-metadata blob, today's
    unbounded behavior). A negative value, or a positive value below the
    smallest possible JCS-encoded JSON object, can never hold any real
    metadata -- both are treated the same as ``0``, with a logged warning,
    rather than rejected outright, since they're well-typed but merely
    pointless rather than structurally invalid.
    """
    if value != 0 and value < _MIN_EFFECTIVE_MAX_SOURCE_METADATA_BYTES:
        log.warning(
            "max-source-metadata-bytes=%d is too small to ever hold data "
            "(minimum useful value is %d bytes); using 0 (unlimited) instead.",
            value,
            _MIN_EFFECTIVE_MAX_SOURCE_METADATA_BYTES,
        )
        return 0
    return value


@dataclass(frozen=True)
class ProvenanceConfig:
    """Configuration settings for SPDX 3 metadata provenance annotations.

    Attributes:
        format: How to record metadata provenance ("annotation", "comment", "both").
        schema: Schema id for provenance Annotations.
        detail: Provenance detail level ("minimal", "full").
        preserve_source_metadata: How to preserve source metadata
            ("auto", "always", "never").
        max_source_metadata_bytes: Byte budget for the serialized
            artifact-metadata Annotation.statement; 0 (default) means
            unlimited. See :func:`normalize_max_source_metadata_bytes`.
    """

    format: str = "both"
    schema: str = DEFAULT_PROVENANCE_SCHEMA
    detail: str = "minimal"
    preserve_source_metadata: str = "auto"
    max_source_metadata_bytes: int = 0
