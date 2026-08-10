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
- ✅ **`pitloom.loom` hyperparameter provenance + PR #96 CLI-consistency doc sweep**: PR [#113](https://github.com/bact/pitloom/pull/113) merged to `main`.

## Release readiness (assessed 2026-08-08, updated same day after a
second pass)

Everything since v0.12.0 (the last tagged release, 2026-07-10) --
Annotation-based provenance (Phase 1, PR #102), the five Phase 2
native-first backfills, the integration test, PR #96's CLI restructuring
(`loom source`/`analyze`/`deployed`/`ids`, merged just before the
provenance work), and the `pitloom.loom` hyperparameter-provenance fix
below -- is **ready to release**. Verified directly:

- `python3 -m pytest tests/ -q` -- 1537 passed, 24 skipped, 0 failed.
- `mypy src/pitloom` and `ruff check src/pitloom tests` -- clean.
- CI on `main` at `510701c` (PR #113 merge) -- green, including the
  second-pass fixes below.
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

### Second pass: PR #96 CLI-consistency sweep, and the hyperparameter-provenance fix

PR [#96](https://github.com/bact/pitloom/pull/96) ("Add CISA-lifecycle
SBOM generation") restructured the CLI from a flat
`pitloom <project_dir>` / `-m/--aimodel` form into
`pitloom source|analyze|deployed|ids` subcommands. It landed *after*
v0.12.0 (same as all the provenance work), and already updated most
CLI-consuming docs/skills as part of the PR itself. A dedicated sweep
for anything it missed found and fixed:

- `working-docs/design/hatchling-build-hook.md` -- referenced the old
  `loom generate` command name (never existed post-#96; should be
  `loom source`).
- `skills/sbom/SKILL.md` / `skills/sbom/references/examples.md` -- had
  no mention of the `deployed` subcommand (SBOM of the current
  installed environment) at all, and `analyze` accepting a `.whl` file
  wasn't called out either. Added a "Deployed SBOMs" section and
  example.
- `docs/index.md` (published) -- same `deployed` gap; added the example
  alongside the existing `source`/`analyze` ones.
- `tests/test_main_cli.py` -- three section-header comments still said
  `# -m / --aimodel: ...` above tests that actually exercise `analyze`
  (the tests themselves were correct, only the comments were stale).

Checked and found **not** affected: the Claude Code plugin
(`.claude-plugin/plugin.json`/`marketplace.json` and
`working-docs/implementation/claude-code-plugin.md` don't hardcode any
CLI invocation -- they only reference the Skills, which were the actual
thing needing the check), `skills/enrich/SKILL.md` (already uses
`loom source`/`loom analyze` correctly), `action.yml` and
`AGENTS.md` (no stale subcommand references), README.md (already
accurate for `source`/`analyze`/`deployed`/`ids`).

**Fixed (was flagged as a release blocker):** `pitloom.loom`
hyperparameter provenance depth. `set_model(hyperparameters=...)` and
the post-hoc `set_model_hyperparameters()` now record exact per-key
provenance (`hyperparameters.<key>`), the same shape the AI-model
extractors produce via `record_dict_field_provenance`, instead of
`set_model()`'s one generic `"package"` note (hyperparameters
unattributed) and `set_model_hyperparameters()` emitting no provenance
at all. Implementation note for whoever touches this next: **don't**
reuse `record_dict_field_provenance` directly here -- it sanitizes its
whole `source` argument (replacing `|` with `/`), which is correct for
extractors (their `source` is always a bare `"Source: X"` string) but
wrong for `loom.py`'s `_get_caller_info()`, which returns an
already-structured `"Source: X | Method: Y"` compound string; running
that through the sanitizer mangles the legitimate internal `|` and
folds the `Method:` segment into `source` when re-parsed. Fixed with a
small local `_record_hyperparameter_provenance()` helper in `loom.py`
that only sanitizes the hyperparameter *key*, not the caller-info
string. Covered by `test_loom_model_hyperparameters` (updated) and the
new `test_loom_set_model_hyperparameters_have_per_key_provenance` in
`tests/test_loom.py`. Verified live (not just via the test suite) by
generating a fragment and inspecting the emitted Annotation JSON.

Also fixed in the same pass: `working-docs/implementation/summary.md`
(the "canonical project structure" doc) -- its directory tree predated
the `provenance.py` module entirely and showed a `docs/design/` +
`docs/implementation/` layout that no longer matches the current
`docs/` (flat, published) + `working-docs/design/` +
`working-docs/implementation/` split; also fixed its stale CLI
subcommand list and `comment`-only provenance description, and flagged
its "Validation with sentimentdemo" section as a historical snapshot
(pre-#96 CLI syntax, stale element counts).

**Not fixed, flagged only (out of scope, not correctness bugs):**

- `examples/sentimentdemo-aibom/` generated fixtures were not
  regenerated against current output (deliberate, carried over from
  Phase 1) -- cosmetic only, not exercised by CI.

**Merged:** all of the above landed in PR
[#113](https://github.com/bact/pitloom/pull/113), merged to `main` at
`510701c`.

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

1. Confirm `main` has PRs #105, #106, #107, #108, #109, #112, #113
   merged, and check whether a release has been cut since this doc was
   written (see "Release readiness" above -- as of 2026-08-08 the answer
   was "ready, not yet cut").
2. Check whether `enrich/` subpackage exists yet (N3's blocker). Report
   status either way before doing anything else.
3. If still blocked, N3 stays deferred -- ask the user what's next
   (cutting the release, or something else) rather than assuming.
4. Re-read `annotation-provenance.md` §10 in full before starting on any
   N-item work, since this handover only summarizes it.

## Prompt to start a new session on this handover

```
Read working-docs/implementation/phase2-native-backfill-handover.md in
full, then working-docs/implementation/annotation-provenance-full-plan.md
for the complete original design (boundary principle, use-case catalog,
N1-N6 rationale) if you need background on any item.

N1, N2, N4, N5, N6 are merged (PRs #108, #105, #106, #109, #107), plus
the combined integration test (PR #112) and a second pass (PR #113) that
fixed the pitloom.loom hyperparameter-provenance gap and a handful of
stale CLI-related docs left over from PR #96's CLI restructuring -- see
"Release readiness" for full detail. As of 2026-08-08 the codebase is
release-ready and nothing is pending in the working tree. N3 (enrichment
CreationInfo) remains blocked on the enrich/ subpackage not existing yet
-- check if it has landed since.

First: check whether a release has been cut since this doc was written
(compare the latest git tag to `main`). If not, ask the user whether to
proceed with cutting one before doing anything else -- don't start new
feature work (N3 or otherwise) without checking first, since release
timing is the maintainer's call.
```
