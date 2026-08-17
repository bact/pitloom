---
Created: 2026-03-24
Last-Modified: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Setuptools support -- implementation notes

## Motivation

Pitloom initially targeted only Hatchling-based projects.  Many real-world
Python packages still use setuptools as their build backend and declare
metadata in `setup.cfg` or `setup.py`.  This document records the design
decisions, conflict resolution strategy, and known limitations of the
initial setuptools support added in the `setuptools-support` branch.

## Source files

| File | Role |
| :--- | :--- |
| `src/pitloom/extract/_setuptools.py` | New extraction module (renamed from `setuptools.py`) |
| `src/pitloom/extract/project.py` | Shared resolver (`read_project()`) used by both the CLI and `generate_project_sbom()` |
| `src/pitloom/cli/` | CLI updated to accept projects without `pyproject.toml` (originally in `__main__.py`, since split into `cli/` -- see `cli-test-coverage-roadmap.md`) |
| `tests/extract/test_setuptools.py` | 53 new unit and integration tests (originally `tests/test_setuptools.py`) |
| `tests/fixtures/projects/sampleproject-setuptools/` | Transitional-layout fixture project |

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
| Wheel file discovery | `get_wheel_files()` still uses `hatchling.builders.wheel.WheelBuilder`; for setuptools projects it returns `(None, [])`, so the SBOM UUID is computed from name + version + deps only (no Merkle root). |
| Build-time dynamic metadata | `version` set via Git tags, `importlib.metadata`, or other runtime mechanisms is not resolved statically.  See [working-docs/design/metadata-sources.md](../design/metadata-sources.md) for the planned PEP 517 approach. |

## Planned enhancements

- **setuptools wheel file discovery** via `setuptools.build_meta` or
  `importlib.metadata` to compute a Merkle root for setuptools projects.
- **`attr:` with deep module paths** (e.g., `pkg.sub.module.ATTR`).
- **Multiple authors** from comma-separated `setup.cfg` `author` fields.
- **`[options.extras_require]`** extraction.
- **PEP 517 `prepare_metadata_for_build_wheel`** as an opt-in higher-priority
  source for dynamic metadata.  See
  [working-docs/design/metadata-sources.md](../design/metadata-sources.md).
