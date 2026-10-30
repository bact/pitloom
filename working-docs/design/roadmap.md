---
Created: 2026-04-14
Last-Modified: 2026-10-30
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
shipped up to 0.21.1 (0.20.0 #226-#286 on 2026-10-05, 0.20.1 on 2026-10-07,
0.20.2 on 2026-10-09, 0.21.0 #300-#350 and 0.21.1 #364-#366 on 2026-10-28),
including their release-plan items,
and the 0.22.0 items built so far. User-facing documentation is in `docs/`
([index](../../docs/index.md)).

## Next: release plan

Order (2026-10-09): 0.20.0 -> 0.20.1 -> 0.20.2 -> 0.21.0 -> 0.21.1 -> 0.22.0
-> 1.0. No date for 1.0 until 0.22.0 lands.

### 0.21.0

**Released 2026-10-28** (v0.21.0); v0.21.1 (#364-#366) the same day; Lumina
pins 0.21.1. See [release-checklist.md](../implementation/release-checklist.md).

Not built in 0.21.0; carried over (decided 2026-10-23):

- [ ] **A fragment value beats a value read from the file** (generated case
  built, #349): a **catalogue** or fragment value must win over a value read
  from the model; today the earlier element wins ([#150](https://github.com/bact/pitloom/issues/150)).
  A losing fragment's `generated` claim: [known-bugs.md](known-bugs.md#p0-in-0210).
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
  fastText label cap, cross-format label counts): [known-bugs-p3.md](known-bugs-p3.md).
- [ ] **Registry layouts beyond `src/` and `lib/`** (`python/`, `packages/`):
  no alias today; add only on demand. See [id-registry-followups-path-keys.md](id-registry-followups-path-keys.md).
- [ ] **Git URL ingestion, open follow-ups**: DNS rebinding, imperative
  `setup.py` reader, CLI clone cap, commit and URL in the SBOM. See
  [remote-git-ingestion.md](../implementation/remote-git-ingestion.md#not-built).
- [ ] **Unknown SPDX id in an SPDX-only field warns** and **`License-File:`
  selection** for wheels. See
  [license-pr276-followups.md](license-pr276-followups.md#a-to-fix).
- [ ] **Metadata-only AI model readers**: bounded pure-Python header readers
  replacing library reads, parity-tested; HDF5 last. See
  [model-metadata-readers.md](model-metadata-readers.md).

Built for 0.21.0 (#300-#350): registry v3, Git URL ingestion and hosts,
G7/CISA/FSCT/BSI conformance tests, SHA-512. See
[roadmap-completed.md](../implementation/roadmap-completed.md#shipped-in-0210-prs-300-350).

### 0.22.0: G7 SBOM for AI field coverage

The 1.0 headline ([#77](https://github.com/bact/pitloom/issues/77)); breakdown
in [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md). **Scope split (decided
2026-09-17):** deterministic field population belongs in core; fuzzy mapping (a
free-text "producer" to a `Person`/`Organization`) stays with the `sbom-enrich`
Skill.

**Focus (decided 2026-10-29): two priorities.** (1) CLI, API and skill
contracts through catalogued messages: the catalogue in code, the grammar
ratchet and the families that matter most to skills (see
[message-catalogue-and-skills.md](message-catalogue-and-skills.md)). (2) The
adoption of `licenseid` 0.7.0 (waits on its release; see
[licenseid-0-7-adoption.md](licenseid-0-7-adoption.md)). The items below
follow, in this order of need; evidence-level work (`Fact` PR-A done) continues
only where it pairs with a catalogue family (over-cap, unreadable file, Hub
failure); the rest may move to 0.23.0, with `--report` and SARIF.

**The 0.22.0 cut (decided 2026-10-30):** catalogue PRs 1 (model stub) and 2
(unreadable files and directories), the `licenseid` 0.7.0 adoption, the
licence provenance mapping ([#384](https://github.com/bact/pitloom/pull/384)),
catalogue PR 18 (licence) and the serious known bugs. The other catalogue
PRs go to 0.22.x or 0.23.0. List, sizes and bugs:
[message-catalogue-migration-plan.md](message-catalogue-migration-plan.md).

**Process (decided 2026-10-30):** two test gates per PR and a pre-release
review before the 0.22.0 tag. See
[testing-and-review-policy.md](../implementation/testing-and-review-policy.md).

Open:

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

Built so far (#374-#376, #378, #381, #382, #385-#387). See
[roadmap-completed.md](../implementation/roadmap-completed.md#shipped-in-0220-so-far).

### 1.0

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
  [installed-dist-info-source.md](installed-dist-info-source.md).
- [ ] **SARIF output** for CI findings; a missing-element report at generation
  would ride on it ([#77](https://github.com/bact/pitloom/issues/77)). See
  [sarif-output.md](sarif-output.md).
- [ ] **Docker container action** (`using: docker`) for hermetic or
  self-hosted runners. See [adoption-surfaces.md](adoption-surfaces.md).
- [ ] **SBOM format gaps ledger**: every mismatch or gap that makes a fact
  impossible to record precisely is noted in
  [sbom-format-gaps.md](sbom-format-gaps.md), for change proposals to SPDX (and
  CycloneDX once written).
- [ ] **External work to review**: Red Hat AI system card, OASIS Data
  Provenance Standard, ETSI TR 104 180; research notes from issues #46, #48,
  #53, #55, #129. See [external-references-to-review.md](external-references-to-review.md).
- [ ] **ML framework and `transformers` use from the code** (#66, #68, #65):
  today `--scan-model-usage` matches model file names only. See
  [ml-framework-from-code.md](ml-framework-from-code.md).
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
- [ ] **Licence resolution categories** (`Apache2` to `Apache-2.0` via
  `licenseid` 0.6.0): partly built in #359; operands, Q4 and Q5 open. Which
  changes to trust, log and record. See
  [license-resolution-categories.md](license-resolution-categories.md).
- [ ] **Message catalogue as the contract between Pitloom and the skills**
  (decided 2026-10-29): design done (#379); skill size cap built (#385);
  catalogue in code, schema and ratchet with the `lfs-pointer` families in
  review (#390); next (0.22.0): `over-cap`, then the migration order there;
  `--report` in 0.23.0. See
  [message-catalogue-and-skills.md](message-catalogue-and-skills.md).
- [ ] **Evidence levels for recorded facts** (proposed 2026-10-29): caps bound
  reading, never reporting. Built: unit fix #382, merge drop #386, sizes under
  a cap #387. See [evidence-levels.md](evidence-levels.md).
- [ ] **Adopt `licenseid` 0.7.0** (compounds, prose and trove names; delete
  about 250 lines of Pitloom's own parsing; Pitloom 0.22.0). Data and plan:
  [licenseid-0-7-adoption.md](licenseid-0-7-adoption.md).
- [ ] **Provenance and enrichment vocabulary** (Method vs Role, source and role
  taxonomy; parked draft). See
  [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md),
  [docs/metadata-provenance.md](../../docs/metadata-provenance.md); issues
  [#154](https://github.com/bact/pitloom/issues/154),
  [#110](https://github.com/bact/pitloom/issues/110).
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
- [ ] **PyPI package ingestion** (`loom pypi <name>[==version]`); first consumer
  Lumina. See
  [remote-source-ingestion.md](remote-source-ingestion.md#pypi-package-ingestion-loom-pypi-nameversion).
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
  [known-bugs-p3.md](known-bugs-p3.md),
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
  [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md#open-follow-up-tech-debt-from-pr-215s---allow-build-review),
  [build-backend-improvements.md](build-backend-improvements.md).
- **`--allow-build`**: what the #226 reviews left. See
  [allow-build-followups.md](allow-build-followups.md),
  [docs/allow-build.md](../../docs/allow-build.md).
- **Embed and wheel scan**: signal-safe rewrite, `wheel --embed
  --sbom-basename`, more. See [embed-wheel-followups.md](embed-wheel-followups.md).
- **setuptools config reading**: `version = attr:` crash, `file:` path
  confinement, untagged warnings. See [setuptools-config-followups.md](setuptools-config-followups.md).
- **ID registry**: what v3 leaves open. See
  [id-registry-followups.md](id-registry-followups.md).
- **AI model scanning**: `env` scans no models; no warning when an extension
  disagrees with the content ([#103](https://github.com/bact/pitloom/issues/103)).
  See [cli-shared-options-ignored.md](cli-shared-options-ignored.md#still-open),
  [ai-model-scanning.md](../implementation/ai-model-scanning.md).
- **Fragments after the merge fixes**: see
  [open-items.md](sbom-fragments/open-items.md#left-after-the-fragment-merge-fixes).
- **`loom env`**: an unmet requirement loses its `dependsOn` edge; two installs
  sharing a pipdeptree `key` collide (#236). See [known-bugs-p3.md](known-bugs-p3.md),
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

## Medium-term

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
