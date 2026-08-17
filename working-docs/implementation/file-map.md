---
Created: 2026-08-17
Last-Modified: 2026-08-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom - project file map

See also: [summary.md](summary.md) (implementation summary this tree
was split out of) and
[cli-test-coverage-roadmap.md](../design/cli-test-coverage-roadmap.md)
(the `__main__.py` → `cli/` split and `tests/` folder split this tree
now reflects).

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
│   │   ├── cli-test-coverage-roadmap.md  # __main__.py/cli/ split + tests/ folder split
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
│       │   │   ├── ai.py           # AI model element assembly
│       │   │   ├── creation_info.py # Shared CreationInfo construction
│       │   │   ├── dataset.py      # Dataset element assembly
│       │   │   ├── deps.py         # Dependency + license element assembly
│       │   │   ├── document.py     # build(DocumentModel) -> Spdx3JsonExporter
│       │   │   ├── fragments.py    # Fragment merging + unification provenance
│       │   │   ├── provenance.py   # Provenance Annotation builders/emitter
│       │   │   └── __init__.py
│       │   └── __init__.py         # generate_*_sbom() orchestrators + backend routing
│       ├── cli/                    # CLI: argparse, options, dispatch (see cli-test-coverage-roadmap.md)
│       │   ├── commands/           # One module per subcommand: _run_<verb>_command() + add_parser()
│       │   │   ├── embed_wheel.py  # loom embed-wheel
│       │   │   ├── enrich.py       # loom enrich
│       │   │   ├── env.py          # loom env
│       │   │   ├── generate.py     # loom generate (smart entrypoint; -o required, see CHANGELOG)
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
│       │   ├── ai_metadata.py      # AiModelMetadata, ModelFormat
│       │   ├── config.py           # PitloomConfig ([tool.pitloom] settings)
│       │   ├── content_type_config.py # [tool.pitloom.content-type] settings
│       │   ├── creation.py         # CreationMetadata (creator / timestamp)
│       │   ├── dataset_metadata.py # DatasetMetadata
│       │   ├── document.py         # DocumentModel (assembled, pre-serialization)
│       │   ├── enrich_config.py    # [tool.pitloom.enrich] / EnrichConfig
│       │   ├── models.py           # Deterministic UUIDs, Merkle root, SPDX ID generation
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
│       │   ├── _huggingface.py     # Hugging Face Hub model extraction
│       │   ├── _keras.py           # Keras v3 (.keras)
│       │   ├── _license.py         # License file/id detection
│       │   ├── _numpy.py           # NumPy (.npy, .npz)
│       │   ├── _onnx.py            # ONNX (.onnx)
│       │   ├── _poetry.py          # [tool.poetry] extractor; Poetry -> PEP 440 conversion
│       │   ├── _pyproject.py       # pyproject.toml extractor ([project] + [tool.poetry] merge)
│       │   ├── _pytorch.py         # PyTorch classic (.pt, .pth)
│       │   ├── _pytorch_pt2.py     # PyTorch PT2 / ExecuTorch (.pt2)
│       │   ├── _safetensors.py     # Safetensors (.safetensors)
│       │   ├── _sdist.py           # sdist archive (.tar.gz/.zip) unpacking
│       │   ├── _setuptools.py      # setup.cfg + setup.py extractor; backend detection; merge
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
│       ├── embed.py                # PEP 770 wheel embedding (RECORD update, stale-entry cleanup)
│       ├── ids.py                  # Loom ID registry (loom-ids.json); stable cross-fragment SPDX ids
│       ├── loom.py                 # ML tracking SDK (Run context manager / decorator)
│       └── py.typed                # PEP 561 marker
├── tests/                          # Mirrors src/pitloom/<package>/ (AGENTS.md Testing section)
│   ├── assemble/                   # 26 files -- assemble/, embed.py, enrich/ coverage + conftest.py
│   ├── cli/                        # 13 files -- one per src/pitloom/cli/ module, + shared.py
│   ├── core/                       # 28 files -- core/, ids.py, loom.py, generator orchestration
│   ├── extract/                    # 32 files, one per extractor
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
