---
Created: 2026-08-08
Last-Modified: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Handover: Native SPDX backfill

> **What this is**: Handover note for native SPDX backfill work following
> provenance Annotation work.
>
> **Goal**: move six facts that previously lived only in a free-text comment or
> Annotation into their proper native SPDX 3 constructs
> (`hasConcludedLicense`, `ExternalIdentifier`, `imports`, relationships, etc.),
> then trim each corresponding Annotation down to just the residual that still
> has no native home.
>
> **Full design record**: [`annotation-provenance-full-plan.md`](annotation-provenance-full-plan.md)
> has the entire original provenance Annotation work plan (boundary principle, use-case catalog
> G1-G4/A1/A2/E1/E2/P1, the six native constructs table with rationale,
> config/schema design)
> archived in-repo. This handover is a status/next-steps summary; read the
> full plan if you need the *why* behind any native construct or Annotation shape.

## Status

Native SPDX backfill is **largely complete and merged**:
- ✅ **Declared vs. Concluded License**: PR [#105](https://github.com/bact/pitloom/pull/105) merged to `main`.
- ✅ **ExternalIdentifier & ExternalRef (DOI / arXiv / URLs)**: PR [#106](https://github.com/bact/pitloom/pull/106) merged to `main`.
- ✅ **Dataset Creator Agent & publishedBy Relationship**: PR [#107](https://github.com/bact/pitloom/pull/107) merged to `main`.
- ✅ **Fragment Origin (`SpdxDocument.imports` + `ExternalMap`)**: PR [#108](https://github.com/bact/pitloom/pull/108) merged to `main`.
- ✅ **Base-Model Lineage (`descendantOf` Relationship)**: PR [#109](https://github.com/bact/pitloom/pull/109) merged to `main`.
- 🛑 **Enrichment `CreationInfo`**: Blocked (waiting for `enrich/` subpackage).

## Principle (carried over from provenance Annotation work)

Never put a value in an Annotation that has a native SPDX home. For each
native construct: **build the native construct, then trim the corresponding
Annotation content to the residual** (the part that still has no native
home — usually the *evidence* or *criterion* behind a value, not the
value itself).

## Remaining work: Enrichment `CreationInfo`

**Blocked** on the `enrich/` subpackage, which does not exist yet (see
`sbom-enrichment.md:145-169`). This is the only unimplemented native construct.
Do not start it until `enrich/` exists — instead:

1. **Check whether `enrich/` has landed.** Search for a
   `src/pitloom/enrich/` (or similarly named) subpackage and any related
   PRs/branches.    if it still doesn't exist, Enrichment `CreationInfo` stays blocked — report
   that back rather than building enrichment machinery as a side effect
   of this task.
2. **If `enrich/` exists**, build a second `CreationInfo` attached to
   elements an enrichment run touches: `createdBy` = the enricher
   agent, `createdUsing` = the enricher tool, `created` = enrichment
   timestamp. Follow the pattern already centralized in
   `src/pitloom/assemble/spdx3/creation_info.py:build_creation_info()` —
   don't hand-roll a second construction path.
3. **Annotation residual (E1/E2)**: once the native `CreationInfo` exists,
   the Annotation on an enriched element should carry only what
   `CreationInfo` can't: which field changed, its before/after value, and
   the inferred-vs-extracted marker (`Source: AI agent | Method:
   inference`, today only in `skills/enrich/SKILL.md`'s free-text
   convention). This is speced as design-only in
   `annotation-provenance.md` (E1/E2) — implement it as part of Enrichment
   `CreationInfo`, not
   separately.
4. Mirror the preceding focused PRs' shape: one focused PR, tests in
   `tests/test_annotation_provenance.py` plus wherever enrichment gets
   its own test file, docs update in `annotation-provenance.md` (flip enrichment CreationInfo
   from "not yet built" to done, same as the other five rows).

## Integration test — recommended, not yet done

Fragment origin, license conclusion, external identifiers, base-model lineage,
and dataset creator attribution each landed as separate PRs, each presumably
tested in
isolation (unit/compliance tests scoped to that one native construct).
What's missing: a single **end-to-end test that exercises all five
together** on one representative input (e.g. an AI-model package with a
detected license, a DOI-bearing HF model, a base-model relation, a
dataset with a creator, assembled from ≥2 fragments so unification also
fires) and asserts on the *whole* generated SBOM:

- All five native constructs appear correctly on the same document at
  once (no interaction bugs — e.g. does adding `ExternalIdentifier` change
  spdxId minting in a way that breaks fragment unification?).
- Each Annotation is trimmed to its residual and does **not** duplicate
  a value now covered natively (the core regression risk: an old
  Annotation shape lingering after its native counterpart landed).
- Determinism holds across the combined output — `sort_keys=True` and
  sorted collections were verified per-feature in provenance Annotation work, but a
  multi-feature SBOM has more interleaving to get wrong; run generation
  twice and diff for byte-identical output.
- `pyspdxtools`/whatever SPDX 3 validator the repo already uses (see
  `tests/test_spdx3_compliance.py`) accepts the combined document.

Suggested location: a new `tests/test_native_spdx_integration.py`, or extend
`tests/test_spdx3_compliance.py` if that's already the repo's home for
whole-document assertions. This can be built once enrichment CreationInfo lands (to cover all
six), or sooner covering the five that are already done — the user
should decide which.

## Workflow notes carried from provenance Annotation work

- **Never commit/push without explicit user instruction.** The user
  merges PRs themselves; don't merge or push branches unprompted.
- Dev/test env: pyenv `pitloom310` (see project memory
  `project_dev_environment.md` if available in this session) — use its
  explicit python path for scratch/out-of-repo builds.
- Verification loop that worked well in provenance Annotation work: implement → run
  `python3 -m pytest tests/ -q` + mypy + ruff → self-review or spawn
  narrow-focus Sonnet review agents (parallel, read-only, each required
  to produce a concrete repro) → triage findings → fix → re-verify.
  Two rounds of this caught 5 real issues (delimiter injection, JSON
  NaN/Infinity validity, non-deterministic set serialization) in provenance Annotation work.
- Determinism requirement: `sort_keys=True` in all JSON serialization,
  sorted lists/sets before emission — Pitloom SBOMs must be byte-stable
  across runs.
- Comments in code: concise, describe *current* state only — don't
  narrate previous iterations or historical approaches in comments.
- CHANGELOG `[Unreleased]` entries: keep additions concise.

## Suggested first action for the picking-up session

1. Confirm `main` has PRs #105, #106, #107, #108, #109 merged.
2. Check whether `enrich/` subpackage exists yet (enrichment CreationInfo's blocker). Report
   status either way before doing anything else.
3. If still blocked, ask the user whether to prioritize the integration
   test (covering the five done items) or wait on enrichment CreationInfo.
4. Re-read `annotation-provenance.md` §10 in full before starting, since
   this handover only summarizes it.

## Prompt to start a new session on this handover

```
Read working-docs/implementation/native-spdx-backfill-handover.md in
full, then working-docs/implementation/annotation-provenance-full-plan.md
for the complete original design (boundary principle, use-case catalog,
the six native constructs rationale) if you need background on any item.

fragment origin, license conclusion, external identifiers, base-model lineage, and dataset creator attribution are merged (PRs #108, #105, #106, #109, #107).
enrichment CreationInfo (enrichment CreationInfo) is blocked on the enrich/ subpackage not
existing yet — check if it has landed since this doc was written. Also
evaluate whether to build the integration test described in the
"Integration test" section now (covering the five merged items) versus
waiting for enrichment CreationInfo. Report status and recommended next step before making
any code changes.
```
