# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclass for metadata provenance Annotations."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PROVENANCE_SCHEMA = "pitloom/1"


@dataclass(frozen=True)
class ProvenanceConfig:
    """Configuration settings for SPDX 3 metadata provenance annotations.

    Attributes:
        format: How to record metadata provenance ("annotation", "comment", "both").
        schema: Schema id for provenance Annotations.
        detail: Provenance detail level ("minimal", "full").
        preserve_source_metadata: How to preserve source metadata
            ("auto", "always", "never").
    """

    format: str = "both"
    schema: str = DEFAULT_PROVENANCE_SCHEMA
    detail: str = "minimal"
    preserve_source_metadata: str = "auto"
