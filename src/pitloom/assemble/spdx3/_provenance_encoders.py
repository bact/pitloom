# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Encoders for SPDX 3 metadata provenance.

See also: :mod:`pitloom.assemble.spdx3.provenance` for annotation builders and
emission, and :func:`pitloom.core.provenance.parse_provenance_value`.
"""

from __future__ import annotations

import json
from typing import Protocol

from pitloom.core.provenance import parse_provenance_value

#: Transparent, re-readable manifest sources.
TRANSPARENT_SOURCES: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "hatchling build backend",
        "setup.cfg",
        "setup.py",
        "wheel metadata",
        "sdist pkg-info",
        "hugging face hub",
    }
)

#: A dependency's installed copy, read for a project SBOM: a record of the
#: local environment, which need not be the artifact the SBOM describes.
INSTALLED_DEPENDENCY_SOURCE = "installed metadata"
#: A deployed package's own installed metadata (``loom env``): that copy is
#: the package the SBOM describes.
DEPLOYED_PACKAGE_SOURCE = "deployed package metadata"

#: Records kept about a package by someone other than the package: a licence
#: read from one is concluded. Every other source -- a manifest, an
#: in-package file (``LICENSE``, ``CITATION.cff``, a model card), an AI model
#: file's own metadata, the package's own installed metadata -- is the
#: package's own statement, so declared, however it was read.
THIRD_PARTY_SOURCES: frozenset[str] = frozenset(
    {"pypi json api", INSTALLED_DEPENDENCY_SOURCE}
)

VALID_PROVENANCE_DETAIL: frozenset[str] = frozenset({"minimal", "full"})
VALID_PROVENANCE_FORMATS: frozenset[str] = frozenset({"annotation", "comment", "both"})


def _source_name(entry: dict[str, str]) -> str:
    """The lower-case source of a parsed provenance entry, without a
    parenthesised qualifier."""
    source = entry.get("source", "").strip().lower()
    return source.split(" (", 1)[0].strip()


def _is_high_signal(entry: dict[str, str]) -> bool:
    """Return whether a parsed field-provenance entry carries high signal: a
    method, a normalisation, a non-manifest source, or a value read from a
    field other than its own (a licence from the ``classifiers``)."""
    if (
        entry.get("method")
        or entry.get("normalized-from")
        or entry.get("deprecated-license-id")
        or "classifier" in entry.get("location", "").lower()
    ):
        return True
    source = _source_name(entry)
    return not source or source not in TRANSPARENT_SOURCES


def is_license_concluded(entry: dict[str, str]) -> bool:
    """Whether a licence from the parsed provenance *entry* is concluded,
    not declared: its source is a third-party record
    (:data:`THIRD_PARTY_SOURCES`) or unknown. How the value was read (a
    ``Method``, such as ``licenseid`` detection of a ``LICENSE`` file) does
    not change whose statement it is.
    """
    source = _source_name(entry)
    return not source or source in THIRD_PARTY_SOURCES


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
