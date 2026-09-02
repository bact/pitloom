---
Last-Modified: 2026-09-03
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable MD024 -->

# Changelog

All notable changes to this project are documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

- Full release notes: <https://github.com/bact/pitloom/releases>
- Commit history: <https://github.com/bact/pitloom/compare/v0.16.4...v0.17.0>

## [Unreleased]

### Added

- Add PDM-backend and Flit-core metadata extraction and wheel file
  discovery
- Add Poetry backend wheel file discovery and lock parsing ([#198])
- Add `pitloom fragment validate` CLI command, using `spdx3-validate`'s
  library API; new `pitloom[validate]` optional extra ([#200])
- Add `--debug`/`--no-debug` flags / `PITLOOM_DEBUG` env var to surface
  `DEBUG:`-level diagnostics on stderr, consistently across every
  subcommand ([#201])
- Add `pitloom verify-wheel`/`validate-wheel` CLI commands and matching
  `embed-wheel --verify`/`--validate` flags ([#202])
- Add SBOM name/version cross-check to `verify-wheel`, with
  `--fail-on-mismatch` to make a mismatch fatal ([#204])
- `embed-wheel --sbom` now cross-checks the SBOM's name/version against
  the wheel's METADATA before writing; aborts on mismatch unless
  `--allow-mismatch` ([#204])

### Fixed

- `read_project()` no longer silently returns empty (nameless,
  versionless) metadata for a project whose `pyproject.toml` declares
  only `[build-system]` (a custom/legacy build backend, no `[project]`
  or `[tool.poetry]`) when `setup.cfg`/`setup.py` hold the real
  metadata -- now falls back to setuptools extraction, with a
  `WARNING:`
- `[tool.setuptools.dynamic] version = {attr = "..."}`/`{file = "..."}`
  now resolves even when a `[project]` table is present (previously
  silently left `version=None`)

### Changed

- Promote 18 log messages from `DEBUG:` to `WARNING:` (shown by
  default, not just under `--debug`) where a failure silently drops
  data from the generated SBOM/AIBOM: Hugging Face Hub fetch failures
  (model card, `model_info()`, license files), PyTorch/PT2
  pickle/graph/metadata parse failures, fastText args/labels reads,
  README enrichment frontmatter, sdist `pyproject.toml` fallback
  parsing, and `pitloom.loom` caller-provenance detection. Each promoted
  message names the affected SBOM field(s) via one grep-able shape,
  `... | Field(s) affected (skipped|degraded): <name>` ([#201])

[#198]: https://github.com/bact/pitloom/pull/198
[#200]: https://github.com/bact/pitloom/pull/200
[#201]: https://github.com/bact/pitloom/pull/201
[#202]: https://github.com/bact/pitloom/pull/202
[#204]: https://github.com/bact/pitloom/pull/204

## [0.17.0] - 2026-08-30

### Added

- Serialize every Annotation's `statement` via RFC 8785 (JSON
  Canonicalization Scheme) ([#189])
- Cap artifact-metadata `Annotation.statement` size via
  `[tool.pitloom.provenance] max-source-metadata-bytes` /
  `--max-source-metadata-bytes` ([#189])
- Setuptools wheel file discovery from static `pyproject.toml`/`setup.cfg`
  config (`packages.find`, `package_data`, `include_package_data`/
  `MANIFEST.in`) ([#196])
- `setuptools>=70` is now a hard runtime dependency (needed to resolve the
  above regardless of the scanned project's own build backend) ([#196])

### Changed

- Split `get_wheel_files()` into a per-backend discovery module + registry,
  ready for Poetry/PDM/Flit-core/`uv_build` ([#196])
- **Setuptools projects**: SBOM element ids shift vs. pre-upgrade output --
  regenerate the base SBOM before merging fragments ([#196])

### Fixed

- Only declare the `simpleLicensing` profile when a real license claim was
  made ([#190])
- Setuptools `packages.find where=` layouts no longer report wrong
  distribution paths (e.g. `lib/pkg/...` instead of `pkg/...`) ([#196])
- Unhandled build backends now log a warning instead of silently falling
  back to a possibly-inaccurate Hatchling-based file list ([#196])
- `detect_build_backend()` now falls back for a malformed `pyproject.toml`,
  not just an absent one ([#196])
- Fix crash reading `pyproject.toml` with both an SPDX `license` string and
  legacy classifiers ([#196])
- `merge_fragments()` now warns on, and fails the merge for, a dangling
  reference left after merging (e.g. a stale-`doc_uuid` fragment) instead of
  silently producing a broken SBOM ([#196])
- `INFO:`-level log messages (e.g. Hatchling build hook status) now actually
  reach stderr ([#196])
- `embed-wheel`/`wheel --embed` INFO: lines now go to stderr, not stdout
  ([#196])
- GitHub Action now surfaces loom's INFO:/WARNING:/ERROR: lines as
  ::notice::/::warning::/::error:: annotations, including any continuation
  lines of a multi-line message ([#196])
- `generate()`'s smart entrypoint now recognizes `.pt2` (PyTorch
  PT2/ExecuTorch) and routes it to model-SBOM generation instead of
  falling through to project-SBOM ([#196])

[#189]: https://github.com/bact/pitloom/pull/189
[#190]: https://github.com/bact/pitloom/pull/190
[#196]: https://github.com/bact/pitloom/pull/196

## [0.16.4] - 2026-08-21

### Fixed

- Deduplicate dependencies ([#184])

[#184]:  https://github.com/bact/pitloom/pull/184

## [0.16.3] - 2026-08-21

### Added

- Auto-sync Loom ID registry after SBOM generation ([#178])
- Atheris fuzz harnesses for license expression normalization and
  GGUF model header parsing. See `fuzz/README.md` ([#179])
- `pytest` now fails on any runtime warning
  (`filterwarnings = ["error"]`, plus `--strict-markers`/`--strict-config`) --
  OpenSSF Best Practices `warnings_strict` ([#179])
- Add Sigstore and provenance attestation to GitHub release ([#180])

### Fixed

- Test coverage near 100% ([#176], [#177])
- `normalize_license_expression` no longer raises `IndexError` on an
  unbalanced `)` (e.g. a lone `")"`) ([#179])
- Dependency metadata reads (`Summary`, `Home-page`, `Author`, license,
  etc.) no longer trip a `DeprecationWarning` on Python 3.14 ([#179])
- Bump `licenseid` floor to `>=0.3.7`, fixing an upstream sqlite3
  connection leak ([#179])

[#176]: https://github.com/bact/pitloom/pull/176
[#177]: https://github.com/bact/pitloom/pull/177
[#178]: https://github.com/bact/pitloom/pull/178
[#179]: https://github.com/bact/pitloom/pull/179
[#180]: https://github.com/bact/pitloom/pull/180

## [0.16.2] - 2026-08-19

### Added

- `loom project`/`loom model`/`loom env`/`loom wheel`/`loom embed-wheel` print
  `PITLOOM_SBOM_OUTPUT_PATH=<path>` to stdout after writing an SBOM ([#171])
- The PyPI release workflow attaches the standalone SBOM as a GitHub Release
  asset, generated via the project's own GitHub Action ([#172], [#174])

### Fixed

- GitHub Action now defers to `loom`'s own default-naming logic
  (`packagename-version.spdx3.json`) ([#171])
- `loom embed-wheel`'s Build SBOM now includes content-type and file-header
  data for each file, while still preserving the wheel's own file records
  ([#172], [#174])
- `loom embed-wheel`'s Merkle root is now computed from the wheel's own file
  hashes instead of a project-directory rescan ([#172])

[#171]: https://github.com/bact/pitloom/pull/171
[#172]: https://github.com/bact/pitloom/pull/172
[#174]: https://github.com/bact/pitloom/pull/174

## [0.16.1] - 2026-08-18

### Fixed

- Split an author list packed into a single email's display name
  (e.g. `"A, B, C" <shared@example.com>`) into individual Persons ([#169])

[#169]: https://github.com/bact/pitloom/pull/169

## [0.16.0] - 2026-08-18

### Added

- Split a string containing a list of authors into discrete agents
  and generate external refs for a group of authors ("Others") ([#151])
- Scan the resolved dependency tree for known CVEs with `pip-audit` in CI,
  blocking on findings ([#165], [#166])

### Changed

- Reorganize configuration parsing architecture: move INI-to-dictionary adapter
  logic entirely into `setuptools.py` ([#152])
- Restructure CLI architecture: decentralize parser configuration into
  individual command modules ([#153])
- Split monolithic test files into domain-scoped folders
  (`cli/`, `core/`, `extract/`, `assemble/`) with `conftest.py`
  ([#153], [#155], [#161])
- Raised test coverage to 90% ([#155], [#162], [#164])
- Avoid loading full file to memory during AI model and sdist extraction,
  reducing peak memory usage by over 97% ([#156])
- Centralize SPDX relationship boilerplate across the codebase ([#157])
- Optimize pytest-xdist parallelization with `loadscope` to prevent
  redundant fixture evaluations ([#158])
- Optimize test workflow by caching the `licenseid` database ([#159])
- `loom generate` now requires `-o`/`--output` and fails with a clear
  error if it's omitted, instead of guessing a filename. ([#160])

### Fixed

- Map legacy `fragments` key to `[tool.pitloom.fragment]` nested table
  in `setup.cfg` to resolve crash ([#152])
- Implement modern sub-section parsing (`provenance`, `content-type`, `fragment`)
  in `setup.cfg`, bringing it to feature parity with `pyproject.toml` ([#152])
- Enforce strict type-checking across all boolean fields, preventing string
  values from silently evaluating to `True` ([#152])
- Remove `split_main.py` and `src/pitloom/__main__.py.bak`, leftover
  files from the CLI restructuring ([#153]) that were accidentally
  committed -- the `.bak` file was shipping inside the built wheel.
- `loom generate` no longer silently writes a fixed `sbom.spdx3.json`
  to the current directory when `-o` is omitted. ([#160])
- Reduce function complexity ([#163])
- `_fickling_get_top_class` no longer folds an AST-walk failure into the
  same debug-level "failed to parse" message as an actual pickle-parse
  failure -- it now logs a distinct warning ([#164])

[#151]: https://github.com/bact/pitloom/pull/151
[#152]: https://github.com/bact/pitloom/pull/152
[#153]: https://github.com/bact/pitloom/pull/153
[#155]: https://github.com/bact/pitloom/pull/155
[#156]: https://github.com/bact/pitloom/pull/156
[#157]: https://github.com/bact/pitloom/pull/157
[#158]: https://github.com/bact/pitloom/pull/158
[#159]: https://github.com/bact/pitloom/pull/159
[#160]: https://github.com/bact/pitloom/pull/160
[#161]: https://github.com/bact/pitloom/pull/161
[#162]: https://github.com/bact/pitloom/pull/162
[#163]: https://github.com/bact/pitloom/pull/163
[#164]: https://github.com/bact/pitloom/pull/164
[#165]: https://github.com/bact/pitloom/pull/165
[#166]: https://github.com/bact/pitloom/pull/166

## [0.15.0] - 2026-08-15

This release introduces backend-agnostic support for embedding SBOM
directly into Python wheels.

### Added

- `loom wheel --embed`, `loom embed-wheel`, and GitHub Action support for
  embedding SPDX 3 SBOMs into Python wheels ([#148])

### Changed

- Reorganize project documentation ([#146])

### Fixed

- SBOM `created` now honours `SOURCE_DATE_EPOCH` (same priority as the
  Hatchling build hook's `builtTime`) -- previously only the embedded
  wheel's ZIP entry timestamp respected it, so a wheel embedded under a
  reproducible-build environment still carried a different SBOM `created`
  value on every rebuild, even with `SOURCE_DATE_EPOCH` set ([#148])

[#146]: https://github.com/bact/pitloom/pull/146
[#148]: https://github.com/bact/pitloom/pull/148

## [0.14.1] 2026-08-13

### Fixed

- `sbomAuthorSupplied` is now consistently a provenance `role`, not
  conflated with `method` ([#143])
- Crash generating an AI model's base-model lineage when `base_model` is
  set but `base_model_relation` is not (e.g. a model card's frontmatter
  has `base_model` but the Hugging Face Hub API never supplied a
  computed relation tag) ([#144])

[#143]: https://github.com/bact/pitloom/pull/143
[#144]: https://github.com/bact/pitloom/pull/144

## [0.14.0] - 2026-08-13

This release introduces per-file header and content-type extraction.
It also fixes format of error and warning CLI outputs for consistency
and grep-ability.

### Added

- Raise RuntimeError if Hatchling version is lower than 1.29.0 ([#136])
- Per-file metadata extraction from SPDX File Tags and header, via
  `[tool.pitloom] extract-file-header` (on by default) ([#138])
- Per-file content-type detection, independent of header scanning, via
  `[tool.pitloom.content-type] enabled` (off by default); `method`
  chooses the detector (`"auto"`/`"magika"`/`"extension"`, matching
  `--content-type-method` CLI flag / `content-type-method` Action
  input), erroring immediately if `"magika"` is requested but the
  package isn't installed ([#138], [#140])
- Config-only, SBOM author-supplied deterministic content-type overrides
  (`[[tool.pitloom.content-type.override]]`): a glob pattern -> MIME-type
  table that pre-empts detection for matching files ([#140])
- Minimum elements-oriented SBOM enrichment ([#139])
- New [Configuration](docs/configuration.md) reference page: every
  `[tool.pitloom]` setting, its default, and its CLI/Action/API mapping
  in one place ([#140])
- Every `[tool.pitloom]` setting is validated at config-read time,
  including an old or misplaced key (e.g. an `ids`/`fragments`/
  `file-headers` table directly under `[tool.pitloom]`), which raises a
  clear error rather than being silently ignored; `content_type_method`
  passed explicitly to the Python API is validated the same way as the
  `pyproject.toml`/CLI paths ([#140])

### Fixed

- `[tool.pitloom] offline` is now honored by `loom generate`,
  `loom wheel`, `loom model`, and `loom env` -- previously only `loom project`
  deferred to it ([#142])
- CLI errors and internal warnings share one grep-able prefix again:
  `ERROR:`/`WARNING:` (uppercase) ([#142])

[#136]: https://github.com/bact/pitloom/pull/136
[#138]: https://github.com/bact/pitloom/pull/138
[#139]: https://github.com/bact/pitloom/pull/139
[#140]: https://github.com/bact/pitloom/pull/140
[#142]: https://github.com/bact/pitloom/pull/142

## [0.13.3] - 2026-08-11

A cleanup release.

### Added

- Pitloom's own hash and Package URL with version number to the generated SBOM
  ([#132])
- AI skills: Add more trigger words and known limitations ([#134])

### Fixed

- Use POSIX path in provenance comment too ([#133])

[#132]: https://github.com/bact/pitloom/pull/132
[#133]: https://github.com/bact/pitloom/pull/133
[#134]: https://github.com/bact/pitloom/pull/134

## [0.13.2] - 2026-08-11

This release fixes bugs and offers few fallbacks to improve SBOM completeness.

### Added

- Copyright extraction from installed License-File ([#131])
- Supplier information from installed Author/Maintainer metadata ([#131])
- PyPI API fallback for supplier/license/integrity-hash when local install
  doesn't have them ([#131])
- NOASSERTION fallback for copyright and license when genuinely nothing is
  found anywhere ([#131])
- Package URL fallback (name-only) for unresolved versions ([#131])

### Fixed

- Dependency name and version parsing (multi-clause specifiers) ([#131])
- Silently-discarded `hasConcludedLicense` relationship ([#131])
- Dropping multi-address Maintainer-email fields ([#131])
- Merkle root/`doc_uuid` platform-dependent on Windows (backslash
  `distribution_path` from Hatchling's `os.path.join`) ([#131])

[#131]: https://github.com/bact/pitloom/pull/131

## [0.13.1] - 2026-08-11

### Changed

- Use default SBOM filename as suggested by [SBOM Everywhere][sbom-naming]
  ([#130])

[sbom-naming]: https://sbom-catalog.openssf.org/sbom-naming.html
[#130]: https://github.com/bact/pitloom/pull/130

## [0.13.0] - 2026-08-11

This release introduces a redesigned CLI and API—a breaking change requiring
updates to existing code and scripts. It also adds AI-model metadata enrichment
and provenance tracking via SPDX 3's `Annotation`.

Finally, usage surfaces are expanded with a new GitHub Action, AI-agent Skills,
and a Claude Code plugin.

### Added

- Initial support of SKILL.md and Claude Code plugin: `sbom-generate`,
  `sbom-enrich`, and `sbom-validate` Skills ([#96], [#123])
- Redesign CLI and Python API around input artifacts
  (project, wheel, model, env, generate) while maintaining CISA SBOM Types
  compliance in output graph ([#96], [#114])
- Native .tar.gz and .zip sdist metadata extraction support ([#114])
- Native-first provenance:
  - `hasConcludedLicense` vs. `hasDeclaredLicense` separation
    for Pitloom-detected vs. SBOM author-asserted licenses. ([#105])
  - `ExternalIdentifier` (DOI) and `ExternalRef`
    (arXiv paper IDs, model page URLs) on `ai_AIPackage`. ([#106])
  - `Agent` and `publishedBy` relationship for dataset creators
    on `dataset_DatasetPackage`. ([#107])
  - Fragment document origin traceability: populate `SpdxDocument.import_`
    with `ExternalMap` entries for merged fragments. ([#108])
  - `descendantOf` `Relationship` and stub `ai_AIPackage`
    for AI base-model lineage. ([#109])
- Record metadata provenance as SPDX 3 Core `Annotation` elements alongside
  the `comment` form, controlled by `[tool.pitloom.provenance] format`. ([#102])
- `[tool.pitloom.provenance] detail` (`minimal` default / `full`) to limit
  provenance Annotations to fields SPDX can't otherwise express.
- Fragment-unification provenance: record why two elements were merged as a
  `provenance/unification/1` Annotation on the survivor. ([#102])
- Artifact-metadata preservation
  (`[tool.pitloom.provenance] preserve-source-metadata`, `auto` default)
  to embed an AI model's verbatim original metadata
  when it isn't shipped with the distribution. ([#102])
- `pitloom.loom`'s `set_model(hyperparameters=...)` and
  `set_model_hyperparameters()` now record exact per-key provenance for
  each hyperparameter, matching the AI-model extractors. ([#113])
- Declared-vs-detected license conflict detection: the project directory
  (`CITATION.cff`, `codemeta.json`, `LICENSE` files) is now independently
  scanned even when a license is already declared, and both sides are
  compared after license expression normalization.
  On a genuine disagreement, both `hasDeclaredLicense` and
  `hasConcludedLicense` are recorded alongside a new `provenance/conflict/1`
  Annotation. ([#121])
- AI-model metadata enrichment is available from every usage surface
  (CLI, API, Hatchling hook, GitHub Action), opt-in via config. ([#124])
- `sbom-enrich` Skill can ask the SBOM author for missing info in
  interactive sessions, tracked with a new `sbomAuthorSupplied`
  provenance role. ([#125])

### Changed

- Dict-valued AI-model metadata (`properties`, `hyperparameters`) now records
  exact per-key provenance instead of one shared note per dict. ([#102])
- Raised the minimum `mypy` version to 2.3.0. ([#118])

### Fixed

- `loom generate` (the smart auto-detect entrypoint) now honours the
  target project's `[tool.pitloom]` config -- including
  `[tool.pitloom.provenance]` -- instead of silently using defaults. ([#116])

### Security

- Sanitize untrusted text (an AI model's filename, and any binary-format
  metadata key) before it's embedded in a provenance string, so a crafted
  value can no longer inject a fake `Source:`/`Field:` segment and
  misattribute or silently suppress provenance. ([#102])
- Ensures Hugging Face `hf_hub_download()` calls are revision-pinned, and
  hardens environment command invocation in the Deployed SBOM path
  against Bandit-flagged risks. ([#117])

[#96]: https://github.com/bact/pitloom/pull/96
[#102]: https://github.com/bact/pitloom/pull/102
[#105]: https://github.com/bact/pitloom/pull/105
[#106]: https://github.com/bact/pitloom/pull/106
[#107]: https://github.com/bact/pitloom/pull/107
[#108]: https://github.com/bact/pitloom/pull/108
[#109]: https://github.com/bact/pitloom/pull/109
[#113]: https://github.com/bact/pitloom/pull/113
[#114]: https://github.com/bact/pitloom/pull/114
[#116]: https://github.com/bact/pitloom/pull/116
[#117]: https://github.com/bact/pitloom/pull/117
[#118]: https://github.com/bact/pitloom/pull/118
[#121]: https://github.com/bact/pitloom/pull/121
[#123]: https://github.com/bact/pitloom/pull/123
[#124]: https://github.com/bact/pitloom/pull/124
[#125]: https://github.com/bact/pitloom/pull/125

## [0.12.0] - 2026-07-10

### Added

- `use_model` method to `loom.run` to record relationship between an inference
  code and an AI model ([#95])

[#95]: https://github.com/bact/pitloom/pull/95

## [0.11.0] - 2026-07-09

### Added

- Loom ID registry:
  - a stable file/entity -> SPDX ID registry (`loom-ids.json`)
  - `pitloom ids generate` pins ids (with SHA-256 hashes) for files under
    chosen paths and for named entities (`--entity`)
  - `pitloom ids import` harvests ids from an existing SPDX 3 SBOM
  - `pitloom.loom`, the `loom -m` extractor, the Hatchling build hook, and
    `generate_sbom()` all consult the registry, so the same dataset, script,
    or model carries the same `spdxId` everywhere ([#91])
- `loom.run` now records the generating script as a `software_File` (with a
  SHA-256 hash) and emits file-level `generates` relationships: the training
  script generates the model, a preprocessing script generates its output
  datasets. Datasets registered via `add_*_dataset()` gain `verifiedUsing`
  SHA-256 hashes when they exist on disk ([#91])
- `set_model()` gains a `generated` keyword to override the default
  heuristic (a run that declares training datasets gets the script ->
  model `generates` edge; an evaluation-only run does not) ([#91])
- The Hatchling build hook's `builtTime` now honours `SOURCE_DATE_EPOCH`
  (reproducible-builds standard) or a pinned `[tool.pitloom.creation]`
  `creation-datetime`, so rebuilding unchanged sources can produce
  byte-identical SBOMs; falls back to the current UTC time ([#91])
- `add_output_dataset()` gains an `input_datasets` keyword naming exactly
  which `add_input_dataset()` calls it derives from, so one accumulating
  `loom.run` can cover multiple independent preprocessing stages (e.g.
  train/valid/test splits) without their `hasInput` lineage cross-linking
  to each other's raw sources. Omitted (the default), it keeps the
  previous behaviour of deriving from every input declared in the run
  ([#91])

### Changed

- `generates` relationships (training script -> model, proprocessing script ->
  output datasets) and `hasDataFile` relationship (inference script -> model)
  are now `LifecycleScopedRelationship`, scoped `build` and `runtime`
  respectively ([#91])
- `merge_fragments()` now *unifies* fragments instead of concatenating them:
  - elements sharing a registry-issued `spdxId`, or provably identical
    content (SHA-256), or structurally identical `Agent`/`Tool` copies are
    collapsed into one element
  - fragment `SpdxDocument`/`software_Sbom` envelopes are dropped
  - duplicate relationships are removed
  - `profileConformance` gains `ai`/`dataset` when fragments contribute those
    profiles
  - a second `software_Sbom` rooted at the merged `ai_AIPackage` is added
    alongside the main one ([#91])
- The sentimentdemo example pipeline pins stable ids in a new stage 0;
  all four fragments describe a single unified model element ([#91])
- Upgraded `safetensors` dependency requirement to `0.8.0` ([#87])

[#87]: https://github.com/bact/pitloom/issues/87
[#91]: https://github.com/bact/pitloom/pull/91

## [0.10.0] - 2026-07-09

### Changed

- Creators can now be `Person`, `Organization`, `SoftwareAgent`, or `Agent`
  via `--creator-type` / `creator_type` ([#84])
- Consolidated config into `[tool.pitloom]`, `[tool.pitloom.creation]`,
  `[tool.pitloom.fragments]` ([#84])
- SBOM fragments (`loom.run`) now carry their own creation metadata,
  since they're generated separately from the main document ([#84])
- BREAKING CHANGE:
  Renamed the `creation_info` parameter to `creation_metadata` in
  `generate_sbom()` and related APIs ([#84])
- BREAKING CHANGE:
  Supports multiple creators and multiple creation tools ([#86])
  - `CreationMetadata.creator_name`/`creator_email`/`creator_type`/
    `creation_tool` (scalar) are replaced by `creators: list[Creator]`
    and `tools: list[Tool] | None`.
  - CLI `--creator-name`/`--creation-tool` are now repeatable
  - config gains `[[tool.pitloom.creator]]` /
    `[[tool.pitloom.creation-tool]]` array-of-tables (replacing the
    old `[tool.hatch.build.hooks.pitloom]`
    `creator-name`/`creator-email` keys).
  - `setup.cfg` keeps single-creator/-tool support only.
- `generate_sbom()` gains optional `project_metadata`/`pitloom_config`
  keyword arguments so callers that already parsed the project
  (e.g. the CLI) can pass them in and skip re-parsing ([#89])
- BREAKING CHANGE:
  `generate_sbom()`'s keyword arguments are now keyword-only -- excepts
  `project_dir` that remains positional-or-keyword ([#89])

### Fixed

- Pitloom itself is now recorded as a `Tool` (`createdUsing`) instead of a
  `Person` (`createdBy`) in generated SBOMs ([#84])
- `generate_sbom()` (and the CLI) now supports projects that use only
  `setup.cfg`/`setup.py` with no `pyproject.toml` -- previously raised
  `FileNotFoundError` unconditionally ([#89])

[#84]: https://github.com/bact/pitloom/pull/84
[#86]: https://github.com/bact/pitloom/pull/86
[#89]: https://github.com/bact/pitloom/pull/89

## [0.9.0] - 2026-07-06

### Added

- Hatchling build hook now reads project metadata directly from the build
  backend's own resolved values, so dynamically-computed metadata
  (e.g. a version from `hatch-vcs`, dependencies from `hatch-requirements-txt`)
  is captured correctly; the hook now only runs for wheel builds, not sdists
  ([#82])
- Every file listed in a generated SBOM now includes an SHA-256 integrity
  hash ([#82])
- The main project package in a generated SBOM now includes a PyPI
  Package-URL (PURL), matching what dependencies already had ([#82])
- A GitHub Action so any Python project can generate an SBOM in CI with a
  single step, regardless of build backend ([#82])
- Two AI-agent Skills (`sbom`, `enrich`) to generate an SBOM on request,
  and optionally enrich it with information inferred from project docs --
  with clear provenance marking so inferred data is never confused with
  extracted data ([#82])
- A Claude Code plugin (`/plugin marketplace add bact/pitloom` then
  `/plugin install pitloom@pitloom`) providing `/pitloom:sbom` and
  `/pitloom:enrich` to generate and enrich SBOMs directly from Claude
  Code ([#82])

### Fixed

- Handle None case of spdxId ([#83])

[#82]: https://github.com/bact/pitloom/pull/82
[#83]: https://github.com/bact/pitloom/pull/83

## [0.8.0] - 2026-05-29

### Added

- An end-to-end example of how to use `loom.run` to create SBOM fragments
  that document relationship between training data and model
  (see: `examples/sentimentdemo-aibom/`) ([#80])

### Changed

- Rename context manager method from `loom.shoot` to `loom.run`;
  make it consistent with MLflow ([#80])

### Fixed

- Fix wrong fickling import in PyTorch extractor ([#80])

[#80]: https://github.com/bact/pitloom/pull/80

## [0.7.1] - 2026-05-14

### Changed

- Record license ID using its canonical version ([#78])

[#78]: https://github.com/bact/pitloom/pull/78

## [0.7.0] - 2026-05-12

### Added

- `-m` / `--aimodel` command-line option now works with Hugging Face Hub URL
  ([#71])

### Fixed

- Export license information of an AI model
  (was previously extracted but not being exported) ([#72])

[#71]: https://github.com/bact/pitloom/pull/71
[#72]: https://github.com/bact/pitloom/pull/72

## [0.6.1] - 2026-05-07

### Added

- `-m` / `--aimodel` command-line option to generate an SBOM for standalone
  AI model (may not be part of a Python project) ([#69])

[#69]: https://github.com/bact/pitloom/pull/69

## [0.6.0] - 2026-05-07

### Added

- `[tool.poetry]` support ([#67])
  - Reads project metadata from `[tool.poetry]` in `pyproject.toml`
  - Reads runtime dependencies from `[tool.poetry.dependencies]`;
    `[tool.poetry.group.*]` dev/deploy dependency groups are excluded
  - Converts Poetry version specifiers (`^`, `~`, bare exact versions)
    to PEP 440 format
  - `read_pyproject()` falls back to `[tool.poetry]` when `[project]`
    is absent; merges both when both are present (`[project]` wins)

[#67]: https://github.com/bact/pitloom/pull/67

## [0.5.1] - 2026-05-06

### Changed

- Fallback gracefully if `[project]` is not found in `pyproject.toml` ([#63])

[#63]: https://github.com/bact/pitloom/pull/63

## [0.5.0] - 2026-04-29

### Added

- Support projects build with setuptools ([#59])
- Detect SPDX License ID from license text ([#60])

[#59]: https://github.com/bact/pitloom/pull/59
[#60]: https://github.com/bact/pitloom/pull/60

## [0.4.1] - 2026-04-02

### Changed

- Warns if the AI extraction library is not installed ([#50])

[#50]: https://github.com/bact/pitloom/pull/50

## [0.4.0] - 2026-04-02

### Added

- File and directory information in SBOM, with "contains" relationship
  ([#42])
- Human-readable description to Relationship ([#44])
- Creation information config to pyproject.toml and command line ([#47])

[#42]: https://github.com/bact/pitloom/pull/42
[#44]: https://github.com/bact/pitloom/pull/44
[#47]: https://github.com/bact/pitloom/pull/47

## [0.3.0] - 2026-04-01

### Added

- AI model metadata extraction from fastText, HDF5, Keras, NumPy,
  PyTorch, PyTorch PT2 ([#33], [#36])
- Dogfooding: Pitloom Hatchling plugin in Pitloom's pyproject.toml ([#39])
- Dataset metadata model and extraction (experiment) ([#40])

### Changed

- JSON output is now sorted ([#29]), implements:
  - [RFC 8785 JSON Canonicalization Scheme (JCS)][jcs]
  - [SPDX 3 canonical serialization][spdx3-canon]
  - Ordering as proposed in [spdx/spdx-spec issue #1339][spdx-spec-1339]:
    - 1: CreationInfo
    - 2: SpdxDocument
    - 3: Bom
    - 4: software_Sbom
    - 5: the rest of the SBOM

[spdx3-canon]: https://spdx.github.io/spdx-spec/v3.0.1/serializations/#canonical-serialization
[jcs]: https://www.rfc-editor.org/rfc/rfc8785
[spdx-spec-1339]: https://github.com/spdx/spdx-spec/issues/1339
[#29]: https://github.com/bact/pitloom/pull/29
[#33]: https://github.com/bact/pitloom/pull/33
[#36]: https://github.com/bact/pitloom/pull/36
[#39]: https://github.com/bact/pitloom/pull/39
[#40]: https://github.com/bact/pitloom/pull/40

## [0.2.0] - 2026-03-27

### Changed

- spdxId is now using deterministic UUID ([#27])
  - A UUIDv5 generated using seeds from the project name, project version,
    dependency list, and the Merkle root of all files included in the wheel.

[#27]: https://github.com/bact/pitloom/pull/27

## [0.1.0] - 2026-03-27

First public pre-release.

Originally titled "Loom," the project was renamed Pitloom before
release because "Loom" and "Pyloom" were unavailable on PyPI.

### Added

- Minimum SBOM generation ([#9])
- SBOM fragments integration ([#10])
- AI model metadata extraction from GGUF, ONNX, and Safetensors ([#11])
- Add Hatch plugin (hatchling.plugin.hookimpl) ([#17])

[#9]: https://github.com/bact/pitloom/pull/9
[#10]: https://github.com/bact/pitloom/pull/10
[#11]: https://github.com/bact/pitloom/pull/11
[#17]: https://github.com/bact/pitloom/pull/17

---

[0.17.0]: https://github.com/bact/pitloom/compare/v0.16.4...v0.17.0
[0.16.4]: https://github.com/bact/pitloom/compare/v0.16.3...v0.16.4
[0.16.3]: https://github.com/bact/pitloom/compare/v0.16.2...v0.16.3
[0.16.2]: https://github.com/bact/pitloom/compare/v0.16.1...v0.16.2
[0.16.1]: https://github.com/bact/pitloom/compare/v0.16.0...v0.16.1
[0.16.0]: https://github.com/bact/pitloom/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/bact/pitloom/compare/v0.14.1...v0.15.0
[0.14.1]: https://github.com/bact/pitloom/compare/v0.14.0...v0.14.1
[0.14.0]: https://github.com/bact/pitloom/compare/v0.13.3...v0.14.0
[0.13.3]: https://github.com/bact/pitloom/compare/v0.13.2...v0.13.3
[0.13.2]: https://github.com/bact/pitloom/compare/v0.13.1...v0.13.2
[0.13.1]: https://github.com/bact/pitloom/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/bact/pitloom/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/bact/pitloom/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/bact/pitloom/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/bact/pitloom/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/bact/pitloom/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/bact/pitloom/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/bact/pitloom/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/bact/pitloom/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/bact/pitloom/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/bact/pitloom/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/bact/pitloom/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/bact/pitloom/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/bact/pitloom/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/bact/pitloom/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bact/pitloom/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bact/pitloom/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bact/pitloom/releases/tag/v0.1.0
