---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Hatchling build hook and PEP 770 wheel embedding

## Overview

This document describes the design of Pitloom's Hatchling build hook plugin
(`pitloom.plugins.hatch`) and the PEP 770-compliant embedding of SBOMs inside
Python wheel archives.

The goal is to make SBOM generation a zero-friction, automatic step: when
a developer runs `hatch build` or `python -m build`, the SBOM is generated
and embedded into the wheel with no additional commands.

## PEP 770 background

[PEP 770](https://peps.python.org/pep-0770/) reserves the
`.dist-info/sboms/` directory inside wheel archives for SBOM documents.
The directory may contain one or more SBOM files in any standard format.
Downstream tools (e.g., Trivy, Grype, `pip show`) can discover and consume
these documents from an installed package or directly from the wheel file.

Target placement for Pitloom output:

```text
{name}-{version}.dist-info/
└── sboms/
    └── sbom.spdx3.json
```

## Data sources from the build backend

Hatchling passes each build hook a fully resolved
`hatchling.metadata.core.ProjectMetadata` instance via `self.metadata`. By
the time `initialize()` runs, Hatchling has already:

- Resolved the project `version` -- whatever the configured
  `[tool.hatch.version]` source is (a literal, a `path`-based regex, a
  `code`-evaluated expression, `hatch-vcs`, etc.).
- Resolved `dependencies` and `optional_dependencies`, including any added
  dynamically by a metadata hook (e.g. `hatch-requirements-txt`).
- Resolved `license` / `license_expression`, `urls`, `authors_data`,
  `keywords`, `description`, `readme` (and `readme_path`), and
  `requires_python`.
- Normalized the project `name` per PEP 503 (`_` and `.` collapsed to `-`,
  lowercased) as `core.name`, while retaining the original, un-normalized
  spelling as `core.raw_name`. `metadata_from_hatchling()` uses `raw_name`,
  matching the literal spelling `read_pyproject()` reports for the same
  `[project] name` in `pyproject.toml`, so the CLI and the build hook agree
  on the project's displayed name (and therefore on the deterministic
  document UUID, which is derived from it).

The build hook maps this object into Pitloom's format-neutral
`ProjectMetadata` via
`pitloom.extract.hatchling.metadata_from_hatchling(self.metadata,
project_dir)` -- **not** via `pitloom.extract.pyproject.read_pyproject()`,
which re-parses `pyproject.toml` from scratch and cannot see dynamic values
resolved by Hatchling plugins. `read_pyproject()` remains the metadata source
for the standalone CLI (`pitloom`/`loom generate`), which has no build
backend to consult; both paths converge on the same
`pitloom.assemble.spdx3.document.build()` assembly layer, so the emitted SBOM
shape is identical either way. `read_pitloom_config()`
(`pitloom.core.config`) reads `[tool.pitloom]` settings independently of
either metadata source.

Two details worth calling out explicitly:

- The `version` parameter passed to `initialize(self, version, build_data)`
  is the **build variant** (`"standard"`, `"editable"`, ...), **not** the
  project version. The project version is `self.metadata.version`.
- The hook only runs for the `wheel` build target
  (`self.target_name == "wheel"`); PEP 770's `.dist-info/sboms/` convention
  does not apply to sdists, so `initialize()` returns immediately for any
  other target.

## Hatchling plugin registration

Hatchling discovers build hooks registered as Python entry points under the
`hatch` group (consumed via [pluggy](https://pluggy.readthedocs.io/)).
The module must expose a `@hookimpl`-decorated
`hatch_register_build_hook()` function that returns the hook class.

### Entry point in Pitloom's `pyproject.toml`

```toml
[project.entry-points."hatch"]
pitloom = "pitloom.plugins.hatch"
```

### User configuration in the target project's `pyproject.toml`

The user adds `pitloom` to their build dependencies and enables the hook:

```toml
[build-system]
requires = ["hatchling", "pitloom"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
# All fields are optional. Defaults are shown.
enabled = true
sbom-basename = ""          # Name part only, no extension; default "sbom"
creator-name = ""           # Defaults to "Pitloom"
creator-email = ""          # Optional
fragments = []              # List of pre-generated fragment paths to merge
```

The full SBOM filename is derived by appending the format extension to the
basename: `{sbom-basename}.spdx3.json` (e.g., `sbom.spdx3.json` by default).

Specifying fragments allows the hook to merge `pitloom.loom`-generated AI/ML
fragments produced during training before the build:

```toml
[tool.hatch.build.hooks.pitloom]
fragments = [
    "fragments/train_run.spdx3.json",
    "fragments/eval_run.spdx3.json",
]
```

## SBOM filename conventions

### Inside the wheel (PEP 770)

The default filename is `sbom.spdx3.json`. The user can override the base
name via `sbom-basename`; the `.spdx3.json` extension is always appended by
Pitloom to reflect the SPDX 3 JSON-LD format.

PEP 770 allows a wheel to contain multiple SBOM files (e.g., one per
format), so the `sbom-basename` option is designed to be forward-compatible
with multi-SBOM scenarios.

### Standalone CLI output

When no `-o` / `--output` argument is given, the CLI derives the default
output filename in priority order:

1. `{sbom-basename}.spdx3.json` -- if `sbom-basename` is set in `[tool.pitloom]`
2. `{name}-{version}.spdx3.json` -- derived from project metadata
3. `sbom.spdx3.json` -- fallback

## Build hook class design

The hook's implementation lives in `src/pitloom/plugins/hatch.py`; see that
module for the authoritative, current source (`PitloomBuildHook.initialize`
and `finalize`, plus the module-level `_build_document_model` helper). At a
high level, `initialize()`:

1. Validates `[tool.hatch.build.hooks.pitloom]` config (`_validate_config`);
   invalid values raise `ValueError` before any file I/O.
2. Returns early if `enabled = false`, or if `self.target_name != "wheel"`.
3. Builds the format-neutral document via `_build_document_model`, which
   calls `metadata_from_hatchling(self.metadata, project_dir)` for project
   metadata and `read_pitloom_config(project_dir / "pyproject.toml")` for
   `[tool.pitloom]` settings, then `get_wheel_files(project_dir)` for the
   packaged file set (SHA-256 digests + Merkle root) and
   `scan_project_for_ai_models` for embedded AI/ML metadata.
4. Assembles the SPDX 3 document via `assemble_spdx3` (the shared
   `pitloom.assemble.spdx3.document.build()` used by the CLI), then merges
   any `[tool.pitloom]` / hook-level `fragments`.
5. Serializes with `exporter.to_json(pretty=False)` -- **always** compact,
   RFC 8785 (JCS) canonical, regardless of any `[tool.pitloom] pretty = true`
   setting or CLI `--pretty` flag. Canonicalization is required by the SPDX
   JSON Serialization Scheme for embedded SBOMs.
6. Writes the JSON to a `tempfile.TemporaryDirectory` that outlives
   `initialize()` and is cleaned up in `finalize()`, and appends its path to
   `build_data["sbom_files"]` (see below).

## What the emitted SBOM contains

Because the hook shares the `pitloom.assemble.spdx3.document.build()`
assembly layer with the CLI, every SBOM Pitloom produces -- embedded or
standalone -- includes:

- A `software_File` element per packaged file, each carrying a SHA-256
  `verifiedUsing` hash (`spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256,
  hashValue=<digest>)`) computed from the same file content used for the
  document's Merkle-root UUID seed. Directory nodes carry no hash.
- A `pkg:pypi/<name>@<version>` PURL (`software_packageUrl`) on the main
  project package, mirroring the PURL already generated for dependencies,
  whenever a real (non-`"unknown"`) version is known.

## Fragment merging and `[tool.pitloom]` configuration

Fragment paths listed under `[tool.hatch.build.hooks.pitloom] fragments` are
merged with any fragments already declared under `[tool.pitloom] fragments`.
The hook concatenates both lists and passes them to `merge_fragments()`.

This means the existing fragment-merging logic is reused unchanged; the hook
only needs to forward the combined list.

## `build_data["sbom_files"]` API

Hatchling 1.28.0 introduced native PEP 770 support.  The wheel builder
initialises `build_data["sbom_files"]` as an empty list and, after all hook
`initialize()` calls complete, copies every path in the list into
`.dist-info/sboms/<basename>` inside the wheel.

`initialize()` uses `build_data.setdefault("sbom_files", []).append(...)` so
that it is safe to call even if another hook or plugin has already added
entries to the list.

## Interaction diagram

```text
Developer runs:
  hatch build  OR  python -m build
         │
         ▼
  Hatchling build process
         │
         ├─── PitloomBuildHook.initialize()
         │       │
         │       ├── target_name != "wheel"? -> return (no sdist staging)
         │       ├── metadata_from_hatchling(self.metadata, project_dir)
         │       ├── read_pitloom_config(project_dir / "pyproject.toml")
         │       ├── get_wheel_files(project_dir)  -> file hashes + Merkle root
         │       ├── scan_project_for_ai_models(...)
         │       ├── assemble_spdx3(DocumentModel, merkle_root)
         │       ├── merge_fragments(all_fragments)
         │       ├── exporter.to_json(pretty=False)   <- JCS canonical, always
         │       ├── write staged SBOM -> TemporaryDirectory
         │       └── build_data["sbom_files"].append(staged_path)
         │
         ├─── Hatchling packages wheel
         │       └── copies sbom_files -> .dist-info/sboms/  <- PEP 770
         │
         └─── PitloomBuildHook.finalize()
                 └── TemporaryDirectory.cleanup()

Output:
  dist/
  ├── mypackage-1.0.tar.gz
  └── mypackage-1.0-py3-none-any.whl
          └── mypackage-1.0.dist-info/
                  └── sboms/
                          └── sbom.spdx3.json
```

## Source and test layout

```text
src/pitloom/
├── extract/
│   └── hatchling.py               # metadata_from_hatchling()
└── plugins/
    ├── __init__.py
    └── hatch.py                   # PitloomBuildHook + hatch_register_build_hook()
tests/
├── fixtures/
│   └── projects/
│       ├── sampleproject-hatchling/          # minimal wheel-build fixture
│       │   ├── pyproject.toml
│       │   ├── src/sampleproject_hatchling/__init__.py
│       │   └── README.md
│       └── sampleproject-hatchling-dynver/   # dynamic-version fixture
│           ├── pyproject.toml
│           ├── src/sampleproject_hatchling_dynver/
│           │   ├── __about__.py
│           │   └── __init__.py
│           └── README.md
├── test_hatch_hook.py
└── test_wheel_integration.py
```

### Changes to Pitloom's `pyproject.toml`

Register the plugin via pluggy entry point:

```toml
[project.entry-points."hatch"]
pitloom = "pitloom.plugins.hatch"
```

Require Hatchling 1.28.0+ for native `sbom_files` support:

```toml
dependencies = [
    "hatchling>=1.28.0",
    ...
]
```

## Test plan

| Test | Description |
| :--- | :--- |
| `test_validate_config_defaults_pass` | Empty config (all defaults) must not raise. |
| `test_validate_config_valid_values_pass` | Fully specified valid config must not raise. |
| `test_validate_config_invalid_raises` | Parametrized (7 cases): invalid field type or value must raise `ValueError` with a clear message. |
| `test_hook_initialize_stages_sbom` | Calls `initialize()` and asserts the staged SBOM path exists and is non-empty. |
| `test_hook_sbom_is_valid_json` | Asserts the staged SBOM is valid JSON-LD with `@context` and `@graph`. |
| `test_hook_creator_name_propagated` | Sets `creator-name` in config; asserts it appears in `@graph`. |
| `test_hook_custom_basename_stored` | Sets `sbom-basename`; asserts `_sbom_filename` and staged path name match. |
| `test_hook_disabled_skips_generation` | Sets `enabled = false`; asserts no staging path and no `sbom_files` entry. |
| `test_hook_finalize_cleans_up` | Asserts temp directory and paths are cleared after `finalize()`. |
| `test_hook_finalize_idempotent` | Calls `finalize()` twice; asserts no exception on the second call. |
| `test_hook_sbom_files_populated` | Asserts `build_data["sbom_files"]` is populated with the staged path after `initialize()`. |
| `test_hook_sbom_files_custom_basename` | Asserts `sbom-basename` config is reflected in the filename in `sbom_files`. |
| `test_hook_sbom_files_appended_to_existing` | Pre-populates `sbom_files`; asserts `initialize()` appends rather than replaces. |
| `test_hook_with_pitloom_fragments` | Provides a valid fragment; asserts its content is merged into the SBOM. |
| `test_hook_missing_fragment_logs_warning` | Provides a non-existent path; asserts a warning is logged, not an exception. |
| `test_hook_with_sampleproject_fixture` | Runs `initialize()` on the real `sampleproject-hatchling` fixture; asserts package name appears in SBOM. |
| `test_metadata_from_hatchling_maps_*` | Unit tests for `metadata_from_hatchling`: version, dependencies, urls, authors, license (direct and fallback-detected). |
| `test_hook_uses_hatchling_resolved_dynamic_version` | Runs `initialize()` on the `sampleproject-hatchling-dynver` fixture (a `[tool.hatch.version] source = "code"` computed version); asserts the resolved, code-evaluated version -- not a naive text scrape -- appears in the SBOM. |
| `test_hook_skips_non_wheel_target` | Sets `target_name = "sdist"`; asserts no staging and no `sbom_files` entry. |
| `test_hook_invalid_config_raises_before_io` | Passes bad config; asserts `ValueError` is raised before any filesystem access. |
| `test_hook_sbom_is_compact_despite_pretty_config` | Sets `[tool.pitloom] pretty = true`; asserts the embedded SBOM is still RFC 8785 (JCS) canonical. |
| `test_sbom_graph_contains_file_hashes` (`test_wheel_integration.py`) | Builds a real wheel; asserts every file-kind `software_File` in the embedded SBOM carries a SHA-256 `verifiedUsing` hash. |
| `test_sbom_graph_contains_main_package_purl` (`test_wheel_integration.py`) | Builds a real wheel; asserts the main package carries a `pkg:pypi/...@<version>` PURL. |

## References

- PEP 770: <https://peps.python.org/pep-0770/>
- Hatchling build hook reference: <https://hatch.pypa.io/latest/plugins/build-hook/reference/>
- Hatchling build hook interface: `hatchling.builders.hooks.plugin.interface.BuildHookInterface`
- Hatchling resolved project metadata: `hatchling.metadata.core.ProjectMetadata`
- Trivy PEP 770 tracking issue: <https://github.com/aquasecurity/trivy/issues/10021>
