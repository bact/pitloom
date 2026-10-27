---
Last-Modified: 2026-10-27
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
- Commit history: <https://github.com/bact/pitloom/compare/v0.21.0...HEAD>

## [Unreleased]

### Fixed

- Setuptools' manifest-step stderr lines are relayed as tagged log lines
  ([#356])

## [0.21.0] - 2026-10-23

### Added

- Every route but `loom env` lists extras as `hasOptionalDependency` (no
  scope, `extras: a, b`, an inner extra marker joined, warned), pinned by
  `uv.lock`, `poetry.lock`, `pdm.lock` ([#300])
- A directory reads `[tool.setuptools.dynamic]` and `setup.cfg` `file:`
  requirements, other `dynamic` deps from `setup.cfg`/`setup.py`; bad lines
  warn; never a lock ([#300])
- Every `[project].authors` entry is an `originatedBy` of the main package,
  one Agent per type, name and email; `embed-wheel --project-dir` uses them
  ([#300])
- `loom id generate --namespace IRI` sets a new registry's document namespace
  instead of a random UUID4 one ([#305])
- `loom.Run`/`loom.run` take `pitloom_config=` (`id-registry`,
  `update-id-registry`, `max-dataset-hash-bytes`) ([#305])
- An AI model's producer is `originatedBy` (the Hub owner also `suppliedBy`);
  its parameter count an `ai_hyperparameter` `parameters` entry ([#306])
- SHA-512 beside SHA-256 for every file Pitloom reads itself ([#309])
- Dataset licence and metadata from Croissant (`loom.run`), local cards and Hub
  dataset cards; several licences are several declared licences ([#309])
- G7, CISA 2026, FSCT 2024 and BSI conformance tests and expected tables
  ([#309])
- One `INFO:` per model whose architecture goes into `ai_typeOfModel` ([#309])
- References to one dataset (a Hub id in any case) give one dataset package
  with a relationship per role; a later reference fills only unset fields
  ([#311])
- `loom project`/`loom generate` take a Git repository or page URL;
  GitLab redirects are followed and `check_url=` guards each hop ([#317])
- `loom id import --project-dir` roots a new registry at the project directory
  ([#338])
- `max_bytes=` of `fetch_git_project` and `max_clone_bytes=` of
  `generate_git_project_sbom` stop a clone past a disk cap (`git.too-large`)
  ([#339])
- Git URLs: Gitiles, cgit and Azure DevOps page URLs are read; a clone whose
  blob filter the server rejects (HTTP 400) is retried without it ([#347])

### Changed

- Required, locked and phantom edges are `dependsOn` with scope `runtime` (not
  in `loom env`) ([#300])
- A dependency is named (PEP 503) and declared alike on every route, `loom
  env` too; `doc_uuid` changes for a project with extras or requirements files
  ([#300])
- One `Author`/`author` is one author on every route (`Jane, Bob` too), cut
  only next to an address; a project's holding `,`/`;`/`and` gets an `INFO:`
  ([#300])
- `Author-email` splits on `,`/`;`, not `and`; a split warns; a dependency's
  maintainer stands in only for an absent author ([#300])
- Author fields read up to 65,536 characters/1,000 entries; a quoted
  name (`"…"`, `“…”`) stays whole; a name's white space is collapsed ([#300])
- `copyrightText` is a notice from the project's licence files (never a GNU
  licence's own FSF notice), else `NOASSERTION`; no longer made from the
  authors ([#300])
- Every input over a cap (model bounds, labels, names, wheel/sdist header
  blocks, config members, a 1 MiB model card) warns `<KEY>=…: larger than the
  N-unit … cap; <outcome>` ([#300])
- ID registry format v3: `elements` by type and name, `project_root` and
  `id_counters` (a retired id is never minted again); v2 is an `ERROR:`.
  `id generate` and harvest record a model's SHA-256, never erase it ([#305])
- `loom.Run` dataset files are a `dataset_DatasetPackage` that `contains` a
  `software_File`; a directory gets a Merkle root; `max-dataset-hash-bytes`
  (4 GiB) caps the read ([#305])
- `loom.set_model()`/`use_model()` take `path=`: the file's SHA-256 gates the
  model's registry id, and a new model is saved to the registry ([#305])
- API: `FileEntry`/`EntityEntry` become `RegistryEntry`; new `persist_registry`,
  `registry_key_for_path`, `type_id_prefix`. `loom.Run` messages carry their
  `WARNING:`/`INFO:` tag ([#305])
- ID registry keys files, models and datasets by path (one id on every
  surface), gated by SHA-256; `src/`/`lib/` alias; a `set_model()` name wins
  a merge; `wheel`/`project <sdist>` take `--project-dir` ([#308])
- `--content-type-method` and `--creator-type` list their choices sorted; a card
  description skips tables of contents, HTML and badges ([#309])
- Skills' minimum-elements tables follow the checker; `loom enrich` licence
  behaviour stated correctly ([#318])
- A malformed or out-of-range `SOURCE_DATE_EPOCH` is an `ERROR:` on every
  command, pinned datetime or not;
  the hook fails the build ([#322])
- Hook: one `ERROR:` per failed build; Hatchling's own keys accepted;
  editable builds skipped; `sbom-files` name clash refused ([#322])
- `embed-wheel --sbom` embeds exact bytes;
  re-embedding replaces only a Pitloom build SBOM of the same name and version
  ([#322])
- Fragments that cannot be canonicalised are skipped with a `WARNING:`;
  existing relationship descriptions are kept ([#322])
- Hatchling hook: tests read the staged SBOM from `build_data`, not a private
  attribute ([#325])
- `licenseid>=0.5.0` is required: its database is built from a host the
  Claude Code sandbox allows ([#333])

### Fixed

- Poetry dependencies match poetry-core's (`optional`, `markers`/`python`,
  git/url, extras; `path` warns), read only for a Poetry backend; a nameless
  2.x `[tool.poetry]` is read ([#300])
- An sdist keeps all its authors; no `build-backend` lists setuptools' files
  (PEP 517), not Hatchling's; setuptools' deprecation banners are `DEBUG:`
  lines, not untagged stderr ([#300])
- An author named `... Brothers` is a Person, not a group; a setuptools
  `UNKNOWN` author is no author; a stated name stays beside an invalid
  address, warned once per field ([#300])
- A creator's name and email are stripped; `embed-wheel --project-dir` warns
  once about a split in the adopted project authors, `--config` or not
  ([#300])
- A licence file, `project.license.file` or `project.readme` outside the
  project is not read; a `project.license.file` `Source:` is project-relative
  ([#300])
- A dynamic version file (setuptools, Hatch, Flit, PDM) outside the project,
  or a dependency `License-File` outside its `.dist-info`, is not read ([#300])
- Crafted author fields, copyright lines, extras self-references and
  requirements files no longer take quadratic or exponential time or memory
  ([#300])
- A requirement or marker nesting over 64 parentheses warns instead of
  crashing the run ([#300])
- `id import` keeps a model's hash unless its id changes (`INFO:`); in-tree
  registries and their wheel/sdist copies settle; `id generate` indexes `build/`
  and warns on unreadable files or directories ([#305])
- Merge: an id shared by a different type, or by the same type with a
  conflicting SHA-256, keeps both (new id, `WARNING:`); for equal content the
  registry-pinned id survives ([#305])
- `id generate`: an unreadable `PATH` or non-directory `--project-dir` is an
  `ERROR:`, `-o -` a usage error; a skipped-directory `PATH` warns; a symlinked
  `PATH` directory is walked; a name UTF-8 cannot hold is skipped, warned. `id import`: `@graph` not a list is an
  `ERROR:` ([#305])
- A wheel with no identity (`unknown`) is not looked up in or recorded into an
  ID registry, and its ids depend on its file name;
  a `loom.Run` dataset is one package per name and content ([#305])
- A Hugging Face model's description is found again: the whole model card,
  front matter included, goes to the description helper ([#310])
- Dataset readers: a model card lists at most 1000 datasets, Croissant JSON
  nests at most 64 levels, a placeholder (`unknown`, `N/A`, `NOASSERTION`) is
  no name, licence or URL, and Hub card warnings name no cache path ([#311])
- The main package's `suppliedBy` is never a `software-agent` creator:
  the next creator is taken, or none is set ([#312])
- `loom.Run` names a dataset as a model card does (`Org/Data` is `org/data`,
  a file never folded); a folded spelling is said once by an `INFO:`
  ([#314])
- The NumPy reader type-checks on numpy 2.3 and 2.5 alike:
  no `type: ignore` that one of the two calls unused ([#315])
- Lock readers warn and move on for nested, oversized or non-regular files,
  invalid names and padded versions;
  URL passwords are masked whole ([#323])
- A lock file never read says `Cannot read`, not `Failed to parse`;
  Hatchling hook: an `sbom-files` name clash is refused ignoring case ([#326])
- A "has no effect" warning masks a URL's credentials; lock and `id import`
  messages escape the paths they name ([#331])
- A Hub model URL as `www.huggingface.co`, `hf.co`, `http://` or any case
  is read like the canonical one, with an `INFO:` line ([#332])
- A default SBOM name cannot leave the output directory or name a Windows
  device; the CLI, hook and wheel embed share one helper ([#334])
- Paths in log, print, argparse and raised messages are quoted and escaped, one
  `ERROR:` line each; a hostile name cannot forge a line ([#335], [#336])
- Requirements continuation lines are joined as pip does; a Croissant record
  count is reported only when every record set states one ([#337])
- An sdist with members that share one path key warns instead of clashing
  silently ([#338])
- Symlinked projects get one ID registry prefix; Merkle leaves are NFC; loom
  opens `path=` as the OS does and names an outside script by file name
  ([#340], [#341])
- A redirect carries URL credentials only to the same scheme, host and port
  ([#342])
- SourceHut tree URLs with a slash in the branch name are split correctly
  ([#343])
- A timed-out git clone is killed with its child processes on Windows
  ([#344])
- A Bitbucket `/branch/` or `/commits/` page no longer clones the default
  branch; a folder page that names a file reads its folder ([#347])
- A Hugging Face Space or dataset URL is fetched as a Git repository, not read
  as a model; `loom project` of a model URL and `loom model` of a Git URL name
  the other command ([#347])
- URL messages mask a secret-named query value and a userinfo holding
  whitespace; a Hugging Face URL's query is no part of the model id
  ([#347])
- A fragment's value replaces a model's description, domain or input/output
  text that Pitloom generated from the file's format ([#349])

[#300]: https://github.com/bact/pitloom/pull/300
[#305]: https://github.com/bact/pitloom/pull/305
[#306]: https://github.com/bact/pitloom/pull/306
[#308]: https://github.com/bact/pitloom/pull/308
[#309]: https://github.com/bact/pitloom/pull/309
[#310]: https://github.com/bact/pitloom/pull/310
[#311]: https://github.com/bact/pitloom/pull/311
[#312]: https://github.com/bact/pitloom/pull/312
[#314]: https://github.com/bact/pitloom/pull/314
[#315]: https://github.com/bact/pitloom/pull/315
[#317]: https://github.com/bact/pitloom/pull/317
[#318]: https://github.com/bact/pitloom/pull/318
[#322]: https://github.com/bact/pitloom/pull/322
[#323]: https://github.com/bact/pitloom/pull/323
[#325]: https://github.com/bact/pitloom/pull/325
[#326]: https://github.com/bact/pitloom/pull/326
[#331]: https://github.com/bact/pitloom/pull/331
[#332]: https://github.com/bact/pitloom/pull/332
[#333]: https://github.com/bact/pitloom/pull/333
[#334]: https://github.com/bact/pitloom/pull/334
[#335]: https://github.com/bact/pitloom/pull/335
[#336]: https://github.com/bact/pitloom/pull/336
[#337]: https://github.com/bact/pitloom/pull/337
[#338]: https://github.com/bact/pitloom/pull/338
[#339]: https://github.com/bact/pitloom/pull/339
[#340]: https://github.com/bact/pitloom/pull/340
[#341]: https://github.com/bact/pitloom/pull/341
[#342]: https://github.com/bact/pitloom/pull/342
[#343]: https://github.com/bact/pitloom/pull/343
[#344]: https://github.com/bact/pitloom/pull/344
[#347]: https://github.com/bact/pitloom/pull/347
[#349]: https://github.com/bact/pitloom/pull/349
[#356]: https://github.com/bact/pitloom/pull/356

## [0.20.2] - 2026-10-09

### Added

- CRFsuite models (`.crfsuite`, or `.model` with the `lCRF` magic): labels,
  counts and a label-based description, from a bounded header reader
  ([#294])
- GGUF `general.license` becomes the model's licence ([#294])

### Changed

- Model annotations: collections as arrays, scalars as text (RFC 8785 floats);
  schema `/2` adds `valueTypes`, `maxEntries`; fastText `labels` is a JSON
  array; embedded JSON is RFC 8785; `--pretty` is the same text indented
  ([#294])
- Model, base model, dataset and creator names over 1024 characters are cut,
  ending in a digest of the full name; labels over 4 KiB dropped; each with a
  `WARNING:` ([#294])
- Invisible, bidi and control characters from a model are shown as `\uXXXX`
  (URLs percent-encoded), licences included; a lone surrogate no longer
  aborts the SBOM. In every SBOM's provenance comments, `;`, CR, LF (and `:`
  in a field) are `\uXXXX` too: `requests>=2\u003b python_version...` ([#294])

### Fixed

- An unnamed AI model, or an ONNX exporter-default `graph.name` (`torch_jit`,
  `tf2onnx`), is named after its file, as is a `loom model` document; ids
  change ([#292])
- ONNX: reads `model_license` and packed SemVer `model_version`; `domain` is
  not the model type; `metadata_props` keys are prefixed; NumPy dtype names;
  IR 3 initializers are not inputs; ONNX-ML has no type ([#292], [#294])
- A licence id over 50,000 characters in a licence text no longer reads as
  a broken licence database: requires `licenseid` 0.4.3 ([#292])
- fastText cbow/skipgram vocabulary no longer read as labels; GGUF big-endian
  format version, non-integer `file_type`, blank version fixed ([#294])

[#292]: https://github.com/bact/pitloom/pull/292
[#294]: https://github.com/bact/pitloom/pull/294

## [0.20.1] - 2026-10-07

### Changed

- setuptools projects: a `setup()` keyword overrides the same `setup.cfg`
  option unless empty, as setuptools does; SBOM output changes ([#287])

### Fixed

- `setup.py` without a literal `name=` keeps its other keywords; a `setup.cfg`
  placeholder licence no longer wins; overridden real values become conflicts
  ([#287])
- Licence detection requires `licenseid` 0.4.2 (Windows fixes): a runner-up or
  stated licence that fits the text measurably worse no longer ties; an
  unusable database warns ([#287], [#289])
- `-o -` leaves stdout as the SBOM alone: no `PITLOOM_SBOM_OUTPUT_PATH=-`
  line, embed `WHEEL=` record on stderr; `embed-wheel -o -` no longer writes
  a file named `-` ([#288])

[#287]: https://github.com/bact/pitloom/pull/287
[#288]: https://github.com/bact/pitloom/pull/288
[#289]: https://github.com/bact/pitloom/pull/289

## [0.20.0] - 2026-10-05

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
  models inside the wheel; `max-model-extract-bytes` caps a model (4x for
  the wheel), beyond which it has no metadata ([#263])
- `--trust-wheel-model` (`trust_wheel_model=`, no config key): without it, a
  wheel's fastText, GGUF, HDF5, ONNX and `.pt`/`.pth` models are listed
  without metadata, with one `INFO:` ([#263])
- A `.pt`/`.pth` is a PyTorch model only when it opens as a ZIP or a pickle:
  Python `.pth` path-config files (`distutils-precedence.pth`) are no longer
  reported as models ([#263])
- `generate_wheel_sbom_with_metadata()`; `embed_sbom_in_wheel(identity=...)`
  ([#266])
- A `License ::` classifier is a licence source after the licence field
  (manifests, hook, wheel, sdist, dependencies); `License :: OSI Approved` is
  a category, never a licence ([#276])

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
- An sdist reads its own `[tool.pitloom]` like its unpacked directory (an
  invalid one fails; `--config` bypasses it); `embed-wheel --project-dir
  <sdist>` no longer merges `--config` fragments ([#232])
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
- Renamed `loom ids` to `loom id`, `--registry` (`ids-file`, `registry=`) to
  `--id-registry`, `--update-registry` to `--update-id-registry`; old keys
  raise a moved-key error ([#235])
- A registry is used only when declared (flag, `[tool.pitloom]`,
  `--config`), never searched for; suggested name `loom-id-registry.json`;
  `id generate`/`id import` require `--id-registry` ([#235])
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
- A valid SPDX licence is a canonical `LicenseExpression`; other text is
  `SimpleLicensingText` less leading blank space and final line breaks
  ([#276])
- `NOASSERTION`/`UNKNOWN`/`NONE` are the `NoAssertionLicense`/`NoneLicense`
  individuals; NoAssertion is weak: any real licence wins, no conflict ([#276])
- No licence stated gives no licence relationship and no licensing profile; the
  `NOASSERTION` fallback is gone and `License-N` ids shift ([#276])
- A package's own licence (model file or card, own `LICENSE`, `loom env`) is
  declared; PyPI and dependencies' installed metadata are concluded ([#276])
- Several `License ::` classifiers are one AND `LicenseExpression` of
  `LicenseRef-pitloom-classifier-` terms, with one `WARNING:` ([#276])
- `max-source-metadata-bytes` of 1-7 or below 0 is an error, not unlimited;
  `normalize_max_source_metadata_bytes()` is now
  `require_max_source_metadata_bytes()` ([#280])
- CLI stdout is `KEY=VALUE` data only (`WHEEL=`/`SBOM=`, `STATUS=`, `FILE=`,
  `PITLOOM_ID_REGISTRY_PATH=`); counts, hints and `-v` are `INFO:` on stderr
  ([#281])
- `loom merge` output (also `generate_merged_sbom()`) has an `SpdxDocument`
  with `profileConformance`, imports and unification annotations ([#284])

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
- Project file scan: an unreadable file (`FILE=`) or unlistable directory
  (`DIR=`) warns once and is skipped alone; before, the file list was emptied
  or the directory dropped silently ([#244], [#257])
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
- AI model readers refuse oversized headers (pickle opcodes or digits, GGUF,
  Safetensors, `.npy`) with one `WARNING:` each; limits in
  `docs/ai-model-scan-limits.md` ([#263], [#267])
- A ZIP model over 100k entries (counted as `zipfile` reads them) or 25.6 MB of
  directory is refused ([#263])
- A model is cut to 1000 entries per list or map (the same ones every run)
  and an unparsed HDF5 config to 500 characters, each with one `WARNING:`
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
- A fragment `Relationship`/`Annotation` pointing at `NoAssertionElement`,
  `NoneElement`, `SpdxOrganization` or a licence individual no longer fails the
  merge as dangling ([#276])
- Hugging Face `license: unknown` is recorded as `NOASSERTION`, not dropped
  ([#276])
- Licence text with a trailing newline no longer gains a false detection
  method; multi-line `License` text from Core Metadata is unfolded ([#276])
- `setup.cfg` `file:` lists read as setuptools reads them; an unreadable file,
  a `version` file too, is skipped with one `WARNING:`, not a crash ([#276])
- `profileConformance` lists `simpleLicensing`/`expandedLicensing` from the
  graph, so a direct build and a fragment merge agree ([#276])
- A wheel named `x.WHL` was read by `wheel` and `generate` but refused by
  `embed-wheel`; every wheel surface refuses it, as `pip` does ([#278])
- An unknown `[tool.pitloom]` key warns once per file with a hint; `setup.cfg`
  `creation-tool`/`tool` now reaches the SBOM (was dropped) ([#280])
- Licence file picked by exact case, not listing order, skipped over 256 KiB
  with one `WARNING:`; sdist `PKG-INFO` read as headers only, capped as a
  wheel's `METADATA` ([#282])
- An sdist reads its root `LICENSE`, `CITATION.cff` and `codemeta.json` as a
  directory does; with no `PKG-INFO`, `project.license` too. A non-object
  `codemeta.json` no longer crashes ([#283])
- Fragment merge: equal licences unified, re-declared base ids no longer
  crash, warnings name elements by id; `fragment list` flags an earlier SBOM
  of the project (`SAME_DOCUMENT=`) ([#284])
- Licence detection: a copyright notice no longer hides MIT; a stated licence
  wins a near-tie (`Apache-2.0`, not `Pixar`); an unstated tie concludes none
  ([#286])
- Licence text of an installed dependency keeps its indent; whitespace-only
  lines are blank on every surface; a classifier licence keeps its provenance
  ([#286])

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
[#278]: https://github.com/bact/pitloom/pull/278
[#280]: https://github.com/bact/pitloom/pull/280
[#281]: https://github.com/bact/pitloom/pull/281
[#282]: https://github.com/bact/pitloom/pull/282
[#283]: https://github.com/bact/pitloom/pull/283
[#284]: https://github.com/bact/pitloom/pull/284
[#286]: https://github.com/bact/pitloom/pull/286

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

[0.21.0]: https://github.com/bact/pitloom/compare/v0.20.2...v0.21.0
[0.20.2]: https://github.com/bact/pitloom/compare/v0.20.1...v0.20.2
[0.20.1]: https://github.com/bact/pitloom/compare/v0.20.0...v0.20.1
[0.20.0]: https://github.com/bact/pitloom/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/bact/pitloom/compare/v0.18.1...v0.19.0
