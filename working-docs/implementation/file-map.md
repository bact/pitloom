---
Created: 2026-08-17
Last-Modified: 2026-08-18
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom - project file map

See also: [summary.md](summary.md) (implementation summary this tree
was split out of) and
[cli-test-coverage-roadmap.md](../design/cli-test-coverage-roadmap.md)
(the CLI, test-suite, and source modularization this tree reflects).

This tree is the canonical reference for the repository's file/directory
layout; `README.md` and design docs point here rather than duplicating
it. `docs/` is the published GitHub Pages site (flat, user-facing);
`working-docs/design/` and `working-docs/implementation/` are the
internal design/progress docs, including this file.

```text
pitloom/
├── docs/                           # Published site (mkdocs.yml at repo root)
│   ├── agent-skills.md
│   ├── ai-model-formats.md
│   ├── api.md
│   ├── claude-code-plugin.md
│   ├── cli.md
│   ├── configuration.md
│   ├── creation-metadata.md
│   ├── github-action.md
│   ├── hatchling-build-hook.md
│   ├── index.md
│   ├── mascot.png
│   ├── metadata-provenance.md
│   ├── python-api.md
│   └── resources.md
├── working-docs/
│   ├── design/
│   │   ├── adoption-surfaces.md
│   │   ├── architecture-overview.md
│   │   ├── cli-test-coverage-roadmap.md        # CLI split + test suite modularization roadmap
│   │   ├── complexity-and-file-size-roadmap.md # Complexity metrics and file limits tracking
│   │   ├── format-neutral-representation.md
│   │   ├── metadata-sources.md
│   │   ├── mlflow-extractor.md
│   │   ├── model-metadata-extraction.md
│   │   ├── provenance-enrichment-vocabulary.md
│   │   ├── roadmap.md              # Canonical roadmap
│   │   ├── sbom-enrichment.md
│   │   └── sbom-fragments.md
│   ├── implementation/
│   │   ├── provenance/             # 4 files -- annotation-provenance(-full-plan).md, etc.
│   │   ├── adoption-surfaces.md
│   │   ├── agent-skill.md
│   │   ├── claude-code-plugin.md
│   │   ├── cli-ux.md
│   │   ├── demo.md
│   │   ├── file-headers.md
│   │   ├── file-map.md             # this file
│   │   ├── github-action.md
│   │   ├── hatchling-build-hook.md
│   │   ├── license-pipeline.md
│   │   ├── model-metadata-extraction.md
│   │   ├── poetry-support.md
│   │   ├── release-checklist.md
│   │   ├── setuptools-support.md   # Setuptools extractor design and limitations
│   │   ├── summary.md              # implementation summary; points here for the tree
│   │   ├── wheel-embedding.md
│   │   └── wheel-sbom-verification.md
│   └── archive/
│       └── protobom-evaluation.md  # Wholesale-rejected paths
├── skills/                         # Claude Code Skills (also bundled by .claude-plugin/)
│   ├── sbom-generate/              # Generate an SBOM/AIBOM
│   ├── sbom-enrich/                # Enrich an existing SBOM with agent-inferred facts
│   └── sbom-validate/              # Schema/SHACL conformance check
├── .claude-plugin/
│   ├── plugin.json                 # Plugin manifest
│   └── marketplace.json            # Self-hosted marketplace entry
├── examples/
│   └── sentimentdemo-aibom/        # Worked AI-pipeline SBOM example
├── src/
│   └── pitloom/
│       ├── assemble/               # Layers 2+3 -- build DocumentModel + map to spec
│       │   ├── spdx3/              # SPDX 3 specific (future: spdx23, cyclonedx)
│       │   │   ├── _ai_package.py  # AIPackage creation and optional field mapping
│       │   │   ├── _document_deployed.py    # Deployed-environment assembly
│       │   │   ├── _document_files.py       # File-element assembly
│       │   │   ├── _document_model.py       # Single-AI-model assembly
│       │   │   ├── _fragments_unify.py      # Fragment entity unification and deduplication
│       │   │   ├── _provenance_encoders.py  # Provenance encoder and payload builders
│       │   │   ├── ai.py             # AI model element assembly facade
│       │   │   ├── creation_info.py  # Shared CreationInfo construction
│       │   │   ├── dataset.py        # Dataset element assembly
│       │   │   ├── deps_installed.py # Installed-environment dependency tree mapping
│       │   │   ├── deps_license.py   # License element assembly
│       │   │   ├── deps_pypi.py      # PyPI release-info lookups
│       │   │   ├── deps_originator.py # Originator resolution
│       │   │   ├── deps.py           # Dependency enrichment facade
│       │   │   ├── document.py       # Facade: build(DocumentModel) -> Spdx3JsonExporter
│       │   │   ├── fragments.py      # Fragment merging + unification provenance facade
│       │   │   ├── provenance.py     # Provenance Annotation builders/emitter facade
│       │   │   └── __init__.py
│       │   ├── _generators.py      # Project, wheel, and env SBOM generators
│       │   ├── _model_generator.py # Model SBOM generator and enrichment orchestration
│       │   └── __init__.py         # Public assemble facade and generate() entrypoint
│       ├── cli/                    # CLI: argparse, options, dispatch
│       │   ├── commands/           # One module per subcommand: _run_<verb>_command() + add_parser()
│       │   │   ├── embed_wheel.py  # loom embed-wheel
│       │   │   ├── enrich.py       # loom enrich
│       │   │   ├── env.py          # loom env
│       │   │   ├── generate.py     # loom generate (smart entrypoint; -o required)
│       │   │   ├── merge.py        # loom merge
│       │   │   ├── model.py        # loom model
│       │   │   ├── project.py      # loom project
│       │   │   ├── utils.py        # cli_error_handler decorator, wheel-glob path resolution
│       │   │   └── wheel.py        # loom wheel
│       │   ├── constants.py        # Shared literals (.spdx3.json ext, source labels)
│       │   ├── ids.py              # loom ids generate|import
│       │   ├── options.py          # CLI > pyproject.toml > default resolution helpers
│       │   ├── parser.py           # argparse tree: parent parser + every subcommand
│       │   └── verbose.py          # --verbose effective-options report
│       ├── core/                   # Format-neutral data models (no SBOM lib deps)
│       │   ├── _config_legacy.py   # Migration error checks and constants
│       │   ├── _config_parse.py    # TOML parser for [tool.pitloom]
│       │   ├── _config_types.py    # Configuration dataclasses and type definitions
│       │   ├── _models_wheel.py    # Wheel file records and Merkle root calculation
│       │   ├── ai_metadata.py      # AiModelMetadata, ModelFormat
│       │   ├── config.py           # PitloomConfig facade and re-exports
│       │   ├── content_type_config.py # [tool.pitloom.content-type] settings
│       │   ├── creation.py         # CreationMetadata (creator / timestamp)
│       │   ├── dataset_metadata.py # DatasetMetadata
│       │   ├── document.py         # DocumentModel (assembled, pre-serialization)
│       │   ├── enrich_config.py    # [tool.pitloom.enrich] / EnrichConfig
│       │   ├── models.py           # Deterministic UUIDs, Merkle root, SPDX ID generation facade
│       │   ├── project.py          # ProjectMetadata, ProjectFile
│       │   └── provenance.py       # ProvenanceConfig ([tool.pitloom.provenance])
│       ├── enrich/                 # Local README/model-card frontmatter enrichment
│       │   ├── base.py             # Enricher protocol + run_enrichers_for_models()
│       │   └── readme.py           # README.md/MODEL_CARD.md YAML frontmatter enricher
│       ├── export/                 # Layer 4 -- serialise to physical format
│       │   └── spdx3_json.py       # SPDX 3 JSON-LD serialiser
│       ├── extract/                # Layer 1 -- read sources (_prefix = internal, see AGENTS.md)
│       │   ├── _croissant.py       # Croissant metadata parser
│       │   ├── _croissant_keys.py  # Croissant JSON-LD key constants
│       │   ├── _extract_utils.py   # Shared extraction utilities (incl. provenance sanitization)
│       │   ├── _fasttext.py        # fastText (.ftz, .bin)
│       │   ├── _file_headers.py    # SPDX-File* comment-header scanner
│       │   ├── _gguf.py            # GGUF (.gguf)
│       │   ├── _hdf5.py            # HDF5 / Keras v1-v2 (.h5, .hdf5)
│       │   ├── _huggingface.py     # Hugging Face Hub model extraction (facade)
│       │   ├── _huggingface_fetch.py # HF API/card fetching + license detection
│       │   ├── _huggingface_fields.py # HF metadata field parsing
│       │   ├── _keras.py           # Keras v3 (.keras)
│       │   ├── _license_detect.py  # License text detection and file scanning
│       │   ├── _license.py         # License normalization and resolution facade
│       │   ├── _numpy.py           # NumPy (.npy, .npz)
│       │   ├── _onnx.py            # ONNX (.onnx)
│       │   ├── _poetry.py          # [tool.poetry] extractor; Poetry -> PEP 440 conversion
│       │   ├── _pyproject.py       # pyproject.toml extractor ([project] + [tool.poetry] merge)
│       │   ├── _pytorch.py         # PyTorch classic (.pt, .pth)
│       │   ├── _pytorch_pt2.py     # PyTorch PT2 / ExecuTorch (.pt2)
│       │   ├── _safetensors.py     # Safetensors (.safetensors)
│       │   ├── _sdist.py           # sdist archive (.tar.gz/.zip) unpacking
│       │   ├── _setuptools_cfg.py  # setup.cfg parser and [tool:pitloom] config extraction
│       │   ├── _setuptools_py.py   # setup.py AST parser
│       │   ├── _setuptools.py      # Setuptools extractor facade and backend detection
│       │   ├── ai_model.py         # AI model dispatcher + format detection (public entry point)
│       │   ├── binary.py           # Bundled third-party binary ("phantom dependency") detection
│       │   ├── dataset.py          # Dataset metadata extraction public API (Croissant)
│       │   ├── env.py              # Deployed SBOM: installed-environment dependency tree
│       │   ├── hatchling.py        # Metadata from Hatchling's own resolved ProjectMetadata
│       │   ├── project.py          # pyproject.toml/setup.cfg/setup.py -> dispatcher (public entry point)
│       │   ├── scanner.py          # Heuristic scanner for AI model files
│       │   └── wheel.py            # Analyzed SBOM: project metadata + file records from a built .whl
│       ├── plugins/                # Build-system integrations
│       │   └── hatch.py            # Hatchling BuildHookInterface (PEP 770)
│       ├── __about__.py            # Package version (__version__)
│       ├── __init__.py
│       ├── __main__.py             # Thin entry point only: logging setup + args.func dispatch
│       ├── _embed_wheel.py         # Low-level ZIP rewriting and RECORD injection
│       ├── _ids_types.py           # ID registry types and hash helpers
│       ├── _loom_caller.py         # Caller stack inspection and provenance helpers
│       ├── _loom_active_run.py     # Active-run state machine
│       ├── embed.py                # PEP 770 wheel embedding facade
│       ├── ids.py                  # Loom ID registry facade (loom-ids.json)
│       ├── loom.py                 # ML tracking SDK facade (Run context manager / decorator)
│       └── py.typed                # PEP 561 marker
├── tests/                          # Mirrors src/pitloom/<package>/ (AGENTS.md Testing section)
│   ├── assemble/                   # 29 files -- assemble/, embed.py, enrich/ coverage + conftest.py
│   ├── cli/                        # 13 files -- one per src/pitloom/cli/ module, + shared.py
│   ├── core/                       # 32 files -- core/, ids.py, loom.py, generator orchestration
│   ├── extract/                    # 36 files, one per extractor
│   │   └── huggingface/            # 23 files -- split by metadata category + _hf_patches_*.py
│   ├── fixtures/                   # Per-format model/project fixtures (see fixtures/README.md)
│   ├── conftest.py                 # Cross-cutting fixtures (each subfolder has its own too)
│   └── ids_shared.py               # Shared helpers for ids-registry tests
├── AGENTS.md                       # CLAUDE.md is a symlink to this
├── CHANGELOG.md
├── CITATION.cff
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── SECURITY.md
├── action.yml                      # GitHub Action wrapper (loom project/model/embed-wheel)
├── codemeta.json
├── mkdocs.yml                      # docs/ site config
└── pyproject.toml                  # Project config and Hatchling build settings
```
