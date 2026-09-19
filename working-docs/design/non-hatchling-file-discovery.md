---
Created: 2026-04-14
Last-Modified: 2026-09-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Non-Hatchling file discovery (feature parity)

See also: [roadmap.md](roadmap.md) (Near-term -- "Non-Hatchling file
discovery"), [sbom-lifecycle-stages.md](../implementation/sbom-lifecycle-stages.md)
(the mechanism and why this stays a static-config read for every backend,
never a build), [backend-file-discovery-validation.md](../implementation/backend-file-discovery-validation.md)
(real-world validation method and results so far),
[allow-build-timeout.md](../implementation/allow-build-timeout.md) (why
the build-and-read mechanism below runs as a killable subprocess tree
with a `--build-timeout`, not an in-process, unbounded build).

## The bug

`get_wheel_files()` file discovery is not backend-agnostic --
**closed (2026-09-15):** `get_wheel_files()`
(`src/pitloom/core/_models_wheel.py`) is a dispatch facade over
one discovery module per static/declarative backend (`_models_wheel_hatchling.py`,
`_models_wheel_setuptools.py`, `_models_wheel_poetry.py`,
`_models_wheel_pdm.py`, `_models_wheel_flit.py`); any backend with no
dedicated module (`uv_build`, or a Track B backend, or any future/
unrecognized backend) resolves via the generic build-and-read mechanism
(`_models_wheel_build_and_read.py`, see below) when `--allow-build` is
passed, and otherwise falls back to the Hatchling heuristic with a
logged warning, same as before. The bug below (originally reported for
setuptools) still stands as documentation for the default
(non-`--allow-build`) fallback path, which is unchanged by this closure.

Confirmed by direct testing before the fix:

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
- The same applied to Poetry, PDM-backend, and Flit-core (all now
  closed) and still applies by default (without `--allow-build`) to
  `uv_build` projects with their own inclusion config -- this affects
  **any non-Hatchling backend** without a dedicated static module, not
  setuptools specifically. Passing `--allow-build` closes the gap for
  `uv_build` (and any other unhandled backend) via a real build instead.
- Impact differs by command: `loom project`/`loom generate` (Source
  SBOM, directory target) has no wheel to fall back on, so the wrong
  file list, hashes, and Merkle-root integrity hash go straight into
  the SBOM. `loom embed-wheel --project-dir` is safer -- its
  `_merge_file_extras` step already keeps the real wheel's file
  list/hashes as truth (see the Merkle root item in
  [roadmap.md](roadmap.md)'s Build backend improvements section), so
  only `--content-type`/`--extract-file-header` enrichment silently
  fails to attach per mismatched file, degrading gracefully rather
  than corrupting the SBOM.
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

## Backend priority

Two fundamentally different classes of backend, needing two different
fixes:

- **Track A -- static/declarative backends** (setuptools, Poetry,
  PDM-backend, Flit-core): every file that ends up in the
  wheel already exists as a real file in `project_dir` before any build
  runs. A backend-aware rescan (read each backend's own inclusion
  config, walk the matching files) is correct and sufficient here --
  the same strategy `get_wheel_files()` already uses for Hatchling,
  just with each backend's own config format instead of
  `[tool.hatch.build...]`. `uv_build` is a Track A backend in principle
  (its files exist pre-build too) but has no in-process introspection
  API to write a rescan against (see the priority table below) -- it
  resolves via the build-and-read mechanism instead, same as Track B.
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
  a real wheel, then discover files by extracting them from it (see
  `_models_wheel_build_and_read.py`), mirroring the same ground-truth
  principle `_merge_file_extras`/`read_wheel()` already use for
  `embed-wheel`. **Implemented (2026-09-15)** as a generic,
  backend-agnostic mechanism gated behind the CLI's `--allow-build` flag
  (opt-in: it executes third-party build-time code, needs the backend's
  build dependencies installed, and is categorically slower than an
  in-process rescan) -- one implementation covers `uv_build` today, and
  automatically extends to any Track B backend (`maturin`,
  `scikit-build-core`, `meson-python`) the moment its own toolchain is
  available, with no further Pitloom code needed. It also doubles as a
  robustness fallback for Track A: when a registered backend's own
  static rescan fails on a given project, `--allow-build` retries via a
  real build before giving up. See
  [`docs/allow-build.md`](../../docs/allow-build.md)
  for the full flag/security documentation.

## Dependency packaging strategy

Decided 2026-08-31, after Poetry (item #2) shipped and raised the
question directly: as the number of Track A/B backend libraries grows,
should any become optional extras (mirroring the `ai`/`content-type`
extras) instead of hard `dependencies`?

Checked first: metadata extraction never imports the real
`setuptools`/`poetry-core`/`hatchling` packages at all -- `setuptools.py`,
`poetry.py`, and `hatchling.py` (under `pitloom.extract.project`) are self-contained TOML/AST parsers.
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
  **Implemented (2026-09-15):** `pitloom[build]` (`build>=1.2.2`) is the
  new optional extra backing the mechanism (`pyproject_hooks` comes in
  transitively via `build`; `virtualenv` was deliberately not added --
  `build`'s default isolated-env backend uses the stdlib `venv` module,
  which is enough). No individual Track B backend (`maturin`, etc.) has
  its own extra -- there's nothing backend-specific to depend on; the
  isolated build environment installs whichever backend a *target*
  project's own `[build-system] requires` names, same as it does for
  `uv_build`.

Priority order, weighing popularity, prevalence in AI/ML Python
projects, implementation size, and reuse leverage across backends:

| # | Backend | Track | Why this order |
| :-- | :--- | :--- | :--- |
| 1 | setuptools | A | **Done (2026-08-27).** Was the single most-installed backend with no dedicated support; now resolved via `setuptools.config.pyprojecttoml`/`setupcfg` + `build_py` introspection (`src/pitloom/core/_models_wheel_setuptools.py`). See [setuptools-support.md](../implementation/setuptools-support.md). |
| 2 | Poetry | A | **Done (2026-08-31).** Declarative `[tool.poetry]`/`packages`/`exclude` config, no build-time code execution to model -- resolved by delegating to poetry-core's own `WheelBuilder.find_files_to_add()` (`src/pitloom/core/_models_wheel_poetry.py`), the same delegate-to-the-real-library pattern as Hatchling's module (poetry-core is fully declarative, unlike setuptools). Also gained `poetry.lock`-resolved transitive dependencies (source-stage only) as an additional parity item beyond the original file-discovery scope. |
| 3 | PDM-backend, Flit-core | A | **Done (2026-09-02).** Both PEP 621-native and declarative -- resolved via `Builder.get_files()`/`WheelBuilder._collect_files()` for PDM-backend (`src/pitloom/core/_models_wheel_pdm.py`) and `flit_core.common.Module.iter_files()` for Flit-core (`src/pitloom/core/_models_wheel_flit.py`), the same delegate-to-the-real-library pattern as Poetry's module. Also closed the paired "PDM / Flit extractors" metadata item from Medium-term in the same pass (`pitloom.extract.project.pdm`/`flit`, dynamic `version`/`description` resolution). See [backend-file-discovery-validation.md](../implementation/backend-file-discovery-validation.md)'s Flit-core/PDM-backend round. |
| 4 | Build-and-read fallback | (mechanism) | **Done (2026-09-15).** Generic, backend-agnostic (`_models_wheel_build_and_read.py`), gated behind `--allow-build`; needs no per-backend name to dispatch on. Landed together with step 5, since `uv_build`'s only viable path was this mechanism. |
| 5 | `uv_build` | A (via build-and-read) | **Done (2026-09-15).** `uv_build` (PyPI package `uv_build`) is a thin PEP 517 shim that shells out to a compiled `uv-build` binary via subprocess, with no in-process introspection API comparable to Hatchling's `WheelBuilder`. No existing logic to adapt for a hand-rolled rescan, so it resolves via the build-and-read mechanism (step 4) rather than a Track A rescan, despite files existing pre-build in principle. `uv_build` itself is never a Pitloom dependency (mandatory or optional) -- only `build` (PyPA), as the new optional `pitloom[build]` extra, is added; the isolated build environment installs `uv_build` from the *target* project's own `[build-system] requires`. |
| 6 | `maturin`, `scikit-build-core` | B | Automatically covered by step 4's mechanism once each backend's own toolchain is available -- no further Pitloom code needed; not separately implemented in this pass. Tied -- both are surging in the AI/ML stack specifically (Rust-based tooling via PyO3 for `maturin`; CUDA/C++/Fortran extensions for `scikit-build-core`), and neither is meaningfully cheaper or more valuable than the other. |
| 7 | `meson-python` | B | Same as step 6 -- already covered by the mechanism, not separately implemented. Lower priority for Pitloom's own user base specifically: it's foundational to the AI/ML ecosystem (NumPy, SciPy) but those are far more often a Pitloom user's *dependency* than a project they're generating an SBOM for directly. |

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

## Open follow-up tech debt (from PR #215's `--allow-build` review)

The priority table above is closed for every backend, but the PR #215
review that landed the build-and-read mechanism (item #4/#5) surfaced
five smaller, independently-fixable follow-ups. None block the closed
work above; each is its own reviewed change.

- **Consolidate the duplicated blanket-except pattern across Track A
  backend discovery modules** -- the "`try: ... except Exception as exc:
  log.warning('<Backend> file discovery failed for %s: %s', ...);
  return None`" contract is byte-for-byte duplicated across
  `_models_wheel_{setuptools,poetry,pdm,flit}.py`. Deliberately deferred
  out of PR #215 (cosmetic, unrelated to landing `uv_build` support,
  adds regression surface to four stable, individually
  real-world-validated modules for no feature benefit).
- **Factor out the hand-rolled `tool` -> `tool.X` -> nested-table walk
  repeated across 6+ modules** -- `has_uv_build_backend_overrides()`
  (`_models_wheel_types.py`) reimplements the same isinstance-guarded
  chain `_load_pitloom_tool_section()` and every `extract/project/*.py`
  metadata producer (`poetry.py`, `pdm.py`, `setuptools_cfg.py`,
  `pyproject.py`, `pyproject_dynamic.py`) already does independently --
  the "pattern hand-copied across 3+ call sites drifts" class CLAUDE.md
  calls out by name. A shared `get_tool_table(data, *keys)`-style helper
  would touch several stable, already-tested producer modules.
- **`scripts/compare_allow_build.py` duplicates sdist extraction already
  in `tests/fixtures/real_world.py`** -- `_extract_archive()`
  reimplements `extract_sdist()`'s tar/zip-open, `filter="data"`,
  single-top-level-dir logic, generalized to accept any archive path.
  Dev-only script, not shipped code, no user-facing risk -- low priority.
- **`--allow-build`-sourced files never match a `loom ids
  generate`-pinned registry entry** -- `IdRegistry.generate()` (`ids.py`)
  keys every entry by physical, project-root-relative path; a
  build-and-read-sourced `ProjectFile.physical_path` is an ephemeral
  temp path instead, so neither of `_document_files.py`'s two lookup
  attempts (`physical_path`, then `distribution_path`) can ever match a
  pre-pinned entry for such a file -- a new spdxId is silently minted
  instead. Harvest-to-harvest id stability (a normal `loom project` run
  finding ids a *previous* `loom project` run wrote) is unaffected --
  both write and read sides key by `distribution_path` there. Real fix
  needs `_document_files.py`'s registry lookup to gain a third candidate
  (`project_dir`-relative `distribution_path`, checked for existence),
  which needs threading `project_dir` into a currently filesystem-free
  assembly function -- a real design change, not a quick patch.
  **Partially addressed** (2026-09-15, a later PR #215 review round): a
  *separate* AI-model registry lookup, `_ai_package.py`'s
  `_lookup_ai_model_entity`, was found with the identical hazard but no
  guard at all -- it offered the raw ephemeral `physical_path` as its
  only path-based candidate, guaranteed to never match anything, unlike
  `_document_files.py`'s two-attempt (still-insufficient) lookup above.
  Fixed by adding a `file_path_relative` fallback via the new shared
  `pitloom.core.project.project_relative_or_fallback()` helper (also now
  used by `_document_files.py`'s determinism fix and
  `enrich._resolve_model_search_dir`, consolidating what had been three
  independent inline implementations of the same "prefer a
  project-relative stand-in over an absolute physical_path" check -- see
  CLAUDE.md's "Recurring bug patterns" section). This closes the
  guaranteed-never-match case for AI models but does **not** fully solve
  the general problem above: `file_path_relative` still won't match an
  entry `loom ids generate` pinned under the *original*
  project-relative `physical_path` for a `src/`-layout project, so the
  real fix (a third, existence-checked candidate) described above still
  applies equally here.
- **Real static `uv_build` discoverer for `[tool.uv.build-backend]`** --
  validated empirically (2026-09-15, see
  [allow-build-validation.md](../implementation/allow-build-validation.md#--allow-build-build-and-read-with-vs-without-2026-09-15))
  that the Hatchling-heuristic fallback over-includes files a project's
  own `wheel-exclude`/`wheel-include`/`module-name` directives in
  `[tool.uv.build-backend]` would drop (15 extra files for the
  rendercv-2.8 fixture, all correctly excluded by `--allow-build`'s real
  build). `--allow-build` already closes this gap exactly, so this is a
  precision improvement for the *default* (no-flag) path only --
  parsing `[tool.uv.build-backend]` statically, the same shape of work
  as the existing setuptools/Poetry/PDM/Flit modules. **Partially
  addressed** (2026-09-15): the fallback's `WARNING:` now names this
  specific divergence risk and points at `--allow-build` when
  `wheel-exclude`/`wheel-include` is actually present
  (`has_uv_build_backend_overrides()` in `_models_wheel_types.py`).
  **Wider sweep** (2026-09-15, 9 more real packages, see
  [allow-build-validation.md](../implementation/allow-build-validation.md#--allow-build-wider-sweep-9-more-real-uv_build-packages-2026-09-15))
  found a second, more severe failure shape: a `module-name` that
  doesn't match Hatchling's zero-config guess (django-model-import)
  makes the fallback fail outright with zero files, not just
  over-include -- already loudly `WARNING:`-logged, and a future real
  discoverer would need to handle two distinct config schemas, not one:
  `[tool.uv.build-backend]` (current) and an older flat
  `[tool.uv_build]` (found on ffmpeg-normalize, currently invisible to
  `has_uv_build_backend_overrides()` too, though no practical divergence
  was observed for it).
