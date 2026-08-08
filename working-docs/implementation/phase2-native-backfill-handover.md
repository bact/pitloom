---
Created: 2026-08-08
Last-Modified: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Handover: Phase 2 native-first backfill

> **What this is**: Handover note for Phase 2 native-first backfill work following Phase 1 (provenance-as-Annotation).
>
> **Goal**: move six facts (N1-N6) that previously lived only in a free-text comment or Annotation into their proper native SPDX 3 constructs (`hasConcludedLicense`, `ExternalIdentifier`, `imports`, relationships, etc.), then trim each corresponding Annotation down to just the residual that still has no native home.

## Status

Phase 2 native-first backfill is **largely complete and merged**:
- ✅ **N2 — Declared vs. Concluded License**: PR [#105](https://github.com/bact/pitloom/pull/105) merged to `main`.
- ✅ **N4 — ExternalIdentifier & ExternalRef (DOI / arXiv / URLs)**: PR [#106](https://github.com/bact/pitloom/pull/106) merged to `main`.
- ✅ **N6 — Dataset Creator Agent & publishedBy Relationship**: PR [#107](https://github.com/bact/pitloom/pull/107) merged to `main`.
- ✅ **N1 — Fragment Origin (`SpdxDocument.imports` + `ExternalMap`)**: PR [#108](https://github.com/bact/pitloom/pull/108) merged to `main`.
- ✅ **N5 — Base-Model Lineage (`descendantOf` Relationship)**: PR [#109](https://github.com/bact/pitloom/pull/109) merged to `main`.
- 🛑 **N3 — Enrichment `CreationInfo`**: Blocked (waiting for `enrich/` subpackage).

## Principle (carried over from Phase 1)

Never put a value in an Annotation that has a native SPDX home. For each
N-item: **build the native construct, then trim the corresponding
Annotation content to the residual** (the part that still has no native
home — usually the *evidence* or *criterion* behind a value, not the
value itself).

## Work items, in recommended order

### 1. N2 — declared vs. concluded license (highest value, do first)

- **Where**: `src/pitloom/assemble/spdx3/deps.py:246-252` — concluded
  license is currently just mirrored from declared, comment says "no
  inference yet."
- **Build**: make `hasConcludedLicense` genuinely distinct from
  `hasDeclaredLicense` when Pitloom detects a license itself (from a
  `LICENSE` file, `licenseid` heuristic) rather than reading an
  author-asserted `project.license` field in `pyproject.toml`.
- **Trim**: once concluded license is native and distinct, the Annotation
  should keep only the *evidence* (which file/heuristic fired) — this is
  the G1/G2 use cases in the catalog, already implemented as Annotation
  content; just confirm it survives once N2 is native and doesn't
  duplicate the now-distinct concluded value.
- **Tests to touch**: `tests/test_spdx3_compliance.py`,
  `tests/test_provenance.py`, `tests/test_annotation_provenance.py`.

### 2. N4 — ExternalIdentifier for DOI / arXiv

- **Where**: `src/pitloom/extract/_huggingface.py:710-764` — DOI/arXiv/
  repo/model-card URLs currently land only in `extra_data`/provenance.
- **Build**: on the `ai_AIPackage`, add native `ExternalIdentifier` (type
  `doi`) and `ExternalRef` entries for arXiv/repo/model-card URLs — see
  `ai.py:124-357` for where the package is assembled.
- **Trim**: none needed once mapped — this field is fully native, no
  Annotation residual (per the plan's Phase 2 table).
- Lowest-ambiguity item, good if you want a quick isolated win.

### 3. N6 — dataset `creator`

- **Where**: extracted already in `src/pitloom/extract/_croissant.py:208`
  but never wired onto `dataset_DatasetPackage`.
- **Build**: `Agent` + a creation/attribution relationship on the dataset
  package, in `src/pitloom/assemble/spdx3/dataset.py:104-235`.
- **Trim**: none needed once mapped (fully native).
- Small, isolated, good second quick win.

### 4. N1 — fragment origin (`SpdxDocument.imports` + `ExternalMap`)

- **Where**: `src/pitloom/assemble/spdx3/fragments.py:461-464` —
  `_merge_fragment_set` discards fragment origin at merge time; `imports`
  is flagged unbuilt in `sbom-fragments.md:146,698-701`.
- **Build**: one `ExternalMap` per source fragment document, referenced
  via `SpdxDocument.imports`, so a merged element's origin fragment is
  recoverable natively.
- **Trim**: the unification *criterion* (registry-id/sha256/structural)
  stays in the A1 Annotation — `imports` can say *which* fragment, not
  *why* two elements were unified. Don't remove the A1 Annotation; just
  confirm N1 doesn't duplicate it.
- Bigger than N2/N4/N6 — touches the merge loop
  (`merge_fragments`, ~`fragments.py:575-607`) and document-level
  structure. Do after the smaller wins land and CI is stable.

### 5. N3 — enrichment `CreationInfo` (blocked)

- **Blocked** on the `enrich/` subpackage, which is not yet built (see
  `sbom-enrichment.md:145-169`). Skip until that subpackage exists.
- When unblocked: a second `CreationInfo` (createdBy = enricher agent,
  createdUsing = enricher tool, created = enrichment time) attached to
  enriched elements. Annotation residual is E1/E2 (before/after value +
  inferred-marker), already speced in `annotation-provenance.md` as
  design-only.

### 6. N5 — base-model lineage

- **Where**: HF `base_model` / `base_model_relation`, currently in
  `extra_data` only.
- **Build**: check whether an existing SPDX 3 `RelationshipType` fits a
  "derived from base model" edge; if yes, add a `Relationship` to the
  base-model element; if no clean fit, fall back to `ExternalRef` with
  the raw relation string kept as Annotation residual.
- Do last — needs a spec-fit judgment call before implementation, not
  just wiring.

## Workflow notes carried from Phase 1

- **Never commit/push without explicit user instruction.** The user
  merges PRs themselves; don't merge or push branches unprompted.
- Dev/test env: pyenv `pitloom310` (see project memory
  `project_dev_environment.md` if available in this session) — use its
  explicit python path for scratch/out-of-repo builds.
- Verification loop that worked well in Phase 1: implement → run
  `python3 -m pytest tests/ -q` + mypy + ruff → self-review or spawn
  narrow-focus Sonnet review agents (parallel, read-only, each required
  to produce a concrete repro) → triage findings → fix → re-verify.
  Two rounds of this caught 5 real issues (delimiter injection, JSON
  NaN/Infinity validity, non-deterministic set serialization) in Phase 1.
- Determinism requirement: `sort_keys=True` in all JSON serialization,
  sorted lists/sets before emission — Pitloom SBOMs must be byte-stable
  across runs.
- Comments in code: concise, describe *current* state only — don't
  narrate previous iterations or historical approaches in comments.
- CHANGELOG `[Unreleased]` entries: keep additions concise.

## Suggested first action for the picking-up session

1. Confirm `main` is at or past `404c03c` and branch `provenance-annotation`
   is gone (already merged/deleted).
2. Create a new branch (e.g. `phase2-native-backfill` or one per N-item —
   ask the user which granularity they want for PRs).
3. Start with N2 (license) per the order above, or ask the user to
   confirm/reorder — the order here is a recommendation, not a fixed
   sequence the user has approved.
4. Re-read `annotation-provenance.md` §10 in full before starting, since
   this handover only summarizes it.
