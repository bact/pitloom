---
Created: 2026-08-08
Last-Modified: 2026-08-10
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
- ✅ **CLI/API redesign (`generate`/`project`/`wheel`/`model`/`env`/`merge`/`ids`, sdist support)**: PR [#114](https://github.com/bact/pitloom/pull/114), merged to `main`; see "2026-08-10 recheck" below -- supersedes the PR #96 vocabulary this handover previously documented.
- ✅ **`loom generate` project-config precedence fix**: PR [#116](https://github.com/bact/pitloom/pull/116) merged to `main`.
- ✅ **G2 -- multi-source disagreement, generalized** (the Annotation-evidence
  half of N2, not itself an N-item but directly completes it): declared-vs-
  independently-detected license conflict detection, generic
  `provenance/conflict/1` Annotation schema (reusable for any field),
  wired uniformly across all four project-metadata extraction paths
  (CLI/library, Hatchling build hook, poetry-only, setuptools-only --
  the Hatchling path silently had zero G2 coverage until this PR).
  PR [#121](https://github.com/bact/pitloom/pull/121) merged to `main`.
  See `annotation-provenance.md`'s G2 section for the full design.
- ✅ **AI-agent Skills renamed + `sbom-validate` added**: `skills/sbom/` ->
  `skills/sbom-generate/`, `skills/enrich/` -> `skills/sbom-enrich/`, new
  `skills/sbom-validate/` (thin wrapper around the third-party
  `spdx3-validate` CLI). PR [#123](https://github.com/bact/pitloom/pull/123)
  merged to `main`. Not an N-item and not blocking N3, but renames every
  `skills/sbom/` / `skills/enrich/` path this handover previously cited --
  see the doc-currency note below.

## Release readiness (last rechecked 2026-08-10, after #121/#123)

Everything since v0.12.0 (the last tagged release, 2026-07-10) is
**ready to release**. Re-verified directly on `main` at `210b203`:

- `python3 -m pytest tests/ -q` -- 1604 passed, 24 skipped, 0 failed.
- `mypy examples/ src/ tests/` and `ruff check examples/ src/ tests/` -- clean.
- `claude plugin validate .claude-plugin/plugin.json` and
  `.../marketplace.json` -- pass (both manifests were fixed in #123 --
  `$schema`, `displayName`, and a bare top-level `description` are
  rejected by the CLI's actual strict schema despite looking
  spec-compliant against the SchemaStore `$schema` URL; don't trust that
  URL as ground truth, see `claude-code-plugin.md`'s design notes).
- `tests/test_provenance_integration.py`, `test_annotation_provenance.py`,
  `test_fragments.py` -- all still pass; the N1-N6 machinery survived
  the CLI/API redesign below intact.

### 2026-08-10 recheck: what changed since PR #113, and why it matters

A **second CLI/API redesign landed in PR
[#114](https://github.com/bact/pitloom/pull/114)** ("cli-redesign"),
one day after #113 -- this supersedes the PR #96 CLI vocabulary this
handover previously documented. Don't trust any earlier mention of
`loom source`/`analyze`/`deployed` in this repo's history as current;
see [`cli-ux.md`](../design/cli-ux.md) and
[`cisa-sbom-lifecycle.md`](../design/cisa-sbom-lifecycle.md) for the
full rationale. As of now:

- **CLI subcommands**: `loom generate [target]` (smart auto-detect),
  `loom project [path]` (was `source`), `loom wheel <file>` and
  `loom model <target>` (`analyze` split in two, since it mixed local
  file inspection with Hugging Face network calls under one verb --
  `--offline` now exists on both `generate` and `model`), `loom env`
  (was `deployed`), `loom merge <fragments_dir>` (new -- CLI-exposed
  fragment merging), `loom ids ...` (unchanged).
- **Native sdist support** (`.tar.gz`/`.zip`) for `loom project` and
  `loom generate`, feeding a Source SBOM without needing a checked-out
  directory.
- **Python API renamed and reshaped**: `generate_sbom` ->
  `generate_project_sbom`, `generate_analyzed_sbom` split into
  `generate_wheel_sbom` / `generate_model_sbom` (`generate_model_sbom`
  also absorbs what `generate_huggingface_sbom` used to do -- that
  function no longer exists), `generate_deployed_sbom` ->
  `generate_env_sbom`. **No backward-compat aliases** -- this is a hard
  breaking change for any external code calling the old names. The four
  loose `provenance_format`/`_schema`/`_detail`/`_preserve_source_metadata`
  keyword arguments were also collapsed into a single
  `provenance: pitloom.core.provenance.ProvenanceConfig | None` parameter
  (same effective settings, new shape). `[tool.pitloom.provenance]`
  TOML keys themselves (`format`/`schema`/`detail`/`preserve-source-metadata`)
  are unchanged.
- **Follow-up bugfix, PR [#116](https://github.com/bact/pitloom/pull/116)**
  (merged the next day): `loom generate` initially *always* used
  `PitloomConfig()` defaults and never read the target's
  `pyproject.toml` -- meaning `[tool.pitloom.provenance]`, creator
  config, `pretty`, `describe-relationship` were all silently ignored
  when using the smart entrypoint on a project. Fixed to call
  `read_project()` on the target when it's an existing path, matching
  `loom project`'s precedence. Covered by 58 new lines in
  `tests/test_main_cli.py`.
- **Also merged in this window**: #115/#117 (Bandit hardening --
  pinned `hf_hub_download()` revisions, hardened env-command
  invocation), #118 (mypy >= 2.3.0), #119 (OpenSSF Scorecard CI),
  #120 (README/website updates).

**Doc/skill currency, re-checked against the new CLI vocabulary**:
README.md, `docs/index.md`, `skills/sbom-generate/SKILL.md` and its
`references/examples.md`, `skills/sbom-enrich/*` are **already correct** --
they use `project`/`wheel`/`model`/`env`/`generate`/`merge` throughout,
not the stale `source`/`analyze`/`deployed` this handover previously
recorded. This was done as part of #114/#116/#120, not by this recheck.
(Paths updated 2026-08-10 for the #123 skill rename -- this section
previously said `skills/sbom/` and `skills/enrich/*`, which no longer
exist. New `skills/sbom-validate/` added in #123 has no CLI-vocabulary
concern of its own since it wraps the third-party `spdx3-validate`
CLI, not `loom`.)
`working-docs/design/cli-ux.md` and `cisa-sbom-lifecycle.md` correctly
describe the new design (their mentions of `source`/`analyze`/`deployed`
are explicitly framed as historical background, not current state).

**CHANGELOG.md** was missing entries for #113 (loom hyperparameter
provenance) and #116 (the `loom generate` config-precedence fix) --
added in this recheck.

**Not fixed, flagged only (out of scope, not correctness bugs):**

- `examples/sentimentdemo-aibom/` generated fixtures were not
  regenerated against current output (deliberate, carried over from
  Phase 1) -- cosmetic only, not exercised by CI.

**Recommendation:** cut the release. Given the existing version history
(0.5.0 through 0.12.0, each a minor bump for additive features), most of
this window is additive/backward-compatible at the *output* level
(`comment` preserved by default, `Annotation` and the five native
constructs are pure additions) -- **except** the Python API rename in
#114, which has no back-compat shim and is a real breaking change for
any external caller of the old `generate_*_sbom` names or the old
`provenance_*` keyword arguments. Whether that alone pushes this past a
minor bump into `v1.0.0` (or is accepted as pre-1.0 API churn under
`0.x`, where SemVer allows breaking minor bumps) is the maintainer's
call, not this assessment's -- flagging it explicitly since it changes
the previous "safe minor bump" recommendation.

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

**When this handover doc itself can close:** once `enrich/` (MVP -- doesn't
need every enricher in `sbom-enrichment.md`'s table, just enough that an
enrichment run exists to attach a `CreationInfo` to) and N3 both land, all
six N-items are `[x]` and this doc's entire stated purpose -- tracking the
Phase 2 N1-N6 backfill -- is done. At that point: flip N3 to ✅ in the
Status list above, update `annotation-provenance.md`'s top-of-file status
line (currently "5 of 6 items shipped ... N3 still blocked") to "6 of 6",
extend the integration test per "Integration test -- done" below to cover
N3 too, then either delete this file or add the same archival framing
`annotation-provenance-full-plan.md` already uses ("historical reference,
not a live task list") rather than deleting outright -- matches how Phase 1's
equivalent handover-style content was retired. Don't close it early just
because `enrich/` MVP lands without N3 itself being built -- the doc's
job is the N-item backfill, not the enrich subpackage's existence.

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

1. **Check git log since this doc's Last-Modified date** (`git log
   --oneline <date>..HEAD`) before trusting anything in this file about
   current CLI/API shape or PR status -- this handover has already been
   caught out of date twice by fast-moving CLI redesigns (#96, then
   #114 a day after #113). Don't assume; verify.
2. Confirm `main` has PRs #105, #106, #107, #108, #109, #112, #113,
   #114, #116, #121, #123 merged, and check whether a release has been
   cut since this doc was written (see "Release readiness" above -- as
   of 2026-08-10 the answer was "ready, not yet cut").
3. Check whether `enrich/` subpackage exists yet (N3's blocker). Report
   status either way before doing anything else.
4. If still blocked, N3 stays deferred -- ask the user what's next
   (cutting the release, or something else) rather than assuming.
5. Re-read `annotation-provenance.md` §10 in full before starting on any
   N-item work, since this handover only summarizes it.

## Prompt to start a new session on this handover

```
Read working-docs/implementation/phase2-native-backfill-handover.md in
full, then working-docs/implementation/annotation-provenance-full-plan.md
for the complete original design (boundary principle, use-case catalog,
N1-N6 rationale) if you need background on any item.

N1, N2, N4, N5, N6 are merged (PRs #108, #105, #106, #109, #107), the
combined integration test (PR #112), and two follow-up passes (#113,
#116) fixed real gaps. G2 (the Annotation-evidence half of N2 -- generic
multi-source conflict detection, license as its first field) landed
separately in #121; the AI-agent Skills were renamed and gained a
sbom-validate skill in #123, unrelated to N-item work but touching every
skills/sbom/ and skills/enrich/ path this doc used to cite (now
skills/sbom-generate/ and skills/sbom-enrich/). IMPORTANT: PR #114
redesigned the CLI/API again one day after #113 -- run `git log --oneline
<this doc's Last-Modified date>..HEAD` FIRST and don't trust this file's
account of "current" CLI subcommands, Python API names, or skill paths
without checking git history yourself, since this doc has gone stale on
exactly that point before (twice, now three times counting the skill
rename). As of 2026-08-10 the codebase is release-ready. N3 (enrichment
CreationInfo) remains blocked on the enrich/ subpackage not existing yet
-- check if it has landed since. Once enrich/ (even an MVP) and N3 both
land, this handover doc's job is done -- see "When this handover doc
itself can close" under "Remaining work: N3" for what closing it means.

Check whether a release has been cut since this doc was written (compare
the latest git tag to `main`). If not, ask the user whether to proceed
with cutting one before doing anything else -- don't start new feature
work (N3 or otherwise) without checking first, since release timing is
the maintainer's call.
```
