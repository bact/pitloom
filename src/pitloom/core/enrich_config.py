# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclass for AI-model metadata enrichment."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnrichConfig:
    """Configuration settings for ``[tool.pitloom.enrich]``.

    Attributes:
        local: Whether to run local, no-network enrichment (README/model-card
            YAML frontmatter). On by default -- always-safe per
            ``working-docs/design/sbom-enrichment.md``'s source table.

    New sources (``openssf_scorecard``, ``huggingface``, ``pypi``, ...) each
    get their own field here when they're actually built -- not
    pre-declared ahead of the enricher that would use them.
    """

    local: bool = True
