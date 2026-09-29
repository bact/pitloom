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

from pitloom.core.ai_metadata import AiModelFormatInfo, AiModelMetadata
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.project import project_relative_or_fallback
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
    ``pitloom.extract.remote.huggingface``'s own catch-and-log helpers).
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
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:
            log.warning("Enricher %r failed, skipping: %s", enricher.name, exc)
    return results


def _resolve_model_search_dir(
    project_dir: Path, format_info: AiModelFormatInfo
) -> Path:
    """Resolve the directory to search for one model's enrichment sources.

    ``format_info.physical_path`` is normally project-root-relative, so
    joining it onto *project_dir* is safe -- except for a build-and-read
    discovered file (see ``ProjectFile.physical_path``'s docstring),
    whose ``physical_path`` is instead an absolute path into a fresh
    ``tempfile.mkdtemp()`` extraction directory. ``project_dir /
    Path(physical_path).parent`` with an absolute right-hand operand
    silently discards *project_dir* (`pathlib`'s own join semantics),
    resolving into the extracted-wheel tempdir instead of the real
    project tree -- which won't contain a co-located README the wheel
    never packaged, silently disabling README enrichment. Fall back to
    ``file_path_relative`` (the file's wheel-distribution path, always
    project_dir-relative) in that case, the same "prefer
    distribution_path over an absolute physical_path" rule
    ``_document_files.py``'s own determinism fix applies.
    """
    physical_path = project_relative_or_fallback(
        format_info.physical_path or "", format_info.file_path_relative or ""
    )
    return project_dir / Path(physical_path).parent


def run_enrichers_for_models(
    ai_models: list[AiModelMetadata], config: EnrichConfig, project_dir: Path
) -> list[list[EnrichmentResult]]:
    """Run :func:`run_enrichers` once per model in *ai_models*.

    Each model's own directory (own directory only, no ancestor walk-up,
    same rule the single-model path uses) is resolved from
    ``format_info.physical_path`` relative to *project_dir* -- see
    :func:`_resolve_model_search_dir` for the one exception. Returns one
    ``list[EnrichmentResult]`` per model, same order as *ai_models* --
    shared by every project-level caller (``generate_project_sbom()``, the
    Hatchling build hook) so the "which directory does this model's
    enrichment look in" logic exists in exactly one place.
    """
    return [
        run_enrichers(
            ai_model,
            config,
            _resolve_model_search_dir(project_dir, ai_model.format_info),
        )
        for ai_model in ai_models
    ]


__all__ = ["run_enrichers", "run_enrichers_for_models"]
