---
Created: 2026-04-14
Last-Modified: 2026-10-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

How to read it: [Done](#done) lists what shipped; [Next](#next-release-plan)
is the committed order of releases; [To design](#to-design) holds questions
that need a decision before any code; [Needs systematic
rules](#needs-systematic-rules) holds cross-cutting rule sets that must apply
identically on every surface;
[Open follow-ups by area](#open-follow-ups-by-area)
are recorded findings, not scheduled; [Backlog](#backlog-designed-not-scheduled)
and the [Medium-term](#medium-term)/[Long-term](#long-term) lists are ideas.
Bugs with a target release live in [known-bugs.md](known-bugs.md). Each
bullet stays one or two lines plus a link; detail lives in the linked doc.

## Done

[roadmap-completed.md](../implementation/roadmap-completed.md), including
everything shipped in 0.20.0 (#226-#286, released 2026-10-05); 0.20.1 and 0.20.2 are listed under Next. User-facing documentation is in
`docs/` ([index](../../docs/index.md)).

## Next: release plan

Order (2026-10-09): 0.20.0 -> 0.20.1 -> 0.20.2 -> 0.21.0 -> 0.22.0 -> 1.0. No date for
1.0 until 0.21.0 lands.

### 0.20.0

- [x] Embed fix ([#269](https://github.com/bact/pitloom/issues/269)), licence
  element typing (#276), sdist licence detection (#283), fragment-merge
  fixes (#284), sdist member order (#272), `sbom-basename` extension (#273).
- [x] Docs PR (#285): licence rules, known bugs, test tiers, field notes.
- [x] Release PR (#286): licence detection on real licence files (notice,
  near-tie), raw installed `METADATA`. See
  [license-rules.md](license-rules.md#4-declared-or-concluded).
- [x] Released 2026-10-05; published artefacts verified, see
  [wheel-sbom-verification.md](../implementation/wheel-sbom-verification.md).
- [ ] CI workflow hardening from the release review. See
  [testing-ci-followups.md](testing-ci-followups.md#ci-workflow-review-0200).
  Fuzz run after the release passed (2026-10-05).

### 0.20.1

Shipped 2026-10-07 (#287, #289, #291): setuptools precedence, licence
detection on Windows. Three planned fixes (a very long lock-file version,
Safetensors licence keys, a `%` in `setup.cfg`) did not make it; they are in
[known-bugs.md](known-bugs.md#p2-in-0210).

### 0.20.2

Released 2026-10-09 (tag v0.20.2). AI model metadata made
uniform and safer:

- [x] **One spelling for scalar text**, built in #294. See
  [scalar-text-spelling.md](../implementation/scalar-text-spelling.md).
- [x] **CRFsuite models** (#294): `lCRF` magic, stdlib-only bounded reader.
  See [crfsuite-support.md](../implementation/crfsuite-support.md).
- [x] **ONNX names, licence and version** (#292); **name, label and entry
  caps, display escape of bidi/invisible text, RFC 8785 embedded JSON,
  GGUF `general.license`** (#294).
- Known issue: a generated CRFsuite description can override a fragment
  description (see 0.21.0, "Fragment value beats an extracted one").

### 0.21.0

- [ ] **Same AI model, same id on every surface** (first item after #294):
  `loom model`, `loom enrich` and `loom id generate` use the project
  scan's name lookup, so enrichment cannot hit the wrong model. See
  [known-bugs.md](known-bugs.md#p0-in-0210).
- [ ] **Fragment value beats an extracted one** (own PR): a fragment or
  catalogue value must win over a value read from or generated for the
  model (e.g. a CRFsuite description). See
  [known-bugs.md](known-bugs.md#p0-in-0210).
- [ ] **Canonical output, next steps**: LF in text values (plan first), stable
  `CreationInfo` IRIs. See
  [canonical-output-followups.md](canonical-output-followups.md),
  [creation-info-iri.md](creation-info-iri.md).
- [x] **Extras, edge kind and authors on every route** (#300): built; open
  follow-ups in [extras-parity.md](../implementation/extras-parity.md#open-questions).
- [ ] **Per-lock "reaching path"**: tell a lock-only package reached only
  through an extra from a required one (today `runtime`). Only `uv.lock` has
  a root walk; build with `pylock.toml`. See
  [extras-parity.md](../implementation/extras-parity.md#open-questions).
- [ ] **Optional lifecycle scope for extras** (a `[tool.pitloom]` mapping the
  project states; never guessed from a name). See
  [extra-lifecycle-scope.md](extra-lifecycle-scope.md).
- [ ] **Hardening from the #294 reviews** (Hangul fillers, ZWJ in prose,
  fastText label cap, cross-format label counts): see
  [known-bugs.md](known-bugs-p3.md).
- [x] **Registry v3** (PR #305): built. See
  [id-registry-v3.md](../implementation/id-registry-v3.md); open follow-ups in
  [id-registry-followups.md](id-registry-followups.md).
- [x] **Registry path keys** (built 2026-10-16): one key helper, a model is
  keyed by its file, content-gated lookups. See
  [id-registry-path-keys.md](../implementation/id-registry-path-keys.md);
  open follow-ups (layouts other than `src/`/`lib/`) in
  [id-registry-followups-path-keys.md](id-registry-followups-path-keys.md).
- [ ] **Registry layouts beyond `src/` and `lib/`** (`python/`, `packages/`):
  no alias today; add only on demand. Same file.
- [ ] **Git LFS pointers outside AI models**: one shared detector, one
  summary `WARNING:`; registry v3 (built) ships without it. See
  [known-bugs.md](known-bugs.md#p0-in-0210).
- [ ] **One default SBOM file name** (PEP 427 escaping) on every surface.
- [ ] **Unknown SPDX id in an SPDX-only field warns** and **`License-File:`
  selection** for wheels. See
  [license-pr276-followups.md](license-pr276-followups.md#a-to-fix).
- [ ] **Metadata-only AI model readers**: bounded pure-Python header readers
  replacing library reads, parity-tested; HDF5 last. See
  [model-metadata-readers.md](model-metadata-readers.md).

### 0.22.0: G7 SBOM for AI field coverage

The 1.0 headline. Full breakdown and the core-vs-Skill scope split:
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md).

- [x] **#3 part 1: `ai_AIPackage.verifiedUsing`** copied from its model
  file, with gated model lookups (built 2026-10-16 with path keys; see
  [id-registry-path-keys.md](../implementation/id-registry-path-keys.md)).
- [x] **#3 part 2: dataset licence wiring** (`DatasetMetadata.license` read by
  `dataset.py`; G7 B1). Open: a reader that feeds a licence in. The 2026 SSSOM mappings fix the shape: a
  `hasDeclaredLicense` Relationship to an `AnyLicenseInfo`, so a URL and an
  SPDX expression both fit.
- [x] **Identifiers from the minimum-elements mappings** (CISA 2026, NTIA 2021,
  G7 AI 2026, BSI 2025): `software_packageUrl` on `ai_AIPackage` and dataset
  packages (G7 B2; see
  [g7-conformance-tests.md](../implementation/g7-conformance-tests.md)).
  Open: a `contentIdentifier` (gitoid).
- [ ] **SHA-512 hash option**: BSI 2025 requires SHA-512 on the deployable
  component; Pitloom emits SHA-256 only (`software_File`, `verifiedUsing`).
  Open: opt-in flag vs always add; the registry keeps SHA-256 as its gate.
- [ ] **Support tiers and demo scope** (tier 1: Safetensors, ONNX, GGUF, NumPy,
  fastText; demo: G7 Metadata/System/Model/Dataset, SPDX 3.0, Hatchling,
  setuptools, Poetry) and the parity ledger. See
  [support-tiers-and-demo-scope.md](support-tiers-and-demo-scope.md).
- [ ] **G7 honesty notices**: an `INFO:`/`WARNING:` for information read
  from a source that SPDX 3.0.1 has no property to record. See
  [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md).
- [x] **G7 conformance tests**: Pitloom's SBOMs checked with
  `ntia-conformance-checker` (`g7ai`) against an expected-outcome table, with
  offline SPDX validation and a coverage report. See
  [g7-conformance-tests.md](../implementation/g7-conformance-tests.md).
- [x] **#6 Model producer and parameter count** from structured sources
  (PR #306): `originatedBy` Agents and the `parameters` hyperparameter
  entry. See
  [g7-model-producer-parameter-count.md](../implementation/g7-model-producer-parameter-count.md).
- [ ] **#7 `loom` SDK**: dataset provenance and training-properties capture.
  See [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md).
- [ ] The skill's G7 checklist lists `hasDataFile` as covered; static
  detection is now behind `--scan-model-usage`. Update
  [minimum-elements.md](../../skills/sbom-enrich/references/minimum-elements.md)
  with G7.

**Scope split (decided 2026-09-17):** deterministic field population
(file formats, structured API responses, explicit `loom` SDK input) belongs
in core; fuzzy mapping (a free-text "producer" to an SPDX `Person`/
`Organization`) stays with the `sbom-enrich` Skill.

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
generic multi-candidate fields, JAX/Orbax.

## To design

Questions that need a decision before code. Nothing below is decided
unless the linked doc says so.

- [ ] **What an SBOM counts as inside the package**, and package-format
  independence (payload vs container metadata, `.data/` naming). See
  [sbom-package-boundary.md](sbom-package-boundary.md).
- [ ] **Generic multi-candidate field representation**: licence, dependency
  version and project fields each hand-build a `ConflictCandidate` list.
  See [generic-multi-candidate-fields.md](generic-multi-candidate-fields.md),
  [metadata-quality.md](metadata-quality.md).
- [ ] **Provenance and enrichment vocabulary** (Method vs Role, source and
  role taxonomy; parked draft). See
  [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md),
  [docs/metadata-provenance.md](../../docs/metadata-provenance.md).
- [ ] **AI model id stability** beyond what registry v3 built (the other
  AIPackage lookups gated by sha256). See
  [ai-model-id-stability.md](ai-model-id-stability.md).
- [ ] **Archive member names**: name-independent `--allow-build`
  extraction, `orig_filename`, tar links in sdists. See
  [archive-member-followups.md](archive-member-followups.md).
- [ ] **Format-neutral representation** for a second output format
  (CycloneDX, AIDOC). See
  [format-neutral-representation.md](format-neutral-representation.md).
- [ ] **Fragments**: signing and SHA-256 enforcement, SDK ergonomics,
  element-level traceability, compliance/interop. See
  [open-items.md](sbom-fragments/open-items.md),
  [sbom-fragments/README.md](sbom-fragments/README.md),
  [docs/fragments.md](../../docs/fragments.md).
- [ ] **Remote repository and forge ingestion** (`loom project <url>`). See
  [remote-source-ingestion.md](remote-source-ingestion.md).
- [ ] **VEX output format** (CSAF v2.0 vs OpenVEX), after the OSV lookup.
  See [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md#relationship-to-csafvex).
- [ ] **Author strings: NLP / named-entity recognition** (candidate): span
  splitting and Person vs Organization typing; today a warning, no guess.
  See [author-entity-recognition.md](author-entity-recognition.md).

## Needs systematic rules

Cross-cutting rule sets: one explicit rule, applied by one shared mechanism
on every surface (see "Usage surfaces" in [AGENTS.md](../../AGENTS.md)).
Each found more than one bug that a per-site fix would only move.

- [ ] **Licence rules**: source taxonomy, cascade per surface, weak and final
  values, declared vs concluded, conflicts, equivalence, provenance,
  tie-breaks. Current rules, rulings and 17 open questions:
  [license-rules.md](license-rules.md); normalisation questions (a licence
  name or URL to its id, case, equivalence): section 6 of
  [canonical-output-followups.md](canonical-output-followups.md); layers:
  [license-layers.md](license-layers.md); what #276 left:
  [license-pr276-followups.md](license-pr276-followups.md).
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
- [ ] **Canonical output**: same bytes and ids for the same input, same
  shape for the same value in every format and surface. See
  [canonical-output-followups.md](canonical-output-followups.md). Decided
  2026-10-08: RFC 8785 key order everywhere (pretty = canonical plus
  indentation), LF in text values; next, stable `CreationInfo` IRIs.
- [ ] **No silent deviations, per surface**: non-directory targets
  (`model`, Hugging Face, `wheel`, `env`, sdist) drop configured fragments
  with no `WARNING:`; the GitHub Action drops any boolean input other than
  exactly `true`/`false` (`allow-build: True` skips the build). See
  [known-bugs.md](known-bugs-p3.md),
  [diagnostics-logging-followups.md](diagnostics-logging-followups.md).
- [ ] **Code health ratchets**: complexity and file-size limits down to the
  AGENTS.md targets. See
  [complexity-and-file-size-roadmap.md](complexity-and-file-size-roadmap.md).
- [ ] **Retire the use-case codenames** (G1-G7, A1-A2, N1-N6, ...; 500+
  occurrences). See [codename-retirement.md](codename-retirement.md).

## Open follow-ups by area

Recorded findings; each is fixable on its own.

- **File discovery**: setuptools gives absolute `physical_path` for a
  project dir named in another letter case (macOS, Windows; #257, in
  [known-bugs.md](known-bugs-p3.md)); four #215 follow-ups. See
  [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md#open-follow-up-tech-debt-from-pr-215s---allow-build-review),
  [build-backend-improvements.md](build-backend-improvements.md).
- **`--allow-build`**: what the #226 reviews left. See
  [allow-build-followups.md](allow-build-followups.md),
  [docs/allow-build.md](../../docs/allow-build.md).
- **Embed and wheel scan**: signal-safe rewrite, `wheel --embed
  --sbom-basename`, dependency versions from Pitloom's own environment and
  more. See [embed-wheel-followups.md](embed-wheel-followups.md).
- **setuptools config reading**: `version = attr:` crash, `file:` path
  confinement, untagged setuptools warnings. See
  [setuptools-config-followups.md](setuptools-config-followups.md).
- **ID registry**: what v3 leaves open. See
  [id-registry-followups.md](id-registry-followups.md).
- **AI model scanning**: `env` scans no models. See
  [cli-shared-options-ignored.md](cli-shared-options-ignored.md#still-open),
  [ai-model-scanning.md](../implementation/ai-model-scanning.md).
- **Fragments after the merge fixes**: see
  [open-items.md](sbom-fragments/open-items.md#left-after-the-fragment-merge-fixes).
- **`loom env`**: an unmet requirement (`installed_version: "?"`) loses its
  `dependsOn` edge silently; two installs sharing one pipdeptree `key`
  collide (#236 review). See [known-bugs.md](known-bugs-p3.md),
  [deployed-env-pipdeptree.md](../implementation/deployed-env-pipdeptree.md).
- **GitHub Action hardening**: hash-pinned transitive dependencies, an
  isolated venv option, lint `scripts/` in CI, `args` edge cases. See
  [github-action.md](../implementation/github-action.md),
  [docs/github-action.md](../../docs/github-action.md).
- **Licence text detection**: composite licence files (a licence plus
  bundled third-party notices: mypy, typing_extensions) still conclude a
  wrong id; two `licenseid` issues to report upstream. See
  [license-rules.md](license-rules.md#4-declared-or-concluded),
  [license-layers.md](license-layers.md).
- **Testing and CI**: see [testing-ci-followups.md](testing-ci-followups.md).
- **Diagnostics and logging**: see
  [diagnostics-logging-followups.md](diagnostics-logging-followups.md).

## Backlog: designed, not scheduled

- [ ] **JAX (Orbax checkpoints)**: design ready, checked against real
  output. See [jax-orbax-support.md](jax-orbax-support.md).
- [ ] **Other model formats**: TensorFlow SavedModel/Lite, scikit-learn
  (pickle/joblib). See
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
- [ ] **SARIF output** for CI findings. See [sarif-output.md](sarif-output.md).
- [ ] **Docker container action** (`using: docker`) for hermetic or
  self-hosted runners. See [adoption-surfaces.md](adoption-surfaces.md).
- Background research: [metadata-sources.md](metadata-sources.md) (how other
  tools read Python metadata), [sbom-enrichment.md](sbom-enrichment.md),
  [architecture-overview.md](architecture-overview.md).

## Medium-term

- [ ] **CycloneDX assembler** consuming the existing `DocumentModel`; no
  extractor changes.
- [ ] **AIDOC / TechOps renderer**, another `DocumentModel` output.
- [ ] **Build log extraction**: compiled dependencies, linker flags and
  bundled libraries from build output.
- [ ] **VEX (CSAF/OpenVEX) generation** from the OSV lookup (format: see
  [To design](#to-design)).

## Long-term

- [ ] **PEP 740 attestations** for generated SBOMs.
- [ ] **IETF SCITT integration**: submit an SBOM as a signed statement
  (`loom scitt submit`), keep the receipt, verify dependencies' receipts.
  See [scitt-integration.md](scitt-integration.md).
- [ ] **Performance**: Rust backend for large-project log parsing, parallel
  file hashing. See
  [performance-optimizations.md](performance-optimizations.md#rust-backend--parallel-hashing).
- [ ] **Agentic skill governance (guardrail mode)**: let the Skills veto or
  flag a coding agent's own action (e.g. pulling an unvetted Hugging Face
  model); needs a hook into the agent's tool-use loop.
- [ ] **Runtime reachability ("living SBOM")**: `loom env` tracking which
  dependencies are loaded at runtime (`sys.modules`, eBPF) to cut
  vulnerability noise. Needs its own design doc.
