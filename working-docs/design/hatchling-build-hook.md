---
Created: 2026-03-25
Last-Modified: 2026-07-08
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
    └── {name}-{version}.spdx3.json
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
  `requires_python`. Accessing a declared-but-missing readme/license file
  raises `OSError` from these lazily-evaluated properties;
  `metadata_from_hatchling()` catches it and degrades gracefully, mirroring
  `read_pyproject()`'s own tolerance for the same case.
- Normalized the project `name` per PEP 503 (`_` and `.` collapsed to `-`,
  lowercased) as `core.name`, while retaining the original, un-normalized
  spelling as `core.raw_name`. `metadata_from_hatchling()` uses `raw_name`,
  matching the literal spelling `read_pyproject()` reports for the same
  `[project] name` in `pyproject.toml`, so the CLI and the build hook agree
  on the project's displayed name (and therefore on the deterministic
  document UUID, which is derived from it).
- Normalizes each dependency specifier's name the same PEP 503 way, via one
  shared `normalize_dependency_specifier()` helper
  (`pitloom.core.models`) that wraps
  `hatchling.metadata.utils.normalize_requirement()`. Both
  `metadata_from_hatchling()` and `read_pyproject()` call this same
  function -- Hatchling's own `core.dependencies` is already canonicalized,
  so the call is idempotent there, but routing both paths through one
  function means they cannot independently drift again. The main
  package's `pkg:pypi/<name>@<version>` PURL and each dependency's PURL are
  likewise built through one shared `build_pypi_purl()` helper (same
  module), which canonicalizes via `packaging.utils.canonicalize_name()`.
- When `[project]` is missing fields (`authors`, `keywords`, `urls`, ...),
  `metadata_from_hatchling()` reads the same `pyproject.toml` a second time
  and reuses `read_pyproject()`'s own `_try_read_poetry()` /
  `_merge_with_poetry()` helpers to fill the gaps from `[tool.poetry]`,
  mirroring what `read_pyproject()` already does for the CLI path.

The build hook maps this object into Pitloom's format-neutral
`ProjectMetadata` via
`pitloom.extract.hatchling.metadata_from_hatchling(self.metadata,
project_dir)` -- **not** via `pitloom.extract.pyproject.read_pyproject()`,
which re-parses `pyproject.toml` from scratch and cannot see dynamic values
resolved by Hatchling plugins. `read_pyproject()` remains the metadata source
for the standalone CLI (`pitloom`/`loom project`), which has no build
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
requires = ["hatchling>=1.31.0", "pitloom>=0.13.3"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
enabled = true    # set to false to skip SBOM generation; the only field
                  # this section supports
```

`[tool.hatch.build.hooks.pitloom]` controls only whether the hook runs.
Everything else -- basename, fragments, creator/tool metadata -- is
configured once under `[tool.pitloom]` / `[[tool.pitloom.creator]]` /
`[[tool.pitloom.creation-tool]]` / `[tool.pitloom.creation]`, the same
settings the CLI reads via `read_pitloom_config()`. `_validate_config()`
rejects `sbom-basename`, `creator-name`, `creator-email`, `creator-type`,
`creation-tool`, or `fragments` under the hook section (naming the correct
location), and rejects any other unrecognised key.

```toml
[tool.pitloom]
sbom-basename = ""          # Name part only, no extension; default "sbom"

[[tool.pitloom.creator]]    # Repeatable; omit entirely for no named creator
name = ""                   # (SoftwareAgent "Pitloom" is recorded instead)
email = ""                  # Optional
type = ""                   # person (default), organization, software-agent, agent

[[tool.pitloom.creation-tool]]  # Repeatable; omit for the default "Pitloom" tool
name = ""

[tool.pitloom.fragments]
files = []                  # List of pre-generated fragment paths to merge
```

The full SBOM filename is derived by appending the format extension to the
basename: `{sbom-basename}.spdx3.json` (e.g., `mypackage-1.0.0.spdx3.json`
by default, from the resolved project name/version).

Specifying fragments allows the hook to merge `pitloom.loom`-generated AI/ML
fragments produced during training before the build:

```toml
[tool.pitloom.fragments]
files = [
    "fragments/train_run.spdx3.json",
    "fragments/eval_run.spdx3.json",
]
```

## SBOM filename conventions

### Inside the wheel (PEP 770)

The default filename is `{name}-{version}.spdx3.json`, derived from the
resolved project name/version (e.g. `mypackage-1.0.0.spdx3.json`). The
user can override the base name via `sbom-basename`; the `.spdx3.json`
extension is always appended by Pitloom to reflect the SPDX 3 JSON-LD
format.

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
   invalid values, or any of the moved keys (`sbom-basename`,
   `creator-name`, `creator-email`, `creator-type`, `creation-tool`,
   `fragments`), raise `ValueError` before any file I/O.
2. Returns early if `enabled = false`, or if `self.target_name != "wheel"`.
3. Reads `read_pitloom_config(project_dir / "pyproject.toml")` for
   `[tool.pitloom]` / `[[tool.pitloom.creator]]` /
   `[[tool.pitloom.creation-tool]]` / `[tool.pitloom.creation]` settings
   (basename, fragments, creator/tool metadata), then builds the format-neutral
   document via `_build_document_model`, which calls
   `metadata_from_hatchling(self.metadata, project_dir)` for project
   metadata (including the Poetry-fallback gap-fill and dependency/name
   canonicalization described above), then `get_wheel_files(project_dir)`
   for the packaged file set (SHA-256 digests + Merkle root) and
   `scan_project_for_ai_models` for embedded AI/ML metadata.
4. Assembles the SPDX 3 document via `assemble_spdx3` (the shared
   `pitloom.assemble.spdx3.document.build()` used by the CLI), then merges
   `[tool.pitloom.fragments]`.
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
  whenever a real (non-`"unknown"`) version is known. Both PURLs are built
  through the same shared `build_pypi_purl()` helper (see above), so a
  dotted or underscored name (e.g. `zope.interface`) canonicalizes
  identically on the main package and on dependencies.

## Fragment merging and `[tool.pitloom]` configuration

Fragment paths listed under `[tool.pitloom.fragments] files` are passed
directly to `merge_fragments()` -- the same call the CLI makes, on the same
list. There is nothing hook-specific to merge in; a project's fragment list
is the same whether it's assembled by `loom` on the command line or by the
build hook.

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
                          └── mypackage-1.0.spdx3.json
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
    "hatchling>=1.31.0",
    ...
]
```

## Test plan

| Test | Description |
| :--- | :--- |
| `test_validate_config_defaults_pass` | Empty config (all defaults) must not raise. |
| `test_validate_config_valid_values_pass` | The only supported key, `enabled`, must not raise. |
| `test_validate_config_invalid_raises` | Parametrized: an invalid `enabled` type must raise `ValueError` with a clear message. |
| `test_validate_config_moved_key_raises` | Parametrized: `sbom-basename`/`fragments`/`creator-name`/`creator-email`/`creator-type`/`creation-tool` under the hook section must raise, naming the new `[tool.pitloom]` / `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]` location. |
| `test_validate_config_unknown_key_raises` | An unrecognised key must raise rather than being silently ignored. |
| `test_hook_initialize_stages_sbom` | Calls `initialize()` and asserts the staged SBOM path exists and is non-empty. |
| `test_hook_sbom_is_valid_json` | Asserts the staged SBOM is valid JSON-LD with `@context` and `@graph`. |
| `test_hook_creator_name_propagated` | Sets `[[tool.pitloom.creator]] name` in `pyproject.toml`; asserts it appears in `@graph`. |
| `test_hook_organization_creator_from_config` | Sets `type = "organization"`; asserts an `Organization` (not `Person`) appears. |
| `test_hook_software_agent_and_generic_agent_creator_from_config` | Parametrized: `type = "software-agent"`/`"agent"` also produce the matching Agent subclass. |
| `test_hook_multiple_creators_appear_in_graph` | Two `[[tool.pitloom.creator]]` tables both appear in `@graph`, as their own Agent subclasses, and both are listed in `createdBy`. |
| `test_hook_default_creator_is_software_agent` | No named creator: the hook records the `SoftwareAgent` "Pitloom" as `createdBy`. |
| `test_hook_creation_comment_and_tool_summary` | Asserts the hook stamps its own `CreationInfo.comment` and a Pitloom-versioned `Tool.summary`. |
| `test_hook_custom_basename_stored` | Sets `[tool.pitloom] sbom-basename`; asserts `_sbom_filename` and staged path name match. |
| `test_hook_disabled_skips_generation` | Sets `enabled = false`; asserts no staging path and no `sbom_files` entry. |
| `test_hook_finalize_cleans_up` | Asserts temp directory and paths are cleared after `finalize()`. |
| `test_hook_finalize_idempotent` | Calls `finalize()` twice; asserts no exception on the second call. |
| `test_hook_sbom_files_populated` | Asserts `build_data["sbom_files"]` is populated with the staged path after `initialize()`. |
| `test_hook_sbom_files_custom_basename` | Asserts `[tool.pitloom] sbom-basename` is reflected in the filename in `sbom_files`. |
| `test_hook_sbom_files_appended_to_existing` | Pre-populates `sbom_files`; asserts `initialize()` appends rather than replaces. |
| `test_hook_with_pitloom_fragments` | Provides a valid fragment via `[tool.pitloom.fragments] files`; asserts its content is merged into the SBOM. |
| `test_hook_missing_fragment_logs_warning` | Provides a non-existent path; asserts a warning is logged, not an exception. |
| `test_hook_with_sampleproject_fixture` | Runs `initialize()` on the real `sampleproject-hatchling` fixture; asserts package name appears in SBOM. |
| `test_metadata_from_hatchling_maps_*` | Unit tests for `metadata_from_hatchling`: version, dependencies, urls, authors, license (direct and fallback-detected). |
| `test_metadata_from_hatchling_canonicalises_dependency_markers` | Dependency specifiers with source-quoted markers normalize to `packaging`'s canonical form via the shared helper. |
| `test_metadata_from_hatchling_matches_read_pyproject_for_noncanonical_name` | Regression guard: hook and CLI paths agree on name, dependencies, and doc UUID for a project with an uppercase/underscore/dotted name and dependencies (the gap the `raw_name`-only fix didn't fully close). |
| `test_metadata_from_hatchling_tolerates_none_authors_data` | `authors_data=None` must not crash `metadata_from_hatchling`. |
| `test_metadata_from_hatchling_tolerates_missing_readme_file` / `test_metadata_from_hatchling_tolerates_missing_license_file` | A declared but missing readme/license file must degrade gracefully (`OSError` caught), not crash the build. |
| `test_metadata_from_hatchling_fills_gaps_from_poetry` | `[tool.poetry]` fills `authors`/`keywords` missing from `[project]`, mirroring `read_pyproject()`'s CLI-path fallback. |
| `test_hook_uses_hatchling_resolved_dynamic_version` | Runs `initialize()` on the `sampleproject-hatchling-dynver` fixture (a `[tool.hatch.version] source = "code"` computed version); asserts the resolved, code-evaluated version -- not a naive text scrape -- appears in the SBOM. |
| `test_hook_skips_non_wheel_target` | Sets `target_name = "sdist"`; asserts no staging and no `sbom_files` entry. |
| `test_hook_invalid_config_raises_before_io` | Passes bad config; asserts `ValueError` is raised before any filesystem access. |
| `test_hook_sbom_is_compact_despite_pretty_config` | Sets `[tool.pitloom] pretty = true`; asserts the embedded SBOM is still RFC 8785 (JCS) canonical. |
| `test_sbom_graph_contains_file_hashes` (`test_wheel_integration.py`) | Builds a real wheel; asserts every file-kind `software_File` in the embedded SBOM carries a SHA-256 `verifiedUsing` hash. |
| `test_sbom_graph_contains_main_package_purl` (`test_wheel_integration.py`) | Builds a real wheel; asserts the main package carries a `pkg:pypi/...@<version>` PURL. |
| `test_sbom_multiple_creators_and_tools_in_wheel` (`test_wheel_integration.py`) | Builds a real wheel from the `sampleproject-hatchling` fixture (now declaring 2 creators + 2 creation tools); resolves `CreationInfo.createdBy`/`createdUsing` to graph elements and asserts both agents and both tools appear correctly. |

## References

- PEP 770: <https://peps.python.org/pep-0770/>
- Hatchling build hook reference: <https://hatch.pypa.io/latest/plugins/build-hook/reference/>
- Hatchling build hook interface: `hatchling.builders.hooks.plugin.interface.BuildHookInterface`
- Hatchling resolved project metadata: `hatchling.metadata.core.ProjectMetadata`
- Trivy PEP 770 tracking issue: <https://github.com/aquasecurity/trivy/issues/10021>
- [wheel-sbom-verification.md](../implementation/wheel-sbom-verification.md) --
  independent check of this design's output against the real, published
  v0.9.0 wheel (location, fields, hashes, SPDX 3.0.1 schema/SHACL
  conformance).
