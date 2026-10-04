# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclass for metadata provenance Annotations.

Also holds :func:`parse_provenance_value`, which both ``extract`` and
``assemble`` read provenance strings with; it lives here, below both, so
neither package has to import the other for it.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass

import rfc8785

DEFAULT_PROVENANCE_SCHEMA = "pitloom/1"

#: Segment-key normalization for "Key: value | Key: value" strings.
_KEY_MAP = {
    "source": "source",
    "field": "location",
    "method": "method",
    "package": "package",
    "role": "role",
}

#: Smallest possible non-empty JCS-encoded JSON object (e.g. ``{"a":""}``),
#: computed from the real serializer so it can't silently drift from it.
MIN_SOURCE_METADATA_BYTES = len(rfc8785.dumps({"a": ""}))


def require_max_source_metadata_bytes(
    value: object, label: str = "max_source_metadata_bytes"
) -> int:
    """*value* as an ``int`` when it is ``0`` (no cap) or a budget of at least
    :data:`MIN_SOURCE_METADATA_BYTES`, the smallest annotation that holds any
    metadata. A smaller one is an error, never a silent "unlimited".

    The one validator for every surface that takes the budget: the config
    key, ``--max-source-metadata-bytes``, ``ConfigOverrides`` and the library
    kwargs. *label* names the setting in the error, e.g.
    ``[tool.pitloom.provenance] 'max-source-metadata-bytes'``; ``""`` leaves
    the message to a caller that names the setting itself. Any
    :func:`operator.index`-able integer (a ``numpy.int64``) passes; a ``bool``
    or a ``float`` does not.

    Raises:
        ValueError: *value* is not an integer, is negative, or is below the
            minimum without being ``0``.
    """
    try:
        if isinstance(value, bool):
            raise TypeError
        number = operator.index(value)  # type: ignore[arg-type]
    except TypeError:
        raise ValueError(
            f"{label} must be an integer, got {type(value).__name__}: {value!r}".strip()
        ) from None
    if number != 0 and number < MIN_SOURCE_METADATA_BYTES:
        raise ValueError(
            f"{label} must be 0 (unlimited) or at least "
            f"{MIN_SOURCE_METADATA_BYTES} bytes, got {number}".strip()
        )
    return number


def parse_provenance_value(value: str) -> dict[str, str]:
    """Parse ``"Source: X | Field: Y"`` into a structured dict."""
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
            unlimited, below :data:`MIN_SOURCE_METADATA_BYTES` is an error. See
            :func:`require_max_source_metadata_bytes`.
    """

    format: str = "both"
    schema: str = DEFAULT_PROVENANCE_SCHEMA
    detail: str = "minimal"
    preserve_source_metadata: str = "auto"
    max_source_metadata_bytes: int = 0

    def __post_init__(self) -> None:
        """Reject an invalid budget, however it got here; keep it as a plain int."""
        object.__setattr__(
            self,
            "max_source_metadata_bytes",
            require_max_source_metadata_bytes(self.max_source_metadata_bytes),
        )
