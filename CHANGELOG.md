---
Last-Modified: 2026-10-03
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable MD024 -->

# Changelog

All notable changes to this project are documented in this file.
Versions before 0.19.0 are in [CHANGELOG-archive.md](CHANGELOG-archive.md).

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

- Full release notes: <https://github.com/bact/pitloom/releases>
- Commit history: <https://github.com/bact/pitloom/compare/v0.19.0...HEAD>

## [Unreleased]

### Added

- `--build-timeout DURATION` for `--allow-build` (CLI, Action input,
  `BuildOptions.timeout`); default 20m, max 7 days; on expiry falls back to
  static discovery ([#226])
- `content_type_method` parameter on `generate_wheel_sbom()`,
  `generate_env_sbom()` and `build_deployed()` ([#228])
- `pitloom.core.config_cascade`: `ConfigOverrides`, `apply_overrides()`
  (was `pitloom.embed._apply_config_overrides`), `load_config_file()`,
  `resolve_standalone_config()` ([#228], [#231])
- `--config FILE` / `pitloom_config=` on every SBOM command, generator
  function and `embed_wheel_sbom()`; replaces the target's own
  `[tool.pitloom]` instead of merging ([#231])
- `max_source_metadata_bytes=` on `generate()`, `generate_wheel_sbom()`,
  `generate_env_sbom()` and `generate_model_sbom()` ([#231])
- `WARNING: Options: ...` for a shared flag (incl. `--use-lockfile`) given on a
  target that cannot act on it ([#231])
- GitHub Action inputs `id-registry` and `update-id-registry` ([#235])
- `pitloom.id_registry.IdRegistrySession`: document-scoped, first-claimant-wins
  registry lookup ([#235])
- `id generate`/`id import` print an `INFO:` config hint after creating an
  undeclared registry; `id import` lists names skipped because the SBOM holds
  several elements under them ([#235])
- `--scan-model-usage`: record which Python files reference a found AI model;
  config key, Action input, `scan_model_usage=`, also on wheels ([#252], [#263])
- `wheel`, `wheel --embed` and `embed-wheel` without `--project-dir` find AI
  models inside the wheel, all but the dist-info its file name names;
  `max-model-extract-bytes` caps a model, 4x that a wheel; beyond it the model
  stays without metadata ([#263])
- `--trust-wheel-model` (`trust_wheel_model=`): a wheel's fastText, GGUF, HDF5,
  ONNX and PyTorch `.pt`/`.pth` models are listed without metadata unless
  given, one `INFO:` naming each format once per batch; no config key ([#263])
- A `.pt`/`.pth` is a PyTorch model only when it opens as a ZIP or a pickle:
  Python `.pth` path-config files (`distutils-precedence.pth`) are no longer
  reported as models ([#263])
- `generate_wheel_sbom_with_metadata()`; `embed_sbom_in_wheel(identity=...)`
  ([#266])

### Changed

- Library `allow_build`/`no_build_isolation` kwargs replaced by
  `build_options=BuildOptions(...)`; ignored build flags warn once on every
  surface, incl. Action `model` mode ([#226])
- `--allow-build` build output is captured (shown at `DEBUG:` on failure), its
  stdin closed, and processes it leaves running killed with an `INFO:` ([#226])
- `ConfigOverrides.provenance` replaces every provenance setting, incl. the
  byte cap ([#227])
- `generate_wheel_sbom()`/`generate_env_sbom()`/`generate_model_sbom()` read
  settings from an explicit `--config`/`pitloom_config=` only, never the
  current directory's `[tool.pitloom]` or registry ([#228], [#231])
- `ConfigOverrides` gained `pretty`, `describe_relationship` and
  `update_id_registry` (inert, warns, on `embed_wheel_sbom()`);
  `embed_wheel_sbom()` raises on an invalid `content_type_method`
  ([#228], [#231])
- `embed-wheel` needs `--project-dir` to rescan a project, else embeds a
  standalone-wheel SBOM; `wheel --embed` embeds a canonical SBOM like
  `embed-wheel` ([#231])
- A relative `--id-registry` (and `id generate` `-o`/PATH) resolves against the
  current directory on every command ([#231], [#235])
- An sdist reads its own `[tool.pitloom]` (root `pyproject.toml`, else
  `setup.cfg`) like an unpacked directory; an invalid one fails the run
  (`--config` bypasses it).
  `embed-wheel --project-dir <sdist>` no longer merges `--config` fragments
  ([#232])
- A declared `[tool.pitloom]` in an unnamed `pyproject.toml` beats
  `setup.cfg`'s ([#232])
- `sbom-basename` must be a file name: no `/`, `\`, `:` or NUL ([#232])
- Deterministic output: AI model scan order, usage files, hyperparameters and
  per-key provenance are sorted; SBOM, fragment and registry files are LF/UTF-8
  on every platform ([#232], [#240])
- `pitloom.ids` renamed `pitloom.id_registry` (a package); `pitloom._ids_types`
  removed ([#234])
- ID registry file format v2 (`entities` keyed by type then name); older files
  are rejected, not migrated ([#234], [#235])
- `Spdx3JsonExporter.to_json()` raises on a duplicate spdxId with differing
  content ([#234])
- Renamed `loom ids` to `loom id`, `--registry`/`ids-file`/`registry=` to
  `--id-registry`/`id-registry`/`id_registry=`, and `--update-registry` etc. to
  `--update-id-registry` etc.; old `[tool.pitloom]` keys raise a moved-key
  `ValueError` ([#235])
- A registry is used only when declared (`--id-registry`, `[tool.pitloom]
  id-registry`, `--config`), never searched for; suggested name
  `loom-id-registry.json`; log lines start `ID registry:`; `id generate`/
  `id import` require `--id-registry` ([#235])
- A declared registry that is missing, unreadable or invalid is `ERROR:`/exit 1
  on the CLI, `ValueError` from the library and `loom.Run`, and fails the
  Hatchling build ([#235])
- `project`, `wheel`, `embed-wheel` and the Hatchling hook take main-package,
  dependency and phantom-dependency ids from a declared registry; auto-harvest
  skips names held by several registry-reading elements ([#235])
- Skills: descriptions within 1024 chars, registry detail in `references/`,
  portable across clients (`compatibility` pitloom >= 0.20.0), stale examples
  fixed ([#235])
- AI model discovery keys on the installed name: a `force-include` rename to a
  model suffix is found, to a non-model suffix dropped ([#239])
- `TerminationGuard.hold()` requires a `GuardedActivity`, which its signal
  `WARNING:` names; `--allow-build` wording unchanged ([#250])
- Recording which `.py` files reference an AI model (`hasDataFile`) is off by
  default on every surface, incl. the Hatchling hook; when unset, one `INFO:`
  names the flag ([#252])
- A `.py` over 1 MiB is skipped by the usage scan with a `WARNING:`; no
  temporary path appears in AI model warnings ([#263])
- A leftover temporary directory `WARNING:` names the directory, not its full
  path ([#263])
- An AI model whose read fails keeps a format-only entry and one `WARNING:` on
  every surface; `loom model` and `enrich` no longer fail on it; `loom id
  generate` registers only what a scan lists ([#270])
- Wheel SBOMs (`wheel`, `generate <whl>`, `embed-wheel`, `wheel --embed`) list
  payload only, not the wheel's `.dist-info`; hook and `project` skip
  `.dist-info/licenses/*` ([#271])
- Release SBOM is the build hook's, not a re-embedded one; checked, attached
  to the release byte-identical, signed and attested ([#275])

### Removed

- `IdRegistry.find()`, registry auto-discovery (incl. `loom.Run`'s),
  `resolve_explicit_registry()`, `claim_registry_hit()` ([#235])
- Unused internal `_project_doc_identity()` ([#256])

### Fixed

- `embed-wheel` with several wheels resolves (and, with `--allow-build`,
  builds) the project file list once per command ([#226])
- `--allow-build`: SIGTERM/SIGHUP/Ctrl-C/Ctrl-Break terminate the build process
  tree and clean up temp dirs ([#226])
- GitHub Action: with both `embed-wheel` and `model` set, build inputs follow
  the `embed-wheel` command that runs ([#226])
- `loom project <dir>`: a build flag for a directory with no project config is
  reported, not silently dropped ([#226])
- `embed-wheel --project-dir`: `--content-type-method` and
  `--max-source-metadata-bytes` reach the SBOM ([#227])
- `build_deployed()` drops `content_type_method`, so `env` fetched remote
  authors files under `extension` ([#228])
- Type checking fails on Hatchling 1.32.4; 1.32.3 stays supported ([#229])
- A missing, unreadable, non-UTF-8 or invalid `--config FILE` is one `ERROR:`
  naming the file; the replaced target config is no longer parsed
  ([#231], [#232])
- `enrich --project-dir <sdist>` names the sdist SBOM's document and no longer
  searches beside the archive for a registry ([#231])
- Enrichment `CreationInfo.created` follows `--creation-datetime`/
  `SOURCE_DATE_EPOCH`, not the wall clock ([#231])
- `embed-wheel --sbom` warns that `--config`/`--project-dir` have no effect,
  without reading them ([#231])
- A wrong-shaped `[tool.pitloom]` value (e.g. `sbom-basename = 3`) raises
  instead of being dropped ([#231])
- `builtTime` is UTC with `Z`; a `Z` or offset `creation-datetime` no longer
  fails the Hatchling build on Python 3.10 ([#232])
- Registry-supplied ids collide with freshly minted or stale ones; a genuine
  collision logs `WARNING: ID registry: ...` once per directory/file; deployed
  dependency names match PEP 503-canonicalized ([#234])
- `pitloom.loom` `set_model()`/`add_*_dataset()` repeated for one name, or the
  generating script sharing an id with a dataset/model, raised at
  `Run.__exit__` ([#234])
- `loom id generate`: a PATH outside `--project-dir` is one `ERROR:`, not a
  traceback ([#235])
- `loom env`: all packages were named `unknown`; now runs `pipdeptree --json`
  ([#236])
- AI model scan: an unreadable candidate (any allowed suffix) warns once and is
  skipped; warnings show a stable project-relative or installed `FILE=` path
  ([#239])
- PyPI, Croissant URL and remote authors-file fetches close HTTP error
  responses (`ResourceWarning` on Python 3.14) ([#242])
- `embed-wheel` with a project directory emits the concluded licence, as
  `loom project` does; CI and publish fail if Pitloom's own SBOM lacks it
  ([#243], [#248])
- `WARNING: licenseid database appears empty` prints once per process ([#243])
- Project file scan: an unreadable file warns once with its `FILE=` path and is
  skipped alone; it emptied the whole file list. A directory discovery cannot
  list warns once with its `DIR=` path; it was dropped silently ([#244], [#257])
- `setup.cfg` `[tool:pitloom]`: boolean and integer keys read as in
  `pyproject.toml`, not as strings ([#247])
- Wheel and sdist file names are the same on every OS (`\` to `/`, `./`
  dropped); unsafe or clashing members are skipped;
  one `WARNING:` each ([#251])
- A name with a space, `#` or `%` (e.g. an AI model title) gave an invalid
  `spdxId`/namespace IRI; it is percent-encoded, `name` unchanged ([#253])
- A wrong-typed `[tool.poetry]` value (e.g. `version = 3`), or a non-table
  `[tool]`/`[tool.poetry]`, warns once and is ignored; it crashed ([#254])
- File-discovery failure `WARNING:` is one line, not a multi-line exception;
  `--allow-build` output drops OSC escapes and blank `DEBUG:` lines ([#258])
- `import pitloom._loom_active_run` as the first Pitloom import failed on a
  circular import; two more cycles hidden by import order removed ([#260])
- `scripts/manual_cli_checks` with a relative `PYTHONPATH` ran checks against
  another installed Pitloom; it now refuses a Pitloom other than its own
  ([#261])
- Ctrl-C prints `ERROR: interrupted`, not a traceback (kept under `--debug`),
  and still ends by SIGINT ([#262])
- A renamed model's provenance `Source:` names its installed file, as
  `--allow-build` did ([#263])
- A `.keras`/`.pt`/`.pt2` inner member is read bounded (8 MiB), also in project
  scans, and reader warnings are escaped with a stable `FORMAT= FILE=` ([#263])
- AI model readers refuse a pickle over 250k opcodes or with a decimal number
  over 4300 digits (never converted), a GGUF header over its 1M budget, a
  Safetensors header over 16 MiB or an `.npy` header over 10000 bytes, each
  with one `WARNING:` ([#263], [#267])
- A ZIP model over 100k entries (counted as `zipfile` reads them) or 25.6 MB of
  directory is refused ([#263])
- A model is cut to 1000 entries per list or map, the same ones every run
  (Safetensors too; also `loom model`), and an unparsed HDF5 config to 500
  characters, each with one `WARNING:`; a cut model's memory is released
  ([#263], [#270])
- A wheel's identity comes from its own top-level `.dist-info`, reading
  `METADATA` headers only (16 MiB, 10,000); setuptools was `zipp`: regenerate
  its registry ([#266])
- A wheel that is not a ZIP, or has an unreadable member, a duplicate or NUL
  name, is refused by every wheel command with one `ERROR:`; SBOM ids ignore
  member order ([#266])
- Default embedded SBOM name: control characters, whitespace, `/`, `\` and `:`
  become `_`; over 255 characters, the `.dist-info` name is used ([#266])
- A GGUF array field is recorded as `<key>.length`, not its last element;
  GGUF quantization reads `general.file_type` as a file type (`Q8_0`, not
  `Q5_1`) ([#267])
- HDF5: a `class_name` or `name` that is not a string crashed the build; a bad
  config part or an unreadable attribute is one `WARNING:`; string-array
  attributes read the same every run ([#270])
- A file whose header contradicts its model suffix (a Git LFS pointer under any
  suffix) is not a model, with one `WARNING:` ([#270])
- `embed-wheel`, `wheel --embed`: embedded hashes stay valid; a `RECORD`-signed
  wheel is refused unless `--allow-signed-wheel` ([#271])
- An sdist's file list is sorted by path, so SPDX ids no longer follow archive
  order ([#272])
- `sbom-basename`/`--sbom-basename` ending in `.spdx3.json` (any case) loses it
  with one `WARNING:`; `project` wrote `x.spdx3.json.spdx3.json` ([#273])
- An sdist's licence is read from `PKG-INFO` `License-Expression`, else
  `License`, as for a wheel; an empty one counts as absent ([#276])

[#226]: https://github.com/bact/pitloom/pull/226
[#227]: https://github.com/bact/pitloom/pull/227
[#228]: https://github.com/bact/pitloom/pull/228
[#229]: https://github.com/bact/pitloom/pull/229
[#231]: https://github.com/bact/pitloom/pull/231
[#232]: https://github.com/bact/pitloom/pull/232
[#234]: https://github.com/bact/pitloom/pull/234
[#235]: https://github.com/bact/pitloom/pull/235
[#236]: https://github.com/bact/pitloom/pull/236
[#239]: https://github.com/bact/pitloom/pull/239
[#240]: https://github.com/bact/pitloom/pull/240
[#242]: https://github.com/bact/pitloom/pull/242
[#243]: https://github.com/bact/pitloom/pull/243
[#244]: https://github.com/bact/pitloom/pull/244
[#247]: https://github.com/bact/pitloom/pull/247
[#248]: https://github.com/bact/pitloom/pull/248
[#250]: https://github.com/bact/pitloom/pull/250
[#251]: https://github.com/bact/pitloom/pull/251
[#252]: https://github.com/bact/pitloom/pull/252
[#253]: https://github.com/bact/pitloom/pull/253
[#254]: https://github.com/bact/pitloom/pull/254
[#256]: https://github.com/bact/pitloom/pull/256
[#257]: https://github.com/bact/pitloom/pull/257
[#258]: https://github.com/bact/pitloom/pull/258
[#260]: https://github.com/bact/pitloom/pull/260
[#261]: https://github.com/bact/pitloom/pull/261
[#262]: https://github.com/bact/pitloom/pull/262
[#263]: https://github.com/bact/pitloom/pull/263
[#266]: https://github.com/bact/pitloom/pull/266
[#267]: https://github.com/bact/pitloom/pull/267
[#270]: https://github.com/bact/pitloom/pull/270
[#271]: https://github.com/bact/pitloom/pull/271
[#272]: https://github.com/bact/pitloom/pull/272
[#273]: https://github.com/bact/pitloom/pull/273
[#275]: https://github.com/bact/pitloom/pull/275
[#276]: https://github.com/bact/pitloom/pull/276

## [0.19.0] - 2026-09-18

### Changed

- GitHub Action installs the Pitloom version of its pinned ref
  (`pitloom-version` overrides), uses the workflow's Python unless
  `python-version` is set, and no longer runs `pip --upgrade pip` ([#224])

### Fixed

- GitHub Action failed on Windows runners and on `args` under macOS's bash 3.2;
  unbalanced `args` quoting is now an error ([#224])

[#224]: https://github.com/bact/pitloom/pull/224

---

[0.19.0]: https://github.com/bact/pitloom/compare/v0.18.1...v0.19.0
