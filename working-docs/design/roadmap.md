---
Created: 2026-04-14
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

How to read it: [Done](#done) lists what shipped; [Next](#next-release-plan)
the committed releases, open items first; the
[`loom` SDK](#loom-sdk-code-model-dataset-annotation) track;
[Backlog](roadmap-backlog.md#backlog-designed-not-scheduled), designed work in
priority order; [To design](roadmap-backlog.md#to-design), questions needing a
decision before code;
[Needs systematic rules](roadmap-backlog.md#needs-systematic-rules), rule sets
that must apply identically on every surface;
[Open follow-ups by area](roadmap-backlog.md#open-follow-ups-by-area),
recorded findings; [Medium-term](roadmap-backlog.md#medium-term) and
[Long-term](roadmap-backlog.md#long-term) ideas;
[Open GitHub issues](#open-github-issues), each issue's status. Bugs with a
target release: [known-bugs.md](known-bugs.md). Each bullet stays one or two
lines plus a link; detail lives in the linked doc.

## Done

[roadmap-completed.md](../implementation/roadmap-completed.md): everything
shipped up to 0.24.0 (0.20.0 #226-#286 on 2026-10-05, 0.20.1 on 2026-10-07,
0.20.2 on 2026-10-09, 0.21.0 #300-#361 and 0.21.1 #364-#366 on 2026-10-28,
0.22.0 #374-#408 on 2026-10-30, 0.22.1 #413-#433 on 2026-11-03, 0.23.0
#434-#449 on 2026-11-05, 0.23.1 #450-#456 and 0.23.2 #457-#459 on 2026-11-07,
0.23.3 #461 and 0.23.4 #462, #464 and #465 on 2026-11-09, 0.24.0 #468, #469
and #471 on 2026-11-11), with each release's highlights and requirements.
User-facing documentation is in `docs/` ([index](../../docs/index.md)).

## Next: release plan

Order (2026-11-04): 0.21.0 -> 0.21.1 -> 0.22.0 -> 0.22.1 -> 0.23.0 -> 0.24.0 ->
1.0. Every release up to 0.24.0 (2026-11-11) has shipped; what each built, and
what it requires, is in
[roadmap-completed.md](../implementation/roadmap-completed.md), the procedure
in [release-checklist.md](../implementation/release-checklist.md). The
catalogue work planned for 0.24.0 is merged for 0.25.0 (not released), under
"After 0.24.0" below with what is left. No date for 1.0.

**Process (decided 2026-10-30):** two test gates per PR and a pre-release
review before each release tag. See
[testing-and-review-policy.md](../implementation/testing-and-review-policy.md).

### Carried over from 0.21.0

Not built in 0.21.0 (decided 2026-10-23):

- [ ] **A fragment value beats a value read from the file** (generated case
  built, #349): a **catalogue** or fragment value must win over a value read
  from the model; today the earlier element wins ([#150](https://github.com/bact/pitloom/issues/150)).
  A losing fragment's `generated` claim: [known-bugs.md](known-bugs/extraction-and-fragments.md#p0-in-0210).
- [ ] **Canonical output, next steps**: LF in text values (plan first), stable
  `CreationInfo` IRIs. See
  [canonical-output-followups.md](canonical-output-followups.md),
  [creation-info-iri.md](creation-info-iri.md).
- [ ] **Per-lock "reaching path"**: tell a lock-only package reached only
  through an extra from a required one (today `runtime`); only `uv.lock` has a
  root walk; build with `pylock.toml`. See [extras-parity.md](../implementation/extras-parity.md#open-questions).
- [ ] **Optional lifecycle scope for extras** (a `[tool.pitloom]` mapping the
  project states; never guessed from a name). See
  [extra-lifecycle-scope.md](extra-lifecycle-scope.md).
- [ ] **Hardening from the #294 reviews** (Hangul fillers, ZWJ in prose,
  cross-format label counts; the fastText label cap is built, #426):
  [known-bugs.md](known-bugs/ai-models-readers-and-metadata.md#p3-after-0200).
- [ ] **Registry layouts beyond `src/` and `lib/`** (`python/`, `packages/`):
  no alias today; add only on demand. See [id-registry-followups-path-keys.md](id-registry-followups-path-keys.md).
- [ ] **Git URL ingestion, open follow-ups**: DNS rebinding, imperative
  `setup.py` reader, CLI clone cap, commit and URL in the SBOM. See
  [remote-git-ingestion.md](../implementation/remote-git-ingestion.md#not-built).
- [ ] **A model file from a Git URL: recursive discovery, origin provenance, a
  gated read of the native-library formats** (model SBOM built for 0.23.4: a
  folder is read non-recursively; the commit and URL are not in the SBOM;
  fastText, GGUF, HDF5, ONNX and PyTorch are listed unread). See
  [model-sbom-from-git.md](../implementation/model-sbom-from-git.md).
- [ ] **`License-File:` selection** for wheels (the unknown-id warning in an
  SPDX-only field is built, #357). See
  [license-pr276-followups.md](license-pr276-followups.md#a-to-fix).
- [ ] **Metadata-only AI model readers**: bounded pure-Python header readers
  replacing library reads, parity-tested; HDF5 last. See
  [model-metadata-readers.md](model-metadata-readers.md).
- [x] **#514: ONNX tool-default graph names, GGUF Gemma-4 tokeniser headers**
  (GGUF header reader, partial read on a cap). Built in #517; open items in
  [model-reader-onnx-defaults-gguf-tokeniser.md](../implementation/model-reader-onnx-defaults-gguf-tokeniser.md),
  "Still open".

### Carried over from 0.23.0

Not built in 0.23.0:

- [ ] **#7 `loom` SDK**: dataset provenance and training-properties capture.
  See the [`loom` SDK](#loom-sdk-code-model-dataset-annotation) section and
  [loom-sdk-expansion.md](loom-sdk-expansion.md).
- [ ] **Record a Git URL target's commit as a `pkg:git` identifier** (decided
  2026-10-23) and **one target resolver with Package-URL targets** (`pkg:git`,
  `github`, `bitbucket`, `huggingface`, `pypi`; later `conda`, `mlflow`): see
  [target-resolution-and-purl.md](target-resolution-and-purl.md).
- [ ] **Support-tier gaps past their target** (2026-10-19, missed): a Hub
  model's file hash, dataset provenance and statistics from the Hub, tier 2
  beyond keeping it working. See [support-tiers-and-demo-scope.md](support-tiers-and-demo-scope.md).
- [ ] **A `contentIdentifier` (gitoid)** beside the PURLs of the identifiers
  item below.

### After 0.24.0: message catalogue and licence provenance

Planned for 0.24.0 (ruling of 2026-11-04), not built when it was cut; the
target is now 0.25.0, which is **not released** (user, 2026-11-16). Each
item is its own PR; the order and counts are in
[message-catalogue-migration-plan.md](message-catalogue-migration-plan.md).

- [x] **Message catalogue** (merged, unreleased; ratchet 0): the frames
  (PR 4, #481), catalogue PRs 3 and 5 to 18 (#482 to #534), sweeps A to C
  (#536, #541, #542, #545, #546, #548, #550), the masking PRs
  (#526, #543 and #544) and the consistency rescan with per-surface
  advice and library argument checks (#553, #556, #557). See
  [the done list](message-catalogue-migration-plan.md#done-so-far-moved-from-the-roadmap-2026-11-26),
  [message-catalogue-finish-plan.md](../implementation/message-catalogue-finish-plan.md),
  [message-consistency-rescan.md](message-consistency-rescan.md).
- [x] **Credentials** (merged, unreleased): masking at the sinks, git helper
  and registry refusal (#487); detect, warn by default or refuse, with a
  per-value override (#489, #490); the Action inputs, Git hardening and
  encoded values (#491); a URL behind a leading character (#555). See
  [credential-leak-fixes.md](../implementation/credential-leak-fixes.md),
  [credential-detect-and-refuse.md](../implementation/credential-detect-and-refuse.md).
- [x] **Namespace mixing in one SBOM**: a registry namespace beside
  `spdx.org/spdxdocs/demo-<uuid>` ids is by design (the registry pins ids as
  first minted); documented, not unified. See
  [id-namespace-mixing.md](../implementation/id-namespace-mixing.md).
- [ ] **0.25.0 cut sweep** (not released): the skills' floor `pitloom >=
  0.24.1` names no release (0.24.0 is the last tag; skills document 0.25.0
  flags and codes): raise to 0.25.0 in every `SKILL.md`, example and install
  line at the cut, keeping "0.24.0 or later" on the PyPI-URL lines; also
  "LicenseID 0.8.4" in three `SKILL.md` files (SKL-1 of the pre-release
  review).
- [ ] **Pre-release review 0.25.0**: 5 blockers and 39 fixes for 0.25.0 in
  five PRs; argument checks (#560), catalogue (#559) and Hub "repository not
  found" (#561) are merged, docs and skills and the bump are left; the
  next-release items (CLI paths as typed, `-v` sources, hook inert keys,
  Action glob count, spdx3-validate blank nodes, ...) are listed there. See
  [pre-release-review-0.25.0.md](../implementation/pre-release-review-0.25.0.md#next-release).
- [ ] **LLMSC 2027 paper camera-ready** (user, 2026-11-23): the submitted
  paper reports Pitloom 0.24.0; keep its structure, update only the data.
  Once 0.25.0 is out and LicenseID is 0.9.x, re-run its observations (Hub
  probe, embedded models, test files), then update its versions, counts and
  the reader gaps fixed since (#483, #509, and #514 fixed by #517: ONNX
  default graph names, GGUF tokeniser header budget). If SBOM-MinBench 0.2 is
  released by then, take the Hub sample from it (not poolable with 0.1: 711
  entries, up to 20 files per repository).
- [ ] **Review follow-ups** (the #492 and #480-#494 reviews): the open
  catalogue, code-shape, docs and size items are listed in
  [message-catalogue-review-rounds.md](../implementation/message-catalogue-review-rounds.md);
  also a NUL byte in a library registry path raises a bare `ValueError`
  (`IdRegistry.load()`, `save()`; checked 2026-11-27), and
  `test_each_view_is_linear` flaked twice on CI runners (bound now 64, retried).
- [ ] **PR 14a follow-ups** (round 5): the PDM
  discoverer's `pitloom-unused-<uuid>` directory, made by pdm-backend, is
  never removed (`_models_wheel_pdm.py:181`, `extract/project/pdm.py:160`);
  a signal test depends on the child's inherited SIGINT disposition (a
  backgrounded shell ignores it).
- [ ] **Unexplained CI hang** (2026-11-21, PR #507's first 3.14 ubuntu run):
  the first test was fixed in #538; the second is unexplained. See
  [ci-hang-link-loop-guard.md](../implementation/ci-hang-link-loop-guard.md#roadmap-entry-moved-2026-11-26).
- [ ] **A repo id `huggingface_hub` refuses is said as `hub-response-invalid`**
  (found in PR 14b round 1; the misroute is new in 14b, `main` said a neutral
  "Failed to load model_info()"): `_HF_ID_RE` accepts `a/b--c`, `a/b..c`, `a/b.git`,
  `a/b-`, `a/b.` and names over 96 characters, which `validate_repo_id`
  rejects with `HFValidationError` before any request, so the line's advice
  ("the Hub may not speak the Hugging Face API") points away from the typo.
  Refuse these ids in `parse_hf_model_id` with `hf-url-invalid`, reusing the
  dataset rule (`core/dataset_names.is_hub_dataset_id`), and test it.
- [ ] **A revision URL is read at the default branch with no signal**
  (`https://huggingface.co/o/m/tree/<sha>`, found in PR 14b round 2): a
  pre-existing silent deviation; say it (INFO) or honour the revision.
- [ ] **The hook accepts an `sbom-basename` that cannot be a file on Windows**
  (found in PR 14c round 1): a `"` in `sbom-basename` passes
  `sbom_base_name`, then `write_text_lf` fails late with a bare `OSError` on
  Win32. Refuse it where the basename is read (`core/file_names.py`).
- [x] **The hook's `scan-model-usage` tri-state is unpinned** (found by PR 14c
  mutation testing): re-measured 2026-11-26, the `is not False` and negation
  mutants are killed on `main` at all five call sites; see
  [mutation-backfill.md](../implementation/mutation-backfill.md).
- [ ] **Mutation backfill, second PR**: `export/_spdx3_credentials` (32
  survivors untriaged), then the `id_registry` modules and the rest changed
  since `v0.24.0` with no pass. See
  [mutation-backfill.md](../implementation/mutation-backfill.md#backlog).
- [ ] **Hub API calls bypass the fetch policy**: `model_info()` and
  `dataset_info()` carry a 30 s socket timeout (#507) but no total deadline,
  no response cap, and `huggingface_hub` follows redirects unchecked. Replace
  them with `fetch_json` through `HubFiles`. See
  [remote-fetch-policy.md](../implementation/remote-fetch-policy.md).
- [ ] **Licence provenance mapping** (T14), after PR 18: per-operand
  `Resolution-<n>`, `License-List` and `Reason`, behind `--provenance`; waits
  for the flags item below and the provenance taxonomy. See
  [licence-resolution-provenance.md](licence-resolution-provenance.md).
- [ ] **Licence variants** (`-only` / `-or-later`; option G ruled 2026-11-19):
  declared as read, a variant concluded only on evidence, now that LicenseID
  0.9 is required (#502, #551); later, an opt-in scan of grant text in
  repository files for more evidence. See
  [licence-variant-evidence.md](licence-variant-evidence.md).
- [ ] **Provenance and source-metadata flags** (decided 2026-11-05):
  provenance annotations and verbatim source metadata off by default, a
  flag each. Plan written 2026-11-11, **deferred**: see
  [provenance-off-by-default.md](provenance-off-by-default.md).
- [ ] **Action builds the LicenseID database** (to decide): the Action
  installs only Pitloom, so a fresh runner matches no `LICENSE` text (a
  declared licence is still read). `pitloom-install.sh` could run
  `licenseid update --source packaged` (offline, seconds); CHANGELOG
  "Changed": `LICENSE` text matched by default.
- [ ] **`--report` (JSON Lines), then SARIF 2.1.0**, once most families have
  codes. See [sarif-output.md](sarif-output.md).

### 1.0

- [ ] **G7 SBOM for AI field coverage** (the headline,
  [#77](https://github.com/bact/pitloom/issues/77)): breakdown in
  [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md). **Scope split (decided
  2026-09-17):** deterministic field population belongs in core; fuzzy mapping
  (a free-text "producer" to a `Person`/`Organization`) stays with the
  `sbom-enrich` Skill.
- [ ] **Versioning and compatibility policy** (decision, not code): does
  1.0 commit to SemVer stability, replacing "no backward compat needed
  yet"? Which surfaces (CLI flags and output, library API,
  `[tool.pitloom]` schema, Action inputs, Skills), all at once or
  staggered? Any breaking cleanup to land before 1.0 while it is free?
- [ ] **Pre-release review harness** (golden snapshots, invariants, a seeded
  hostile-input generator): skipped for 0.25.0 by the user's ruling. See
  [testing-and-review-policy.md](../implementation/testing-and-review-policy.md#pre-release-review),
  step 3.
- GitHub milestone `1.0.0` exists (no issues attached, no due date).

**Cut from 1.0** (stay on this roadmap, none block it): OSV.dev lookup,
CycloneDX and other output formats, `pixi.lock`/`conda-lock.yml`,
MLflow/W&B Weave/DVC extractors and fragment Phases 2-4, SARIF, SCITT,
PEP 740, remote ingestion, codename retirement, `loom fragment sign`,
generic multi-candidate fields, JAX/Orbax and TensorFlow Lite (first in the
[Backlog](roadmap-backlog.md#backlog-designed-not-scheduled)).

## `loom` SDK (code-model-dataset annotation)

`pitloom.loom` lets a training, preprocessing or evaluation script declare
its model and datasets; the fragment it writes is merged into the project
SBOM. What it records today, verified against the code, and what to add, tied
to G7 elements: [loom-sdk-expansion.md](loom-sdk-expansion.md).

- [x] **Built**: `loom.run` context manager and decorator; `set_model`,
  `use_model`, hyperparameters, four dataset roles, Croissant and card
  readers, `trainedOn`/`testedOn`/`hasInput`/`generates` edges, registry ids.
- [ ] **Dataset provenance arguments** (collection method, sensitivity, bias,
  intended use, preprocessing on any dataset; G7 DP-006/DP-008): wiring onto
  existing `DatasetMetadata` fields. Section B1.
- [ ] **Training properties, metrics, energy, lineage, producer** (G7 MDL-011,
  MDL-006, KPI; `ai_informationAboutTraining`, `ai_metric`, `descendantOf`).
  Sections B2, B3.
- [ ] **Several models per run**: only the last declared model gets the run's
  relationships. Section B4.
- [ ] **Stable ids without a registry** (each run mints under a fresh UUID4)
  and a docs line that a model without `path=` stays a separate package after
  the merge (the sentimentdemo case). Sections B4, C1.
- [ ] **Notebook sessions, `log_*` API, IPython magic**: earlier sketch in
  [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md).

## Backlog, open design and follow-ups

Moved to [roadmap-backlog.md](roadmap-backlog.md): Backlog (designed, not
scheduled), To design, Needs systematic rules, Open follow-ups by area,
Medium-term and Long-term.

## Open GitHub issues

The 26 open issues, triaged 2026-10-23: two are closable
([#62](https://github.com/bact/pitloom/issues/62),
[#97](https://github.com/bact/pitloom/issues/97)); the others are linked from
the items above or are research notes. Status and evidence per issue:
[github-issues-triage.md](github-issues-triage.md).
