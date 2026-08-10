---
Created: 2026-07-05
Last-Modified: 2026-08-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Adoption surfaces

## Philosophy: an invisible enabler

Pitloom's strategic goal is not to be a tool people have to remember to run.
It is to be **an invisible enabler**: SBOM and AIBOM generation that shows
up wherever Python and AI work already happens, without asking anyone to
adopt a new standalone product.

Concretely, this means Pitloom is **open for adoption by structure**: every
place a consumer might already be -- a Python REPL, a CI pipeline, a
Hatchling build, a training script, a GitHub workflow, an AI coding agent --
gets a thin, native-feeling entry point onto the same core engine. All
surfaces below converge on the same `DocumentModel` -> assemble -> export
pipeline, so the SBOM shape and guarantees (determinism, schema compliance,
provenance tracking) are meant to be identical regardless of which surface
produced it.

That convergence is a design intent, not an automatic guarantee: the
project-metadata extraction step upstream of `DocumentModel` still has one
implementation per surface family (`pyproject.py`'s `[project]` path for
the CLI/library, `hatchling.py` for the build hook, `poetry.py` and
`setuptools.py` for the poetry-only/setuptools-only fallback paths), and
each has drifted out of sync with the others before -- see "Keeping
surfaces consistent" below. Treat "identical regardless of surface" as
the thing to keep re-verifying, not a property that, once true, stays
true on its own.

## The surfaces

| Surface | Reach for this when... | Learn more |
| :--- | :--- | :--- |
| Library API | You are calling Pitloom from Python code you control (a script, a larger tool, a test). | [README.md](../../README.md#python-api) |
| CLI (`loom` / `pitloom`) | You want a one-off SBOM from a terminal, a Makefile target, or any shell script. | [README.md](../../README.md#command-line) |
| Hatchling build hook | You build wheels with Hatchling and want an SBOM embedded automatically, with no extra command. | [hatchling-build-hook.md](hatchling-build-hook.md) |
| ML tracking SDK (`pitloom.loom`) | You are training or fine-tuning a model and want to capture dataset/hyperparameter/metric provenance as you go, as an SPDX fragment. | [README.md](../../README.md#python-tracking-decorator), [sbom-fragments.md](sbom-fragments.md) |
| GitHub Action | Your project is *not* Hatchling-based (or you just want CI to produce an SBOM artefact with one `uses:` line), regardless of build backend. | [github-action.md](../implementation/github-action.md) |
| AI-agent Skills (`sbom-generate`, `sbom-enrich`, `sbom-validate`) | You want an AI coding agent (Claude Code, the Agent SDK, or similar) to generate -- and optionally enrich and validate -- an SBOM on request, as a first-class capability rather than an ad hoc shell command. | [agent-skill.md](../implementation/agent-skill.md) |
| Claude Code plugin | You use Claude Code and want all three Skills installable with one command (`/plugin install`), plus namespaced explicit invocation (`/pitloom:sbom-generate`, `/pitloom:sbom-enrich`, `/pitloom:sbom-validate`). | [claude-code-plugin.md](../implementation/claude-code-plugin.md) |

## Why the Action and the Skill matter

The library, CLI, build hook, and tracking SDK all assume the consumer
already has Pitloom "nearby" -- installed, imported, or wired into a build
backend they control. Two adoption paths were still missing:

1. **Any repository, any build backend.** Not every Python project uses
   Hatchling. A composite **GitHub Action** lets *any* repository add SBOM
   generation to CI with a single `uses:` step, independent of build
   backend, publishing the SBOM as a workflow artefact (and, optionally,
   feeding a release pipeline).
2. **Agent-native operation.** As AI coding agents become a normal part of
   how software gets written and maintained, "generate an SBOM for this"
   needs to be something an agent can just do, the same way it edits a
   file or runs a test. Three **AI-agent Skills** (`skills/sbom-generate/`,
   `skills/sbom-enrich/`, `skills/sbom-validate/`) package Pitloom's CLI
   (and, for validation, the third-party `spdx3-validate` CLI) as
   explicit, independently triggerable capabilities for Claude Code, the
   Claude Agent SDK, and similar agent runtimes.

## The Skills are more than a CLI wrapper: agent-driven enrichment

The `sbom-enrich` skill is deliberately framed as an **enrichment
surface**, not just a thin CLI wrapper, because an AI agent can do things
static extraction cannot:

- Read a model card or README in prose and infer an unstated license.
- Classify what a dependency is *for*, not just that it exists.
- Derive `trainedOn` / `testedOn` dataset relationships from documentation
  that no model file format encodes explicitly.

Pitloom already has the machinery to accept this safely, without blurring
the line between "extracted fact" and "AI guess":

- **Per-field provenance** -- every SBOM field can carry a source
  attribution (see [metadata-provenance.md](metadata-provenance.md)).
- **The fragment system** -- independently generated SPDX 3 JSON-LD files
  are merged into the final SBOM via `[tool.pitloom.fragments]` and
  `merge_fragments()` (see [sbom-fragments.md](sbom-fragments.md)).

The `sbom-enrich` skill's guidance has an agent contribute enrichment as a
fragment, with every inferred field marked `Source: AI agent | Method:
inference`, so the result stays transparent and auditable. See
[sbom-enrichment.md](sbom-enrichment.md) for the full data-source model
this builds on.

## Keeping surfaces consistent: product owners (proposed, not yet implemented)

Growing the number of surfaces (this doc currently lists seven) makes it
progressively easier for a feature or bugfix to land correctly on one
surface's underlying extraction path while silently missing another's --
not because anyone decided to skip it, but because no single person is
looking at all seven every time. The motivating instance: the G2
declared-vs-concluded license conflict check shipped wired into the CLI's
`pyproject.py` path, but the Hatchling build hook (`hatchling.py`) called
the lower-level detection function directly and skipped the independent
directory scan G2 depends on -- so every Hatchling-built project silently
got zero G2 conflict detection until a later review caught it. The fix
(`resolve_license_concluded` as one shared entry point every extraction
path calls, described in
[annotation-provenance.md](../implementation/annotation-provenance.md))
closes that specific gap, but doesn't stop the *next* new field or feature
from repeating the pattern on some other surface.

It repeated almost immediately: the enrichment MVP shipped wired into
`generate_model_sbom()` only (the CLI's single-model path); project-level
generation (`generate_project_sbom()`, and therefore the Hatchling build
hook, which calls `build()` directly rather than going through
`generate_project_sbom()`) silently ran zero enrichment even with
`[tool.pitloom.enrich] local = true` set, discovered only when writing
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
