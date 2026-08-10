# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared types every enrichment source implements.

An :class:`Enricher` mutates an :class:`~pitloom.core.ai_metadata.AiModelMetadata`
in place -- the same convention every extractor already follows -- and
returns an :class:`EnrichmentResult` describing exactly what it changed.
That return value, not a post-hoc diff of the whole object, is what the
assemble layer uses to build a per-enrichment ``CreationInfo`` (N3) and
the ``enrichment`` Annotation (E1/E2); see
``working-docs/implementation/annotation-provenance.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol

from pitloom.core.ai_metadata import AiModelMetadata


@dataclass(frozen=True)
class EnrichedField:
    """One field an enrichment run changed.

    Attributes:
        field: Field name. A scalar field on ``AiModelMetadata`` uses its
            own name (``"license"``); a new list entry (e.g. a dataset
            reference) uses ``"<list-field>:<identity>"``
            (``"datasets:tiny-imagenet"``) so each addition is its own
            entry rather than one opaque list-diff -- this is what lets
            the assemble layer match a specific new element back to the
            enrichment run that created it (N3), and lets the E1/E2
            Annotation list one entry per actual change, matching G2's
            per-candidate shape.
        before: Value before enrichment (``None`` for a new list entry).
        after: Value after enrichment.
        role: Epistemic-process label, reusing G2's exact vocabulary
            (``"declared"``/``"detected"``/``"externalReported"``/
            ``"inferred"`` -- see
            :class:`~pitloom.assemble.spdx3.provenance.ConflictCandidate`).
            A deterministic parser (like the README frontmatter enricher)
            is always ``"detected"``, never ``"inferred"`` -- that role is
            reserved for genuine AI-agent judgment.
        source: A ``"Key: Value | Key: Value"`` provenance string, same
            convention used everywhere else
            (:func:`~pitloom.assemble.spdx3.provenance.parse_provenance_value`).
    """

    field: str
    before: Any
    after: Any
    role: str
    source: str


@dataclass(frozen=True)
class EnrichmentResult:
    """What one enricher did on one run.

    Attributes:
        source_name: Short, stable identity for this source
            (``"readme"``, ``"openssf_scorecard"``, ...) -- becomes part
            of the ``Tool`` name in N3's enrichment ``CreationInfo``.
        fields: Every field this run changed. Empty means a genuine no-op
            (e.g. no README found, or every candidate field was already
            populated) -- callers should not emit a ``CreationInfo`` or
            Annotation for an empty result.
    """

    source_name: str
    fields: list[EnrichedField] = field(default_factory=list)


# pylint: disable=too-few-public-methods
class Enricher(Protocol):
    """A single enrichment data source.

    Implement this and add one line to :func:`~pitloom.enrich.run_enrichers`'s
    fixed dispatch order and one :class:`~pitloom.core.enrich_config.EnrichConfig`
    key -- no other framework change needed to add a new source.
    """

    name: ClassVar[str]

    def enrich(self, model: AiModelMetadata, *, model_dir: Path) -> EnrichmentResult:
        """Mutate *model* in place with whatever this source can add, and
        report exactly what changed. Must never raise for a missing/absent
        source (no README, no network, etc.) -- return an empty result
        instead; :func:`~pitloom.enrich.run_enrichers` treats an actual
        exception as this source failing, not as "nothing to add"."""
        raise NotImplementedError


__all__ = ["EnrichedField", "EnrichmentResult", "Enricher"]
