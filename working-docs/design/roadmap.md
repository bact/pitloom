---
Created: 2026-04-14
Last-Modified: 2026-09-01
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

## Completed

Implementation detail for each item below (design decisions, function
names, PR links) lives in `working-docs/implementation/` where noted --
read the code/that doc for current state rather than this list, which
is not kept in sync with post-ship changes.

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
  (`src/pitloom/extract/_setuptools.py`; `pyproject.toml` > `setup.cfg` >
  `setup.py` conflict resolution)
- [x] Poetry support -- initial implementation
  (`src/pitloom/extract/_poetry.py`; `read_pyproject()` falls back to
  `[tool.poetry]` when `[project]` is absent, merges both when present)
- [x] **PDM-backend and Flit-core support** -- metadata extraction
  (`src/pitloom/extract/_pdm.py`, `_flit.py`: dynamic `version`/
  `description` resolved via each backend's own logic --
  `[tool.pdm.version]`'s `file`/`scm` sources, Flit's module
  `__version__`/docstring convention) and wheel file discovery
  (`src/pitloom/core/_models_wheel_pdm.py`, `_models_wheel_flit.py`),
  wired into `read_pyproject()` and `_models_wheel.py`'s
  `backend_discoverers` registry. See
  [backend-file-discovery-validation.md](../implementation/backend-file-discovery-validation.md)'s
  Flit-core/PDM-backend round.
- [x] **Multiple creators / tools per `CreationInfo` record** -- `Creator`/
  `Tool` dataclasses, repeatable `--creator-name`/`--creation-tool`,
  array-of-tables config. See [creation-metadata.md](../../docs/creation-metadata.md).
- [x] **SPDX license expression normalization and declared-vs-detected
  conflict detection (G2)** -- via [`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license).
  Remaining, narrower scope: `[project.license-files]` (PEP 639 glob-list
  for bundling multiple license files) not specifically parsed -- tracked
  under Metadata quality below.
  See [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md)
  ([PR #121](https://github.com/bact/pitloom/pull/121)).
- [x] **Auto-sync the Loom ID registry after SBOM generation** -- `loom
  project`/`wheel`/`env` harvest newly-minted ids back into the resolved
  registry after each run. `ai_AIPackage`/`dataset_DatasetPackage`
  deliberately excluded -- see
  [Loom IDs across fragments](../../README.md#loom-ids-across-fragments-pitloom-ids).
  Open follow-ups: [AI model id stability](#ai-model-id-stability-follow-up-to-178),
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
  backend. See [github-action.md](../implementation/github-action.md).
- [x] **AI-agent Skills** (`skills/sbom-generate/`, `skills/sbom-enrich/`,
  `skills/sbom-validate/`) -- generate/enrich/validate an SBOM on
  request from Claude Code, the Claude Agent SDK, or similar runtimes.
  See [agent-skill.md](../implementation/agent-skill.md) and
  [sbom-enrichment.md](sbom-enrichment.md).
- [x] **Claude Code plugin** (`.claude-plugin/`) -- bundles all three
  Skills under the `pitloom` plugin namespace (`/plugin install`,
  `/pitloom:sbom-generate` etc). See
  [claude-code-plugin.md](../implementation/claude-code-plugin.md).
- [ ] **Docker container action** (future) -- a `Dockerfile` +
  `action.yml` `using: docker` variant of the GitHub Action for hermetic
  or self-hosted-runner use.
- [ ] **SARIF output** (replaces the earlier `::warning::`/`::error::`
  annotation idea below) -- emit a SARIF file as a build artifact,
  uploaded via a separate `github/codeql-action/upload-sarif` step.
  Sidesteps the streaming/race problem that stalled the
  workflow-command approach entirely: SARIF is written synchronously
  once `loom` finishes, then uploaded as its own step -- no `tee`/
  process-substitution race to prove free of. Gets PR "Files changed"
  inline annotations and a GitHub Security-tab view for free, no custom
  UI work. Findings sources to map, once each exists:
  - Every `WARNING:`/`ERROR:` a `loom` run emits today (e.g.
    artifact-metadata truncation, see
    [metadata-provenance.md](../implementation/provenance/metadata-provenance.md))
    -- already done for AI-agent Skills, see
    [agent-skill.md](../implementation/agent-skill.md#relaying-warningerror-stderr-to-the-user).
  - OSV.dev vulnerability lookup (Near-term / Metadata quality, once
    built) -- one SARIF `result` per CVE (`ruleId=CVE-xxxx`,
    `level=`severity, location = the dependency's declaration line in
    `pyproject.toml`).
  - Declared-vs-detected license conflicts (already shipped, see
    [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md),
    [PR #121](https://github.com/bact/pitloom/pull/121)) -- currently a
    warning message only, would become an inline PR annotation on the
    license line.
  Not an SBOM format -- SARIF is a diagnostics/findings interchange
  format, unrelated to the CycloneDX assembler item (Medium-term);
  the two don't overlap or compete.

## Near-term

**Next up:**
[Non-Hatchling file discovery](#non-hatchling-file-discovery-feature-parity)
below -- a major feature-parity gap affecting the accuracy of `loom
project`'s file inventory for any non-Hatchling project. Setuptools,
Poetry, PDM-backend, and Flit-core support (priorities 1-3 below) are
done; `uv_build` is next, named as "also in the plan" without a
committed version yet.

### Non-Hatchling file discovery (feature parity)

- [ ] **`get_wheel_files()` file discovery is not backend-agnostic** --
  **partially fixed (2026-08-27):** `get_wheel_files()`
  (`src/pitloom/core/_models_wheel.py`) is now a dispatch facade over
  one discovery module per backend (`_models_wheel_hatchling.py`,
  `_models_wheel_setuptools.py`, `_models_wheel_poetry.py`), with any
  backend that doesn't have a dedicated module yet (PDM, Flit,
  `uv_build`, ...) falling back to the Hatchling heuristic -- now with
  a logged warning instead of silently risking an inaccurate result.
  Setuptools and Poetry were the first two backends closed; the bug
  below (originally reported for setuptools) still stands as
  documentation for every backend still on the fallback path. See
  [sbom-lifecycle-stages.md](../implementation/sbom-lifecycle-stages.md)
  for the mechanism and why this stays a static-config read for every
  backend, never a build. Confirmed by direct testing before the fix:
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
  - The same applied to Poetry (now closed -- see below) and still
    applies to PDM and Flit projects with their own inclusion config --
    this affects **any non-Hatchling backend** without a dedicated
    module, not setuptools specifically.
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
  **Real-world validation policy:** every backend's `discover()` (this
  one and Hatchling's) is checked against at least 10 diverse real
  PyPI packages -- not just synthetic fixtures -- before being
  considered production-ready; see
  [backend-file-discovery-validation.md](../implementation/backend-file-discovery-validation.md)
  for the method and the setuptools/Hatchling results so far. Apply the
  same bar to each backend below as it's implemented.

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

#### Dependency packaging strategy

Decided 2026-08-31, after Poetry (item #2) shipped and raised the
question directly: as the number of Track A/B backend libraries grows,
should any become optional extras (mirroring the `ai`/`content-type`
extras) instead of hard `dependencies`?

Checked first: metadata extraction never imports the real
`setuptools`/`poetry-core`/`hatchling` packages at all -- `_setuptools.py`,
`_poetry.py`, and `hatchling.py` are self-contained TOML/AST parsers.
Only the three file-discovery modules (`_models_wheel_setuptools.py`,
`_models_wheel_poetry.py`, `_models_wheel_hatchling.py`) import the real
libraries, and every one of those imports is already function-local/lazy.
So the question is narrower than "make backend support optional" -- it's
specifically about the libraries backing *file-discovery accuracy*,
never metadata.

- **Track A (setuptools, Poetry, PDM-backend, Flit-core) stays mandatory
  for now.** Unlike `ai`/`content-type`, which gate
  *opt-in* features a user explicitly requests, backend detection isn't
  opt-in: `loom project .` inspects whatever `pyproject.toml` says, and
  the user can't know in advance which backend a target project uses.
  Making these optional would mean a bare `pip install pitloom`
  silently degrades to the Hatchling-heuristic fallback (with a
  `WARNING:`, not silently wrong -- but still a worse default) for a
  large fraction of real-world targets, not a niche one. Each library
  is also individually lightweight and low-risk (poetry-core is a
  ~370KB pure-Python wheel; setuptools ships in most environments
  already) -- nothing like `ai`'s heavy, mutually-exclusive ML
  dependencies (numpy/onnx/safetensors/fasttext). Hatchling itself was
  never a candidate either way: it's already required to build Pitloom
  itself (`[build-system] requires`), so it's free regardless.
  **Revisit if Track A's mandatory footprint grows enough to matter**
  (more backends landing, or an individual library turning out heavier
  than expected) -- if/when it's worth splitting, bundle them under one
  umbrella extra (e.g. `pitloom[backends]`), not one extra per backend:
  per-backend extras multiply combinatorially as Track A grows and cost
  real install-instruction complexity for little benefit, since a user
  scanning a mixed-backend fleet needs all of them anyway.
- **Track B (`maturin`, `scikit-build-core`, `meson-python`,
  build-and-read), once implemented, should be an optional extra from
  the start.** These pull in real compiler toolchains (Rust for
  `maturin`, CMake/Ninja-adjacent tooling for `scikit-build-core`,
  Meson/Ninja for `meson-python`) -- a categorically heavier,
  environment-specific dependency than Track A's static introspection,
  much closer in kind to why `ai` was split out. This is already
  implicit in the build-and-read trade-off noted above (item #4); this
  decision makes explicit that the mechanism's dependencies, not just
  its runtime behavior, should be opt-in.

Priority order, weighing popularity, prevalence in AI/ML Python
projects, implementation size, and reuse leverage across backends:

| # | Backend | Track | Why this order |
| :-- | :--- | :--- | :--- |
| 1 | setuptools | A | **Done (2026-08-27).** Was the single most-installed backend with no dedicated support; now resolved via `setuptools.config.pyprojecttoml`/`setupcfg` + `build_py` introspection (`src/pitloom/core/_models_wheel_setuptools.py`). See [setuptools-support.md](../implementation/setuptools-support.md). |
| 2 | Poetry | A | **Done (2026-08-31).** Declarative `[tool.poetry]`/`packages`/`exclude` config, no build-time code execution to model -- resolved by delegating to poetry-core's own `WheelBuilder.find_files_to_add()` (`src/pitloom/core/_models_wheel_poetry.py`), the same delegate-to-the-real-library pattern as Hatchling's module (poetry-core is fully declarative, unlike setuptools). Also gained `poetry.lock`-resolved transitive dependencies (source-stage only) as an additional parity item beyond the original file-discovery scope. |
| 3 | PDM-backend, Flit-core | A | **Done (2026-09-02).** Both PEP 621-native and declarative -- resolved via `Builder.get_files()`/`WheelBuilder._collect_files()` for PDM-backend (`src/pitloom/core/_models_wheel_pdm.py`) and `flit_core.common.Module.iter_files()` for Flit-core (`src/pitloom/core/_models_wheel_flit.py`), the same delegate-to-the-real-library pattern as Poetry's module. Also closed the paired "PDM / Flit extractors" metadata item from Medium-term in the same pass (`pitloom.extract._pdm`/`_flit`, dynamic `version`/`description` resolution). See [backend-file-discovery-validation.md](../implementation/backend-file-discovery-validation.md)'s Flit-core/PDM-backend round. |
| 4 | Build-and-read fallback | (mechanism) | Not a backend -- the mechanism Track B requires. Moved up from its original slot (was 5): `uv_build` (next row) is now expected to consume this mechanism too, not just the three Track B backends, so it's a prerequisite for step 5 as well as steps 6-7. Medium effort, the single highest-leverage item on this list. |
| 5 | `uv_build` | A (via build-and-read) | `uv_build` (PyPI package `uv_build`) is a thin PEP 517 shim that shells out to a compiled `uv-build` binary via subprocess, with no in-process introspection API comparable to Hatchling's `WheelBuilder`. No existing logic to adapt for a hand-rolled rescan, so the practical path is the build-and-read mechanism (step 4) rather than a Track A rescan, despite files existing pre-build in principle. Still the fastest-growing default for new pure-Python projects on `uv`'s adoption curve, so kept ahead of the Track B backends -- just moved behind the mechanism it now depends on, and behind the genuinely cheap Track A items (2-3). |
| 6 | `maturin`, `scikit-build-core` | B | Tied -- both are surging in the AI/ML stack specifically (Rust-based tooling via PyO3 for `maturin`; CUDA/C++/Fortran extensions for `scikit-build-core`), both need exactly the build-and-read mechanism from step 4, and neither is meaningfully cheaper or more valuable than the other. |
| 7 | `meson-python` | B | Same mechanism as step 6, but lower priority for Pitloom's own user base specifically: it's foundational to the AI/ML ecosystem (NumPy, SciPy) but those are far more often a Pitloom user's *dependency* than a project they're generating an SBOM for directly. |

Caveat: the research behind this ranking (see the conversation this
list came from) is qualitative, not install-count data -- re-validate
popularity/AI-relevance claims against PyPI download stats or a
dependency survey before treating the exact ordering as authoritative.
The `uv_build` correction above (2026-08-27) is a concrete example of
this ranking shifting once real API/implementation research replaced
the original qualitative assumption.

**Architecture note (2026-08-27):** closing item #1 (setuptools) also
restructured `get_wheel_files()` into a per-backend module + registry
(`src/pitloom/core/_models_wheel.py` dispatches to
`_models_wheel_<backend>.py` siblings, each exposing one `discover()`
function). Item #2 (Poetry) confirmed the pattern holds for a
delegate-to-the-real-library backend too, not just setuptools'
hand-rolled one. Item #3 (PDM-backend, Flit-core) confirmed it again
for two more delegate-to-the-real-library backends -- one new
`_models_wheel_<backend>.py` module + one registry entry each, no
changes needed to the facade's dispatch logic, the shared per-file
processing loop, or any of `get_wheel_files()`'s callers. PDM-backend
was the first backend since setuptools to need `_WRITER_BACKENDS`'
process-wide `os.chdir()` (its own package auto-discovery globs
relative to the process cwd, not the `Builder`'s `location`). `uv_build`
(item #5) still needs the build-and-read mechanism (item #4) rather
than this pattern.

### Build backend improvements

- [ ] **PEP 517 `prepare_metadata_for_build_wheel`** (opt-in) -- call the build
  backend in a subprocess to resolve dynamic metadata (Git-tag versions,
  computed deps) that static parsing cannot handle.
  See [metadata-sources.md](metadata-sources.md).
- [x] **Setuptools wheel file discovery** -- setuptools' own official
  config-resolution API (`setuptools.config.pyprojecttoml`/`setupcfg`)
  and `build_py` introspection now resolve a setuptools project's file
  set from static config, instead of Hatchling's `WheelBuilder`. See
  [setuptools-support.md](../implementation/setuptools-support.md) and
  [sbom-lifecycle-stages.md](../implementation/sbom-lifecycle-stages.md).
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
  See [metadata-sources.md](./metadata-sources.md).
- [x] **`poetry.lock`** -- done (2026-08-31): `loom project`/`loom generate`
  against a Poetry project now reads a sibling `poetry.lock` (when
  present) for its `main`-group resolved transitive dependencies
  (`pitloom.extract._poetry_lock`), additive to the direct
  `[tool.poetry.dependencies]` constraints, with its own provenance tag
  and `RelationshipCompleteness.complete` marking on the additive
  `dependsOn` edges. Scoped source-stage-only (never `loom wheel`/
  `embed-wheel`/`loom env`) -- poetry-core's build backend never reads
  `poetry.lock` itself, only the separate `poetry install` CLI command
  does.
- [ ] **Remaining lock formats as a resolved-dependency source**
  (`Pipfile.lock`, `uv.lock`, pinned `requirements.txt`) -- `loom
  project` still records only the declared version specifier from
  `pyproject.toml [project] dependencies`
  (`normalize_dependency_specifier`, `src/pitloom/extract/_pyproject.py:220`,
  e.g. `requests>=2.0`) for every non-Poetry project, never a concrete
  resolved version. Parsing one when present would let a Source SBOM
  carry the actual pinned version a build will use, not just the
  declared range -- closer to what CISA's Source SBOM guidance expects.
  The `poetry.lock` case above establishes the pattern (additive
  transitive-only edges, `completeness` tagging, source-stage-only
  scoping); needs a source-priority decision analogous to
  `metadata-sources.md`'s existing tiering (which lock file wins if more
  than one is present) and a provenance `method` tag per lock format.
  See [lock-files.md](./lock-files.md) for the broader multi-format
  extraction-priority roadmap (PEP 751 `pylock.toml`, `uv.lock`,
  `pixi.lock`, `conda-lock.yml`, `pdm.lock`, `Pipfile.lock`) this item
  now defers to.

### PEP 770 / embed-wheel

- [x] **`loom verify-wheel` / `loom validate-wheel`** ([#202](https://github.com/bact/pitloom/pull/202))
  -- check that a wheel's embedded SBOM is at the correct
  `.dist-info/sboms/<basename>` location and, separately, passes
  schema/SHACL validation. Shipped as two flat subcommands rather than the
  `--verify` flag originally sketched here: `verify-wheel` (structural,
  format-neutral -- location + recommended-extension check) and
  `validate-wheel` (content, SPDX3-only today -- schema/SHACL via
  `spdx3-validate`'s library API), reusing
  `pitloom._wheel_sbom_location.find_embedded_sbom()` for the shared
  location logic and `pitloom.cli.commands.utils._validate_spdx3_documents()`
  (also now backing `pitloom fragment validate`) for the shared validation
  path. `embed-wheel` gained `--verify`/`--validate` convenience flags
  that run the same checks against the wheel just embedded, mirroring how
  `wheel --embed` already chains into a shared function rather than
  duplicating logic. Replaces `.github/workflows/pypi-publish.yml`'s
  hand-rolled bash `unzip -Z1` + glob-match location check and its
  separate `spdx3-validate --json` shell-out.
- [x] **`verify-wheel` name/version cross-check** -- an embedded SBOM's
  declared subject `name`/`software_packageVersion` (SPDX3 JSON-LD only)
  is now cross-checked against the wheel's own `.dist-info/METADATA`
  `Name`/`Version`, PEP 503/440-normalized. Lives in `verify-wheel`
  (`src/pitloom/cli/commands/verify_wheel.py`) rather than
  `embed_wheel_sbom`, since it covers every embedding path, not just
  `--sbom`-supplied SBOMs. Default severity `WARNING:` (exit 0); the new
  `--fail-on-mismatch` flag makes it `ERROR:` (exit 1). Shared helpers:
  `read_wheel_name_version` (`src/pitloom/_wheel_sbom_location.py`, also
  now used by `_derive_wheel_sbom_filename`,
  `src/pitloom/_embed_wheel.py:149-166`, replacing its previously-inlined
  METADATA parse), `extract_spdx3_subject_identity`, and
  `check_spdx3_name_version` (both `src/pitloom/_sbom_format.py`).
- [x] **`embed-wheel --sbom` pre-embed name/version enforcement** --
  building on the `verify-wheel` cross-check above (which only catches
  a mismatch post-hoc, and only if someone runs it), `embed_wheel_sbom()`
  (`src/pitloom/embed.py`, `_enforce_sbom_name_version`) now cross-checks
  an externally-supplied `--sbom`'s declared name/version against the
  target wheel's own METADATA *before* anything is written. A mismatch
  raises `ValueError` and aborts the embed (exit 1, nothing written) by
  default; the new `--allow-mismatch` flag downgrades it to `WARNING:`
  and embeds anyway (CI/best-effort use case). A Pitloom-generated SBOM
  (no `--sbom`) is never checked -- it's built from the same wheel
  metadata, so it can't diverge. `embed-wheel --verify` was also fixed to
  actually run the name/version check (it previously called
  `_check_location` directly, bypassing it entirely) -- always
  non-fatal there, matching `--verify`'s existing severity contract.

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

- [x] **Audit where element/entry sort order feeds hash or id construction.**
  Audited every `sorted()`/`.sort()` call in the assemble/id-registry
  path. Findings, made explicit in code rather than left as a roadmap
  note: `_sorted_by_spdx_id()` (`src/pitloom/ids.py`) is *not* canonical
  -- it only orders `IdRegistry` bookkeeping, never hashed/serialized
  SBOM content, and its docstring now says so. The genuinely load-bearing
  one, formerly `_stable_key()` in
  `src/pitloom/assemble/spdx3/_fragments_unify.py`, was renamed to
  `_canonical_merge_key()` with a docstring explaining that its order
  decides which duplicate element survives fragment unification --
  changing it changes SBOM output content. `provenance.py`'s
  `sorted()` calls feeding annotation `statement` arrays, and
  `_document_files.py`'s `summary_entries.sort()`, are also canonical
  (RFC 8785 canonicalizes JSON object-member order but not array order)
  and are now commented as such at each site. No behavior changed;
  `_sorted_by_spdx_id` vs `_canonical_merge_key` intentionally stay
  separate helpers -- they sort different things for different reasons
  and share no key strategy worth unifying.

### Extractors

- [ ] **Additional AI model format extractors**
  - JAX (Orbax checkpoints) -- higher priority
  - TensorFlow SavedModel and TensorFlow Lite
  - Scikit-learn (pickle/joblib; no single standard format -- complex)
  - See [model-metadata-extraction.md](model-metadata-extraction.md)
- [x] **Dataset-to-model relationship linking** -- `AiModelMetadata` carries
  dataset references (`DatasetReference`, `pitloom.core.dataset_metadata`);
  `add_datasets_for_model()` (`src/pitloom/assemble/spdx3/dataset.py`)
  emits `trainedOn`/`testedOn` `Relationship`s natively, falling back to
  `RelationshipType.other` + an explanatory comment for the three SPDX
  3.0.1 lacks (`finetunedOn`, `validatedOn`, `pretrainedOn`). Wired in from
  `assemble/spdx3/ai.py` and `_document_model.py`. See
  [sbom-enrichment.md](sbom-enrichment.md).
- [ ] **Croissant dataset size calculation** -- `dataset_DatasetSize` is
  currently always `0` (see `_extract_croissant_core_fields()` in
  `_croissant.py`); needs real logic summing `cr:totalItems` across
  `cr:recordSet` entries (and handling the string-vs-int value variance
  seen in real Croissant files).

### Metadata quality

- [ ] **Revise and publish the provenance/enrichment vocabulary reference**
  -- [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md)
  is currently "draft, parked for later review": a full-repo vocabulary
  inventory (`method`/`role`/Annotation kinds/dataset relationship
  roles/minimum-elements gap status) and a drafted `docs/vocabulary.md`
  page were written, then reverted out of `docs/` per the user's request
  (one independent bug fix kept -- see that file's "Already applied").
  Revising the `role`/`method` taxonomies themselves is planned next;
  once settled, publish the reference page and update every place that
  currently documents this vocabulary ad hoc (`docs/metadata-provenance.md`,
  the `sbom-enrich` Skill's own conventions, `working-docs/implementation/
  provenance/annotation-provenance-full-plan.md`'s older/duplicate
  taxonomy shape) so there is one canonical source instead of several
  independently-maintained copies.
- [ ] **Generalize multi-source conflict detection beyond license**
  (priority) -- `build_conflict_annotation`
  (`src/pitloom/assemble/spdx3/provenance.py:169`) is the only place the
  `conflict` Annotation kind (Section 5.7/G2,
  [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md))
  is constructed, and it has exactly one caller:
  `src/pitloom/assemble/spdx3/deps_license.py:256`. The independent-detection
  vs. declared-value comparison mechanism this implements is general --
  obtain a fact two independent ways, normalize, compare, emit `conflict`
  only on genuine disagreement -- but today it exists for license only.
  Dependency version (declared specifier vs. lock-file-resolved version,
  once the lock file item above ships) is the most obvious next
  candidate: the same "don't let two sources silently disagree" argument
  applies, and the comparison/normalization scaffolding already built for
  license is largely reusable.
- [ ] **`[project.license-files]` support** -- PEP 639's glob-list field
  for bundling multiple license files (narrower remainder of the old
  "License expression support" item -- expression parsing/normalization
  and conflict detection shipped, see Completed above).
- [ ] **Enhanced dependency analysis** -- transitive dependencies, optional
  extras, development dependencies.
- [x] **SBOM enrichment from external sources** (the `enrich/` subpackage)
  -- MVP shipped: local README/model-card YAML frontmatter parsing,
  gated by `[tool.pitloom] enrich` (default off). Code-level and
  deterministic -- distinct from the agent-facing `sbom-enrich` Skill
  above. Exposed across every generation surface (`loom enrich` CLI,
  `--enrich`/`--no-enrich` flags, Hatchling build hook, GitHub Action
  input). Still not started: OpenSSF Scorecard, Hugging Face Hub and
  PyPI metadata sources, per-source enable/disable config.
  See [sbom-enrichment.md](sbom-enrichment.md).
- [ ] **OSV.dev vulnerability lookup** (`--enrich-cve` or similar) -- ping
  [OSV.dev](https://osv.dev)'s API to append known vulnerabilities
  against generated Python dependencies. Static enrichment only (no
  exploitability judgement) -- see VEX generation under Medium-term for
  the follow-on triage step. Needs a caching/rate-limit design per
  "Resource efficiency" in `AGENTS.md` before landing.

### Diagnostics / logging

- [x] **Surface `DEBUG:`-level output on request** -- shipped both
  triggers rather than choosing one: a new top-level `--debug` flag
  (parsed before the subcommand, like `-V`; `cli/verbose.py`'s existing
  `--verbose` was left alone since it does something unrelated) and the
  `PITLOOM_DEBUG` environment variable, which also covers entry points
  that don't parse CLI flags themselves (the Hatchling build hook, every
  public library-API generator). `configure_logging(debug=...)`
  resolves `None` (every existing no-argument call site) against the
  env var; an explicit `True`/`False` (the CLI's `--debug`) wins outright.
  See `pitloom.logging_config`. ([PR #201](https://github.com/bact/pitloom/pull/201))
- [x] **Promote silent-data-loss `DEBUG:` messages to `WARNING:`** --
  18 messages across the HF Hub, PyTorch/PT2, fastText, README
  enrichment, and sdist extractors, plus `pitloom.loom` caller-provenance
  detection, now surface by default (not just under `--debug`) when a
  failure drops or degrades an SBOM/AIBOM field. Each names the affected
  field(s) via one shared, grep-able helper, `field_loss_suffix()`
  (`pitloom.logging_config`), instead of hand-duplicated suffix text per
  call site. ([PR #201](https://github.com/bact/pitloom/pull/201))

## Medium-term

- [ ] **CycloneDX assembler** -- add a CycloneDX serializer consuming the
  existing `DocumentModel`; no changes to extractors required.
- [ ] **AIDOC / TechOps renderer** -- additional output format consuming
  `DocumentModel`.
- [ ] **Build log extraction** -- capture compiled dependencies, linker flags,
  and bundled libraries from build output logs.
- [ ] **VEX (VEX/OpenVEX) generation** -- consumes the OSV.dev lookup
  above (once it exists) to classify a component as affected/
  not_affected/fixed/under_investigation, rather than just listing raw
  CVE hits. Depends on the OSV enrichment item under Near-term /
  Metadata quality landing first.

## Long-term

- [ ] **PEP 740 attestations** -- cryptographic signing and provenance
  tracking for generated SBOMs.
- [ ] **IETF SCITT integration** -- submit a generated SBOM as a signed
  SCITT statement to a transparency service, receive a receipt back as
  proof of registration; separately, verify a dependency's own SCITT
  receipt when consuming its SBOM and feed the result into the
  existing provenance role vocabulary (`externalReported` vs
  `sbomAuthorSupplied`). See <https://scitt.io/>. Complementary to (not
  a replacement for) the PEP 740 item above -- SCITT covers third-party
  transparency-log attestation, PEP 740 covers index-hosted signing.
  Related: [Issue #79](https://github.com/bact/pitloom/issues/79)
  (Cisco `model-provenance-kit`) could layer on the same mechanism.
  **Receipt placement (decided 2026-08-30): outside the wheel, not in
  `.dist-info/sboms/`.** A receipt embeds a transparency-log
  timestamp/index that varies per submission, so embedding it would
  break wheel/SBOM reproducibility; obtaining it also requires a
  network call to an external service, which a build hook shouldn't
  block on. Sidecar file next to the built wheel (e.g.
  `dist/<wheel>.receipt.cbor`), produced by a separate post-build step
  (`loom scitt submit`) -- mirrors how PEP 740 itself keeps attestations
  outside the artifact, served by the index rather than embedded.
  **Pitloom's role is client-only, not log operator.** A receipt is
  countersigned by the transparency service itself -- only the log can
  issue one. Pitloom builds and signs the SCITT statement, submits it
  to a transparency-service URL the user configures (self-hosted CCF
  instance, DataTrails, etc.), and stores whatever receipt comes back;
  it never runs a transparency service of its own.
  **Tooling landscape checked 2026-08-30, thin:** DataTrails is the
  main hosted, spec-compliant (draft-10) transparency service, with a
  GitHub Action client but no general Python library; the reference
  client/server, `scitt-api-emulator` (Python), is archived and
  unmaintained since 2024-11-22. No mature OSS client library exists
  yet, so this needs a from-scratch thin client -- `pyproject.toml` has
  no signing/crypto dependency today (`pycose` or `cryptography` would
  be new).
  **Shape:**
  ```
  loom scitt submit dist/mypkg-1.0.0.whl
    1. hash the SBOM, build a COSE_Sign1 statement
       (issuer identity + sha256(sbom) payload)
    2. sign it with the user's configured key
    3. POST to the configured transparency-service URL
    4. save the returned receipt as
       dist/mypkg-1.0.0.whl.receipt.cbor

  loom scitt verify <dependency-sbom> --receipt <file>
    -- checks a third party's receipt when consuming their SBOM
       as a dependency
  ```
- [ ] **Performance optimization** -- Rust backend for large-project
  log parsing; parallel file hashing for Merkle root computation.
- [ ] **Agentic skill governance (guardrail mode)** -- extend the
  existing AI-agent Skills (Adoption surfaces above) from "generate an
  SBOM on request" to "veto/flag a coding agent's own action" -- e.g.
  block or require override when an agent attempts to pull an unvetted
  Hugging Face model. Distinct capability from the current Skills:
  needs a hook into the calling agent's tool-use loop, not just a
  callable Skill.
- [ ] **Runtime reachability ("living SBOM")** -- evolve `loom env`
  (currently a static environment graph, see Market signals above)
  toward tracking which dependencies are actually loaded/executed at
  runtime (`sys.modules` introspection or eBPF), to suppress
  vulnerability noise from installed-but-unreachable code. Large scope
  -- needs its own design doc before estimating.
