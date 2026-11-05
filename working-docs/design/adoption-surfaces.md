---
Created: 2026-07-05
Last-Modified: 2026-11-05
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

With seven surfaces, a feature or bugfix can land correctly on one
surface's extraction path and silently miss another's, because no single
person looks at all seven every time. The motivating case: the G2
declared-vs-concluded licence conflict check shipped wired into the CLI's
`pyproject.py` path, but the Hatchling build hook (`hatchling.py`) called
the lower-level detection function directly and skipped the directory scan
G2 depends on, so every Hatchling-built project got no G2 conflict
detection until a later review. The fix (`resolve_license_concluded` as one
shared entry point for every extraction path, described in
[multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md))
closes that gap, but not the next new field or feature repeating the
pattern.

It repeated at once: the enrichment MVP was wired into
`generate_model_sbom()` only (the CLI's single-model path). Project-level
generation (`generate_project_sbom()`, and the Hatchling hook, which calls
`build()` directly) ran no enrichment even with `[tool.pitloom] enrich =
true`, found when the Hatchling hook test got an empty
`dataset_DatasetPackage` list (fix: the "Surfaces" section of
[sbom-enrichment.md](sbom-enrichment.md)). Two occurrences in two
consecutive rounds is the pattern issue #122 exists to address.

[Issue #122](https://github.com/bact/pitloom/issues/122) proposes
assigning a **product owner** to each usage surface (CLI, Python API,
Python decorator/`pitloom.loom`, Hatchling build hook, AI-agent Skills,
Claude Code plugin, GitHub Action) who reviews any feature or bugfix that
touches their surface before it lands, against review instructions and
acceptance criteria suited to that surface. This is documented here as
the proposed answer to "how do we stop this class of gap from
recurring". **Not implemented**: no owners are assigned and no
review instructions or acceptance criteria exist per surface. Track it on
issue #122.

## What is intentionally not in scope yet

- A **Docker container action** variant of the GitHub Action (hermetic,
  self-hosted-runner friendly); see [roadmap.md](roadmap.md).
- New enrichment *code* inside Pitloom core (README/model-card parsers,
  OpenSSF Scorecard, Hugging Face/PyPI enrichers) -- tracked separately in
  [sbom-enrichment.md](sbom-enrichment.md) and [roadmap.md](roadmap.md); the
  `sbom-enrich` skill enables agent-driven enrichment today without
  waiting for that code.
