---
Created: 2026-04-14
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

How to read it: [Done](#done) lists what shipped; [Next](#next-release-plan)
is the committed order of releases, open items first in each;
[`loom` SDK](#loom-sdk-code-model-dataset-annotation) is the code-to-model-to-dataset
annotation track; [Backlog](#backlog-designed-not-scheduled) is designed work
in priority order, not scheduled; [To design](#to-design) holds questions that
need a decision before any code; [Needs systematic
rules](#needs-systematic-rules) holds cross-cutting rule sets that must apply
identically on every surface; [Open follow-ups by area](#open-follow-ups-by-area)
are recorded findings, not scheduled; the [Medium-term](#medium-term) and
[Long-term](#long-term) lists are ideas; [Open GitHub
issues](#open-github-issues) maps each open issue to its status. Bugs with a
target release live in [known-bugs.md](known-bugs.md). Each bullet stays one
or two lines plus a link; detail lives in the linked doc.

## Done

[roadmap-completed.md](../implementation/roadmap-completed.md): everything
shipped up to 0.20.2 (0.20.0 #226-#286 on 2026-10-05, 0.20.1 on 2026-10-07,
0.20.2 on 2026-10-09), including their release-plan items; 0.21.0 is listed
under Next. User-facing
documentation is in `docs/` ([index](../../docs/index.md)).

## Next: release plan

Order (2026-10-09): 0.20.0 -> 0.20.1 -> 0.20.2 -> 0.21.0 -> 0.22.0 -> 1.0. No
date for 1.0 until 0.22.0 lands.

### 0.21.0

**Progress (2026-10-23):** every code PR of the release is merged (#305-#350;
the last were #347 more Git hosts, #349 fragment value replaces generated, #350
the Spaces note). PR #346 holds the version bump, CHANGELOG, coverage snapshots
and the release review (CHANGELOG against the code, user docs and skills,
working-docs and comments). Before the tag: merge #346, tag v0.21.0, publish to
PyPI. After it: Lumina pins `pitloom==0.21.0` (it takes `licenseid` 0.6.0 through
Pitloom's floor), then adds
its non-GitHub examples. See [release-checklist.md](../implementation/release-checklist.md).

Not built in 0.21.0; carried over (decided 2026-10-23):

- [ ] **A fragment value beats a value read from the file** (the generated case
  is built, #349 below): a catalogue or fragment value must win over a value read
  from the model, not only over one Pitloom generated. Today the earlier element
  wins. Merge precedence: [#150](https://github.com/bact/pitloom/issues/150);
  a losing fragment's `generated` claim is in
  [known-bugs.md](known-bugs.md#p0-in-0210).
- [ ] **Canonical output, next steps**: LF in text values (plan first), stable
  `CreationInfo` IRIs. See
  [canonical-output-followups.md](canonical-output-followups.md),
  [creation-info-iri.md](creation-info-iri.md).
- [ ] **Per-lock "reaching path"**: tell a lock-only package reached only
  through an extra from a required one (today `runtime`). Only `uv.lock` has
  a root walk; build with `pylock.toml`. See
  [extras-parity.md](../implementation/extras-parity.md#open-questions).
- [ ] **Optional lifecycle scope for extras** (a `[tool.pitloom]` mapping the
  project states; never guessed from a name). See
  [extra-lifecycle-scope.md](extra-lifecycle-scope.md).
- [ ] **Hardening from the #294 reviews** (Hangul fillers, ZWJ in prose,
  fastText label cap, cross-format label counts): see
  [known-bugs-p3.md](known-bugs-p3.md).
- [ ] **Registry layouts beyond `src/` and `lib/`** (`python/`, `packages/`):
  no alias today; add only on demand. See
  [id-registry-followups-path-keys.md](id-registry-followups-path-keys.md).
- [ ] **Git URL ingestion, open follow-ups**: DNS rebinding between the
  caller's address check and git's own lookup; a reader for imperative
  `setup.py` (a monorepo such as `labs.etsi.org/rep/ocf/capif` fails with a
  hint naming its sub-projects); a clone size cap on the CLI (the library's is
  built, #339); record the commit and URL in the SBOM (see 0.22.0). See
  [remote-git-ingestion.md](../implementation/remote-git-ingestion.md#not-built).
- [ ] **Unknown SPDX id in an SPDX-only field warns** and **`License-File:`
  selection** for wheels. See
  [license-pr276-followups.md](license-pr276-followups.md#a-to-fix).
- [ ] **Metadata-only AI model readers**: bounded pure-Python header readers
  replacing library reads, parity-tested; HDF5 last. See
  [model-metadata-readers.md](model-metadata-readers.md).

What was built:

- [x] **Same AI model, same id on every surface**, and **registry path keys**
  (2026-10-16): one key helper, a model keyed by its file, content-gated
  lookups. See [id-registry-path-keys.md](../implementation/id-registry-path-keys.md).
- [x] **Registry v3** (PR #305). See
  [id-registry-v3.md](../implementation/id-registry-v3.md); open follow-ups in
  [id-registry-followups.md](id-registry-followups.md).
- [x] **Extras, edge kind and authors on every route** (#300); open
  follow-ups in [extras-parity.md](../implementation/extras-parity.md#open-questions).
- [x] **Git URL ingestion** (PR #317): `loom project <url>` and
  `loom generate <url>` for GitLab, GitHub, Gitea/Forgejo, Bitbucket and
  SourceHut; redirects followed hop by hop with a caller check; Lumina uses
  it. See [remote-git-ingestion.md](../implementation/remote-git-ingestion.md),
  [docs/git-urls.md](../../docs/git-urls.md).
- [x] **More Git hosts** (#347): Bitbucket `branch`/`commits` pages (the ref
  was dropped silently), SourceHut `log`, Gitiles `/+/`, cgit `?h=`, Azure
  DevOps `?version=`; a folder page naming a file reads its folder; a clone
  rejected with HTTP 400 on the blob filter is retried without it; a Hugging
  Face Space or dataset is a Git repository, not a model. Live checks on 12
  hosts. See [docs/git-urls.md](../../docs/git-urls.md).
- [x] **A fragment value replaces one Pitloom generated** (#349): the
  `description`, `ai_domain` and input/output text a reader made from the file's
  format (`generated_from_labels`, `derived_from_format`), with one `INFO:` and
  the property's provenance dropped, in any order of fragments. See
  [docs/fragments.md](../../docs/fragments.md).
- [x] **Git URL hardening** (#339, #342-#344): `max_bytes=` clone cap in the
  library (`git.too-large`), credentials only on same-origin redirects,
  SourceHut slash branches, the process tree killed on Windows.
- [x] **One default SBOM file name** (#334): one helper for the CLI, the hook
  and `embed-wheel`. It replaces unsafe characters only, not PEP 427's
  escaping as [known-bugs.md](known-bugs.md#p0-in-0210) decided; whether to
  change the rule is open.

Also built for 0.21.0 (the G7 and conformance work; full breakdown in
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md)):

- [x] **#3 part 1: `ai_AIPackage.verifiedUsing`** from its model file, with
  gated lookups (2026-10-16; see
  [id-registry-path-keys.md](../implementation/id-registry-path-keys.md)).
- [x] **#3 part 2: dataset licence wiring** (`DatasetMetadata.license` read
  by `dataset.py`; G7 B1) and its three readers
  (Croissant via `loom.run`, a local dataset card, a Hub model's dataset
  cards): [dataset-licence-readers.md](dataset-licence-readers.md).
- [x] **Identifiers from the minimum-elements mappings** (CISA 2026, NTIA 2021,
  G7 AI 2026, BSI 2025): `software_packageUrl` on `ai_AIPackage` and dataset
  packages (G7 B2; [g7-conformance-tests.md](../implementation/g7-conformance-tests.md)).
- [x] **SHA-512 beside SHA-256** (always, no flag) for every file Pitloom
  reads and describes: model files, project/wheel/sdist file elements,
  `loom` files, bundled libraries (`pitloom.core.file_hash`). The registry
  gate, a Merkle root and a lock file's dependency hash stay SHA-256; a
  dependency's SHA-512
  stays unspecified while no source states one (decided 2026-10-18;
  [build-backend-improvements.md](build-backend-improvements.md)).
- [x] **Hub revision** (G7 B3): a Hub model's commit hash as its version and
  its last-modified time as `releaseTime`.
- [x] **Support tiers and demo scope** (tier 1: Safetensors, ONNX, GGUF, NumPy,
  fastText, Hugging Face Hub; demo: G7 Metadata/System/Model/Dataset, SPDX 3.0,
  Hatchling, setuptools, Poetry) and the parity ledger on
  `docs/g7-sbom-for-ai.md`; open gaps are above.
- [x] **G7 honesty notices** (2026-10-18): one `INFO:` per model naming a G7
  element SPDX 3.0.1 has no property for (today the architecture, in
  `ai_typeOfModel`; no reader drops a value). Always on, stderr only
  (`extract/ai_model/unrecordable.py`). See
  [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md).
- [x] **Conformance tests**: G7 (`g7ai`, with offline SPDX validation),
  CISA 2026 (`cisa2026`, SPDX 3.0), FSCT 2024 (`fsct3`) and BSI TR-03183-2
  v2.1 (rule-based `rules/bsi.yaml`; the hand-written `BSIChecker` is
  removed), each with an expected-outcome table and surface-parity tests;
  coverage in `g7-coverage-history/`. CISA's hash rule is checked as "an
  integrity method is present" only. BSI
  [ontology](https://bact.github.io/bom/req/bsi2025/bsi2025.ttl) and
  [mapping](https://bact.github.io/bom/mapping/bsi2025-to-spdx30.sssom.tsv).
  See [g7-conformance-tests.md](../implementation/g7-conformance-tests.md).
- [x] **Same reachability for every standard** (checker `151460c`,
  2026-10-18): `trainedOn` and `testedOn` are the default `reach_via`, so
  every standard judges the datasets a reachable model uses;
  `bsi-expected.tsv` refreshed.
- [x] **CLI option choices in a stable order** (2026-10-18):
  `--content-type-method` and `--creator-type` listed a `frozenset` in hash
  order; now sorted (`tests/cli/test_cli_choices_order.py`).
- [x] **Dataset readers' edge cases** (2026-10-19): Croissant nesting cap,
  placeholder and non-URL values, card warnings without a cache path, one
  reference per dataset, a `datasets:` cap, YAML 1.1 and generated-input
  tests. See [dataset-licence-readers.md](dataset-licence-readers.md).
- [x] **One dataset, one package, one relationship per role** (PR #311, #314):
  first reference wins, later ones fill unset fields, a conflict warns once
  per field; `loom.Run` folds spellings the same way (`Org/Data` is
  `org/data`, an existing path never folded). See
  [ai-dataset-linking.md](../implementation/ai-dataset-linking.md).
- [x] **A software-agent creator is the author, not the supplier** (PR #312):
  `suppliedBy` takes the first creator that is not a `software-agent`, else
  none; Lumina reports itself as the author and Pitloom as the tool.
- [x] **#6 Model producer and parameter count** from structured sources
  (PR #306): `originatedBy` Agents and the `parameters` hyperparameter
  entry. See
  [g7-model-producer-parameter-count.md](../implementation/g7-model-producer-parameter-count.md).
- [x] CHANGELOG entries for the 2026-10 G7/CISA/FSCT/SHA-512 work (#309), the
  Hub model description fix (#310) and the dataset and creator fixes (#311,
  #312, #314).
- [x] The skill's G7 checklist matches the code (`hasDataFile` only with
  `--scan-model-usage`; dataset edges; SHA-512): see
  [minimum-elements.md](../../skills/sbom-enrich/references/minimum-elements.md).

### 0.22.0: G7 SBOM for AI field coverage

The 1.0 headline ([#77](https://github.com/bact/pitloom/issues/77)). Full
breakdown and the core-vs-Skill scope split:
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md). **Scope split (decided
2026-09-17):** deterministic field population (file formats, structured API
responses, explicit `loom` SDK input) belongs in core; fuzzy mapping (a
free-text "producer" to an SPDX `Person`/`Organization`) stays with the
`sbom-enrich` Skill.

Open:

- [ ] **#7 `loom` SDK**: dataset provenance and training-properties capture.
  See the [`loom` SDK](#loom-sdk-code-model-dataset-annotation) section and
  [loom-sdk-expansion.md](loom-sdk-expansion.md).
- [x] **Git LFS pointers**, built for 0.22.0: one detector; a checkout
  pointer is listed by its `oid`, one `WARNING:` per SBOM. See
  [git-lfs-pointers.md](../implementation/git-lfs-pointers.md). Open
  follow-ups (ceiling flags, LFS fetch) are in [known-bugs.md](known-bugs.md).
- [ ] **Record a Git URL target's commit as a `pkg:git` identifier** (decided
  2026-10-23) and **one target resolver with Package-URL targets** (`pkg:git`,
  `github`, `bitbucket`, `huggingface`, `pypi`; later `conda`, `mlflow`): see
  [target-resolution-and-purl.md](target-resolution-and-purl.md).
- [ ] **Support-tier gaps past their target** (2026-10-19, missed): a Hub
  model's file hash, dataset provenance and statistics from the Hub, tier 2
  beyond keeping it working. See
  [support-tiers-and-demo-scope.md](support-tiers-and-demo-scope.md).
- [ ] **A `contentIdentifier` (gitoid)** beside the PURLs of the identifiers
  item below.

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
- [ ] **External work to review**: Red Hat AI system card, OASIS Data Provenance
  Standard (provenance taxonomy redesign; also data provenance annotation beside
  the SBOM), ETSI TR 104 180 data quality metrics; research notes from issues
  ([#46](https://github.com/bact/pitloom/issues/46),
  [#48](https://github.com/bact/pitloom/issues/48),
  [#53](https://github.com/bact/pitloom/issues/53),
  [#55](https://github.com/bact/pitloom/issues/55),
  [#129](https://github.com/bact/pitloom/issues/129)). See
  [external-references-to-review.md](external-references-to-review.md).
- [ ] **ML framework and `transformers` use from the code**
  ([#66](https://github.com/bact/pitloom/issues/66),
  [#68](https://github.com/bact/pitloom/issues/68); Qwen
  [#65](https://github.com/bact/pitloom/issues/65)): infer the framework from
  dependencies or imports and a Hub model from `from_pretrained("org/name")`;
  today `--scan-model-usage` matches model file names only. Needs a design note.
- Background research: [metadata-sources.md](metadata-sources.md) (how other
  tools read Python metadata), [sbom-enrichment.md](sbom-enrichment.md),
  [architecture-overview.md](architecture-overview.md).

## To design

Questions that need a decision before code. Nothing below is decided
unless the linked doc says so.

- [ ] **Generation gaps, sorted into extraction and recording gaps**: can we
  extract (or resolve a conflict about) a minimum element, and can we record it
  in the format? The second needs a way to record it that the format does not
  provide (a stated workaround, a Pitloom `Annotation` taxonomy, an SPDX
  extension, a proposal). Tried: none beyond the workaround. See
  [generation-gaps-extraction-and-recording.md](generation-gaps-extraction-and-recording.md),
  issue [#110](https://github.com/bact/pitloom/issues/110).
- [ ] **Hugging Face Spaces**: a Space is an application with no
  `pyproject.toml`, so `loom project` fetches it and finds no project; read the
  README front matter, `requirements.txt` and the Hub's `models` list instead,
  and the LFS pointer's `oid` for model files (built). See
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
- [ ] **Adopt `licenseid` 0.7.0** (compounds, prose and trove names; delete about 250
  lines of Pitloom's own parsing; Pitloom 0.22.0). Data and plan: see
  [licenseid-0-7-adoption.md](licenseid-0-7-adoption.md).
- [ ] **Licence resolution provenance** (T14: one `license` entry with a
  `Resolution-n`/`Expansion-n` per operand, one `Tool` list, `License-List`,
  `Reason:` for an unread SPDX field; after the adoption). See
  [licence-resolution-provenance.md](licence-resolution-provenance.md).
- [ ] **Provenance and enrichment vocabulary** (Method vs Role, source and role
  taxonomy; parked draft; includes renaming the fragment `role` and
  `DatasetReference.role`, whose names are provisional). See
  [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md),
  [docs/metadata-provenance.md](../../docs/metadata-provenance.md). Issues
  [#154](https://github.com/bact/pitloom/issues/154);
  [#110](https://github.com/bact/pitloom/issues/110) (the `Annotation` schema as
  an SPDX 3 extension).
- [ ] **Dataset splits**: read Croissant `cr:Split` record sets; record each
  stated split as a `DatasetPackage` under the whole one (`contains`); then
  raise a part-and-intended-use question with SPDX. Never link a model to a
  split no source states. See [dataset-splits.md](dataset-splits.md).
- [ ] **AI model id stability** beyond what registry v3 built (the other
  AIPackage lookups gated by sha256). See
  [ai-model-id-stability.md](ai-model-id-stability.md).
- [ ] **Archive member names**: name-independent `--allow-build`
  extraction, `orig_filename`, tar links in sdists. See
  [archive-member-followups.md](archive-member-followups.md).
- [ ] **Format-neutral representation** for a second output format (CycloneDX,
  AIDOC); mappings kept as data, not code (CodeMeta crosswalk,
  [#52](https://github.com/bact/pitloom/issues/52)). See
  [format-neutral-representation.md](format-neutral-representation.md).
- [ ] **Fragments**: signing and SHA-256 enforcement, SDK ergonomics,
  element-level traceability, compliance/interop; reusing a project's own
  earlier SBOM ([#41](https://github.com/bact/pitloom/issues/41)); configurable
  merge precedence ([#150](https://github.com/bact/pitloom/issues/150)). See
  [open-items.md](sbom-fragments/open-items.md),
  [sbom-fragments/README.md](sbom-fragments/README.md),
  [docs/fragments.md](../../docs/fragments.md).
- [ ] **Forge APIs and private repositories** (tokens, `ssh://`, forge archive
  tarballs, forge licence and VCS provenance). Git URLs are built (0.21.0). See
  [remote-source-ingestion.md](remote-source-ingestion.md).
- [ ] **PyPI package ingestion** (`loom pypi <name>[==version]`): resolve a release
  through the JSON API, take its sdist or wheel, verify the digest, build the
  SBOM; first consumer Lumina. See
  [remote-source-ingestion.md](remote-source-ingestion.md#pypi-package-ingestion-loom-pypi-nameversion).
- [ ] **VEX output format** (CSAF v2.0 vs OpenVEX), after the OSV lookup.
  See [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md#relationship-to-csafvex).
- [ ] **Author strings: NLP / named-entity recognition** (candidate): span
  splitting and Person vs Organization typing; today a warning, no guess. A list
  of known organisations ([#170](https://github.com/bact/pitloom/issues/170)) is
  one candidate. See
  [author-entity-recognition.md](author-entity-recognition.md).
- [ ] **SPDX 3.1 output beside 3.0.1**
  ([#147](https://github.com/bact/pitloom/issues/147)): pick the version by CLI,
  config or Skill keyword and validate against its schema; today `specVersion`
  is fixed at `3.0.1`. See [architecture-overview.md](architecture-overview.md).
- [ ] **Package-URL as `spdxId`**
  ([#30](https://github.com/bact/pitloom/issues/30), needs decision): where a
  PURL is unique, it could dedup fragment merges; SPDX spec issue 1379.
- [ ] **CSVW round trip for missing facts**
  ([#81](https://github.com/bact/pitloom/issues/81), needs decision): list what
  a conformance check finds missing as CSVW, a person fills it, Pitloom reads it
  back as a fragment.

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
- [ ] **Canonical output**: same bytes and ids for the same input, same shape
  for the same value in every format and surface. See
  [canonical-output-followups.md](canonical-output-followups.md); a separate
  serialiser library ([#51](https://github.com/bact/pitloom/issues/51)) needs a
  decision. Decided 2026-10-08: RFC 8785 key order everywhere (pretty =
  canonical plus indentation), LF in text values; next, stable `CreationInfo`
  IRIs.
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

- **G7 dataset creator**: Pitloom writes a dataset's creator as `publishedBy`;
  the checker's `DP-006.1` reads `originatedBy`, so the rule stays missing.
  Decide whether a Hub dataset owner is an originator (never guessed), and
  whether the checker should also accept `publishedBy`. See
  [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md).
- **File discovery**: setuptools gives absolute `physical_path` for a project
  dir named in another letter case (macOS, Windows; #257, in
  [known-bugs-p3.md](known-bugs-p3.md)); four #215 follow-ups; scikit-build-core
  checked only through `--allow-build`
  ([#61](https://github.com/bact/pitloom/issues/61)). See
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
- **AI model scanning**: `env` scans no models; no warning when a file's
  extension disagrees with its content
  ([#103](https://github.com/bact/pitloom/issues/103)). See
  [cli-shared-options-ignored.md](cli-shared-options-ignored.md#still-open),
  [ai-model-scanning.md](../implementation/ai-model-scanning.md).
- **Fragments after the merge fixes**: see
  [open-items.md](sbom-fragments/open-items.md#left-after-the-fragment-merge-fixes).
- **`loom env`**: an unmet requirement (`installed_version: "?"`) loses its
  `dependsOn` edge silently; two installs sharing one pipdeptree `key`
  collide (#236 review). See [known-bugs-p3.md](known-bugs-p3.md),
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
- **Testing and CI**: see [testing-ci-followups.md](testing-ci-followups.md),
  including the CI workflow hardening from the 0.20.0 release review
  ([section](testing-ci-followups.md#ci-workflow-review-0200)).
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
- [ ] **IETF SCITT integration**: submit an SBOM as a signed statement (`loom
  scitt submit`), keep the receipt, verify dependencies' receipts; model
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
