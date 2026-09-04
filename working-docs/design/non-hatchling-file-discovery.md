---
Created: 2026-04-14
Last-Modified: 2026-09-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Non-Hatchling file discovery (feature parity)

See also: [roadmap.md](roadmap.md) (Near-term -- "Non-Hatchling file
discovery"), [sbom-lifecycle-stages.md](../implementation/sbom-lifecycle-stages.md)
(the mechanism and why this stays a static-config read for every backend,
never a build), [backend-file-discovery-validation.md](../implementation/backend-file-discovery-validation.md)
(real-world validation method and results so far).

## The bug

`get_wheel_files()` file discovery is not backend-agnostic --
**partially fixed (2026-08-27):** `get_wheel_files()`
(`src/pitloom/core/_models_wheel.py`) is now a dispatch facade over
one discovery module per backend (`_models_wheel_hatchling.py`,
`_models_wheel_setuptools.py`, `_models_wheel_poetry.py`,
`_models_wheel_pdm.py`, `_models_wheel_flit.py`), with any backend
that doesn't have a dedicated module yet (`uv_build`, ...) falling
back to the Hatchling heuristic -- now with a logged warning instead
of silently risking an inaccurate result. Setuptools, Poetry,
PDM-backend, and Flit-core are closed (see priority table below); the
bug below (originally reported for setuptools) still stands as
documentation for every backend still on the fallback path.

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
  closed) and still applies to `uv_build` projects with their own
  inclusion config -- this affects **any non-Hatchling backend**
  without a dedicated module, not setuptools specifically.
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

## Dependency packaging strategy

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
