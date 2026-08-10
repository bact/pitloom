# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Enrichment: fill AI-model metadata gaps from sources beyond the model
file itself.

Distinct from the AI-agent ``sbom-enrich`` Skill (``skills/sbom-enrich/``),
which has an agent read prose and contribute a fragment -- this
subpackage is deterministic, non-agent, in-process code, dispatched
automatically as part of SBOM generation. See
``working-docs/design/sbom-enrichment.md``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.enrich_config import EnrichConfig
from pitloom.enrich.base import Enricher, EnrichmentResult
from pitloom.enrich.readme import ReadmeEnricher

log = logging.getLogger(__name__)


def run_enrichers(
    model: AiModelMetadata, config: EnrichConfig, model_dir: Path
) -> list[EnrichmentResult]:
    """Run every enabled enricher, in a fixed order, against *model*.

    Each enricher mutates *model* in place; this returns one
    :class:`~pitloom.enrich.base.EnrichmentResult` per *enabled* source
    (empty ``fields`` when that source found nothing to add). A source
    that enables but raises is logged and skipped -- one failing source
    must not prevent the others from running, same discipline already
    used for extraction sources elsewhere (e.g.
    ``_huggingface.py``'s own catch-and-log helpers).
    """
    sources: list[tuple[bool, Enricher]] = [
        (config.local, ReadmeEnricher()),
    ]

    results: list[EnrichmentResult] = []
    for enabled, enricher in sources:
        if not enabled:
            continue
        try:
            results.append(enricher.enrich(model, model_dir=model_dir))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning("Enricher %r failed, skipping: %s", enricher.name, exc)
    return results


__all__ = ["run_enrichers"]
