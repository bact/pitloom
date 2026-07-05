---
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
provenance tracking) are identical regardless of which surface produced it.

## The surfaces

| Surface | Reach for this when... | Learn more |
| :--- | :--- | :--- |
| Library API | You are calling Pitloom from Python code you control (a script, a larger tool, a test). | [README.md](../../README.md#python-api) |
| CLI (`loom` / `pitloom`) | You want a one-off SBOM from a terminal, a Makefile target, or any shell script. | [README.md](../../README.md#command-line) |
| Hatchling build hook | You build wheels with Hatchling and want an SBOM embedded automatically, with no extra command. | [hatchling-build-hook.md](hatchling-build-hook.md) |
| ML tracking SDK (`pitloom.loom`) | You are training or fine-tuning a model and want to capture dataset/hyperparameter/metric provenance as you go, as an SPDX fragment. | [README.md](../../README.md#python-tracking-decorator), [sbom-fragments.md](sbom-fragments.md) |
| GitHub Action | Your project is *not* Hatchling-based (or you just want CI to produce an SBOM artefact with one `uses:` line), regardless of build backend. | [github-action.md](../implementation/github-action.md) |
| AI-agent Skills (`sbom`, `enrich`) | You want an AI coding agent (Claude Code, the Agent SDK, or similar) to generate -- and optionally enrich -- an SBOM on request, as a first-class capability rather than an ad hoc shell command. | [agent-skill.md](../implementation/agent-skill.md) |
| Claude Code plugin | You use Claude Code and want both Skills installable with one command (`/plugin install`), plus namespaced explicit invocation (`/pitloom:sbom`, `/pitloom:enrich`). | [claude-code-plugin.md](../implementation/claude-code-plugin.md) |

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
   file or runs a test. Two **AI-agent Skills** (`skills/sbom/`,
   `skills/enrich/`) package Pitloom's CLI as explicit, independently
   triggerable capabilities for Claude Code, the Claude Agent SDK, and
   similar agent runtimes.

## The Skills are more than a CLI wrapper: agent-driven enrichment

The `enrich` skill is deliberately framed as an **enrichment surface**,
not just a thin CLI wrapper, because an AI agent can do things static
extraction cannot:

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

The `enrich` skill's guidance has an agent contribute enrichment as a
fragment, with every inferred field marked `Source: AI agent | Method:
inference`, so the result stays transparent and auditable. See
[sbom-enrichment.md](sbom-enrichment.md) for the full data-source model
this builds on.

## What is intentionally not in scope yet

- A **Docker container action** variant of the GitHub Action (hermetic,
  self-hosted-runner friendly) -- see [roadmap.md](roadmap.md).
- New enrichment *code* inside Pitloom core (README/model-card parsers,
  OpenSSF Scorecard, Hugging Face/PyPI enrichers) -- tracked separately in
  [sbom-enrichment.md](sbom-enrichment.md) and [roadmap.md](roadmap.md); the
  `enrich` skill enables agent-driven enrichment today without waiting for
  that code.
