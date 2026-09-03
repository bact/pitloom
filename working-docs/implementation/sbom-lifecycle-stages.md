---
Created: 2026-08-27
Last-Modified: 2026-09-03
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Source SBOM vs. build SBOM: lifecycle stages and per-backend mechanism

See also: [setuptools-support.md](setuptools-support.md) and
[poetry-support.md](poetry-support.md) for the backend-specific
discovery implementations this doc justifies the scope of;
`working-docs/design/roadmap.md`'s "Non-Hatchling file discovery"
section for the backend-priority table this decision feeds.

## Source SBOM vs. build SBOM

SPDX 3's lifecycle-scope concept distinguishes an SBOM describing a
project as it exists *before* any build (source/design-stage) from one
describing an actual produced artifact (build-stage). Pitloom's two
wheel-file-discovery paths map directly onto this:

- **Source-stage**: `loom project`/`loom generate` run against a
  source-tree directory. No build artifact exists yet; file discovery
  asks each backend's own static/declarative config "what would be
  included," without invoking a build.
- **Build-stage**: `loom wheel` and `embed-wheel`'s wheel-merge step,
  which read an *actual built* `.whl` file via `read_wheel()`. This is
  ground truth by construction -- whatever the build produced,
  regardless of how or why.

## Mechanism per backend/command

| Command | Target | Mechanism | Stage |
| :--- | :--- | :--- | :--- |
| `loom project`/`loom generate` (directory) | source tree | `get_wheel_files()` -> backend-specific in-process introspection | Source |
| ...Hatchling backend | -- | `WheelBuilder.recurse_included_files()` (`src/pitloom/core/_models_wheel_hatchling.py`) -- a method distinct from `WheelBuilder.build()`; walks static `[tool.hatch.build...]` config only | Source |
| ...setuptools backend | -- | `Distribution`/`build_py` introspection via `apply_configuration()` + `find_all_modules()`/`_get_data_files()` (`src/pitloom/core/_models_wheel_setuptools.py`) -- static config only, no `setup.py` execution | Source |
| ...Poetry backend | -- | `poetry.core.masonry.builders.wheel.WheelBuilder.find_files_to_add()` (`src/pitloom/core/_models_wheel_poetry.py`) -- delegates to poetry-core's own declarative config resolution, no `[tool.poetry.build].script` execution; see [poetry-support.md](poetry-support.md)'s "Wheel file discovery" section | Source |
| ...PDM-backend | -- | `Builder.get_files()` (via `WheelBuilder`'s overridden `_collect_files()` for `src/`-layout prefix-stripping) + `_get_wheel_data()` (`src/pitloom/core/_models_wheel_pdm.py`) -- static config only; never calls `initialize()`/`_get_metadata_files()`, both of which write to disk as a pdm-backend side effect | Source |
| ...Flit-core backend | -- | `flit_core.common.Module.iter_files()` + `walk_data_dir()` (`src/pitloom/core/_models_wheel_flit.py`) -- static config only; a dynamic `version`/`description` is resolved via an AST-only scan (`get_docstring_and_version_via_ast()`), never by importing the target module | Source |
| ...any other backend (`uv_build`, ... until it lands) | -- | Falls back to the Hatchling heuristic, with a logged warning that the result may be inaccurate for that backend | Source (approximated) |
| `loom wheel` | built `.whl` file | `read_wheel()` reads the real artifact directly, backend-agnostic | Build |
| `embed-wheel` (wheel-merge step) | built `.whl` file | Same `read_wheel()` path; `_merge_file_extras` treats it as ground truth, discarding `get_wheel_files()`'s own Merkle root in favor of one computed from the real wheel's hashes | Build |

## Why the Hatchling and setuptools mechanisms are the same tier

`WheelBuilder.recurse_included_files()` (confirmed via
`hatchling/builders/plugin/interface.py`) is a **separate method from
`build()`**. Hatchling's actual build hook execution
(`initialize`/`finalize` on custom `[tool.hatch.build.hooks.*]`
plugins -- the only place arbitrary Python could run for a Hatchling
project) lives entirely inside `build()`. `recurse_included_files()`
never calls `build()` -- it only walks static include/exclude/
`force-include` config. So Pitloom's existing Hatchling-based source
discovery was already static-config-only *in effect*, despite going
through an in-process backend API rather than hand-parsed TOML.

The setuptools addition (`setuptools.config.pyprojecttoml`/`setupcfg`'s
`apply_configuration()`, `build_py.find_all_modules()`/
`_get_data_files()`) is the same class of technique: ask the backend's
own declarative-config-resolution machinery what it would include,
without executing arbitrary project code. Not a new double standard --
the same tier of fidelity and risk as the Hatchling path that predates
it.

One partial exception on the setuptools side: `include_package_data`
resolution requires setuptools' manifest analysis, which internally
invokes the real `egg_info` command (a `distutils`/`setuptools`
built-in command, not project-authored code) -- redirected via
`egg_base` to a temp directory so it never mutates the project
directory. This is still config-driven, not execution of any
project-authored logic; see [setuptools-support.md](setuptools-support.md)'s
"Wheel file discovery" section for the mechanism.

## The bigger-picture workflow for maximum fidelity

For a user who wants the most complete and accurate SBOM: build the
wheel yourself (via `setuptools`, or any backend), then use `loom
wheel` or `embed-wheel`. That path gets strictly more complete
information than static analysis can ever produce -- compiled
extensions, `MANIFEST.in`/`egg_info`-resolved data files, dynamic
`setup.py` logic, all of it -- with **none** of the execution-risk,
determinism, or build-dependency costs of running `setup.py` inside
Pitloom, because the code execution already happened on the user's own
machine as a normal build, not inside Pitloom's process.

The static source-stage path this doc's mechanism table describes
specifically serves the pre-build case: no wheel built yet (e.g. early
CI, before a build step runs), or someone who wants an SBOM without
building at all.

## Why `setup.py` execution is out of scope (not just "not done yet")

Considered and rejected as part of extending setuptools support, for
reasons beyond scope discipline:

- **Determinism** (`AGENTS.md`: bit-for-bit reproducible SBOMs) is only
  guaranteed by pure/static config resolution; executing arbitrary
  `setup.py` code can leak env vars, network calls, or other
  non-deterministic state into the result.
- **No new hard dependency surface**: execution would require whatever
  the target project's `setup.py` imports (numpy, Cython, ...) to be
  pre-installed in Pitloom's own environment -- a requirement the
  static-analysis design currently avoids entirely for every backend.
- **Cross-platform reliability** (`AGENTS.md`: Windows/macOS/Linux):
  static parsing is inherently portable; execution inherits the
  *target project's* build-toolchain quirks (a guarantee about
  Pitloom's own code, not every project it scans).
- **Lifecycle-stage modeling**: `setup.py` execution would be a
  build-stage operation happening inside a nominally source-stage
  command (`loom project`). Mixing stages silently within one static
  scan is a modeling smell on top of being a silent deviation from
  what the command claims to do.
- **Security/surface exposure varies sharply by usage surface**: CLI
  (lower risk -- user already trusts their own project) vs. library
  API (higher risk -- arbitrary execution as a side effect embedded in
  someone else's tool/CI script) vs. AI-agent Skills (worst fit --
  agent-triggered on repos a user may just be exploring, without
  explicit awareness that code would run).

If `setup.py` execution is ever added, it should be scoped
CLI/GitHub-Action-only, excluded from the AI-agent Skills surface, and
recorded as a distinct build-stage Annotation on the resulting SBOM --
not a transparent upgrade to the static source-stage path.
