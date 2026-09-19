---
Created: 2026-08-17
Last-Modified: 2026-09-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom - project file map

See also: [summary.md](summary.md) (implementation summary) and
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
│   ├── allow-build.md              # --allow-build/--no-build-isolation/--build-timeout, split from cli.md
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
│   │   └── sbom-fragments/          # 5 files -- fragment-merge-design.md, etc.
│   ├── implementation/
│   │   ├── provenance/             # 10 files -- annotation-provenance(-mechanism/-full-plan).md, role-vocabulary.md, etc.
│   │   ├── adoption-surfaces.md
│   │   ├── agent-skill.md
│   │   ├── allow-build-termination.md # Signal handling around a build-and-read and its result
│   │   ├── allow-build-timeout.md  # --build-timeout: build subprocess, kill path, traps
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
│       │   ├── _models_wheel.py    # get_wheel_files(): discovery facade + shared per-file processing loop
│       │   ├── _models_wheel_build_and_read.py  # --allow-build: build a real wheel, extract its files
│       │   ├── _models_wheel_build_kill.py      # Kill the build's process tree (POSIX group / taskkill)
│       │   ├── _models_wheel_build_subprocess.py # Run `python -m build` as a child tree with a timeout
│       │   ├── _models_wheel_dispatch.py   # Backend dispatch: static module, build-and-read, Hatchling fallback
│       │   ├── _models_wheel_flit.py       # flit-core-backed discover()
│       │   ├── _models_wheel_hatchling.py  # Hatchling WheelBuilder-based discover()
│       │   ├── _models_wheel_lock.py       # Reader/writer lock for backend file discovery
│       │   ├── _models_wheel_pdm.py        # pdm-backend-backed discover()
│       │   ├── _models_wheel_poetry.py     # poetry-core WheelBuilder-based discover()
│       │   ├── _models_wheel_setuptools.py # setuptools static-config-based discover()
│       │   ├── _models_wheel_types.py # IncludedFile, BackendDiscoverer protocol, shared helpers
│       │   ├── ai_metadata.py      # AiModelMetadata, ModelFormat
│       │   ├── build_options.py    # BuildOptions: --allow-build flags, validation, no-effect warnings
│       │   ├── build_signals.py    # TerminationGuard: SIGTERM/SIGHUP cleanup of a build-and-read
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
│       ├── extract/                # Layer 1 -- read sources
│       │   ├── ai_model/           # AI model extractors (fasttext, gguf, hdf5, keras, numpy, onnx, pytorch, pytorch_pt2, safetensors, reader)
│       │   ├── dataset/            # Dataset extractors (croissant, croissant_key, reader)
│       │   ├── lock/               # Lockfile extractors (cascade, poetry, pdm, uv, pylock, pipfile, requirements, _common, _hash, etc.)
│       │   ├── project/            # Build backend & project metadata extractors (pyproject, poetry, pdm, flit, setuptools, sdist, hatchling, reader)
│       │   ├── remote/             # Remote registries/hubs (huggingface, huggingface_fetch, huggingface_field)
│       │   ├── _extract_utils.py   # Shared extraction utilities (incl. provenance sanitization)
│       │   ├── _file_headers.py    # SPDX-File* comment-header scanner
│       │   ├── _license.py         # License normalization and resolution facade
│       │   ├── _license_detect.py  # License text detection and file scanning
│       │   ├── _toml_io.py         # Shared tomllib/tomli compat import + raw TOML-file read
│       │   ├── binary.py           # Bundled third-party binary ("phantom dependency") detection
│       │   ├── env.py              # Deployed SBOM: installed-environment dependency tree
│       │   ├── scanner.py          # Heuristic scanner for AI model files
│       │   └── wheel.py            # Analyzed SBOM: project metadata + file records from a built .whl
│       ├── plugins/                # Build-system integrations
│       │   └── hatch.py            # Hatchling BuildHookInterface (PEP 770)
│       ├── __about__.py            # Package version (__version__)
│       ├── __init__.py
│       ├── __main__.py             # Thin entry point only: logging setup + args.func dispatch
│       ├── _embed_build_sbom.py    # embed-wheel Build SBOM: project rescan + wheel files, EmbedFileCache
│       ├── _embed_wheel.py         # Low-level ZIP rewriting and RECORD injection
│       ├── _ids_types.py           # ID registry types and hash helpers
│       ├── _loom_caller.py         # Caller stack inspection and provenance helpers
│       ├── _loom_active_run.py     # Active-run state machine
│       ├── embed.py                # PEP 770 wheel embedding facade
│       ├── ids.py                  # Loom ID registry facade (loom-ids.json)
│       ├── logging_config.py       # Shared INFO:/WARNING:/ERROR: stderr formatting (configure_logging)
│       ├── loom.py                 # ML tracking SDK facade (Run context manager / decorator)
│       └── py.typed                # PEP 561 marker
├── tests/                          # Mirrors src/pitloom/<package>/ (AGENTS.md Testing section)
│   ├── assemble/                   # 35 files -- assemble/, embed.py, enrich/ coverage + conftest.py
│   ├── cli/                        # 14 files -- one per src/pitloom/cli/ module, + shared.py
│   ├── core/                       # 42 files -- core/, ids.py, loom.py, generator orchestration
│   │   └── models_wheel/           # Wheel file discovery: backends, build-and-read, build timeout/kill
│   ├── extract/                    # 46 files, one per extractor
│   │   └── huggingface/            # 20 files -- split by metadata category
│   │       └── hf_patches/         # 13 files -- shared mock patches for HF tests
│   ├── fixtures/                   # Per-format model/project fixtures (see fixtures/README.md)
│   ├── scripts/                    # Mirrors scripts/: probe, resolver, install and Generate-step tests
│   ├── build_and_read_shared.py    # Shared fake build, temp-dir and simulated-signal helpers
│   ├── conftest.py                 # Cross-cutting fixtures (each subfolder has its own too)
│   └── ids_shared.py               # Shared helpers for ids-registry tests
├── scripts/
│   ├── action/                     # GitHub Action helpers (install, Python probe/resolver)
│   ├── check_version_consistency.py  # CI version check; --print-version also used by the action
│   └── compare_allow_build.py      # Manual --allow-build parity check
├── .gitattributes                  # LF for *.sh and action.yml
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
