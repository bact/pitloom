---
Created: 2026-04-14
Last-Modified: 2026-10-05
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
everything shipped in 0.20.0 (#226-#286, released 2026-10-05). User-facing documentation is in
`docs/` ([index](../../docs/index.md)).

## Next: release plan

Order (2026-10-05): 0.20.0 -> 0.20.1 -> 0.21.0 -> 0.22.0 -> 1.0. No date for
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

Crash, mapping and parity fixes, each in
[known-bugs.md](known-bugs.md#p0-in-0201): a very long lock-file version,
`-o -` ending stdout with a path line, GGUF `general.license`, a `%` in
`setup.cfg`, and two `setup.py`/`setup.cfg` merges that disagree with the
built wheel.

### 0.21.0

- [ ] **Registry v3**: one typed table, content gate chosen at lookup;
  closes the P1 registry bugs. See [id-registry-v3.md](id-registry-v3.md),
  [id-registry-v3-rollout.md](id-registry-v3-rollout.md).
- [ ] **Git LFS pointers outside AI models**: one shared detector, one
  summary `WARNING:`; lands before registry v3. See
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

- [ ] **#3 Mechanical wiring**: dataset licence, `ai_AIPackage.verifiedUsing`
  copied from its model `software_File`.
- [ ] **#6 Model producer and parameter count** from structured sources
  only (Hugging Face Hub fields, per-format metadata).
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
- [ ] **AI model id stability** beyond what registry v3 decides. See
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

## Needs systematic rules

Cross-cutting rule sets: one explicit rule, applied by one shared mechanism
on every surface (see "Usage surfaces" in [AGENTS.md](../../AGENTS.md)).
Each found more than one bug that a per-site fix would only move.

- [ ] **Licence rules**: source taxonomy, cascade per surface, weak and final
  values, declared vs concluded, conflicts, equivalence, provenance,
  tie-breaks. Current rules, rulings and 16 open questions:
  [license-rules.md](license-rules.md); layers:
  [license-layers.md](license-layers.md); what #276 left:
  [license-pr276-followups.md](license-pr276-followups.md).
- [ ] **Config cascade parity**: every option means the same on every
  surface, or warns as inert. See
  [config-cascade-parity.md](config-cascade-parity.md),
  [cli-shared-options-ignored.md](cli-shared-options-ignored.md),
  [docs/configuration.md](../../docs/configuration.md).
- [ ] **Merged manifest sources** (`setup.cfg` + `setup.py`, `[project]` +
  `[tool.poetry]`): which wins per field, as the build tool decides. See
  [setuptools-config-followups.md](setuptools-config-followups.md),
  [license-rules.md](license-rules.md#open-questions) (questions 2, 4).
- [ ] **Canonical output**: names, identifiers and key order the same for
  the same real-world thing. See
  [canonical-output-followups.md](canonical-output-followups.md).
- [ ] **No silent deviations, per surface**: non-directory targets
  (`model`, Hugging Face, `wheel`, `env`, sdist) drop configured fragments
  with no `WARNING:`; the GitHub Action drops any boolean input other than
  exactly `true`/`false` (`allow-build: True` skips the build). See
  [known-bugs.md](known-bugs.md#p3-after-0200),
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
  [known-bugs.md](known-bugs.md#p3-after-0200)); four #215 follow-ups. See
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
  collide (#236 review). See [known-bugs.md](known-bugs.md#p3-after-0200),
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
