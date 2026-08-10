---
Created: 2026-08-08
Last-Modified: 2026-08-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Handover: Phase 2 native-first backfill

> **Phase 2 is complete**: all six N-items (N1-N6) are `[x]` (N3 was the
> last, shipped in PR #124 -- see the Status list below). This file's
> stated purpose -- tracking the N1-N6 backfill -- is done; kept here as
> historical reference (same archival framing as
> [`annotation-provenance-full-plan.md`](annotation-provenance-full-plan.md)
> uses for Phase 1) rather than deleted, since it documents *why* each
> N-item's scope landed where it did (especially N3's new-elements-only
> limit). Not a live task list going forward -- the forward-looking
> "what to do about N3" and "start a new session" sections that used to
> follow are removed as of 2026-08-11 (N3 shipped, they were stale).

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
- ✅ **N3 — Enrichment `CreationInfo`**: `enrich/` subpackage MVP (local
  README/model-card YAML frontmatter, `enrich/readme.py`) plus N3 itself
  (`build_enrichment_creation_info()` in `creation_info.py`, scoped to
  *new* elements an enrichment run creates -- see its own docstring for
  why in-place field fills on existing elements can't get a second
  `CreationInfo`) and the E1/E2 Annotation
  (`build_enrichment_annotation()` in `provenance.py`,
  `provenance/enrichment/1` schema) all landed together in PR
  [#124](https://github.com/bact/pitloom/pull/124), which also exposed
  enrichment across every surface (CLI `loom enrich`, Python API,
  Hatchling hook, GitHub Action, config opt-in). PR
  [#125](https://github.com/bact/pitloom/pull/125) extended the
  `sbom-enrich` Skill to ask the SBOM author directly in interactive
  sessions, adding a fifth E1/E2 role (`sbomAuthorSupplied`) alongside
  `declared`/`detected`/`externalReported`/`inferred` -- see
  `annotation-provenance.md`'s role vocabulary.
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
see [`cli-ux.md`](../design/cli-ux.md) for the full rationale. As of now:

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
`working-docs/design/cli-ux.md` correctly describes the new design (its
mentions of `source`/`analyze`/`deployed` are explicitly framed as
historical background, not current state; a separate
`cisa-sbom-lifecycle.md` covering the same decision was merged into it
2026-08-11).

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
`tests/test_fragments.py`). Not extended to cover N3 -- enrichment's own
coverage lives in `test_generator.py`/`test_main_cli.py`/
`test_hatch_hook.py` instead (see PR #124).

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
