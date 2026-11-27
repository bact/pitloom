# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclass for AI-model metadata enrichment."""

from __future__ import annotations

from dataclasses import dataclass

from pitloom.core.bool_arguments import check_bool_fields


@dataclass(frozen=True)
class EnrichConfig:
    """Configuration settings for ``[tool.pitloom] enrich``.

    Attributes:
        local: Whether to run local, no-network enrichment (README/model-card
            YAML frontmatter). Off by default -- enrichment is still
            immature (single source, frontmatter-only); opt in explicitly
            until more sources land.

    New sources (``openssf_scorecard``, ``huggingface``, ``pypi``, ...) each
    get their own field here when they're actually built -- not
    pre-declared ahead of the enricher that would use them.
    """

    local: bool = False

    def __post_init__(self) -> None:
        """Refuse a ``bool`` field given another type.

        Raises:
            pitloom.messages.CodedTypeError: ``option-invalid``.
        """
        check_bool_fields(self)
