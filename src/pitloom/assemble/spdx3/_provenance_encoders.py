# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Encoders and value parsing for SPDX 3 metadata provenance.

See also: :mod:`pitloom.assemble.spdx3.provenance` for annotation builders and emission.
"""

from __future__ import annotations

import json
from typing import Protocol

#: Segment-key normalization for "Key: value | Key: value" strings.
_KEY_MAP = {
    "source": "source",
    "field": "location",
    "method": "method",
    "package": "package",
    "role": "role",
}

#: Transparent, re-readable manifest sources.
TRANSPARENT_SOURCES: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "hatchling build backend",
        "setup.cfg",
        "setup.py",
        "wheel metadata",
        "hugging face hub",
    }
)

VALID_PROVENANCE_DETAIL: frozenset[str] = frozenset({"minimal", "full"})
VALID_PROVENANCE_FORMATS: frozenset[str] = frozenset({"annotation", "comment", "both"})


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


def _is_high_signal(entry: dict[str, str]) -> bool:
    """Return whether a parsed field-provenance entry carries high signal."""
    if entry.get("method"):
        return True
    source = entry.get("source", "").strip().lower()
    if " (" in source:
        source = source.split(" (", 1)[0].strip()
    return not source or source not in TRANSPARENT_SOURCES


def filter_high_signal(provenance: dict[str, str]) -> dict[str, str]:
    """Return the subset of provenance whose entries are high-signal."""
    return {
        field: src
        for field, src in provenance.items()
        if _is_high_signal(parse_provenance_value(src))
    }


# pylint: disable=too-few-public-methods
class ProvenanceEncoder(Protocol):
    """Turns Pitloom's ``field -> source string`` map into an SPDX statement."""

    schema_id: str
    content_type: str

    def encode(self, provenance: dict[str, str]) -> str:
        """Return the serialized Annotation.statement body."""
        raise NotImplementedError


# pylint: disable=too-few-public-methods
class PitloomV1Encoder:
    """Pitloom's own simple JSON schema (the default)."""

    schema_id = "pitloom/1"
    schema_url = "https://pitloom.dev/provenance/fields/1"
    content_type = "application/json"

    def encode(self, provenance: dict[str, str]) -> str:
        fields = {
            field: parse_provenance_value(src) for field, src in provenance.items()
        }
        envelope = {"schema": self.schema_url, "kind": "fields", "fields": fields}
        return json.dumps(envelope, ensure_ascii=False, sort_keys=True)


_ENCODERS: dict[str, ProvenanceEncoder] = {
    PitloomV1Encoder.schema_id: PitloomV1Encoder(),
}

DEFAULT_SCHEMA_ID = PitloomV1Encoder.schema_id


def resolve_encoder(schema_id: str | None = None) -> ProvenanceEncoder:
    """Return the encoder registered for *schema_id* (default when ``None``)."""
    key = DEFAULT_SCHEMA_ID if schema_id is None else schema_id
    try:
        return _ENCODERS[key]
    except KeyError:
        known = ", ".join(sorted(_ENCODERS))
        raise ValueError(f"Unknown provenance schema {key!r}; known: {known}") from None
