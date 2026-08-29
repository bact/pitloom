---
Created: 2026-02-06
Last-Modified: 2026-08-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom - SBOM generator implementation summary

See also: [file-map.md](file-map.md) for the full project directory tree.

## Project overview

Successfully implemented a complete, production-ready prototype of an SBOM
(Software Bill of Materials) generator for Python projects.  Supports
Hatchling, Poetry, and setuptools build backends.  The generator produces
SPDX 3.0 compliant SBOMs in JSON-LD format.

## What was delivered

### ✅ Core functionality

1. **SPDX 3.0 data models** (`spdx-python-model`)
   - Fully migrated to the official `spdx-python-model` library
   - Proper JSON-LD serialization and validation
   - Deterministic UUIDv5 SPDX document IDs (`compute_doc_uuid`) keyed on
     project name, version, normalized dependencies,
     and SHA-256 Merkle root of wheel files
   - Per-element sequential IDs (`generate_spdx_id`) reproducible across builds

2. **Metadata extraction** (`src/pitloom/extract/`)
   - `_pyproject.py` -- reads `pyproject.toml`; supports PEP 621 `[project]`,
     Poetry `[tool.poetry]` (fallback when `[project]` is absent), and merging
     of both when both sections are present (`[project]` wins field-by-field)
   - `_poetry.py` -- extracts metadata from `[tool.poetry]` and
     `[tool.poetry.dependencies]`; converts Poetry version specifiers
     (`^`, `~`, bare versions) to PEP 440; `[tool.poetry.group.*]` dev/deploy
     dependency groups are intentionally excluded from the SBOM
   - `_setuptools.py`, `_setuptools_cfg.py`, `_setuptools_py.py` --
     extract metadata from `setup.cfg` and `setup.py` for setuptools projects;
     `detect_build_backend()` auto-selects the right extractor;
     `merge_metadata()` fills gaps across sources (setup.cfg > setup.py)
   - `project.py`/`wheel.py`/`env.py`/`ai_model.py`/`hatchling.py`/
     `binary.py`/`scanner.py` are the public, cross-package-imported entry
     points; `_pyproject.py`/`_poetry.py`/`_setuptools*.py`/`_sdist.py` and
     the per-model-format parsers below them are internal-only (leading
     underscore = nothing outside `extract/` imports it -- see `AGENTS.md`'s
     Naming section for the rule)
   - `wheel.py` -- reads metadata from built `.whl` files (Analyzed SBOM) and
     computes file-level SHA-256 hashes
   - `env.py` -- delegates to `pipdeptree` to extract a complete dependency
     graph of the active installed environment (Deployed SBOM)
   - `binary.py` -- heuristic scanner that detects bundled third-party binary
     libraries (e.g. `.so`, `.dylib`) within wheel files (phantom dependencies)
   - Extracts project metadata (name, version, description, authors, URLs)
   - Handles dynamic versions from `__about__.py`
   - Parses dependency specifications with version constraints
   - Returns `(ProjectMetadata, PitloomConfig)` tuple

3. **SPDX 3 exporter** (`src/pitloom/export/spdx3_json.py`)
   - JSON-LD output using official bindings and SHACLObjectSet
   - Clean API for building SPDX documents and adding elements
   - Graceful component ingestion via `spdx3.JSONLDDeserializer`

4. **SBOM generator** (`src/pitloom/assemble/`)
   - `generate_project_sbom()` / `generate()` orchestrates the full pipeline
     for source code (Source SBOM)
   - `generate_wheel_sbom()` and `generate_model_sbom()` orchestrate the
     pipeline for built wheels and AI models
     (Analyzed SBOM), utilizing `wheel.py`, `ai.py`, and `binary.py`
     to identify phantom dependencies
   - `generate_env_sbom()` orchestrates the pipeline for active
     environments (Deployed SBOM), mapping the tree using `env.py`
   - Builds `DocumentModel` from extracted metadata
   - Passes `DocumentModel` to assembly functions
     (`build()`, `build_deployed()`) in `assemble/spdx3/`
   - Merges pre-generated SBOM fragments
   - Generates copyright information from metadata

5. **Hatchling build hook** (`src/pitloom/plugins/hatch.py`)
   - `PitloomBuildHook` registered via pluggy entry point
     (`[project.entry-points."hatch"]`)
   - Generates SBOM in `initialize()`, stages to a `TemporaryDirectory`
   - Appends staged path to `build_data["sbom_files"]` --
     Hatchling 1.29.0+ places it at `.dist-info/sboms/<filename>`
     (PEP 770) natively
   - `finalize()` cleans up the staging directory
   - Config: `[tool.hatch.build.hooks.pitloom] enabled` only; basename,
     fragments, and creator/tool metadata come from `[tool.pitloom]` /
     `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]` /
     `[tool.pitloom.creation]` -- the same settings the CLI uses

6. **Command-line interface & API redesign** (`src/pitloom/cli/`,
  `src/pitloom/__main__.py`, `src/pitloom/assemble/`)
   - `__main__.py` is a thin entry point only: logging setup and
     `args.func(args)` dispatch. Argparse construction (`cli/parser.py`),
     CLI-vs-`pyproject.toml`-vs-default option resolution (`cli/options.py`),
     `--verbose` reporting (`cli/verbose.py`), the `ids` subcommand
     (`cli/ids.py`), and each subcommand's own `_run_<verb>_command()` +
     `add_parser()` (`cli/commands/*.py`, one module per subcommand) all
     live under `cli/` -- see
     [cli-test-coverage-roadmap.md](../design/cli-test-coverage-roadmap.md)
     for the per-module breakdown
   - User-friendly argparse-based CLI with input-centric subcommands
     (`project`, `wheel`, `model`, `env`, `merge`, `embed-wheel`, `ids`)
     and a smart entrypoint `loom generate [TARGET]` (requires `-o`,
     unlike the input-centric subcommands, which each have an obvious
     target-derived default filename)
   - Emitted SBOM data model strictly complies with CISA 6 SBOM Types
     (Source, Build, Analyzed, Deployed, Runtime per CISA April 2023 guide)
     and SPDX 3.0.1
   - `loom project` scans unbuilt source directories or `.tar.gz`/`.zip` sdist
     archives (Source SBOM)
   - `loom wheel` scans built `.whl` archives (Analyzed SBOM)
   - `loom model` scans local model files or Hugging Face repositories with
     explicit `--offline` support (Analyzed AIBOM)
   - `loom env` scans the active installed environment (Deployed SBOM)
   - `loom merge` stitches dynamic execution fragments (Runtime SBOM)
   - Python API harmonized 1:1 (`pitloom.generate()`,
     `generate_project_sbom()`, `generate_wheel_sbom()`,
     `generate_model_sbom()`, `generate_env_sbom()`)
   - See [working-docs/implementation/cli-ux.md](cli-ux.md)
   - Default output filename derived from project metadata
     (`{name}-{version}.spdx3.json`)
     or `[tool.pitloom] sbom-basename` when set
   - Creator information options
   - Clear error messages

7. **Metadata provenance tracking**
   (`src/pitloom/assemble/spdx3/provenance.py`,
   `src/pitloom/extract/_pyproject.py`, `src/pitloom/loom.py`)
   - Tracks source of each metadata field
   - Records extraction method (static, dynamic, or inferred)
   - Supports dynamic introspection via `loom.py` inspection
   - Recorded as SPDX 3 Core `Annotation` elements
     (structured, machine-readable JSON),
     with the original SPDX 3 `comment` attribute kept for back-compat,
     controlled by `[tool.pitloom.provenance]`
   - See [working-docs/implementation/provenance/metadata-provenance.md](provenance/metadata-provenance.md)
     and [annotation-provenance.md](provenance/annotation-provenance.md)

8. **ML tracking SDK** (`src/pitloom/loom.py`)
   - Dual-syntax ContextDecorator (`@loom.run` and `with loom.run`)
   - Emits SPDX 3 SBOM fragments automatically during ML executions
   - Seamlessly ingested into project SBOMs using
     `[tool.pitloom.fragment]` config

### ✅ Testing (comprehensive coverage - all passing)

1. **Model & provenance tests**
   - SPDX ID generation
   - CreationMetadata serialization and provenance tracking
   - `spdx-python-model` validation

2. **Metadata extraction tests**
   - Basic metadata extraction and generic fragment paths
   - Error handling for missing files
   - Dynamic and build-time version extraction via `importlib.metadata`

3. **Generator integration tests**
   - End-to-end SBOM generation
   - Generic fragment merging via Deserialization

4. **SDK tracker tests**
   - `test_loom.py` verifies both Decorator and Context Manager tracking
   - Asserts caller-inspection relative path generation

### ✅ Quality assurance

- **Linting**: pylint 10.00/10, flake8 clean, ruff clean
- **Type checking**: mypy -- no issues across all source files
- **Type hints**: Comprehensive type annotations throughout
- **Documentation**: Inline docstrings for all public APIs

### ✅ Documentation

1. **README.md**: Complete usage guide with examples
2. **working-docs/implementation/demo.md**:
   Prototype capabilities and validation
3. **working-docs/implementation/demo-provenance.md**: Provenance tracking demo
4. **working-docs/design/format-neutral-representation.md**:
   Multi-format support plan
5. **working-docs/design/metadata-provenance.md**:
   Provenance tracking specification
6. **working-docs/design/metadata-sources.md**:
   Metadata sources research and integration plan
7. **working-docs/implementation/setuptools-support.md**:
   Setuptools extractor design and limitations
8. **Inline documentation**: Comprehensive docstrings

## Validation with sentimentdemo

> **Historical snapshot, early prototype.** The invocation and element
> counts below predate the input-centric CLI subcommands
> (`project`/`wheel`/`model`/`env`/`generate`/`ids`) and
> provenance-as-Annotation (see
> [annotation-provenance.md](provenance/annotation-provenance.md)) -- a current run
> uses `loom project <path>` (or `loom generate <path>`), not the bare
> un-namespaced form shown here, and
> emits additional `Annotation` elements for provenance. Kept as a record
> of the initial validation, not a spec for current output shape; see
> [examples/sentimentdemo-aibom/](../../examples/sentimentdemo-aibom/) for
> a current, fuller worked example (AI pipeline, fragments, dataset).

Successfully generated SPDX 3 SBOM for the reference repository:

```text
$ loom project /tmp/sentimentdemo -o sbom.spdx3.json
Generating SBOM for project in: /tmp/sentimentdemo
SBOM written to: sbom.spdx3.json
```

### Generated SBOM structure

- **Total Elements**: 14
- **CreationInfo**: 1 (with timestamp and creator)
- **SoftwareAgent**: 1 (default createdBy agent when no creator is named;
  one `Person`/`Organization` per `[[tool.pitloom.creator]]` table instead
  when set)
- **Tool**: 1 (Pitloom, in createdUsing)
- **SpdxDocument**: 1 (root document)
- **software_Sbom**: 1 (SBOM declaration)
- **software_Package**: 5 (main package + 4 dependencies)
- **Relationship**: 4 (dependsOn relationships)

### Captured information

**Main package:**

- Name: sentimentdemo
- Version: 0.0.2 (dynamically extracted)
- Download: <https://github.com/bact/sentimentdemo>
- Description: Full description preserved

**Dependencies (all captured correctly):**

- fasttext: 0.9.3
- newmm-tokenizer: 0.2.2
- numpy: 1.26.4
- th-simple-preprocessor: 0.10.1

## Technical achievements

### 1. Clean architecture

Src-layout, one directory per pipeline layer
(`extract/` -> `core/` -> `assemble/` -> `export/`), plus a `cli/`
package for the CLI surface and a `tests/` tree that mirrors
`src/pitloom/<package>/` once an area grows past a few files. See
[file-map.md](file-map.md) for the full tree.

### 2. Extensible design

- Easy to add new extractors (PDM, Flit, etc.)
- Easy to add new assemblers/exporters (CycloneDX, AIDOC, etc.) consuming
  the same `DocumentModel` -- no changes to extractors needed
- Clean separation of concerns: extractors -> `DocumentModel` -> serializers

### 3. Best practices

- src-layout for proper package structure
- Type hints with Python 3.10+ compatibility
- Comprehensive error handling
- Runtime dependencies kept minimal and declared in `pyproject.toml`

## Comparison with reference SBOM

| Feature | Reference SBOM | Pitloom Generated | Status |
| ------- | -------------- | -------------- | ------ |
| SPDX 3.0 Structure | ✅ | ✅ | ✅ Complete |
| Package Metadata | ✅ | ✅ | ✅ Complete |
| Dependencies | ✅ | ✅ | ✅ Complete |
| Relationships | ✅ | ✅ | ✅ Complete |
| File-level Details | ✅ | ⚠️ | 🔄 Roadmap |
| AI/Dataset Profiles | ✅ | ✅ | ✅ Complete |
| License Expressions | ✅ | ⚠️ | 🔄 Roadmap |

**Legend:**

- ✅ Complete: Fully implemented
- ⚠️ Basic: Core functionality present, enhancements planned
- 🔄 Roadmap: Planned for future releases

## Roadmap

See [working-docs/design/roadmap.md](../design/roadmap.md) for the canonical,
up-to-date roadmap.
