---
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable MD024 -->

# Changelog archive

Releases before 0.19.0, condensed. See also [CHANGELOG.md](CHANGELOG.md) for
newer releases. This file is not edited for new changes.

- Full release notes: <https://github.com/bact/pitloom/releases>

## [0.18.1] - 2026-09-18

### Added

- `FragmentConfig` for `[tool.pitloom.fragment]` entries (role, description,
  required, sha256, link-to-main; plain path strings still work) and
  `loom fragment list` ([#217])

### Changed

- `fasttext-community` replaces `fasttext` on all supported Python versions
  ([#220], [#222])
- Skills: broader trigger coverage (CISA/NTIA/G7, wheel-embedded SBOM presence
  vs. validity); ID registry id-stability documented ([#223])

### Fixed

- Hatchling build hook works with Hatchling >=1.32.0 incl. the 1.32.3+
  `BuildHookInterface` arity change; floor lowered to the real minimum
  `>=1.29.0` ([#222], [#223])

## [0.18.0] - 2026-09-16

### Added

- Poetry wheel file discovery and lock parsing ([#198])
- `loom fragment validate`, using `spdx3-validate`'s library API ([#200])
- `--debug`/`--no-debug` / `PITLOOM_DEBUG` to show `DEBUG:` diagnostics ([#201])
- `loom verify-wheel`/`validate-wheel`, `embed-wheel --verify`/`--validate`,
  and an SBOM name/version cross-check (`--fail-on-mismatch`,
  `embed-wheel --sbom --allow-mismatch`) ([#202], [#204])
- PDM-backend and Flit-core metadata extraction and wheel file discovery
  ([#205])
- PEP 639 `[project.license-files]`: file references to the wheel's
  `.dist-info/licenses/` paths ([#207])
- Resolved dependencies from `pylock.toml`, `uv.lock`, `pdm.lock`,
  `Pipfile.lock` and pinned `requirements.txt`, with declared-vs-locked version
  conflict detection and lock SHA-256 hashes as `verifiedUsing`; see
  [Dependency sources and precedence](docs/dependency-sources.md)
  ([#208], [#211], [#212])
- `--no-use-lockfile` / `[tool.pitloom] use-lockfile` opt-out; `offline` and
  `use-lockfile` Action inputs ([#210])
- In-tree `.egg-info`/`.dist-info` as a supplementary metadata source: gap-fills
  undeclared fields, flags disagreement as an Annotation ([#214])
- `--allow-build`/`--no-build-isolation`: opt-in file discovery via a real
  PEP 517 build ([#215], [#216])

### Changed

- 18 log messages promoted from `DEBUG:` to `WARNING:` where a failure silently
  drops SBOM data; each names the affected field(s) as
  `... | Field(s) affected (skipped|degraded): <name>` ([#201])
- `embed-wheel` skips per-file SHA-256 hashing in the source-tree rescan
  ([#213])

### Fixed

- `read_project()` returned empty metadata for a `[build-system]`-only
  `pyproject.toml` with real metadata in `setup.cfg`/`setup.py` ([#205])
- `[tool.setuptools.dynamic] version` `attr`/`file` did not resolve with a
  `[project]` table; `detect_license_from_text()` fuzzy-matched labels under
  100 characters ([#205])
- Flit no longer executes project code for a computed `version`/`description`;
  PDM `scm` version no longer writes to disk or leaks stale `.pdm-build/`
  content ([#205])
- `embed-wheel --project-dir` shows the real reason when metadata can't be
  resolved ([#205])
- `enrich --project-dir` always ran the lock-file cascade for the base
  document's identity, giving dangling fragment references ([#210])

## [0.17.0] - 2026-08-30

### Added

- Annotation `statement` serialized via RFC 8785 (JCS); size cap via
  `[tool.pitloom.provenance] max-source-metadata-bytes` /
  `--max-source-metadata-bytes` ([#189])
- Setuptools wheel file discovery from static config (`packages.find`,
  `package_data`, `include_package_data`/`MANIFEST.in`); `setuptools>=70` is a
  runtime dependency ([#196])

### Changed

- **Setuptools projects**: element ids shift vs. earlier output; regenerate the
  base SBOM before merging fragments ([#196])

### Fixed

- `simpleLicensing` profile declared only when a license claim was made ([#190])
- Setuptools `packages.find where=` layouts reported wrong distribution paths;
  unhandled backends warn instead of silently using a Hatchling file list;
  `detect_build_backend()` falls back for a malformed `pyproject.toml`; crash on
  an SPDX `license` string plus legacy classifiers ([#196])
- `merge_fragments()` fails, with a warning, on a dangling reference after the
  merge ([#196])
- `INFO:` messages reach stderr; `embed-wheel`/`wheel --embed` `INFO:` lines go
  to stderr, not stdout; Action turns loom's `INFO:`/`WARNING:`/`ERROR:` lines
  into `::notice::`/`::warning::`/`::error::` annotations ([#196])
- `generate()` routes `.pt2` to model-SBOM generation ([#196])

## [0.16.4] - 2026-08-21

### Fixed

- Deduplicate dependencies ([#184])

## [0.16.3] - 2026-08-21

### Added

- Auto-sync Loom ID registry after SBOM generation ([#178])
- Sigstore and provenance attestations on the GitHub release ([#180])

### Fixed

- `normalize_license_expression` raised `IndexError` on an unbalanced `)`;
  dependency metadata reads warned `DeprecationWarning` on Python 3.14;
  `licenseid` floor `>=0.3.7` fixes a sqlite3 connection leak ([#179])

## [0.16.2] - 2026-08-19

### Added

- `PITLOOM_SBOM_OUTPUT_PATH=<path>` on stdout after `project`/`model`/`env`/
  `wheel`/`embed-wheel` write an SBOM ([#171])
- Release workflow attaches the standalone SBOM to the GitHub Release via the
  project's own Action ([#172], [#174])

### Fixed

- Action defers to loom's default naming (`packagename-version.spdx3.json`)
  ([#171])
- `embed-wheel` Build SBOM includes content-type and file-header data per file
  while keeping the wheel's own file records; its Merkle root uses the wheel's
  file hashes, not a project rescan ([#172], [#174])

## [0.16.1] - 2026-08-18

### Fixed

- An author list packed into one email's display name (`"A, B" <x@y>`) is
  split into individual Persons ([#169])

## [0.16.0] - 2026-08-18

### Added

- A string holding several authors is split into discrete agents; "Others" gets
  external refs ([#151])

### Changed

- `setup.cfg` legacy `fragments` key maps to `[tool.pitloom.fragment]`;
  `provenance`/`content-type`/`fragment` sub-sections reach parity with
  `pyproject.toml`; boolean fields are strictly type-checked ([#152])
- AI model and sdist extraction no longer load the full file; peak memory down
  by over 97% ([#156])
- `loom generate` requires `-o`/`--output` instead of silently writing
  `sbom.spdx3.json` ([#160])

### Fixed

- Leftover `split_main.py` and `src/pitloom/__main__.py.bak` (shipped in the
  wheel) removed ([#153])
- `_fickling_get_top_class` logs a distinct warning for an AST-walk failure
  ([#164])

## [0.15.0] - 2026-08-15

### Added

- `loom wheel --embed`, `loom embed-wheel` and Action support for embedding
  SPDX 3 SBOMs into wheels ([#148])

### Fixed

- SBOM `created` honours `SOURCE_DATE_EPOCH`, as the ZIP entry timestamp
  already did ([#148])

## [0.14.1] - 2026-08-13

### Fixed

- `sbomAuthorSupplied` is a provenance `role`, not a `method` ([#143])
- Crash on AI base-model lineage when `base_model` is set but
  `base_model_relation` is not ([#144])

## [0.14.0] - 2026-08-13

### Added

- `RuntimeError` if Hatchling is older than 1.29.0 ([#136])
- Per-file metadata from SPDX file tags and headers
  (`[tool.pitloom] extract-file-header`, on by default) ([#138])
- Per-file content-type detection (`[tool.pitloom.content-type] enabled`, off by
  default; `method` `auto`/`magika`/`extension`, also `--content-type-method`
  and the Action input); errors if `magika` is requested but not installed
  ([#138], [#140])
- Minimum-elements-oriented SBOM enrichment ([#139])
- `[[tool.pitloom.content-type.override]]`: glob -> MIME-type table that
  pre-empts detection; [Configuration](docs/configuration.md) reference page;
  every `[tool.pitloom]` setting is validated at read time, so an old or
  misplaced key raises ([#140])

### Fixed

- `[tool.pitloom] offline` honoured by `generate`, `wheel`, `model` and `env`,
  not only `project`; `ERROR:`/`WARNING:` prefixes uppercase again ([#142])

## [0.13.3] - 2026-08-11

### Added

- Pitloom's own hash and Package URL with version in the generated SBOM
  ([#132])
- Skills: more trigger words and known limitations ([#134])

### Fixed

- POSIX path in the provenance comment ([#133])

## [0.13.2] - 2026-08-11

### Added

- Installed-dependency fallbacks: copyright from License-File, supplier from
  Author/Maintainer, PyPI API for supplier/license/hash, `NOASSERTION` for
  copyright/license, name-only Package URL for unresolved versions ([#131])

### Fixed

- Multi-clause specifier parsing, dropped `hasConcludedLicense` relationship,
  dropped multi-address Maintainer-email, and Windows-dependent Merkle
  root/`doc_uuid` ([#131])

## [0.13.1] - 2026-08-11

### Changed

- Default SBOM filename follows [SBOM Everywhere][sbom-naming] ([#130])

## [0.13.0] - 2026-08-11

### Added

- **Breaking**: CLI and Python API redesigned around input artifacts (project,
  wheel, model, env, generate), CISA SBOM Types in the output graph; native
  `.tar.gz`/`.zip` sdist extraction ([#96], [#114])
- Skills `sbom-generate`, `sbom-enrich`, `sbom-validate` and a Claude Code
  plugin ([#96], [#123])
- Metadata provenance as SPDX 3 `Annotation`s (`[tool.pitloom.provenance]
  format`, `detail`, `preserve-source-metadata`), unification provenance,
  exact per-key provenance for dict-valued AI metadata ([#102])
- `hasConcludedLicense` vs. `hasDeclaredLicense` split ([#105])
- `ExternalIdentifier` (DOI) and `ExternalRef` (arXiv, model page) on
  `ai_AIPackage` ([#106])
- `Agent` and `publishedBy` for dataset creators ([#107])
- `SpdxDocument.import_` `ExternalMap` entries for merged fragments ([#108])
- `descendantOf` `Relationship` and stub `ai_AIPackage` for base-model lineage
  ([#109])
- Per-key hyperparameter provenance in `set_model(hyperparameters=...)` and
  `set_model_hyperparameters()` ([#113])
- Declared-vs-detected license conflict detection (`CITATION.cff`,
  `codemeta.json`, `LICENSE`), recorded as a `provenance/conflict/1`
  Annotation ([#121])
- AI-model metadata enrichment on every surface, opt-in via config ([#124])
- `sbom-enrich` asks the SBOM author for missing info in interactive sessions
  (`sbomAuthorSupplied` role) ([#125])

### Fixed

- `loom generate` honours the target's `[tool.pitloom]` config ([#116])

### Security

- Untrusted text (model filename, binary metadata key) is sanitized before
  entering a provenance string ([#102])
- Hugging Face `hf_hub_download()` is revision-pinned; environment command
  invocation hardened against Bandit findings ([#117])

## [0.12.0] - 2026-07-10

### Added

- `loom.run` `use_model` records inference code -> AI model ([#95])

## [0.11.0] - 2026-07-09

### Added

- Loom ID registry (`loom-ids.json`): stable file/entity -> SPDX ID mapping;
  `loom ids generate`/`import`; consulted by `pitloom.loom`, `loom -m`, the
  Hatchling hook and `generate_sbom()` ([#91])
- `loom.run` records the generating script as a hashed `software_File`, emits
  file-level `generates` relationships and dataset `verifiedUsing` hashes;
  `set_model(generated=)`, `add_output_dataset(input_datasets=)` ([#91])
- Hatchling hook `builtTime` honours `SOURCE_DATE_EPOCH` or
  `[tool.pitloom.creation] creation-datetime` ([#91])

### Changed

- `generates`/`hasDataFile` are `LifecycleScopedRelationship` (`build`/
  `runtime`) ([#91])
- `merge_fragments()` unifies fragments (shared registry ids or identical
  content collapse; envelopes and duplicate relationships dropped) instead of
  concatenating ([#91])

## [0.10.0] - 2026-07-09

### Changed

- Creators may be `Person`, `Organization`, `SoftwareAgent` or `Agent`
  (`--creator-type`); config consolidated into `[tool.pitloom]`,
  `[tool.pitloom.creation]`, `[tool.pitloom.fragments]`; fragments carry their
  own creation metadata ([#84])
- **Breaking**: `creation_info` renamed `creation_metadata` in `generate_sbom()`
  and related APIs ([#84])
- **Breaking**: multiple creators and tools: `creators: list[Creator]`,
  `tools: list[Tool] | None`; repeatable `--creator-name`/`--creation-tool`;
  `[[tool.pitloom.creator]]`/`[[tool.pitloom.creation-tool]]` replace the
  `[tool.hatch.build.hooks.pitloom]` keys ([#86])
- **Breaking**: `generate_sbom()` keyword arguments are keyword-only (except
  `project_dir`); optional `project_metadata`/`pitloom_config` skip re-parsing
  ([#89])

### Fixed

- Pitloom is recorded as a `Tool` (`createdUsing`), not a `Person` ([#84])
- Projects with only `setup.cfg`/`setup.py` raised `FileNotFoundError` ([#89])

## [0.9.0] - 2026-07-06

### Added

- Hatchling hook reads the backend's resolved metadata (e.g. `hatch-vcs`
  versions) and runs for wheel builds only; every file gets a SHA-256 hash; the
  main package gets a PyPI Package URL ([#82])
- GitHub Action, Skills (`sbom`, `enrich`) and a Claude Code plugin ([#82])

### Fixed

- `None` spdxId ([#83])

## [0.8.0] - 2026-05-29

### Added

- End-to-end `examples/sentimentdemo-aibom/` for `loom.run` fragments ([#80])

### Changed

- `loom.shoot` renamed `loom.run` ([#80])

### Fixed

- Wrong fickling import in the PyTorch extractor ([#80])

## [0.7.1] - 2026-05-14

### Changed

- License ID recorded in its canonical form ([#78])

## [0.7.0] - 2026-05-12

### Added

- `-m`/`--aimodel` accepts a Hugging Face Hub URL ([#71])

### Fixed

- AI model license exported ([#72])

## [0.6.1] - 2026-05-07

### Added

- `-m`/`--aimodel` for a standalone AI model SBOM ([#69])

## [0.6.0] - 2026-05-07

### Added

- `[tool.poetry]` support: metadata, runtime dependencies (groups excluded),
  Poetry specifiers converted to PEP 440; `[project]` wins when both exist
  ([#67])

## [0.5.1] - 2026-05-06

### Changed

- Fall back gracefully if `[project]` is missing from `pyproject.toml` ([#63])

## [0.5.0] - 2026-04-29

### Added

- Setuptools projects ([#59]); SPDX License ID detection from license text
  ([#60])

## [0.4.1] - 2026-04-02

### Changed

- Warn if the AI extraction library is not installed ([#50])

## [0.4.0] - 2026-04-02

### Added

- Files and directories with `contains` relationships ([#42])
- Human-readable Relationship description ([#44])
- Creation information in `pyproject.toml` and on the command line ([#47])

## [0.3.0] - 2026-04-01

### Added

- AI model metadata from fastText, HDF5, Keras, NumPy, PyTorch, PyTorch PT2
  ([#33], [#36])
- Pitloom's Hatchling plugin used in its own `pyproject.toml` ([#39])
- Dataset metadata model and extraction (experimental) ([#40])

### Changed

- JSON output sorted per [RFC 8785 JCS][jcs] and [SPDX 3 canonical
  serialization][spdx3-canon]; element order: CreationInfo, SpdxDocument, Bom,
  software_Sbom, rest ([#29])

## [0.2.0] - 2026-03-27

### Changed

- spdxId is a deterministic UUIDv5 seeded by project name, version, dependency
  list and the Merkle root of the wheel's files ([#27])

## [0.1.0] - 2026-03-27

First public pre-release. Originally "Loom"; renamed Pitloom before release
because "Loom" and "Pyloom" were unavailable on PyPI.

### Added

- Minimum SBOM generation ([#9]), SBOM fragments ([#10]), AI model metadata from
  GGUF, ONNX and Safetensors ([#11]), Hatch plugin ([#17])

[sbom-naming]: https://sbom-catalog.openssf.org/sbom-naming.html
[jcs]: https://www.rfc-editor.org/rfc/rfc8785
[spdx3-canon]: https://spdx.github.io/spdx-spec/v3.0.1/serializations/#canonical-serialization
[#9]: https://github.com/bact/pitloom/pull/9
[#10]: https://github.com/bact/pitloom/pull/10
[#11]: https://github.com/bact/pitloom/pull/11
[#17]: https://github.com/bact/pitloom/pull/17
[#27]: https://github.com/bact/pitloom/pull/27
[#29]: https://github.com/bact/pitloom/pull/29
[#33]: https://github.com/bact/pitloom/pull/33
[#36]: https://github.com/bact/pitloom/pull/36
[#39]: https://github.com/bact/pitloom/pull/39
[#40]: https://github.com/bact/pitloom/pull/40
[#42]: https://github.com/bact/pitloom/pull/42
[#44]: https://github.com/bact/pitloom/pull/44
[#47]: https://github.com/bact/pitloom/pull/47
[#50]: https://github.com/bact/pitloom/pull/50
[#59]: https://github.com/bact/pitloom/pull/59
[#60]: https://github.com/bact/pitloom/pull/60
[#63]: https://github.com/bact/pitloom/pull/63
[#67]: https://github.com/bact/pitloom/pull/67
[#69]: https://github.com/bact/pitloom/pull/69
[#71]: https://github.com/bact/pitloom/pull/71
[#72]: https://github.com/bact/pitloom/pull/72
[#78]: https://github.com/bact/pitloom/pull/78
[#80]: https://github.com/bact/pitloom/pull/80
[#82]: https://github.com/bact/pitloom/pull/82
[#83]: https://github.com/bact/pitloom/pull/83
[#84]: https://github.com/bact/pitloom/pull/84
[#86]: https://github.com/bact/pitloom/pull/86
[#89]: https://github.com/bact/pitloom/pull/89
[#91]: https://github.com/bact/pitloom/pull/91
[#95]: https://github.com/bact/pitloom/pull/95
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
[#121]: https://github.com/bact/pitloom/pull/121
[#123]: https://github.com/bact/pitloom/pull/123
[#124]: https://github.com/bact/pitloom/pull/124
[#125]: https://github.com/bact/pitloom/pull/125
[#130]: https://github.com/bact/pitloom/pull/130
[#131]: https://github.com/bact/pitloom/pull/131
[#132]: https://github.com/bact/pitloom/pull/132
[#133]: https://github.com/bact/pitloom/pull/133
[#134]: https://github.com/bact/pitloom/pull/134
[#136]: https://github.com/bact/pitloom/pull/136
[#138]: https://github.com/bact/pitloom/pull/138
[#139]: https://github.com/bact/pitloom/pull/139
[#140]: https://github.com/bact/pitloom/pull/140
[#142]: https://github.com/bact/pitloom/pull/142
[#143]: https://github.com/bact/pitloom/pull/143
[#144]: https://github.com/bact/pitloom/pull/144
[#148]: https://github.com/bact/pitloom/pull/148
[#151]: https://github.com/bact/pitloom/pull/151
[#152]: https://github.com/bact/pitloom/pull/152
[#153]: https://github.com/bact/pitloom/pull/153
[#156]: https://github.com/bact/pitloom/pull/156
[#160]: https://github.com/bact/pitloom/pull/160
[#164]: https://github.com/bact/pitloom/pull/164
[#169]: https://github.com/bact/pitloom/pull/169
[#171]: https://github.com/bact/pitloom/pull/171
[#172]: https://github.com/bact/pitloom/pull/172
[#174]: https://github.com/bact/pitloom/pull/174
[#178]: https://github.com/bact/pitloom/pull/178
[#179]: https://github.com/bact/pitloom/pull/179
[#180]: https://github.com/bact/pitloom/pull/180
[#184]: https://github.com/bact/pitloom/pull/184
[#189]: https://github.com/bact/pitloom/pull/189
[#190]: https://github.com/bact/pitloom/pull/190
[#196]: https://github.com/bact/pitloom/pull/196
[#198]: https://github.com/bact/pitloom/pull/198
[#200]: https://github.com/bact/pitloom/pull/200
[#201]: https://github.com/bact/pitloom/pull/201
[#202]: https://github.com/bact/pitloom/pull/202
[#204]: https://github.com/bact/pitloom/pull/204
[#205]: https://github.com/bact/pitloom/pull/205
[#207]: https://github.com/bact/pitloom/pull/207
[#208]: https://github.com/bact/pitloom/pull/208
[#210]: https://github.com/bact/pitloom/pull/210
[#211]: https://github.com/bact/pitloom/pull/211
[#212]: https://github.com/bact/pitloom/pull/212
[#213]: https://github.com/bact/pitloom/pull/213
[#214]: https://github.com/bact/pitloom/pull/214
[#215]: https://github.com/bact/pitloom/pull/215
[#216]: https://github.com/bact/pitloom/pull/216
[#217]: https://github.com/bact/pitloom/pull/217
[#220]: https://github.com/bact/pitloom/pull/220
[#222]: https://github.com/bact/pitloom/pull/222
[#223]: https://github.com/bact/pitloom/pull/223

---

[0.18.1]: https://github.com/bact/pitloom/compare/v0.18.0...v0.18.1
[0.18.0]: https://github.com/bact/pitloom/compare/v0.17.0...v0.18.0
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
