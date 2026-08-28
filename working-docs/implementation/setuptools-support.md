---
Created: 2026-03-24
Last-Modified: 2026-08-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Setuptools support -- implementation notes

See also: [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md) for why
wheel file discovery below stays a static-config read (never executes
`setup.py`), and how this compares to the Hatchling backend and to
`loom wheel`/`embed-wheel`'s build-stage path.

## Motivation

Pitloom initially targeted only Hatchling-based projects.  Many real-world
Python packages still use setuptools as their build backend and declare
metadata in `setup.cfg` or `setup.py`.  This document records the design
decisions, conflict resolution strategy, and known limitations of the
initial setuptools support added in the `setuptools-support` branch.

## Source files

| File | Role |
| :--- | :--- |
| `src/pitloom/extract/_setuptools.py` | Extraction facade and backend detection |
| `src/pitloom/extract/_setuptools_cfg.py` | `setup.cfg` metadata and `[tool:pitloom]` parser (split from `_setuptools.py`) |
| `src/pitloom/extract/_setuptools_py.py` | `setup.py` AST metadata parser (split from `_setuptools.py`) |
| `src/pitloom/extract/project.py` | Shared resolver (`read_project()`) used by both the CLI and `generate_project_sbom()` |
| `src/pitloom/cli/` | CLI updated to accept projects without `pyproject.toml` (originally in `__main__.py`, since split into `cli/` -- see `cli-test-coverage-roadmap.md`) |
| `tests/extract/test_setuptools_cfg.py`, `test_setuptools_cfg_config.py`, `test_setuptools_py.py`, `test_setuptools_integration.py` | Unit and integration tests (originally `tests/test_setuptools.py`, later split into these modular suites -- see `cli-test-coverage-roadmap.md`) |
| `tests/fixtures/projects/sampleproject-setuptools/` | Transitional-layout fixture project |
| `src/pitloom/core/_models_wheel.py` | Backend-dispatch facade for wheel file discovery (`get_wheel_files()`), shared per-file hashing/header loop |
| `src/pitloom/core/_models_wheel_setuptools.py` | Setuptools wheel file discovery -- static config only, see below |
| `src/pitloom/core/_models_wheel_hatchling.py`, `_models_wheel_types.py` | Hatchling discovery module and shared types, siblings of the facade above |
| `tests/core/test_models_wheel_setuptools.py`, `test_models_wheel_files.py` | Wheel file discovery tests (setuptools-specific, and facade dispatch/fallback) |
| `tests/fixtures/projects/sampleproject-setuptools-data/` | `package_data`/`include_package_data`/`MANIFEST.in` fixture for the manifest-analysis discovery path |

## Extraction functions

### `detect_build_backend(project_dir)`

Reads `[build-system] build-backend` from `pyproject.toml` and returns a
lower-case backend identifier (`"setuptools"`, `"hatchling"`, `"flit"`, …).
When no `pyproject.toml` is present but `setup.cfg` or `setup.py` exist,
returns `"setuptools"` by convention.

### `read_setup_cfg(project_dir)`

Parses `[metadata]` and `[options]` using stdlib `configparser`.

**Supported `[metadata]` fields:**

| setup.cfg key | `ProjectMetadata` field |
| :--- | :--- |
| `name` | `name` |
| `version` | `version` |
| `description` / `summary` | `description` |
| `long_description` | `readme` |
| `author` + `author_email` | `authors` |
| `license` | `license_name` |
| `keywords` | `keywords` (space, comma, or newline separated) |
| `url` | `urls["Homepage"]` |
| `project_urls` | `urls` (multi-line key = value) |

**Supported `[options]` fields:**

| setup.cfg key | `ProjectMetadata` field |
| :--- | :--- |
| `python_requires` | `requires_python` |
| `install_requires` | `dependencies` |

**Version directives:**

- **Literal** (`version = 1.2.3`) -- used as-is.
- **`file:` directive** (`version = file: VERSION`) -- reads the referenced
  file; expects a plain version string on a single line.
- **`attr:` directive** (`version = attr: package.__version__`) -- resolves via
  AST parsing of the referenced module file.  Checks both flat-layout
  (`package.py`) and src-layout (`src/package/__init__.py`).  Falls back to
  `None` when the attribute is dynamic (e.g., assigned by a function call).

**Pitloom configuration:**

`[tool:pitloom]` (note the colon separator, which is the `setup.cfg`
convention for tool namespaces) mirrors `[tool.pitloom]` in `pyproject.toml`.
An optional `[tool:pitloom:creation]` sub-section mirrors
`[tool.pitloom.creation]`.  Either section can exist independently.

### `read_setup_py(project_dir)`

Parses `setup.py` using `ast.parse()`.  Extracts **literal** keyword
arguments from the first `setup()` or `setuptools.setup()` call found.

**What is extractable:**

```python
setup(
    name="mypackage",           # ✅ string literal
    version="1.0.0",            # ✅ string literal
    install_requires=[          # ✅ list of string literals
        "requests>=2.0",
        "click",
    ],
    ...
)
```

**What is silently skipped:**

```python
setup(
    version=get_version(),  # ✗ function call
    name=PKG_NAME,  # ✗ variable
    install_requires=REQS,  # ✗ variable
)
```

Skipping non-literal values is intentional: it avoids executing untrusted
code and keeps the extractor predictable.  Affected fields are left `None`
or empty in `ProjectMetadata`.

`setup.py` has no Pitloom configuration section; `read_setup_py` always
returns a default `PitloomConfig()`.

### `read_setuptools(project_dir)`

Orchestrates both extractors and merges their results with
`setup.cfg` taking precedence over `setup.py`.  Returns the `PitloomConfig`
from `setup.cfg` if available, otherwise a default instance.

### `merge_metadata(primary, secondary)`

Field-by-field merge: for each attribute, the primary value is used when
non-empty/truthy; otherwise the secondary value fills the gap.  The primary
`name` is always kept.  Provenance dicts are merged with primary entries
overriding secondary on key conflicts.

## Wheel file discovery (`_models_wheel_setuptools.discover()`)

`get_wheel_files()` (`src/pitloom/core/_models_wheel.py`) dispatches to
`pitloom.core._models_wheel_setuptools.discover()` for any project whose
`detect_build_backend()` result is `"setuptools"`. Same static-only
boundary as metadata extraction above -- resolves
`packages`/`package_dir`/`packages.find`/`package_data`/
`include_package_data` via setuptools' own official config-resolution
API (`setuptools.config.pyprojecttoml`/`setupcfg`'s
`apply_configuration()`), which fully populates a `Distribution` the
same way a real setuptools build would, without executing `setup.py`.
See [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md) for why.

Unlike metadata extraction's `read_project()` (see "Conflict
resolution" below), this module applies **both** `setup.cfg` and
`pyproject.toml` when both are present, `setup.cfg` first: setuptools'
own `apply_configuration()` calls are cumulative on the same
`Distribution`, so `pyproject.toml` (applied second) can supply
`[tool.setuptools.dynamic]`/PEP 621 fields on top of `setup.cfg`'s
`packages`/`package_dir`, matching how a real setuptools build
consults both rather than treating them as mutually exclusive. A
`pyproject.toml` carrying only a PEP 621 `[project]` table, with no
`[tool.setuptools]` table at all, is also resolved -- setuptools'
own zero-config auto-discovery applies there.

`apply_configuration()` runs with the process cwd already set to the
target project directory (`_chdir`, serialized by a module-level
`threading.Lock` against concurrent `discover()` calls racing on the
shared `os.chdir()` state): `[tool.setuptools.dynamic]`/`attr:`
resolution can import the target project's own modules, and running
that import from the wrong cwd risks resolving it against an
unrelated module reachable from Pitloom's own `sys.path` instead of
the intended one.

**Module files** (`.py`): `setuptools.command.build_py.build_py`'s
`find_all_modules()`, called after `finalize_options()`.

**Data files** (`package_data`, and `include_package_data` +
`MANIFEST.in`): `build_py._get_data_files()`, which internally runs
setuptools' manifest analysis. `include_package_data=True` triggers a
real `egg_info` command invocation -- redirected via the command's own
`egg_base` option to a `tempfile.TemporaryDirectory()` so the project
directory is never mutated by what is meant to be a read-only
discovery pass (verified by a regression test asserting no `.egg-info`
artifact is left behind).

**No static config at all** -- a `pyproject.toml` with only
`[build-system]` (no `[project]`, no `[tool.setuptools]`) and no
`setup.cfg`, meaning packages/data files are only resolvable by
executing an imperative `setup.py` -- returns `None` from this module,
same "out of scope" boundary as `read_setup_py`'s literal-only AST
parsing above. At the facade level (`_models_wheel.py`), when the
`pyproject.toml` also has no `[project]` table at all (missing,
unparseable, or `[build-system]`-only), Hatchling's own discovery is
guaranteed to fail the same way, so the facade returns an empty file
list directly with a logged warning -- it never attempts the
Hatchling-branded heuristic for this case. Only a project whose
`pyproject.toml` *does* have a `[project]` table falls back to the
Hatchling-based heuristic when this module's own static config can't
be resolved. Files resolved from static config are also deduplicated
by distribution path (a `package_data` glob can overlap a `.py` module
already found by module discovery); each output entry is unique.

**Fixes the exact bug from `working-docs/design/roadmap.md`'s
"Non-Hatchling file discovery" item**: a `where = ["lib"]`-style
`[options.packages.find]` layout previously reported
`lib/mypkg/__init__.py` (wrong -- carried the `where=` source directory
into the distribution path); now correctly reports `mypkg/__init__.py`.

## Conflict resolution

Multiple metadata sources may coexist in a single project (common during
migration to pyproject.toml).  Resolution happens in `read_project()` in
`src/pitloom/extract/project.py`, the single entry point used by both the
CLI and `generate_project_sbom()`'s default parsing path:

1. If `pyproject.toml` exists at all (existence check only -- regardless of
   whether it has a `[project]` section), it is the sole metadata source,
   via `read_pyproject()`. `setup.cfg`/`setup.py` are not consulted, even if
   present -- there is no cross-source field merge at this level.
2. Otherwise, if `setup.cfg` and/or `setup.py` exist, `read_setuptools()` is
   used as the sole source (this is where `merge_metadata` applies -- see
   below -- but only between `setup.cfg` and `setup.py`, not `pyproject.toml`).
3. If none of the three files exist, `FileNotFoundError` is raised.

**Why pyproject.toml wins:** PEP 517 and PEP 621 designate `[project]` in
`pyproject.toml` as the canonical metadata location.  Setuptools itself gives
`pyproject.toml` precedence over `setup.cfg` when both are present.

**Known limitation:** a transitional project with `[build-system]`-only
`pyproject.toml` plus real metadata in `setup.cfg` (see the fixture project
below) does not currently get its `setup.cfg` metadata merged in -- step 1
above takes `pyproject.toml`'s (mostly empty) metadata as-is. Field-level
merging across `pyproject.toml` and `setup.cfg` is a possible future
enhancement, not yet implemented.

## Provenance tracking

Each field records its source using the same `"Source: X | Field: Y"` /
`"Source: X | Method: Y"` pattern as `read_pyproject`:

```text
name         -> "Source: setup.cfg | Field: metadata.name"
version      -> "Source: VERSION | Method: file_directive"
version      -> "Source: src/mypkg/__init__.py | Method: attr_directive"
authors      -> "Source: setup.py | Field: setup(author=...)"
```

When fields are filled by `merge_metadata`, the higher-priority provenance
entry wins; the lower-priority entry is preserved only where the higher
source had no value.

## Fixture project

`tests/fixtures/projects/sampleproject-setuptools/` demonstrates the common
**transitional layout**:

```text
sampleproject-setuptools/
├── pyproject.toml        # [build-system] only -- no [project] section
├── setup.cfg             # [metadata] + [options] + [tool:pitloom]
├── setup.py              # bare setup() shim
├── README.md
└── src/
    └── sampleproject_setuptools/
        └── __init__.py   # __version__ = "0.1.0"
```

This mirrors the pattern seen in many real projects that have adopted
`pyproject.toml` for the build-system declaration but still keep metadata
in `setup.cfg`.

## Known limitations

| Limitation | Notes |
| :--- | :--- |
| Dynamic `setup.py` values | Variables, function calls, `f`-strings are skipped; affected fields are `None`. |
| `attr:` with complex paths | Only `module.ATTR` (two-part) is resolved; deeper paths (e.g., `pkg.sub.module.ATTR`) fall back to `None`. |
| Multiple authors in `setup.cfg` | `author` / `author_email` yield at most one entry; setuptools supports comma-separated lists but pitloom does not yet parse them. |
| Optional / extras dependencies | `[options.extras_require]` is not extracted. |
| Wheel file discovery, no static config | A setuptools project with no `[project]`/`[tool.setuptools]` in `pyproject.toml` and no `setup.cfg` (packages only resolvable via imperative `setup.py`) returns an empty file list -- the facade skips the Hatchling-based heuristic entirely for this case (logged warning), since it's guaranteed to fail Hatchling's own discovery too; same static-only boundary as metadata extraction. |
| Build-time dynamic metadata | `version` set via Git tags, `importlib.metadata`, or other runtime mechanisms is not resolved statically.  See [working-docs/design/metadata-sources.md](../design/metadata-sources.md) for the planned PEP 517 approach. |
| Wheel file discovery, `setup.py` overrides packaging imperatively | A project can look statically resolvable (a `setup.cfg`/zero-config auto-discovery finds *something*) while its real `setup.py` also passes `packages`/`package_data`/etc. imperatively -- silently dropping files (real-world boto3) or including spurious ones (real-world cffi's implicit-namespace-package guess for a non-package `src/c/` dir). Neither is fixable without executing `setup.py` (out of scope), so `discover()` AST-scans `setup.py` for these argument names and logs a `WARNING:` when present, rather than staying silent. See [backend-file-discovery-validation.md](backend-file-discovery-validation.md#findings). |

## Real-world validation

`discover()` is checked against real PyPI packages, not just the
synthetic fixtures under `tests/fixtures/projects/` -- method, the
current 10-package results, and findings now live in
[backend-file-discovery-validation.md](backend-file-discovery-validation.md)
(shared with the Hatchling backend's own validation).

## Planned enhancements

- **`attr:` with deep module paths** (e.g., `pkg.sub.module.ATTR`).
- **Multiple authors** from comma-separated `setup.cfg` `author` fields.
- **`[options.extras_require]`** extraction.
- **PEP 517 `prepare_metadata_for_build_wheel`** as an opt-in higher-priority
  source for dynamic metadata.  See
  [working-docs/design/metadata-sources.md](../design/metadata-sources.md).
