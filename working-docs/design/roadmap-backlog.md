---
Created: 2026-11-26
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap: backlog, open design and follow-ups

See also: [roadmap.md](roadmap.md) (the release plan, the `loom` SDK track
and the open GitHub issues; read it first), [known-bugs.md](known-bugs.md),
[roadmap-completed.md](../implementation/roadmap-completed.md).

The unscheduled part of the roadmap, split out for size. Same rule as
roadmap.md: each bullet stays one or two lines plus a link.

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
- [x] **Split `license-resolution-categories.md`** (37 KB, over the hard limit):
  done; sections 2 and 9 are in
  [license-resolution-categories-licenseid.md](license-resolution-categories-licenseid.md).
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
  per-operand provenance (T14, not scheduled) and Q5 (the list version), both in
  [licence-resolution-provenance.md](licence-resolution-provenance.md), and
  Q4 (a cross-field indicator). See
  [license-resolution-categories.md](license-resolution-categories.md).
- [ ] **Message catalogue as the contract between Pitloom and the skills**
  (decided 2026-10-29): design done (#379); skill size cap built (#385);
  catalogue in code, schema and ratchet; the `lfs-pointer`, `over-cap`,
  model-stub and unreadable-file families built (#390, #396, #404, #408;
  0.22.0); PRs 1b, 1c and 2b in 0.23.0; the other families, sweeps and
  rescan merged for 0.25.0 (ratchet 0); `--report` open. See
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
  for it (see the flags item under After 0.24.0 in [roadmap.md](roadmap.md)).
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
