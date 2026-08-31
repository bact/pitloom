---
Created: 2026-07-05
Last-Modified: 2026-08-31
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Adoption surfaces: open governance and scope questions

See [implementation/adoption-surfaces.md](../implementation/adoption-surfaces.md)
for what's shipped: the philosophy behind Pitloom's surfaces, the surface
list itself, and why the Action/Skills matter. This file covers what's
still proposed or explicitly out of scope.

## Keeping surfaces consistent: product owners (proposed, not yet implemented)

Growing the number of surfaces (seven today) makes it progressively
easier for a feature or bugfix to land correctly on one surface's
underlying extraction path while silently missing another's -- not
because anyone decided to skip it, but because no single person is
looking at all seven every time. The motivating instance: the G2
declared-vs-concluded license conflict check shipped wired into the CLI's
`pyproject.py` path, but the Hatchling build hook (`hatchling.py`) called
the lower-level detection function directly and skipped the independent
directory scan G2 depends on -- so every Hatchling-built project silently
got zero G2 conflict detection until a later review caught it. The fix
(`resolve_license_concluded` as one shared entry point every extraction
path calls, described in
[multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md))
closes that specific gap, but doesn't stop the *next* new field or feature
from repeating the pattern on some other surface.

It repeated almost immediately: the enrichment MVP shipped wired into
`generate_model_sbom()` only (the CLI's single-model path); project-level
generation (`generate_project_sbom()`, and therefore the Hatchling build
hook, which calls `build()` directly rather than going through
`generate_project_sbom()`) silently ran zero enrichment even with
`[tool.pitloom] enrich = true` set, discovered only when writing
this round's Hatchling hook test and getting an empty `dataset_DatasetPackage`
list where one was expected (see [sbom-enrichment.md](sbom-enrichment.md)'s
"Surfaces" section for the fix). Two occurrences of the same failure mode
in two consecutive rounds is exactly the pattern issue #122 exists to
address.

[Issue #122](https://github.com/bact/pitloom/issues/122) proposes
assigning a **product owner** to each usage surface (CLI, Python API,
Python decorator/`pitloom.loom`, Hatchling build hook, AI-agent Skills,
Claude Code plugin, GitHub Action) who reviews any feature or bugfix that
touches their surface before it lands, against review instructions and
acceptance criteria suited to that surface. This is documented here as
the proposed answer to "how do we stop this class of gap from
recurring" -- **not yet implemented**: no owners are assigned, and no
review-instructions/acceptance-criteria set exists per surface yet. Track
implementation on issue #122.

## What is intentionally not in scope yet

- A **Docker container action** variant of the GitHub Action (hermetic,
  self-hosted-runner friendly) -- see [roadmap.md](roadmap.md).
- New enrichment *code* inside Pitloom core (README/model-card parsers,
  OpenSSF Scorecard, Hugging Face/PyPI enrichers) -- tracked separately in
  [sbom-enrichment.md](sbom-enrichment.md) and [roadmap.md](roadmap.md); the
  `sbom-enrich` skill enables agent-driven enrichment today without
  waiting for that code.
