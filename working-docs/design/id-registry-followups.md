---
Created: 2026-09-29
Last-Modified: 2026-09-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry and id-stability follow-ups

Open items left by the explicit-ID-registry work (PR #235) and the earlier
id-stability work (PR #178), moved out of [roadmap.md](roadmap.md), which
keeps a one-to-two-line bullet for each and links here.

See also: [ai-model-id-stability.md](ai-model-id-stability.md),
[id-registry-autosync.md](../implementation/id-registry-autosync.md),
[skills-trigger-coverage.md](../implementation/skills-trigger-coverage.md),
[diagnostics-logging-followups.md](diagnostics-logging-followups.md).

## Skill trigger coverage for `loom id generate`/`loom id import`

Flagged in the 2026-09-18 skills-coverage audit. As of PR #235 the skills
cover the registry end to end except for discovery: `sbom-generate`'s
"Pinning element ids" section states the declared-only rule (ids are
content-addressed, so a registry pins them only across runs whose inputs
differ, e.g. a fragment merged after the source changed), its
`references/id-registry.md` holds the create-a-registry workflow
(`loom id generate`/`loom id import`) and the log lines, and
`sbom-enrich`'s dangling-reference troubleshooting points at a registry
mismatch. What is still missing: no `description` has a trigger phrasing
for the two commands (a skill fires only through its description), and it
is undecided which skill owns them (a new one, or folded into
`sbom-generate`). Open question: which phrasings separate "pin ids before
a first run" from "import ids from an existing SBOM" without colliding
with plain generate/enrich requests. See
[skills-trigger-coverage.md](../implementation/skills-trigger-coverage.md).

## Deterministic same-model identification for auto-harvest

`ai_AIPackage` elements are excluded from the Loom ID registry's
auto-harvest since `ai_model.name` is extraction-dependent. Open design
question: whether a content-hash match (narrower than "same model" for
re-exported/re-quantized models) plus a non-identifying "machine ID"
scoping tag could safely extend auto-harvest to AI models. No
implementation direction chosen yet. See
[ai-model-id-stability.md](ai-model-id-stability.md).

## Wheel/sdist targets and src-layout registry file ids

`loom id generate` keys files by project path (`src/demo/x.py`), while a
wheel's distribution path is `demo/x.py` and an sdist's is
`demo-1.0.0/src/...`. A `loom project` harvest writes a
distribution-path alias (`demo/x.py`) next to the `src/` entry, so a later
`wheel` run does reuse the id. The gap
applies to a registry seeded by `loom id generate` alone, which has no
alias, and to an sdist target, which finds neither key.

## Harvest rewrites per-document entities; `env` root is never looked up

Found in PR A2 (#235) while making package ids registry-driven:
`SoftwareAgent`/`Tool`/`License` entries carry each document's own uuid,
so alternating `project`/`wheel` runs still change the registry's bytes
(package entries are stable); `env`'s root `deployed-environment` package
is always minted, and a pinned id for it is overwritten on harvest. See
[id-registry-autosync.md](../implementation/id-registry-autosync.md).

## A declared registry inside the package tree never settles

The registry file is itself a hashed project file, so with
`id-registry = "src/demo/reg.json"` every `project` run changes both the
SBOM and the registry bytes (`INFO: ... updated stale entries` each time;
seen at 6e83f41). Candidate fix: exclude the resolved registry path from
file discovery and from `id generate`'s indexing (the latter is the
custom-name gap in
[diagnostics-logging-followups.md](diagnostics-logging-followups.md)).
