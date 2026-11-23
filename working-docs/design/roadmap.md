---
Created: 2026-04-14
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

How to read it: [Done](#done) lists what shipped; [Next](#next-release-plan)
the committed releases, open items first; the [`loom` SDK](#loom-sdk-code-model-dataset-annotation)
track; [Backlog](#backlog-designed-not-scheduled), designed work in priority
order; [To design](#to-design), questions needing a decision before code;
[Needs systematic rules](#needs-systematic-rules), rule sets that must apply
identically on every surface; [Open follow-ups by area](#open-follow-ups-by-area),
recorded findings; [Medium-term](#medium-term) and [Long-term](#long-term)
ideas; [Open GitHub issues](#open-github-issues), each issue's status. Bugs with
a target release: [known-bugs.md](known-bugs.md). Each bullet stays one or two
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
catalogue and provenance work planned for 0.24.0 is under "After 0.24.0"
below, targeting 0.25.0 (not released). No date for 1.0.

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
- [ ] **#514: ONNX tool-default graph names, GGUF Gemma-4 tokeniser headers**
  (GGUF header reader, partial read on a cap; after #515). See
  [model-reader-onnx-defaults-gguf-tokeniser.md](model-reader-onnx-defaults-gguf-tokeniser.md).

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
target is now 0.25.0, which is **not released** (user, 2026-11-16). Several
design docs still say "0.24.0" for these items. Each item is its own PR; the order and
counts are in [message-catalogue-migration-plan.md](message-catalogue-migration-plan.md).

- [x] **Frames (catalogue PR 4)**: the uniform `loom <command>:` prefix on
  every CLI `ERROR:` line, built; coding the `Build:` and `Git source:` lines
  is unblocked (PRs 13 and 14). See
  [message-frames.md](../implementation/message-frames.md).
- [x] **Catalogue PR 3**: input, option, SBOM and target errors coded, paths
  named as typed, URL credentials masked on every `ERROR:` line, one strict
  SBOM reader for `id import` and `embed-wheel`, the `messages` package split
  by topic (#482); ratchet 454 to 398.
- [x] **Catalogue PR 5**: ID registry file errors coded (`FILE=` as
  given); a missing `loom id generate` PATH is an error (#485); ratchet
  398 to 366.
- [x] **Credential leaks (#487)**: masking at the sinks, git helper, registry
  refusal; built, unreleased. See
  [credential-leak-fixes.md](../implementation/credential-leak-fixes.md).
- [x] **Credentials: detect, warn or refuse, PR 2**: the SBOM strip replaced
  by detect; warns by default, refuses opt in (`url-credentials = "refuse"`),
  per-value fingerprint override; merged (#490, 2026-11-16), unreleased. See
  [credential-detect-and-refuse.md](credential-detect-and-refuse.md).
- [x] **Credentials PR 3** (#491, merged 2026-11-16): the Action's `url-credentials`
  and `accept-url-credentials` inputs with `::add-mask::`, Git hardening (a
  Git URL's query never reaches git: spy test), encoded query and fragment
  values, `urllib3` log masking. Same doc, "Built in PR 3".
- [x] **Namespace mixing in one SBOM**: a registry namespace beside
  `spdx.org/spdxdocs/demo-<uuid>` ids is by design (the registry pins ids as
  first minted); documented, not unified. See
  [id-namespace-mixing.md](../implementation/id-namespace-mixing.md).
- [x] **Catalogue PRs 6 (#486) and 7 (#492)**: ID registry id, key and
  conflict messages; then save, file-set and summary lines (`file-unwritable`,
  `registry-file-missing`, `registry-conflict/file-set`); merged, ratchet 366
  to 328 to 316.
- [ ] **Catalogue PR 17** (the remaining families): miscellany (author split,
  dataset fields, over-cap, library misuse); then the final sweep. Done: lock files (10, 11, #496), config
  (8, 9, #497), licence (18, #498), project metadata and file discovery (12,
  #501; ratchet 211 to 154), Git source (13, #503; ratchet 154 to 132,
  frames by exact code, relays dropped), build, temporary directories and signals
  (14a, #506), the Hub timeout (#507), Hub and PyPI relay (14b, #508), hook
  lines (14c, #511; ratchet 132 to 108), SBOM fragments and merge
  (15, #513; ratchet 108 to 85), wheels and embedding (16, #515; ratchet 85 to
  44), the generated values page (#499). The
  consistency re-check of the merged families is done (#494). Plans:
  [message-catalogue-pr8-12-plan.md](message-catalogue-pr8-12-plan.md),
  [message-catalogue-pr12-18-plan.md](message-catalogue-pr12-18-plan.md).
- [ ] **0.25.0 cut sweep** (not released): the skills' floor `pitloom >=
  0.24.1` names no release (0.24.0 is the last tag; skills document 0.25.0
  flags and codes): raise to 0.25.0 in every `SKILL.md`, example and install
  line at the cut, keeping "0.24.0 or later" on the PyPI-URL lines.
- [ ] **LLMSC 2027 paper camera-ready** (user, 2026-11-23): the submitted
  paper reports Pitloom 0.24.0. Once 0.25.0 is out and LicenseID is 0.9.x,
  re-run its observations (Hub probe, embedded models, test files), then
  update its versions, counts and the reader gaps fixed since (#483, #509).
- [ ] **Review follow-ups** (the #492 and #480-#494 reviews): the open
  catalogue, code-shape, docs and size items are listed in
  [message-catalogue-review-rounds.md](../implementation/message-catalogue-review-rounds.md);
  also a NUL byte in a library registry path raises `InternalError`, and
  `test_each_view_is_linear` flaked twice on CI runners (bound now 64, retried).
- [ ] **Log masker: a token after an escaped control character** (found in
  PR 13 round 1): `TOKEN_RE` (`core/url_masking/_tokens.py`) lookbehind sees
  the `t` of an escaped `\t` (or `n` of `\n`), so `ghp_...` after it prints
  raw; pre-existing. PR 13 masks Git's text before `loggable`; the root fix
  (allow a token after an escape sequence, as after `%XX`) and `shown_url`
  (`_http_errors.py`, same order) are open. Also `pypi_url._refuse` still
  relays its refusal as an uncoded `WARNING:` (dropped in PR 14b). See
  [message-catalogue-review-rounds.md](../implementation/message-catalogue-review-rounds.md).
- [ ] **PR 14a follow-ups** (round 5, see the review-rounds page): the PDM
  discoverer's `pitloom-unused-<uuid>` directory is created by pdm-backend and
  never removed (`_models_wheel_pdm.py:181`, `extract/project/pdm.py:160`);
  `Bearer <jwt>` in a build's output is not masked; a signal test depends on
  the child's inherited SIGINT disposition (a backgrounded shell ignores it);
  `docs/git-urls.md` is over the 30 KB limit.
- [ ] **Unexplained CI hang** (2026-11-21, PR #507's first 3.14 ubuntu run):
  two xdist workers stopped for 23 minutes in `tests/core/models_wheel`
  (`test_models_wheel_guard.py::test_a_link_loop_in_a_clone_is_stopped_by_the_cap[setuptools-find]`
  and `test_models_wheel_build_timeout.py::test_allow_build_settings_reach_build_and_read_registered_backend`),
  then passed on a re-run of the same commit; the diff touched neither. Not
  reproduced on macOS 3.14 (full suite, coverage on, `-n 4`). A repeat is a
  real Linux-only hang: suspect the link-loop guard's `sys.setprofile` hook
  (`_models_wheel_guard.py`); first step, run `tests/core/models_wheel` under
  `-n 4` on Linux.
- [ ] **`pypi-url-unusable` is also logged bare before it is raised**
  (`assemble/_model_generator.py:_refuse_pypi_url`, found in PR 14b): the same
  duplicate that 14b dropped for `pypi-url-invalid` (Q15); `generate_model_sbom`
  on a PyPI URL prints the line twice. A test pins it
  (`test_generate_pypi_hosts.py`). Needs the same ruling, then drop it and the
  pin.
- [ ] **A repo id `huggingface_hub` refuses is said as `hub-response-invalid`**
  (found in PR 14b round 1; the misroute is new in 14b, `main` said a neutral
  "Failed to load model_info()"): `_HF_ID_RE` accepts `a/b--c`, `a/b..c`, `a/b.git`,
  `a/b-`, `a/b.` and names over 96 characters, which `validate_repo_id`
  rejects with `HFValidationError` before any request, so the line's advice
  ("the Hub may not speak the Hugging Face API") points away from the typo.
  Refuse these ids in `parse_hf_model_id` with `hf-url-invalid`, reusing the
  dataset rule (`core/dataset_names.is_hub_dataset_id`), and test it.
- [ ] **The `failure` cut is counted before memory addresses are dropped**
  (`messages/_field_writers.py:failure_text`, new in 14b; `main` had no cut): a text over 500 characters with
  an object repr before the cut can show a different tail per run. Drop the
  addresses from the masked text, then cut.
- [ ] **`docs/ai-model-formats.md` is over the 30 KB limit** (about 39 KB, over
  already on `main`); split it, with `docs/git-urls.md`.
- [ ] **Hub failure lines hold a per-run Request ID** (found in PR 14b round
  2): `huggingface_hub`'s 4xx/5xx text carries `(Request ID: Root=...)`, so the
  line differs on every real run (same on `main`). Drop it where the failure
  is written, with the canonical-output follow-ups.
- [ ] **A revision URL is read at the default branch with no signal**
  (`https://huggingface.co/o/m/tree/<sha>`, found in PR 14b round 2): a
  pre-existing silent deviation; say it (INFO) or honour the revision.
- [ ] **The hook accepts an `sbom-basename` that cannot be a file on Windows**
  (found in PR 14c round 1): a `"` in `sbom-basename` passes
  `sbom_base_name`, then `write_text_lf` fails late with a bare `OSError` on
  Win32. Refuse it where the basename is read (`core/file_names.py`).
- [ ] **The hook's `scan-model-usage` tri-state is unpinned** (found by PR 14c
  mutation testing): `scan_model_usage is True` and the `usage_hint` condition
  in `plugins/_hatch_document.py` (`build_document_model`) survive a change to
  `is not False` or a negation; add a test per state (`True`, `False`, `None`
  with the hint).
- [ ] **`error_frame`'s docstring says the hook "runs where no frame is open"**
  (`logging_config.py`), but `plugins/hatch.py` opens `error_frame(HOOK_FRAME)`
  itself; correct the docstring.
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
  declared as read, a variant concluded only on evidence, after the LicenseID
  0.9 bump (0.9.0 released 2026-11-19); later, an opt-in scan of grant text in
  repository files for more evidence. See
  [licence-variant-evidence.md](licence-variant-evidence.md).
- [ ] **Provenance and source-metadata flags** (decided 2026-11-05):
  provenance annotations are off by default (they make the SBOM huge, and the
  taxonomy is not settled); `--provenance`/`--no-provenance` turns them on
  (name to settle). Today they are on (`format = "both"`, `detail =
  "minimal"`). The verbatim source metadata (`preserve-source-metadata`) gets
  its own flag, `--preserve-source-metadata auto|always|never`, beside
  `--max-source-metadata-bytes`; default `never` (today `auto`). Each flag
  needs a `[tool.pitloom]` key, an Action input, an API parameter, the
  Hatchling hook, skills, a `_matrix_plan.py` entry and a CHANGELOG "Changed"
  note. Tests, manual checks and sweeps run with provenance on (one shared
  test default); default-off is asserted on each surface (CLI, library, hook,
  Action). Plan written 2026-11-11, **deferred** (too large; no release set;
  0.25.0 recommended over 0.24.1): see
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
- GitHub milestone `1.0.0` exists (no issues attached, no due date).

**Cut from 1.0** (stay on this roadmap, none block it): OSV.dev lookup,
CycloneDX and other output formats, `pixi.lock`/`conda-lock.yml`,
MLflow/W&B Weave/DVC extractors and fragment Phases 2-4, SARIF, SCITT,
PEP 740, remote ingestion, codename retirement, `loom fragment sign`,
generic multi-candidate fields, JAX/Orbax and TensorFlow Lite (first in the
[Backlog](#backlog-designed-not-scheduled)).

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

## Backlog: designed, not scheduled

Highest priority first.

- [ ] **JAX: Orbax checkpoints and Flax msgpack**: Orbax design checked
  against real output; a Flax file's layout checked on one Hub file. See
  [jax-orbax-support.md](jax-orbax-support.md).
- [ ] **TensorFlow Lite** (and SavedModel): `TFL3` FlatBuffer checked on two
  Hub files; design note with open questions. See
  [tensorflow-lite-savedmodel-support.md](tensorflow-lite-savedmodel-support.md).
- [ ] **Fields the built model readers leave unread**: GGUF datasets, PT2
  and CRFsuite counts built 2026-11-21; open: GGUF `general.base_model.*`/
  `general.source.*` lineage, PT2 I/O dtypes, the Hub's declared per-file
  LFS SHA-256. See
  [model-metadata-extraction.md](model-metadata-extraction.md#fields-the-built-readers-could-read).
- [ ] **Other model formats**: scikit-learn (pickle/joblib). See
  [model-metadata-extraction.md](model-metadata-extraction.md),
  [docs/ai-model-formats.md](../../docs/ai-model-formats.md).
- [ ] **MLflow run extractor** (`loom.from_mlflow_run()`, keyed against
  [STAV](https://github.com/bact/stav)); W&B Weave and DVC are the same
  shape. See [mlflow-extractor.md](mlflow-extractor.md).
- [ ] **OSV.dev vulnerability lookup**: design gaps resolved. See
  [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md).
- [ ] **More lock files** (`pixi.lock`, `conda-lock.yml`). See
  [lock-files.md](lock-files.md),
  [docs/dependency-sources.md](../../docs/dependency-sources.md).
- [ ] **Installed `.dist-info` as a project source**: see
  [installed-dist-info-site-packages.md](installed-dist-info-site-packages.md)
  (the in-tree slice is built:
  [installed-dist-info-source.md](../implementation/installed-dist-info-source.md)).
- [ ] **SARIF output** for CI findings; a missing-element report at generation
  would ride on it ([#77](https://github.com/bact/pitloom/issues/77)). See
  [sarif-output.md](sarif-output.md).
- [ ] **Docker container action** (`using: docker`) for hermetic or
  self-hosted runners. See [adoption-surfaces.md](adoption-surfaces.md).
- [ ] **Record the SPDX License List version on licence elements
  (`licenseListVersion`)**: small, not blocked by the provenance flags. See
  [licence-resolution-provenance.md](licence-resolution-provenance.md#7-licenselistversion-ships-independently).
- [ ] **SBOM format gaps ledger**: every mismatch or gap that makes a fact
  impossible to record precisely is noted in
  [sbom-format-gaps.md](sbom-format-gaps.md), for change proposals to SPDX (and
  CycloneDX once written).
- [ ] **External work to review**: Red Hat AI system card, OASIS Data
  Provenance Standard, ETSI TR 104 180; research notes from issues #46, #48,
  #53, #55, #129. See [external-references-to-review.md](external-references-to-review.md).
- [ ] **ML framework and `transformers` use from the code** (#66, #68, #65):
  `--scan-model-usage` walks the AST for discovered local model files only, not
  remote Hub ids. See [ml-framework-from-code.md](ml-framework-from-code.md).
- [ ] **Split `license-resolution-categories.md`** (37 KB, over the hard limit).
- Background research: [metadata-sources.md](metadata-sources.md) (how other
  tools read Python metadata), [sbom-enrichment.md](sbom-enrichment.md),
  [architecture-overview.md](architecture-overview.md).

## To design

Questions that need a decision before code. Nothing below is decided
unless the linked doc says so.

- [ ] **Generation gaps, sorted into extraction and recording gaps**: can we
  extract a minimum element, and can the format record it? See
  [generation-gaps-extraction-and-recording.md](generation-gaps-extraction-and-recording.md),
  issue [#110](https://github.com/bact/pitloom/issues/110).
- [ ] **Hugging Face Spaces**: a Space has no `pyproject.toml`; read the README
  front matter, `requirements.txt` and the Hub's `models` list instead. See
  [hugging-face-spaces-support.md](hugging-face-spaces-support.md).
- [ ] **What an SBOM counts as inside the package**, and package-format
  independence (payload vs container metadata, `.data/` naming). See
  [sbom-package-boundary.md](sbom-package-boundary.md).
- [ ] **Generic multi-candidate field representation**: licence, dependency
  version and project fields each hand-build a `ConflictCandidate` list.
  See [generic-multi-candidate-fields.md](generic-multi-candidate-fields.md),
  [metadata-quality.md](metadata-quality.md).
- [ ] **Licence resolution categories** (which changes to trust, log and
  record): built on LicenseID 0.7's `Resolution` (#437, #440). Open:
  per-operand provenance (T14, 0.24.0) and Q5 (the list version), both in
  [licence-resolution-provenance.md](licence-resolution-provenance.md), and
  Q4 (a cross-field indicator). See
  [license-resolution-categories.md](license-resolution-categories.md).
- [ ] **Message catalogue as the contract between Pitloom and the skills**
  (decided 2026-10-29): design done (#379); skill size cap built (#385);
  catalogue in code, schema and ratchet; the `lfs-pointer`, `over-cap`,
  model-stub and unreadable-file families built (#390, #396, #404, #408;
  0.22.0); PRs 1b, 1c and 2b in 0.23.0; the other families and `--report`
  in 0.24.0. See
  [message-catalogue-and-skills.md](message-catalogue-and-skills.md).
- [ ] **Evidence levels for recorded facts** (proposed 2026-10-29): caps bound
  reading, never reporting. Built: unit fix #382, merge drop #386, sizes under
  a cap #387. See [evidence-levels.md](evidence-levels.md).
- [ ] **Provenance and enrichment vocabulary** (Method vs Role, source and role
  taxonomy; parked draft). Redesign drafted from 2026-11-14, taxonomies
  agreed 2026-11-23, not built (the code stage is not started): see
  [provenance-taxonomy/](provenance-taxonomy/README.md). Earlier notes:
  [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md),
  [docs/metadata-provenance.md](../../docs/metadata-provenance.md); issues
  [#154](https://github.com/bact/pitloom/issues/154),
  [#110](https://github.com/bact/pitloom/issues/110).
  **Decided 2026-11-05:** no provenance annotation by default; a flag asks
  for it (see the flags item under After 0.24.0).
- [ ] **Dataset splits**: read Croissant `cr:Split` record sets; record each
  stated split as a `DatasetPackage` under the whole one. See
  [dataset-splits.md](dataset-splits.md).
- [ ] **AI model id stability** beyond what registry v3 built (the other
  AIPackage lookups gated by sha256). See
  [ai-model-id-stability.md](ai-model-id-stability.md).
- [ ] **Archive member names**: name-independent `--allow-build`
  extraction, `orig_filename`, tar links in sdists. See
  [archive-member-followups.md](archive-member-followups.md).
- [ ] **Format-neutral representation** for a second output format (CycloneDX,
  AIDOC); mappings kept as data, not code (CodeMeta crosswalk,
  [#52](https://github.com/bact/pitloom/issues/52)).
  See [format-neutral-representation.md](format-neutral-representation.md).
- [ ] **Fragments**: signing, SDK ergonomics, traceability, reuse of a project's
  earlier SBOM ([#41](https://github.com/bact/pitloom/issues/41)), merge
  precedence ([#150](https://github.com/bact/pitloom/issues/150)). See
  [open-items.md](sbom-fragments/open-items.md),
  [sbom-fragments/README.md](sbom-fragments/README.md),
  [docs/fragments.md](../../docs/fragments.md).
- [ ] **Forge APIs and private repositories** (tokens, `ssh://`, forge archive
  tarballs, forge licence and VCS provenance). Git URLs are built (0.21.0). See
  [remote-source-ingestion.md](remote-source-ingestion.md).
- [x] **PyPI URL targets, iteration 1** (built, 0.24.0): `loom wheel <pypi-url>`
  reads the wheel matching the running environment, `loom project <pypi-url>`
  the sdist; adds `--max-download-bytes`. See
  [pypi-url-targets.md](../implementation/pypi-url-targets.md).
- [ ] **PyPI URL targets, later iterations**: `--wheel-tag`/`--filename` first
  (Lumina needs it), `--list`, `--all-wheels` (one SBOM per wheel), `--choose`
  (interactive, TTY only), `name==version` and `files.pythonhosted.org`
  targets, other indexes and credentials, a download cache. See
  [pypi-url-targets.md](../implementation/pypi-url-targets.md#deferred-after-iteration-1).
- [ ] **VEX output format** (CSAF v2.0 vs OpenVEX), after the OSV lookup.
  See [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md#relationship-to-csafvex).
- [ ] **Author strings: NLP / named-entity recognition** (candidate): span
  splitting and Person vs Organization typing; today a warning, no guess. See
  [author-entity-recognition.md](author-entity-recognition.md),
  [#170](https://github.com/bact/pitloom/issues/170).
- [ ] **SPDX 3.1 output beside 3.0.1** ([#147](https://github.com/bact/pitloom/issues/147));
  today `specVersion` is fixed at `3.0.1`. See
  [architecture-overview.md](architecture-overview.md).
- [ ] **Package-URL as `spdxId`**
  ([#30](https://github.com/bact/pitloom/issues/30), needs decision): where a
  PURL is unique, it could dedup fragment merges; SPDX spec issue 1379.
- [ ] **CSVW round trip for missing facts**
  ([#81](https://github.com/bact/pitloom/issues/81), needs decision): missing
  elements as CSVW, filled by a person, read back as a fragment.

## Needs systematic rules

Cross-cutting rule sets: one explicit rule, applied by one shared mechanism
on every surface (see "Usage surfaces" in [AGENTS.md](../../AGENTS.md)).
Each found more than one bug that a per-site fix would only move.

- [ ] **Licence rules**: source taxonomy, cascade per surface, declared vs
  concluded, conflicts, tie-breaks; 17 open questions. See
  [license-rules.md](license-rules.md), [license-layers.md](license-layers.md),
  [license-pr276-followups.md](license-pr276-followups.md),
  [canonical-output-followups.md](canonical-output-followups.md) (section 6).
- [ ] **Config cascade parity**: every option means the same on every
  surface, or warns as inert. See
  [config-cascade-parity.md](config-cascade-parity.md),
  [cli-shared-options-ignored.md](cli-shared-options-ignored.md),
  [docs/configuration.md](../../docs/configuration.md).
- [ ] **`[project]` vs `[tool.poetry]` precedence**: which wins per field, as
  the build tool decides (`setup.cfg` + `setup.py` is done, #287). See
  [license-rules.md](license-rules.md#open-questions) (question 4),
  [setuptools-support.md](../implementation/setuptools-support.md#out-of-scope-follow-ups).
- [ ] **AI model corpus**: more real-world model files per format (small for
  diversity, large for boundaries) to size and rank the caps and hardening.
  See [ai-model-corpus.md](ai-model-corpus.md).
- [ ] **Canonical output**: same bytes and ids for the same input, same shape
  for the same value everywhere. Next: stable `CreationInfo` IRIs; a serialiser
  library ([#51](https://github.com/bact/pitloom/issues/51)) needs a decision.
  See [canonical-output-followups.md](canonical-output-followups.md).
- [ ] **No silent deviations, per surface**: non-directory targets
  (`model`, Hugging Face, `wheel`, `env`, sdist) drop configured fragments
  with no `WARNING:`; the GitHub Action drops any boolean input other than
  exactly `true`/`false` (`allow-build: True` skips the build). See
  [known-bugs.md](known-bugs/extraction-and-fragments.md#p3-after-0200),
  [known-bugs.md](known-bugs/surfaces-hook-and-wheel.md#p3-after-0200),
  [diagnostics-logging-followups.md](diagnostics-logging-followups.md).
- [ ] **Code health ratchets**: complexity and file-size limits down to the
  AGENTS.md targets. See
  [complexity-and-file-size-roadmap.md](complexity-and-file-size-roadmap.md).
- [ ] **Retire the use-case codenames** (G1-G7, A1-A2, N1-N6, ...; 500+
  occurrences). See [codename-retirement.md](codename-retirement.md).

## Open follow-ups by area

Recorded findings; each is fixable on its own.

- **G7 dataset creator**: written as `publishedBy`, the checker's `DP-006.1`
  reads `originatedBy`. See [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md).
- **File discovery**: setuptools gives an absolute `physical_path` for a
  differently cased project dir (#257); four #215 follow-ups; scikit-build-core
  ([#61](https://github.com/bact/pitloom/issues/61)). See
  [non-hatchling-file-discovery-followups.md](non-hatchling-file-discovery-followups.md#open-follow-up-tech-debt-from-pr-215s---allow-build-review),
  [build-backend-improvements.md](build-backend-improvements.md).
- **`--allow-build`**: what the #226 reviews left. See
  [allow-build-followups.md](allow-build-followups.md),
  [docs/allow-build.md](../../docs/allow-build.md).
- **Embed and wheel scan**: signal-safe rewrite, `wheel --embed
  --sbom-basename`, more. See [embed-wheel-followups.md](embed-wheel-followups.md).
- **setuptools config reading**: `version = attr:` crash, `file:` path
  confinement, untagged warnings. See [setuptools-config-followups.md](setuptools-config-followups.md).
- **ID registry**: what v3 leaves open; dataset identity by name and version
  everywhere (needs a go-ahead). See
  [id-registry-followups.md](id-registry-followups.md).
- **AI model scanning**: `env` scans no models; no warning when an extension
  disagrees with the content ([#103](https://github.com/bact/pitloom/issues/103)).
  See [cli-shared-options-ignored.md](cli-shared-options-ignored.md#still-open),
  [ai-model-scanning.md](../implementation/ai-model-scanning.md).
- **Fragments after the merge fixes**: see
  [open-items.md](sbom-fragments/open-items.md#left-after-the-fragment-merge-fixes).
- **`loom env`**: an unmet requirement loses its `dependsOn` edge; two installs
  sharing a pipdeptree `key` collide (#236). See [known-bugs.md](known-bugs/extraction-and-fragments.md#p3-after-0200),
  [deployed-env-pipdeptree.md](../implementation/deployed-env-pipdeptree.md).
- **GitHub Action hardening**: hash-pinned transitive dependencies, an
  isolated venv option, lint `scripts/` in CI. See
  [github-action.md](../implementation/github-action.md),
  [docs/github-action.md](../../docs/github-action.md).
- **Licence text detection**: composite licence files still conclude a wrong
  id. See [license-rules.md](license-rules.md#4-declared-or-concluded),
  [license-layers.md](license-layers.md).
- **Testing and CI**: see [testing-ci-followups.md](testing-ci-followups.md),
  including the [0.20.0 CI workflow review](testing-ci-followups.md#ci-workflow-review-0200).
- **Diagnostics and logging**: see
  [diagnostics-logging-followups.md](diagnostics-logging-followups.md).
- **Fragment `customIdToUri` integrity** (#471 review): the dangling check
  reads only ids in the main document's namespace, so under `loom merge` a
  wrapper mapping to a missing id or to a non-text merges silently. Also, the
  model path escapes display controls in place on a shared text after the
  `LicenseRef-loom-text-` hash was taken from the raw text. See
  [license-free-text-wrapper.md](../implementation/license-free-text-wrapper.md).
- **Remote fetches (Git, PyPI, Hugging Face)**: what #468 leaves, e.g. Hub API
  calls outside the fetch policy, `huggingface_hub`'s own log lines. See
  [pypi-url-targets.md](../implementation/pypi-url-targets.md#leftovers-after-pr-468-2026-11-10).

## Medium-term

- [ ] **A Hub model file read by HTTP range requests**, for consideration
  (evaluated 2026-11-09, not built: a `.keras`-only Hub repository has no
  Keras-derived field). See [hub-model-file-range-read.md](hub-model-file-range-read.md).
- [ ] **CycloneDX assembler** consuming the existing `DocumentModel`; no
  extractor changes.
- [ ] **AIDOC / TechOps renderer**, another `DocumentModel` output.
- [ ] **Build log extraction**: compiled dependencies, linker flags and
  bundled libraries from build output.
- [ ] **VEX (CSAF/OpenVEX) generation** from the OSV lookup (format: see
  [To design](#to-design)).

## Long-term

- [ ] **PEP 740 attestations** for generated SBOMs; Sigstore model signing
  ([#186](https://github.com/bact/pitloom/issues/186)).
- [ ] **IETF SCITT integration** (`loom scitt submit`, receipts); model
  provenance checks ([#79](https://github.com/bact/pitloom/issues/79)) could
  layer on it. See [scitt-integration.md](scitt-integration.md).
- [ ] **Performance**: Rust backend for large-project log parsing, parallel
  file hashing. See
  [performance-optimizations.md](performance-optimizations.md#rust-backend--parallel-hashing).
- [ ] **Agentic skill governance (guardrail mode)**: let the Skills veto or
  flag a coding agent's own action (e.g. pulling an unvetted Hugging Face
  model); needs a hook into the agent's tool-use loop.
- [ ] **Runtime reachability ("living SBOM")**: `loom env` tracking which
  dependencies are loaded at runtime (`sys.modules`, eBPF) to cut
  vulnerability noise. Needs its own design doc.

## Open GitHub issues

The 26 open issues, triaged 2026-10-23: two are closable
([#62](https://github.com/bact/pitloom/issues/62),
[#97](https://github.com/bact/pitloom/issues/97)); the others are linked from
the items above or are research notes. Status and evidence per issue:
[github-issues-triage.md](github-issues-triage.md).
