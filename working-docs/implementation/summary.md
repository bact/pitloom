---
Created: 2026-02-06
Last-Modified: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom - SBOM generator implementation summary

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
   - `pyproject.py` -- reads `pyproject.toml`; supports PEP 621 `[project]`,
     Poetry `[tool.poetry]` (fallback when `[project]` is absent), and merging
     of both when both sections are present (`[project]` wins field-by-field)
   - `poetry.py` -- extracts metadata from `[tool.poetry]` and
     `[tool.poetry.dependencies]`; converts Poetry version specifiers
     (`^`, `~`, bare versions) to PEP 440; `[tool.poetry.group.*]` dev/deploy
     dependency groups are intentionally excluded from the SBOM
   - `setuptools.py` --
     reads `setup.cfg` and `setup.py` for setuptools projects;
     `detect_build_backend()` auto-selects the right extractor;
     `merge_metadata()` fills gaps across sources (setup.cfg > setup.py)
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
   - `generate_sbom()` orchestrates the full pipeline for source code
     (Source SBOM)
   - `generate_analyzed_sbom()` orchestrates the pipeline for built wheels
     (Analyzed SBOM), utilizing `wheel.py` and `binary.py` to identify phantom
      dependencies
   - `generate_deployed_sbom()` orchestrates the pipeline for active
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
     Hatchling 1.28.0+ places it at `.dist-info/sboms/<filename>`
     (PEP 770) natively
   - `finalize()` cleans up the staging directory
   - Config: `[tool.hatch.build.hooks.pitloom] enabled` only; basename,
     fragments, and creator/tool metadata come from `[tool.pitloom]` /
     `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]` /
     `[tool.pitloom.creation]` -- the same settings the CLI uses

6. **Command-line interface** (`src/pitloom/__main__.py`)
   - User-friendly argparse-based CLI with lifecycle-centric subcommands
     (`source`, `analyze`, `deployed`, `ids`)
   - Subcommands map to CISA SBOM types
     (`source` -> Source SBOM, `analyze` -> Analyzed SBOM --
     dispatches internally to a built `.whl`, a local AI model file,
     or a Hugging Face repository depending on the target's form --
     `deployed` -> Deployed SBOM of the currently installed environment);
     `ids` manages the Loom ID registry
   - Default output filename derived from project metadata
     (`{name}-{version}.spdx3.json`)
     or `[tool.pitloom] sbom-basename` when set
   - Creator information options
   - Clear error messages

7. **Metadata provenance tracking**
   (`src/pitloom/assemble/spdx3/provenance.py`,
   `src/pitloom/extract/pyproject.py`, `src/pitloom/loom.py`)
   - Tracks source of each metadata field
   - Records extraction method (static, dynamic, or inferred)
   - Supports dynamic introspection via `loom.py` inspection
   - Recorded as SPDX 3 Core `Annotation` elements
     (structured, machine-readable JSON),
     with the original SPDX 3 `comment` attribute kept for back-compat,
     controlled by `[tool.pitloom.provenance]`
   - See [working-docs/design/metadata-provenance.md](../design/metadata-provenance.md)
     and [annotation-provenance.md](annotation-provenance.md)

8. **ML tracking SDK** (`src/pitloom/loom.py`)
   - Dual-syntax ContextDecorator (`@loom.run` and `with loom.run`)
   - Emits SPDX 3 SBOM fragments automatically during ML executions
   - Seamlessly ingested into project SBOMs using
     `[tool.pitloom.fragments]` config

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
> counts below predate the `source`/`analyze`/`deployed`/`ids` CLI
> subcommands (PR #96) and provenance-as-Annotation (see
> [annotation-provenance.md](annotation-provenance.md)) -- a current run
> uses `loom source <path>`, not the bare positional form shown here, and
> emits additional `Annotation` elements for provenance. Kept as a record
> of the initial validation, not a spec for current output shape; see
> [examples/sentimentdemo-aibom/](../../examples/sentimentdemo-aibom/) for
> a current, fuller worked example (AI pipeline, fragments, dataset).

Successfully generated SPDX 3 SBOM for the reference repository:

```text
$ loom /tmp/sentimentdemo -o sbom.spdx3.json
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

> This tree is the canonical reference; README.md and design docs point here.
> `docs/` is the published GitHub Pages site (flat, user-facing);
> `working-docs/design/` and `working-docs/implementation/` are the
> internal design/progress docs, including this file.

```text
pitloom/
├── docs/                           # Published site (flat; docs/_config.yml)
│   ├── creation-metadata.md
│   ├── index.md
│   ├── metadata-provenance.md
│   ├── mascot.png
│   └── resources.md
├── working-docs/
│   ├── design/
│   │   ├── adoption-surfaces.md
│   │   ├── architecture-overview.md
│   │   ├── cli-ux.md
│   │   ├── format-neutral-representation.md
│   │   ├── hatchling-build-hook.md
│   │   ├── metadata-provenance.md
│   │   ├── metadata-sources.md
│   │   ├── mlflow-extractor.md
│   │   ├── model-metadata-extraction.md
│   │   ├── protobom-evaluation.md
│   │   ├── roadmap.md              # Canonical roadmap
│   │   ├── sbom-enrichment.md
│   │   └── sbom-fragments.md
│   └── implementation/
│       ├── agent-skill.md
│       ├── annotation-provenance.md  # Provenance-as-Annotation design + status
│       ├── annotation-provenance-full-plan.md
│       ├── claude-code-plugin.md
│       ├── demo.md
│       ├── demo-provenance.md      # Historical; predates Annotation provenance
│       ├── github-action.md
│       ├── license-pipeline.md
│       ├── phase2-native-backfill-handover.md
│       ├── poetry-support.md
│       ├── setuptools-support.md   # Setuptools extractor design and limitations
│       └── summary.md              # this file; canonical project structure
├── skills/                         # Claude Code Skills (also bundled by .claude-plugin/)
│   ├── sbom/                       # Generate an SBOM/AIBOM
│   └── enrich/                     # Enrich an existing SBOM with agent-inferred facts
├── .claude-plugin/
│   ├── plugin.json                 # Plugin manifest
│   └── marketplace.json            # Self-hosted marketplace entry
├── examples/
│   └── sentimentdemo-aibom/        # Worked AI-pipeline SBOM example
├── src/
│   └── pitloom/
│       ├── assemble/               # Layers 2+3 -- build DocumentModel + map to spec
│       │   ├── spdx3/              # SPDX 3 specific (future: spdx23, cyclonedx)
│       │   │   ├── ai.py           # AI model element assembly
│       │   │   ├── creation_info.py # Shared CreationInfo construction
│       │   │   ├── dataset.py      # Dataset element assembly
│       │   │   ├── deps.py         # Dependency + license element assembly
│       │   │   ├── document.py     # build(DocumentModel) -> Spdx3JsonExporter
│       │   │   ├── fragments.py    # Fragment merging + unification provenance
│       │   │   ├── provenance.py   # Provenance Annotation builders/emitter
│       │   │   └── __init__.py
│       │   └── __init__.py         # generate_*_sbom() orchestrators + backend routing
│       ├── core/                   # Format-neutral data models (no SBOM lib deps)
│       │   ├── ai_metadata.py      # AiModelMetadata, ModelFormat
│       │   ├── config.py           # PitloomConfig ([tool.pitloom] settings)
│       │   ├── creation.py         # CreationMetadata (creator / timestamp)
│       │   ├── dataset_metadata.py # DatasetMetadata
│       │   ├── document.py         # DocumentModel (assembled, pre-serialization)
│       │   ├── models.py           # Deterministic UUIDs, Merkle root, SPDX ID generation
│       │   └── project.py          # ProjectMetadata, ProjectFile
│       ├── export/                 # Layer 4 -- serialise to physical format
│       │   └── spdx3_json.py       # SPDX 3 JSON-LD serialiser
│       ├── extract/                # Layer 1 -- read from sources
│       │   ├── ai_model.py         # AI model dispatcher + format detection
│       │   ├── _croissant.py       # Croissant metadata parser
│       │   ├── _croissant_keys.py  # Croissant JSON-LD key constants
│       │   ├── _extract_utils.py   # Shared extraction utilities (incl. provenance sanitization)
│       │   ├── _fasttext.py        # fastText (.ftz, .bin)
│       │   ├── _gguf.py            # GGUF (.gguf)
│       │   ├── _hdf5.py            # HDF5 / Keras v1–v2 (.h5, .hdf5)
│       │   ├── _huggingface.py     # Hugging Face Hub model extraction
│       │   ├── _keras.py           # Keras v3 (.keras)
│       │   ├── _license.py         # License file/id detection
│       │   ├── _numpy.py           # NumPy (.npy, .npz)
│       │   ├── _onnx.py            # ONNX (.onnx)
│       │   ├── _pytorch.py         # PyTorch classic (.pt, .pth)
│       │   ├── _pytorch_pt2.py     # PyTorch PT2 / ExecuTorch (.pt2)
│       │   ├── _safetensors.py     # Safetensors (.safetensors)
│       │   ├── binary.py           # Bundled third-party binary ("phantom dependency") detection in a wheel
│       │   ├── dataset.py          # Dataset metadata extraction (Croissant)
│       │   ├── env.py              # Deployed SBOM: installed-environment dependency tree via pipdeptree
│       │   ├── hatchling.py        # Metadata from Hatchling's own resolved ProjectMetadata (build hook path)
│       │   ├── poetry.py           # [tool.poetry] extractor; Poetry -> PEP 440 conversion
│       │   ├── project.py          # pyproject.toml/setup.cfg/setup.py -> (ProjectMetadata, PitloomConfig) dispatcher
│       │   ├── pyproject.py        # pyproject.toml extractor ([project] + [tool.poetry] merge)
│       │   ├── scanner.py          # Heuristic scanner for AI model files
│       │   ├── setuptools.py       # setup.cfg + setup.py extractor; backend detection; merge
│       │   └── wheel.py            # Analyzed SBOM: project metadata + file records from a built .whl
│       ├── plugins/                # Build-system integrations
│       │   └── hatch.py            # Hatchling BuildHookInterface (PEP 770)
│       ├── __about__.py            # Package version (__version__)
│       ├── __init__.py
│       ├── __main__.py             # CLI entry point (loom / python -m pitloom): source|analyze|deployed|ids
│       ├── ids.py                  # Loom ID registry (loom-ids.json); stable cross-fragment SPDX ids
│       ├── loom.py                 # ML tracking SDK (Run context manager / decorator)
│       └── py.typed                # PEP 561 marker
├── tests/
│   ├── fixtures/                   # Per-format model/project fixtures (see fixtures/README.md)
│   ├── conftest.py
│   ├── test_annotation_provenance.py  # Provenance Annotation builders/emitter
│   ├── test_provenance_integration.py # N1/N2/N4/N5/N6 native-construct integration
│   └── test_*.py                   # One file per extractor/assembler/CLI surface
├── AGENTS.md
├── CHANGELOG.md
├── CITATION.cff
├── LICENSE
├── README.md
├── codemeta.json
└── pyproject.toml                  # Project config and Hatchling build settings
```

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
