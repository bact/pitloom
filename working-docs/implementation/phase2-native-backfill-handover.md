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
>
> **Full design record**: [`annotation-provenance-full-plan.md`](annotation-provenance-full-plan.md)
> has the entire original Phase 1 plan (boundary principle, use-case catalog
> G1-G4/A1/A2/E1/E2/P1, the N1-N6 table with rationale, config/schema design)
> archived in-repo. This handover is a status/next-steps summary; read the
> full plan if you need the *why* behind any N-item or Annotation shape.

## Status

Phase 2 native-first backfill is **largely complete and merged**:

- ✅ **N2 — Declared vs. Concluded License**: PR [#105](https://github.com/bact/pitloom/pull/105) merged to `main`.
- ✅ **N4 — ExternalIdentifier & ExternalRef (DOI / arXiv / URLs)**: PR [#106](https://github.com/bact/pitloom/pull/106) merged to `main`.
- ✅ **N6 — Dataset Creator Agent & publishedBy Relationship**: PR [#107](https://github.com/bact/pitloom/pull/107) merged to `main`.
- ✅ **N1 — Fragment Origin (`SpdxDocument.imports` + `ExternalMap`)**: PR [#108](https://github.com/bact/pitloom/pull/108) merged to `main`.
- ✅ **N5 — Base-Model Lineage (`descendantOf` Relationship)**: PR [#109](https://github.com/bact/pitloom/pull/109) merged to `main`.
- 🛑 **N3 — Enrichment `CreationInfo`**: Blocked (waiting for `enrich/` subpackage).
- ✅ **Integration test** (N1/N2/N4/N5/N6 together): PR [#112](https://github.com/bact/pitloom/pull/112) merged to `main`.

## Release readiness (assessed 2026-08-08)

Everything since v0.12.0 (the last tagged release, 2026-07-10) --
Annotation-based provenance (Phase 1, PR #102) plus the five Phase 2
native-first backfills and the integration test above -- is **ready to
release**. Verified directly:

- `python3 -m pytest tests/ -q` -- 1536 passed, 24 skipped, 0 failed.
- `mypy src/pitloom` and `ruff check src/pitloom tests` -- clean.
- CI on `main` at `9c0d663` (PR #112 merge) -- all green: Unit tests,
  Type checking, Lint and format, Code coverage, Hatch integration,
  Action self-test, Build wheels + validate SBOM.
- All four usage surfaces checked end-to-end, not just read: CLI
  (`__main__.py` delegates to `pyproject.toml`-sourced `PitloomConfig`;
  no direct `--provenance-*` flags, by design -- CLI flags for this were
  deliberately out of scope in Phase 1), Python API
  (`generate_sbom`/`generate_ai_model_sbom`/`generate_huggingface_sbom`/
  `generate_analyzed_sbom`/`generate_deployed_sbom` in `assemble/__init__.py`
  all correctly default and thread `provenance_format`/`_schema`/`_detail`/
  `_preserve_source_metadata`), the Hatchling build hook
  (`plugins/hatch.py` threads the same four settings from
  `read_pitloom_config()`), and the `pitloom.loom` SDK (manually verified
  by generating a fragment via `loom.run()`/`set_model()`/`add_dataset()`
  and confirming Annotation elements with the correct `pitloom/1`
  statement actually appear in the output JSON -- not just a code read).
- No correctness bugs found in this pass -- only stale documentation
  (fixed, see below) and one non-blocking depth gap (also below).

**Docs fixed in this pass** (were stale, now corrected -- see each
file's diff for detail): `docs/metadata-provenance.md` (the published
GitHub Pages doc still described the pre-Annotation `comment`-only
mechanism with no mention of `[tool.pitloom.provenance]` at all -- this
was the most significant gap, since it's user-facing); `README.md`
"Metadata provenance" section (same overstatement); `CHANGELOG.md` (the
top-of-file "Commit history" compare link was one release behind,
`v0.10.0...v0.11.0` instead of `v0.11.0...v0.12.0`);
`working-docs/design/sbom-fragments.md` (still listed
`SpdxDocument.imports` population as an unbuilt Phase 4 item after N1
shipped it); `working-docs/design/metadata-provenance.md` and
`working-docs/implementation/annotation-provenance.md` (status headers
said "uncommitted on branch `provenance-annotation`", predating the
PR #102 merge); `working-docs/implementation/demo-provenance.md` (a
historical walkthrough written for the old always-on comment behavior,
now flagged with a banner rather than rewritten, since it's an internal,
low-traffic doc); `skills/sbom/SKILL.md` (didn't mention the
`[tool.pitloom.provenance]` config surface at all -- added a short
section).

**Not fixed, flagged only (out of scope for this pass, not correctness
bugs):**

- `working-docs/implementation/summary.md` (the "canonical project
  structure" doc) is stale independent of this feature -- its directory
  tree predates the `provenance.py` module entirely and shows a
  `docs/design/` + `docs/implementation/` layout that doesn't match the
  current `docs/` (flat, published) + `working-docs/design/` +
  `working-docs/implementation/` split. Pre-existing drift, not
  introduced by this work; a full rewrite is out of scope here.
- `examples/sentimentdemo-aibom/` generated fixtures were not
  regenerated against current output (deliberate, carried over from
  Phase 1) -- cosmetic only, not exercised by CI.
- **`pitloom.loom` hyperparameter provenance depth**: `set_model()`'s
  `hyperparameters=` argument and the standalone
  `set_model_hyperparameters()` don't get per-key provenance the way the
  AI-model extractors do via `record_dict_field_provenance`
  (`_extract_utils.py`) -- `set_model()` only records one generic
  `"package"` provenance entry (the caller's source location), and
  `set_model_hyperparameters()` (post-hoc update) emits no provenance at
  all for that call. The hyperparameter *values* themselves are correct
  in `ai_hyperparameter` either way -- this is a provenance-richness gap
  in one SDK path, not a data-correctness issue. Worth a small follow-up
  PR (mirror `record_dict_field_provenance` in `loom.py`'s
  `set_model`/`set_model_hyperparameters`) but does not block a release.

**Recommendation:** cut the release. Given the existing version history
(0.5.0 through 0.12.0, each a minor bump for additive features) and that
everything here is additive/backward-compatible -- `comment` output is
preserved by default, `Annotation` and the five new native constructs
are pure additions, no field or CLI flag was removed -- a minor version
bump (e.g. `v0.13.0`) fits the project's own pattern. That said, the
version number and release timing are the maintainer's call, not this
assessment's.

## Principle (carried over from Phase 1)

Never put a value in an Annotation that has a native SPDX home. For each
N-item: **build the native construct, then trim the corresponding
Annotation content to the residual** (the part that still has no native
home — usually the *evidence* or *criterion* behind a value, not the
value itself).

## Remaining work: N3 — enrichment `CreationInfo`

**Blocked** on the `enrich/` subpackage, which does not exist yet (see
`sbom-enrichment.md:145-169`). This is the only unimplemented N-item.
Do not start N3 itself until `enrich/` exists — instead:

1. **Check whether `enrich/` has landed.** Search for a
   `src/pitloom/enrich/` (or similarly named) subpackage and any related
   PRs/branches. If it still doesn't exist, N3 stays blocked — report
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
   `annotation-provenance.md` (E1/E2) — implement it as part of N3, not
   separately.
4. Mirror the N1/N2/N4/N5/N6 PRs' shape: one focused PR, tests in
   `tests/test_annotation_provenance.py` plus wherever enrichment gets
   its own test file, docs update in `annotation-provenance.md` (flip N3
   from "not yet built" to done, same as the other five rows).

## Integration test — done

Landed in [`tests/test_provenance_integration.py`](../../tests/test_provenance_integration.py)
(PR [#112](https://github.com/bact/pitloom/pull/112)), exercising N1, N2,
N4, N5, N6 together on one representative model. Confirms: all five
native constructs present on the same document at once; no Annotation
duplicates a value now covered natively; two generation runs with
identical inputs produce byte-identical JSON; the combined document
round-trips through `spdx-python-model` deserialization without loss.
`test_fragment_origin_round_trips_when_merged` covers N1's `ExternalMap`
shape directly (the real merge path is separately covered by
`test_merge_fragments_populates_spdx_document_imports` in
`tests/test_fragments.py`). Extend this file rather than adding a new one
when N3 lands, to keep all six in one place.

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

1. Confirm `main` has PRs #105, #106, #107, #108, #109, #112 merged, and
   check whether a release has been cut since this doc was written (see
   "Release readiness" above -- as of 2026-08-08 the answer was "ready,
   not yet cut").
2. Check whether `enrich/` subpackage exists yet (N3's blocker). Report
   status either way before doing anything else.
3. If still blocked, N3 stays deferred -- ask the user what's next
   (cutting the release, the loom.py hyperparameter-provenance follow-up
   noted above, or something else) rather than assuming.
4. Re-read `annotation-provenance.md` §10 in full before starting, since
   this handover only summarizes it.

## Prompt to start a new session on this handover

```
Read working-docs/implementation/phase2-native-backfill-handover.md in
full, then working-docs/implementation/annotation-provenance-full-plan.md
for the complete original design (boundary principle, use-case catalog,
N1-N6 rationale) if you need background on any item.

N1, N2, N4, N5, N6 are merged (PRs #108, #105, #106, #109, #107), plus
the combined integration test (PR #112). As of 2026-08-08 the codebase
was assessed as release-ready (see "Release readiness" section: all
tests/mypy/ruff/CI green, all usage surfaces -- CLI, Python API,
Hatchling build hook, pitloom.loom SDK -- verified consistent, stale
docs fixed). N3 (enrichment CreationInfo) remains blocked on the
enrich/ subpackage not existing yet -- check if it has landed since.

Check whether a release has been cut since this doc was written (compare
the latest git tag to `main`). If not, ask the user whether to proceed
with cutting one before doing anything else -- don't start new feature
work (N3, the loom.py hyperparameter-provenance follow-up, or otherwise)
without checking first, since release timing is the maintainer's call.
```
