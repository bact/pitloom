---
Created: 2026-04-14
Last-Modified: 2026-08-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

## Completed

- [x] SPDX 3.0 SBOM generation (JSON-LD)
- [x] Hatchling metadata extraction (`pyproject.toml`)
- [x] Dependency tracking and SPDX relationship elements
- [x] Format-neutral internal representation
  (`DocumentModel` -- see [format-neutral-representation.md](format-neutral-representation.md))
- [x] AI/ML package profiles
  (`software_Package` with AI BOM profile, `dataset_DatasetPackage`)
- [x] PEP 770 support (`.dist-info/sboms/` via `build_data["sbom_files"]`)
- [x] Hatchling build hook (`pitloom.plugins.hatch`) with fragment merging
- [x] ML tracking SDK (`pitloom.loom` -- context manager / decorator)
- [x] Metadata provenance tracking (per-field source attribution)
- [x] CLI (`loom`) with verbose mode and creator info options
- [x] Setuptools support -- initial implementation
  - `read_setup_cfg()`, `read_setup_py()`, `read_setuptools()`,
    `merge_metadata()`, `detect_build_backend()`
    in `src/pitloom/extract/_setuptools.py`
  - Conflict resolution: `pyproject.toml` > `setup.cfg` > `setup.py`
  - CLI and `generate_project_sbom()` work without `pyproject.toml`
  - `[tool:pitloom]` config section in `setup.cfg`
- [x] Poetry support -- initial implementation
  - `read_poetry()`, `extract_poetry_metadata()`
    in `src/pitloom/extract/_poetry.py`
  - Reads `[tool.poetry]` and `[tool.poetry.dependencies]`
  - `[tool.poetry.group.*]` dev/deploy dependency groups intentionally excluded
  - Poetry version specifiers (`^`, `~`, bare versions) converted to PEP 440
  - `read_pyproject()` falls back to `[tool.poetry]` when `[project]` is absent;
    merges both sections when both are present (`[project]` wins field-by-field)
- [x] **Multiple creators / tools per `CreationInfo` record** -- `Creator` /
  `Tool` dataclasses replace the old scalar `creator_name`/
  `creation_tool` fields; `CreationMetadata.creators: list[Creator]` and
  `.tools: list[Tool] | None` allow ≥1 Agents in `createdBy` and 0+
  Tools in `createdUsing`, matching what SPDX 3 allows. CLI: repeatable
  `--creator-name` (stateful -- `--creator-type`/`--creator-email` bind to
  the most recently named creator) and repeatable `--creation-tool`.
  Config: `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]`
  array-of-tables in `pyproject.toml` (Poetry too); `setup.cfg` keeps
  single-creator/-tool support only (INI can't express array-of-tables).
  `suppliedBy` on the main package -- single-valued in SPDX 3 -- is set to
  the first named creator. See
  [creation-metadata.md](../../docs/creation-metadata.md).
- [x] **SPDX license expression normalization and declared-vs-detected
  conflict detection (G2)** -- compound SPDX license expressions
  (`"MIT AND MIT"`, `"(MIT AND Apache-2.0) OR BSD-3-Clause"`) are parsed,
  deduped, and canonically reordered via
  [`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license) (not
  the `license-expression` library originally envisioned here), so a
  casing difference or an equivalent-but-differently-written expression
  is never misreported as a conflict. The project directory
  (`CITATION.cff`, `codemeta.json`, `LICENSE` files) is independently
  scanned even when a license is already declared, uniformly across all
  four project-metadata extraction paths (CLI/library, Hatchling build
  hook, poetry-only, setuptools-only). On genuine disagreement, both
  `hasDeclaredLicense` and `hasConcludedLicense` are recorded alongside a
  generic `provenance/conflict/1` Annotation (reusable for any field, not
  license-specific). See
  [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md).
  ([PR #121](https://github.com/bact/pitloom/pull/121))
  Remaining, narrower scope than "PEP 639 compliance" originally implied:
  `[project.license-files]` (the glob-list field for bundling multiple
  license files) is not specifically parsed.
- [x] **Auto-sync the Loom ID registry after SBOM generation** -- `loom
  project`/`wheel`/`env` harvest newly-minted ids back into the resolved
  registry after each run (`--update-registry`/`--no-update-registry`, on
  by default), so a `project` -> `wheel` -> `env` pipeline keeps stable
  spdxIds with no manual `pitloom ids generate`/`import` step in between.
  `ai_AIPackage` and `dataset_DatasetPackage` are deliberately excluded --
  see [Loom IDs across fragments](../../README.md#loom-ids-across-fragments-pitloom-ids).
  Fixed along the way: `_add_package_files`'s registry lookup only tried
  `physical_path`, so a src/-layout project (`physical_path` !=
  `distribution_path`) never matched its own auto-harvested file entries --
  now falls back to `distribution_path`
  (`src/pitloom/assemble/spdx3/_document_files.py`). Open follow-ups: see
  [AI model id stability](#ai-model-id-stability-follow-up-to-178) and
  [Sort-order canonicalization](#sort-order-canonicalization-follow-up-to-178)
  below. ([PR #178](https://github.com/bact/pitloom/pull/178))

## Adoption surfaces

Pitloom's other surfaces (library API, CLI, Hatchling build hook, ML
tracking SDK) all assume the consumer already has Pitloom installed or
wired into a build backend. These two extend reach beyond that. See
[adoption-surfaces.md](../implementation/adoption-surfaces.md) for the
full picture.

- [x] **GitHub Action** (composite `action.yml`) -- generate an SBOM in CI
  with a single `uses:` line, for any Python project regardless of build
  backend. Dogfooded on Pitloom itself in
  `.github/workflows/action-selftest.yml`.
  See [github-action.md](../implementation/github-action.md).
- [x] **AI-agent Skills** (`skills/sbom-generate/`, `skills/sbom-enrich/`,
  `skills/sbom-validate/`) -- lets Claude Code, the Claude Agent SDK, or
  similar runtimes generate an SBOM on request, optionally enrich it
  (README/model-card inference contributed back as a provenance-marked
  fragment), and validate any SPDX 3 document's schema/shape conformance.
  Independently triggerable by natural language or explicit invocation.
  See [agent-skill.md](../implementation/agent-skill.md) and
  [sbom-enrichment.md](sbom-enrichment.md).
- [x] **Claude Code plugin** (`.claude-plugin/`) -- bundles all three
  Skills under the `pitloom` plugin namespace so they install with
  `/plugin install` directly from this repository, with namespaced
  explicit invocation (`/pitloom:sbom-generate`, `/pitloom:sbom-enrich`,
  `/pitloom:sbom-validate`). See
  [claude-code-plugin.md](../implementation/claude-code-plugin.md).
- [ ] **Docker container action** (future) -- a `Dockerfile` +
  `action.yml` `using: docker` variant of the GitHub Action for hermetic
  or self-hosted-runner use.
- [ ] **Surface `WARNING:`/`ERROR:` stderr as GitHub Actions annotations**
  (future) -- `action.yml`'s composite "Generate SBOM" step captures
  stdout only (`loom_stdout=$(loom "${loom_args[@]}" | tee /dev/stderr)`);
  a `loom`-emitted `WARNING:`/`ERROR:` (e.g. artifact-metadata truncation,
  see [metadata-provenance.md](../implementation/provenance/metadata-provenance.md))
  goes to the raw job log only, not the workflow-run summary or PR
  "Files changed" view (`::warning::`/`::error::` workflow commands).
  A synchronous `2>`-redirect-to-file approach is race-free but drops
  real-time log streaming; a `tee`-based approach needs a provably
  race-free wait, not just bash's default process-substitution
  behavior. Needs a design pass on that trade-off before implementing.
  Already done for AI-agent Skills -- see
  [agent-skill.md](../implementation/agent-skill.md#relaying-warningerror-stderr-to-the-user).

## Near-term

**Next up:**
[Non-Hatchling file discovery](#non-hatchling-file-discovery-feature-parity)
below -- a major feature-parity gap affecting the accuracy of `loom
project`'s file inventory for any non-Hatchling project. Setuptools
support (priority 1 below) is committed to the 0.16.2 release notes as
targeted for **0.17.0**; `uv_build`, Poetry, PDM-backend, and Flit-core
are named as "also in the plan" without a committed version yet.

### Non-Hatchling file discovery (feature parity)

- [ ] **`get_wheel_files()` file discovery is not backend-agnostic** --
  despite its generic name, `get_wheel_files()`
  (`src/pitloom/core/_models_wheel.py`) unconditionally instantiates
  Hatchling's own `WheelBuilder` to discover a project's files,
  regardless of the project's actual `[build-system] build-backend`.
  This is not merely "returns `None` for non-Hatchling projects" (the
  original framing of this item) -- confirmed by direct testing:
  - For a non-Hatchling project whose layout happens to match
    Hatchling's own auto-detection conventions (a single top-level
    package, or `src/<name>`, named after the normalized project name),
    it works by coincidence.
  - For a setuptools project using
    `[tool.setuptools.packages.find] where=` (or `MANIFEST.in`,
    `package_data`, or any other backend-specific inclusion rule
    Hatchling doesn't understand), it silently produces a **wrong** file
    list, not just a missing one -- confirmed with a `where = ["lib"]`
    setuptools layout: `get_wheel_files()` reported
    `lib/mypkg/__init__.py` as the distribution path (plus spurious
    directory-shaped entries) instead of the `mypkg/__init__.py` the
    actual wheel would contain.
  - The same applies to Poetry, PDM, and Flit projects with their own
    inclusion config -- this affects **any non-Hatchling backend**, not
    setuptools specifically.
  - Impact differs by command: `loom project`/`loom generate` (Source
    SBOM, directory target) has no wheel to fall back on, so the wrong
    file list, hashes, and Merkle-root integrity hash go straight into
    the SBOM. `loom embed-wheel --project-dir` is safer -- its
    `_merge_file_extras` step already keeps the real wheel's file
    list/hashes as truth (see the "Build backend improvements" Merkle
    root item below), so only `--content-type`/`--extract-file-header`
    enrichment silently fails to attach per mismatched file, degrading
    gracefully rather than corrupting the SBOM.
  - Project-level metadata (name, version, dependencies, license,
    authors) is unaffected -- `read_project()` resolves it independently
    of `get_wheel_files()` via Pitloom's own setuptools/Poetry
    extractors.
  Documented as a known limitation in [docs/cli.md](../../docs/cli.md)'s
  Source SBOM and embed-wheel sections. Fixing this needs a
  backend-aware file-discovery layer (dispatch on the declared
  `build-backend`) rather than always defaulting to Hatchling's own
  heuristics.

#### Backend priority

Two fundamentally different classes of backend, needing two different
fixes:

- **Track A -- static/declarative backends** (setuptools, Poetry,
  PDM-backend, Flit-core, `uv_build`): every file that ends up in the
  wheel already exists as a real file in `project_dir` before any build
  runs. A backend-aware rescan (read each backend's own inclusion
  config, walk the matching files) is correct and sufficient here --
  the same strategy `get_wheel_files()` already uses for Hatchling,
  just with each backend's own config format instead of
  `[tool.hatch.build...]`.
- **Track B -- compiled/native backends** (`maturin`,
  `scikit-build-core`, `meson-python`): the wheel's actual contents
  (compiled `.so`/`.pyd` extensions, platform-specific artifacts,
  generated files) do not exist as source files at all until the
  backend's own compiler toolchain runs. **No rescan of `project_dir`
  can ever discover these correctly, even in principle** -- this is
  the same "wheel truth vs. rescan" problem `_merge_file_extras`
  already solves for `embed-wheel`, but for Track B there is no static
  fallback at all. The only correct fix is a **build-and-read**
  mechanism: actually invoke the project's declared backend to produce
  a real wheel, then discover files by reading it with the existing
  `read_wheel()` -- the same function `embed-wheel` already trusts as
  ground truth. One implementation unlocks all three Track B backends
  at once (and doubles as a robustness fallback for Track A, and for
  any future/unrecognized backend), at the cost of actually running a
  build (slower, executes arbitrary build-time code, needs the
  backend's build dependencies installed) -- a real trade-off `loom
  project` doesn't currently make.

Priority order, weighing popularity, prevalence in AI/ML Python
projects, implementation size, and reuse leverage across backends:

| # | Backend | Track | Why this order |
| :-- | :--- | :--- | :--- |
| 1 | setuptools | A | Still the single most-installed backend, including plenty of legacy/established AI packages. Bounded but nontrivial effort (`packages.find`/`where`, `package_data`, `MANIFEST.in`). No reuse with anything else -- do it first because it's highest-value, not because it's cheap. |
| 2 | `uv_build` | A | Explicitly designed to be Hatchling-like (zero-config, sensible defaults) -- almost certainly the cheapest Track A backend to add given `get_wheel_files()`'s existing Hatchling-shaped logic, and it's the fastest-growing default for new pure-Python projects on the back of `uv`'s adoption curve. High effort-to-value ratio. |
| 3 | Poetry | A | Declarative `[tool.poetry]`/`packages`/`exclude` config, no build-time code execution to model. Pitloom already has a Poetry config reader (`src/pitloom/extract/_poetry.py`) to build on. Common in AI/ML research repos for reproducible environments. |
| 4 | PDM-backend, Flit-core | A | Bundle together -- both are simple, PEP 621-native, declarative (Flit's default is literally "bundle whatever Git tracks"). Smaller install base than 1-3, but nearly free once the Track A discovery pattern exists from steps 1-3, and already share a metadata-extractor item ("PDM / Flit extractors" under Medium-term) worth doing in the same pass. |
| 5 | Build-and-read fallback | (mechanism) | Not a backend -- the mechanism Track B requires. Medium effort, but the single highest-leverage item on this list: it's a prerequisite for all three Track B backends below, and a correctness safety net everywhere else. |
| 6 | `maturin`, `scikit-build-core` | B | Tied -- both are surging in the AI/ML stack specifically (Rust-based tooling via PyO3 for `maturin`; CUDA/C++/Fortran extensions for `scikit-build-core`), both need exactly the build-and-read mechanism from step 5, and neither is meaningfully cheaper or more valuable than the other. |
| 7 | `meson-python` | B | Same mechanism as step 6, but lower priority for Pitloom's own user base specifically: it's foundational to the AI/ML ecosystem (NumPy, SciPy) but those are far more often a Pitloom user's *dependency* than a project they're generating an SBOM for directly. |

Caveat: the research behind this ranking (see the conversation this
list came from) is qualitative, not install-count data -- re-validate
popularity/AI-relevance claims against PyPI download stats or a
dependency survey before treating the exact ordering as authoritative,
especially for `uv_build` vs. Poetry vs. PDM/Flit-core, which are close
enough that new data could reorder them.

### Build backend improvements

- [ ] **PEP 517 `prepare_metadata_for_build_wheel`** (opt-in) -- call the build
  backend in a subprocess to resolve dynamic metadata (Git-tag versions,
  computed deps) that static parsing cannot handle.
  See [metadata-sources.md](metadata-sources.md).
- [ ] **Setuptools wheel file discovery** -- use setuptools' own file inclusion
  logic for setuptools projects instead of Hatchling's `WheelBuilder`
  (see "Non-Hatchling file discovery" above for the full scope of why
  this is needed -- it's not just about the Merkle root).
- [ ] **`get_wheel_files()` option to skip Merkle root computation** --
  `_build_sbom_from_project_and_wheel` (`src/pitloom/embed.py`) already
  discards `get_wheel_files()`'s own `merkle_root` return value in favor
  of one computed from the wheel's own (post-merge) file hashes (see
  `_compute_wheel_merkle_root`), so that work is wasted for its one
  current caller. Worth adding only when both `extract_file_header` and
  `content_type` are off too -- otherwise every file's bytes get read
  off disk anyway for header/content-type scanning, and skipping just
  the hash/tree-build step on top of bytes already in memory saves
  little. With both scanners off, though, `get_wheel_files()` currently
  reads every file's full bytes solely to hash them for the discarded
  root -- real, avoidable I/O for large projects.
- [ ] **Installed `.dist-info` / `.egg-info` as metadata source** -- treat
  an existing installed package as a high-fidelity source when present
  (editable installs, virtual environments).
  See [metadata-sources.md](metadata-sources.md).

### PEP 770 / embed-wheel

- [ ] **`loom embed-wheel --verify`** -- check that a wheel's embedded SBOM
  is at the correct `.dist-info/sboms/<basename>` location and passes
  schema/SHACL validation, as a single CLI command. Right now
  `.github/workflows/pypi-publish.yml`'s "Check SBOM is at the PEP 770
  location" step hand-rolls this in bash (`unzip -Z1` + a glob match)
  against the same path convention `pitloom._embed_wheel._plan_embed`
  already encodes in Python, plus a separate `spdx3-validate` call -- two
  independently-maintained representations of one convention that could
  drift if `_plan_embed`'s layout ever changes. A `--verify` flag would
  consolidate both checks into the tool itself, reusable by any CI
  pipeline (not just this repo's own release workflow) without
  reimplementing the path convention.
  Since `spdx3-validate` 0.0.7, it's usable as a Python library, not just
  a CLI -- see
  <https://github.com/JPEWdev/spdx3-validate#using-as-a-library> --
  `--verify` could call it in-process instead of shelling out, avoiding a
  second subprocess/dependency-install step in CI.

### AI model id stability (follow-up to [#178](https://github.com/bact/pitloom/pull/178))

- [ ] **Deterministic same-model identification for auto-harvest** --
  `ai_AIPackage` elements are currently excluded from the Loom ID
  registry's auto-harvest (`_sync_registry` in
  `src/pitloom/assemble/_generators.py`) because `ai_model.name` is
  extraction-dependent (varies with whether `ai` extras are installed),
  so a name-keyed harvest would write entries that never match
  `_lookup_ai_model_entity`'s lookup candidates. The only currently-stable
  path is the extras-free, filename-stem-keyed `pitloom ids generate`.
  Revisit whether auto-harvest can be safely extended once there's a
  reliable way to say "this is the same model I saw last time":
  - **Content hash (SHA-256 of the raw model file bytes)** is the
    mechanism already used for regular files (`register_file`/
    `lookup_file`) and would be directly reusable -- `IdRegistry.generate()`
    already computes this hash for every file, AI models included,
    before separately doing the stem-based registration. The blocker is
    that `_lookup_ai_model_entity()` never tries a hash-based lookup
    against `registry.files`, only name/path/stem candidates against
    `registry.entities`; and the harvest side would need the model's
    hash reachable from the `ai_AIPackage` element at harvest time, not
    just on a separately-linked `software_File`.
  - **Caveat**: content hash is strictly *narrower* than "same model" for
    AI models, unlike source files where any byte change legitimately
    means "different provenance." A model re-exported, re-quantized, or
    re-saved with a different serialization -- or retrained
    non-deterministically from the same recipe -- changes every byte
    without changing what a person would call "the same model."
    Content-hash matching would under-match (mint a new id) in exactly
    the cases stability matters most. Source files don't have this
    problem; AI model files might.
  - **"Machine ID" scoping idea**: record a randomly-generated (not
    identifying) machine tag in `loom-ids.json` itself, so the registry
    can distinguish "these runs are from the same working environment
    across time" from "these came from different machines/CI runners,"
    without claiming any actual machine identity. This addresses a
    different axis than the matching criterion above -- how much a match
    should be *trusted* -- rather than what counts as a match. Loose
    heuristic matching (e.g. same relative path, ignore content) might be
    acceptable within one developer's local iteration loop but unsafe
    once a registry is shared, committed, or consulted from CI. Not yet
    clear whether this is needed at all once the content-hash caveat
    above is settled, or how the two ideas would interact.
  No implementation direction chosen yet -- open design question, not a
  committed plan.

### Sort-order canonicalization (follow-up to [#178](https://github.com/bact/pitloom/pull/178))

- [ ] **Audit where element/entry sort order feeds hash or id construction.**
  While fixing [#178], `IdRegistry.import_sbom()`/`harvest()` had a
  double-sort bug (sorted twice, redundant but harmless) consolidated into
  one shared `_sorted_by_spdx_id()` helper (`src/pitloom/ids.py`). That
  particular sort doesn't feed a hash today, but the SBOM output spec
  (top of this doc: bit-for-bit determinism, RFC 8785 JSON
  canonicalization) means *some* sort orders in this codebase do
  eventually feed content that's hashed or id-derived. No incident here --
  just a reminder to check, next time a sort is touched near
  `generate_spdx_id`/hashing/serialization, whether its order is load-bearing
  for determinism (and if so, whether it's documented as such) rather than
  assuming it's cosmetic.

### Extractors

- [ ] **Additional AI model format extractors**
  - JAX (Orbax checkpoints) -- higher priority
  - TensorFlow SavedModel and TensorFlow Lite
  - Scikit-learn (pickle/joblib; no single standard format -- complex)
  - See [model-metadata-extraction.md](model-metadata-extraction.md)
- [ ] **Dataset-to-model relationship linking** -- extend `AiModelMetadata`
  with dataset references; emit SPDX 3 relationship types (`trainedOn`,
  `testedOn`, `finetunedOn`, `validatedOn`, `pretrainedOn`).
  See [sbom-enrichment.md](sbom-enrichment.md).

### Metadata quality

- [ ] **`[project.license-files]` support** -- PEP 639's glob-list field
  for bundling multiple license files (narrower remainder of the old
  "License expression support" item -- expression parsing/normalization
  and conflict detection shipped, see Completed above).
- [ ] **Enhanced dependency analysis** -- transitive dependencies, optional
  extras, development dependencies.
- [x] **SBOM enrichment from external sources** (the `enrich/` subpackage)
  -- MVP shipped: local README/model-card **YAML frontmatter** parsing
  (`enrich/readme.py`, license + dataset gaps only, not prose), gated by
  `[tool.pitloom] enrich` (**default off** -- opt-in until more
  sources ship). Not to be confused with the agent-facing `sbom-enrich`
  *Skill* above -- this is code-level, deterministic, non-agent. Also
  what [use-case-catalog.md](../implementation/provenance/use-case-catalog.md)'s
  N3 ("who/when enriched") needed to exist first -- now shipped too, see
  its own entry there.
  Exposed as a first-class capability across every generation surface,
  not just `generate_model_sbom()`: a standalone `loom enrich`
  CLI/`enrich_model()` API (writes a mergeable fragment, no full SBOM),
  `--enrich`/`--no-enrich` on `loom model`/`loom project`/`loom generate`,
  project-level enrichment for every AI model `loom project`/`loom
  generate` discovers (previously silently skipped), automatic
  inheritance in the Hatchling build hook, and a `enrich` input on the
  GitHub Action. See [sbom-enrichment.md](sbom-enrichment.md)'s
  "Surfaces" section.
  Still not started: OpenSSF Scorecard (public API), Hugging Face Hub and
  PyPI metadata (user opt-in), per-source enable/disable via additional
  `[tool.pitloom]` enrich-related keys added when each lands (`enrich`
  itself is a flat bool now, not a table -- a per-source toggle scheme
  will need its own naming, decided when the first extra source ships).
  See [sbom-enrichment.md](sbom-enrichment.md).

## Medium-term

- [ ] **CycloneDX assembler** -- add a CycloneDX serializer consuming the
  existing `DocumentModel`; no changes to extractors required.
- [ ] **AIDOC / TechOps renderer** -- additional output format consuming
  `DocumentModel`.
- [ ] **Build log extraction** -- capture compiled dependencies, linker flags,
  and bundled libraries from build output logs.
- [ ] **PDM / Flit extractors** -- extend `detect_build_backend()` and
  add per-backend extractor functions following the same
  `read_X() -> (ProjectMetadata, PitloomConfig)` pattern. Worth pairing
  with PDM/Flit-core's Track A file-discovery work (see
  "Non-Hatchling file discovery" under Near-term) in the same pass --
  metadata extraction and file discovery are separate concerns but the
  same backends.

## Long-term

- [ ] **PEP 740 attestations** -- cryptographic signing and provenance
  tracking for generated SBOMs.
- [ ] **Performance optimization** -- Rust backend for large-project
  log parsing; parallel file hashing for Merkle root computation.
