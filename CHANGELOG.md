---
Last-Modified: 2026-08-10
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
- Commit history: <https://github.com/bact/pitloom/compare/v0.11.0...v0.12.0>

## [Unreleased]

### Added

- Initial support of SKILL.md and Claude Code plugin ([#96])
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
  scanned even when `project.license` already declares a value, and both
  sides are compared after SPDX-expression normalization (new
  [`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license)
  dependency), so casing or equivalent-but-differently-written expressions
  aren't misreported as conflicts. On a genuine disagreement, both
  `hasDeclaredLicense` and `hasConcludedLicense` are recorded alongside a
  new `provenance/conflict/1` Annotation; the mechanism is generic across
  fields, not license-specific. ([#121])

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
