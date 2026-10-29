---
Created: 2026-08-17
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom - project file map

See also: [summary.md](summary.md) (implementation summary) and
[cli-test-coverage-roadmap.md](cli-test-coverage-roadmap.md)
(the CLI, test-suite, and source modularization this tree reflects).

This tree is the canonical reference for the repository's file/directory
layout; `README.md` and design docs point here rather than duplicating
it. `docs/` is the published GitHub Pages site (flat, user-facing);
`working-docs/design/` and `working-docs/implementation/` are the
internal design/progress docs, including this file.

```text
pitloom/
├── docs/                           # Published site (mkdocs.yml at repo root); flat, user-facing
│   ├── agent-skills.md
│   ├── ai-model-formats.md
│   ├── ai-model-scan-limits.md
│   ├── ai-model-scan-limits-known-limitations.md
│   ├── allow-build.md              # --allow-build/--no-build-isolation/--build-timeout, split from cli.md
│   ├── api.md
│   ├── claude-code-plugin.md
│   ├── cli.md
│   ├── configuration.md
│   ├── creation-metadata.md
│   ├── dependency-sources.md
│   ├── fragments.md
│   ├── g7-sbom-for-ai.md
│   ├── git-urls.md                 # Git URL targets
│   ├── github-action.md
│   ├── hatchling-build-hook.md
│   ├── id-registry.md
│   ├── id-registry-keys.md
│   ├── index.md
│   ├── mascot.png
│   ├── metadata-provenance.md      # Also metadata-provenance-{artifact-metadata,authors,licences}.md
│   ├── metadata-reading-back.md
│   ├── python-api.md
│   ├── resources.md
│   └── wheel-sbom.md               # Plus slide decks, a diagram and posters (pdf/pptx/key)
├── working-docs/                   # Internal notes; topic-first kebab-case files, grouped in subfolders at 3+ related files
│   ├── design/                     # Unbuilt plans and follow-ups; roadmap.md is the canonical roadmap
│   │   └── sbom-fragments/         # 6 files, start at README.md
│   ├── implementation/             # What was built: decisions, why, rejected paths; this file, summary.md
│   │   ├── g7-coverage-history/    # Coverage-report snapshots (JSON)
│   │   ├── provenance/             # Provenance annotation docs, start at README.md
│   │   └── sbom-generator-field-notes/ # Paper notes, start at README.md
│   └── archive/                    # Wholesale-rejected paths (protobom-evaluation.md)
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
│       │   │   ├── _agents.py  # The one generic Agent per name (originators, supplier, dataset creators)
│       │   │   ├── _ai_originators.py  # Model originators and supplier as Agents
│       │   │   ├── _ai_package.py  # AIPackage creation and optional field mapping
│       │   │   ├── _dep_scope.py  # Edge kind of a dependency: required or optional (extras)
│       │   │   ├── _display_text.py  # Display text of an element built from untrusted model data
│       │   │   ├── _document_conflicts.py  # Conflict Annotation per field conflict on the main package
│       │   │   ├── _document_deployed.py    # Deployed-environment assembly
│       │   │   ├── _document_file_hits.py  # Registry hits for files and directories, resolved before minting
│       │   │   ├── _document_files.py       # File-element assembly
│       │   │   ├── _document_lfs.py         # One WARNING per kind of Git LFS pointer in a document
│       │   │   ├── _document_locked_deps.py  # Locked-dependency dedup, conflict detection, exact-version pins
│       │   │   ├── _document_model.py       # Single-AI-model assembly
│       │   │   ├── _fragments_envelope.py  # SpdxDocument envelope of a merge output
│       │   │   ├── _fragments_equal.py  # Two JSON texts that say the same, in any spelling (bounded, exact)
│       │   │   ├── _fragments_hashes.py     # Hash conflict test, same-name-different-hash warning
│       │   │   ├── _fragments_generated.py  # A fragment value replaces a value generated from the model file
│       │   │   ├── _fragments_ids.py        # rename_id_clash: new id for a type or digest clash
│       │   │   ├── _fragments_licenses.py  # Licence unification for a fragment merge
│       │   │   ├── _fragments_model_names.py  # Base-document AI model name that fragments re-declare
│       │   │   ├── _fragments_props.py      # Property compare and merge helpers
│       │   │   ├── _fragments_refs.py  # Referential-integrity check of a merged graph
│       │   │   ├── _fragments_unify.py      # Fragment entity unification and deduplication
│       │   │   ├── _license_elements.py  # The one place a licence value becomes a licence element
│       │   │   ├── _licensing_profiles.py  # Licensing profiles a graph needs in profileConformance
│       │   │   ├── _main_authors.py  # Main package authors as originatedBy Agents, same on every route
│       │   │   ├── _package_ids.py          # Registry pre-resolution: main package, dependencies, phantom dependencies
│       │   │   ├── _reserved_ids.py  # Registry-held ids a document's mints skip
│       │   │   ├── _provenance_encoders.py  # Provenance encoder and payload builders
│       │   │   ├── ai.py             # AI model element assembly facade
│       │   │   ├── creation_info.py  # Shared CreationInfo construction
│       │   │   ├── dataset.py        # Dataset element assembly
│       │   │   ├── deps_installed.py # Installed-environment dependency tree mapping
│       │   │   ├── deps_license.py   # License element assembly
│       │   │   ├── deps_phantom.py   # Phantom (bundled binary) dependency assembly
│       │   │   ├── deps_pypi.py      # PyPI release-info lookups
│       │   │   ├── deps_originator.py # Originator resolution
│       │   │   ├── deps.py           # Dependency enrichment facade
│       │   │   ├── document.py       # Facade: build(DocumentModel) -> Spdx3JsonExporter
│       │   │   ├── fragments.py      # Fragment merging + unification provenance facade
│       │   │   ├── provenance.py     # Provenance Annotation builders/emitter facade
│       │   │   └── __init__.py
│       │   ├── _generators.py      # Project/sdist SBOM generator
│       │   ├── _generators_env.py  # Installed-environment (Deployed) SBOM generator
│       │   ├── _generators_git.py  # Source SBOM generator for a remote Git repository
│       │   ├── _generators_merge.py  # Merged SBOM generator: a directory of fragments
│       │   ├── _generators_shared.py # Helpers shared by every generator (_sync_registry)
│       │   ├── _generators_wheel.py # Built-wheel (Analyzed) SBOM generator
│       │   ├── _model_generator.py # Model SBOM generator and enrichment orchestration
│       │   └── __init__.py         # Public assemble facade and generate() entrypoint
│       ├── cli/                    # CLI: argparse, options, dispatch
│       │   ├── commands/           # One module per subcommand: _run_<verb>_command() + add_parser()
│       │   │   ├── _embed_wheel_batch.py # embed-wheel batch context, project-dir/registry resolution
│       │   │   ├── embed_wheel.py  # loom embed-wheel
│       │   │   ├── enrich.py       # loom enrich
│       │   │   ├── env.py          # loom env
│       │   │   ├── fragment.py  # loom fragment
│       │   │   ├── generate.py     # loom generate (smart entrypoint; -o required)
│       │   │   ├── merge.py        # loom merge
│       │   │   ├── model.py        # loom model
│       │   │   ├── project.py      # loom project
│       │   │   ├── utils.py        # cli_error_handler decorator, wheel-glob path resolution
│       │   │   └── validate_wheel.py  # loom validate-wheel
│       │   │   └── verify_wheel.py  # loom verify-wheel
│       │   │   └── wheel.py        # loom wheel
│       │   ├── _id_entity.py  # Key and SHA-256 that id generate -e NAME:TYPE stores
│       │   ├── _id_target.py  # Where id generate/import write the registry; config hint
│       │   ├── constants.py        # Shared literals (.spdx3.json ext, source labels)
│       │   ├── id.py               # loom id generate|import
│       │   ├── kv_output.py  # print_kv(): KEY=VALUE stdout data lines; INFO: KEY=VALUE on stderr
│       │   ├── options.py          # add_*_argument()/warn_*() flag-definition helpers
│       │   ├── options_config.py   # args -> library kwargs/ConfigOverrides map; --config loading
│       │   ├── options_resolve.py  # CLI > --config > pyproject.toml > default resolution
│       │   ├── parser.py           # argparse tree: parent parser + every subcommand
│       │   └── verbose.py          # --verbose effective-options report (project targets only)
│       ├── core/                   # Format-neutral data models (no SBOM lib deps)
│       │   ├── _config_keys.py  # Keys of [tool.pitloom] and the warning for any other key
│       │   ├── _config_legacy.py   # Migration error checks and constants
│       │   ├── _config_parse.py    # TOML parser for [tool.pitloom]
│       │   ├── _config_parse_scan.py # File/model scanning keys (content-type, extract-file-header)
│       │   ├── _config_read.py     # Leaf read primitives (bool/int/table/choice) for the parsers
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
│       │   ├── _models_wheel_setuptools_relay.py # setuptools' warnings and stderr lines, relayed as tagged records
│       │   ├── _models_wheel_unlistable.py  # Warn about project directories file discovery could not list
│       │   ├── _models_wheel_types.py # IncludedFile, BackendDiscoverer protocol, shared helpers
│       │   ├── ai_metadata.py      # AiModelMetadata, ModelFormat
│       │   ├── archive_member_names.py # zip_file_members()/archive_members(): member -> install location, same on every OS
│       │   ├── build_options.py    # BuildOptions: --allow-build flags, validation, no-effect warnings
│       │   ├── build_signals.py    # TerminationGuard: SIGTERM/SIGHUP cleanup of a build-and-read
│       │   ├── canonical_json.py  # The one serialisation of JSON text embedded in an SBOM string
│       │   ├── config.py           # PitloomConfig facade and re-exports
│       │   ├── config_cascade.py   # ConfigOverrides + the one [tool.pitloom] cascade every surface resolves through
│       │   ├── content_type_config.py # [tool.pitloom.content-type] settings
│       │   ├── creation.py         # CreationMetadata (creator / timestamp)
│       │   ├── dataset_hash.py  # Hash a dataset path: file SHA-256 or directory Merkle root
│       │   ├── dataset_merge.py  # One dataset referenced more than once becomes one dataset
│       │   ├── dataset_names.py  # When two dataset spellings are one dataset; the listing cap
│       │   ├── dataset_metadata.py # DatasetMetadata
│       │   ├── document.py         # DocumentModel (assembled, pre-serialization)
│       │   ├── enrich_config.py    # [tool.pitloom.enrich] / EnrichConfig
│       │   ├── extra_gate.py  # The extras a requirement marker requires, read from its text
│       │   ├── file_hash.py        # One chunked reader: SHA-256 and SHA-512 of a file, from one pass
│       │   ├── file_identity.py  # Whether two paths are one file, by identity not spelling
│       │   ├── file_names.py       # is_plain_file_name(), escape_file_name_part(): an SBOM file name is a name, not a path
│       │   ├── iri.py  # Human name to IRI segment for an SPDX 3 identifier
│       │   ├── lfs_pointer.py   # Git LFS pointer grammar, bounded read, prefix capture, run summary warning
│       │   ├── inert_options.py    # INERT: options a target kind can't act on; forward_options()
│       │   ├── license_individuals.py  # The SPDX 3 named licence individuals Pitloom emits
│       │   ├── model_extract_limit.py  # Validation of max-model-extract-bytes and max-dataset-hash-bytes
│       │   ├── model_originators.py  # A model's originators: the names a source states
│       │   ├── model_parameters.py  # A model's parameter count: derived from shapes or stated
│       │   ├── models.py           # Deterministic UUIDs, Merkle root, SPDX ID generation facade
│       │   ├── path_confine.py  # Confined open: a project's own files must lie inside it
│       │   ├── path_probe.py  # Genuinely missing path vs present-but-inaccessible
│       │   ├── pep440.py  # Every PEP 440 version and specifier Pitloom parses (number length bounded)
│       │   ├── pep508.py  # Every PEP 508 requirement and marker Pitloom parses
│       │   ├── no_effect.py        # warn_no_effect(): the one "has no effect" WARNING: shape
│       │   ├── requirements.py  # Requires-Dist strings of a built wheel: names canonicalised, extras tagged
│       │   ├── project.py          # ProjectMetadata, ProjectFile
│       │   ├── provenance.py       # ProvenanceConfig ([tool.pitloom.provenance])
│       │   ├── scalar_text.py  # The one spelling of a scalar as text
│       │   ├── purl.py             # pkg:huggingface and pkg:generic package URLs
│       │   ├── untrusted_text.py  # Untrusted text shown to a reader, invisible controls made visible
│       │   ├── temp_dirs.py        # registered_temp_dir(): temp dirs removed via TerminationGuard
│       │   └── walk_rules.py  # Rules shared by every project file walk
│       │   └── wheel_dist_info.py  # resolve_own_dist_info(), wheel_members(), open_wheel_zip(), WheelRefused: a wheel's own .dist-info; header-only METADATA read
│       ├── enrich/                 # Local README/model-card frontmatter enrichment
│       │   ├── base.py             # Enricher protocol + run_enrichers_for_models()
│       │   └── readme.py           # README.md/MODEL_CARD.md YAML frontmatter enricher
│       ├── export/                 # Layer 4 -- serialise to physical format
│       │   ├── hashes.py           # sha256_of, file_digests_of: read an element's SHA-256/SHA-512
│       │   ├── spdx3_describe.py  # One way to name an SPDX 3 element or value in a message
│       │   └── spdx3_json.py       # SPDX 3 JSON-LD serialiser
│       ├── extract/                # Layer 1 -- read sources
│       │   ├── ai_model/           # AI model extractors (crfsuite, fasttext, gguf, hdf5, keras, numpy, onnx, pytorch, pytorch_pt2, safetensors, reader)
│       │   │   └── formats/        # Metadata-only format readers, stdlib only, no Pitloom import (pickle_walk, crfsuite)
│       │   ├── dataset/            # Dataset extractors (card, croissant, croissant_key, licence, reader)
│       │   ├── lock/               # Lockfile extractors (cascade, poetry, pdm, uv, pylock, pipfile, requirements, _common, _hash, etc.)
│       │   ├── project/            # Build backend & project metadata extractors (pyproject, poetry, pdm, flit, setuptools, sdist, hatchling, reader)
│       │   ├── remote/             # Remote sources (git, git_url, _git_* helpers, errors, huggingface, huggingface_dataset, huggingface_fetch, huggingface_field)
│       │   ├── _author_parts.py  # Where a free-text author field is cut into entries
│       │   ├── _author_warnings.py  # WARNING: lines of the free-text author reading
│       │   ├── _core_metadata.py  # Shared RFC 822 Core-Metadata parsing helpers
│       │   ├── _interrupt_hold.py  # Bounded waiting for the undo of a capture block
│       │   ├── _json_io.py  # Shared raw-bytes JSON-file read
│       │   ├── _extract_utils.py   # Shared extraction utilities (incl. provenance sanitization)
│       │   ├── _file_headers.py    # SPDX-File* comment-header scanner
│       │   ├── _license_classify.py  # Classify a licence value; provenance notes for a rewrite
│       │   ├── _license.py         # License normalization and resolution facade
│       │   ├── _reader_log.py  # Capture of the log records an AI model reader emits
│       │   ├── _scanner_messages.py  # Text helpers for AI model scanner messages
│       │   ├── _license_detect.py  # License text detection and file scanning
│       │   ├── authors.py  # The one reading of a free-text author field, on every surface
│       │   ├── copyright_notices.py  # Copyright notices in a package's own licence files
│       │   ├── dependency_authors.py  # A dependency's originators from its author/maintainer fields
│       │   ├── binary.py           # Bundled third-party binary ("phantom dependency") detection
│       │   ├── env.py              # Deployed SBOM: installed-environment dependency tree
│       │   ├── license_refs.py  # Several License:: classifiers as one licence expression
│       │   ├── scanner.py          # AI model discovery policy: ModelCandidate, discover/attach passes
│       │   ├── scanner_project.py  # Project-directory producer for the AI model scanner
│       │   ├── scanner_wheel.py  # Built-wheel producer for the AI model scanner
│       │   ├── stderr_capture.py  # Per-thread capture of what third-party code writes to sys.stderr
│       │   └── wheel.py            # Analyzed SBOM: project metadata + file records from a built .whl
│       ├── id_registry/             # Loom ID registry (loom-id-registry.json)
│       │   ├── __init__.py          # Public API re-exports (IdRegistry, IdRegistrySession, resolve_registry)
│       │   ├── _ambiguous.py        # Names held by several elements of one document (never harvested)
│       │   ├── _counters.py         # id_counters: retired ids are never minted again (I8)
│       │   ├── _sbom_read.py  # Read an SPDX 3 SBOM for id import
│       │   ├── _format.py           # v3 file load/save, strict validation
│       │   ├── _generate.py         # index_files: `id generate` file and model indexing
│       │   ├── _harvest.py          # SBOM-element harvest helpers (_import_sbom_element)
│       │   ├── _persist.py          # save_registry, persist_registry, rebase and replay
│       │   ├── _registry.py         # IdRegistry class (typed table)
│       │   ├── _session.py          # IdRegistrySession: one document's first-claimant-wins lookups
│       │   ├── import_keys.py  # Keys id import writes files, datasets and models under
│       │   ├── keys.py  # Loom ID registry keys: the one place every surface computes them
│       │   ├── _types.py            # Registry dataclasses, element keys, file traversal
│       │   └── resolve.py           # resolve_registry(id_registry, configured, base_dir)
│       ├── plugins/                # Build-system integrations
│       │   └── hatch.py            # Hatchling BuildHookInterface (PEP 770)
│       ├── __about__.py            # Package version (__version__)
│       ├── __init__.py
│       ├── __main__.py             # Thin entry point only: logging setup + args.func dispatch
│       ├── _embed_build_sbom.py    # embed-wheel Build SBOM: project rescan + wheel files, EmbedFileCache
│       ├── _embed_generate.py      # Embed SBOM JSON: registry peek, batch option settling, standalone/project branch
│       ├── _embed_wheel.py         # Low-level ZIP rewriting and RECORD injection
│       ├── _loom_caller.py         # Caller stack inspection and provenance helpers
│       ├── _loom_active_run.py     # Active-run state machine
│       ├── _loom_dataset.py        # Loom datasets: package plus contained file, hash, registry lookup
│       ├── _loom_model.py          # Loom models: declared, resolved and recorded at run exit
│       ├── _loom_dataset_meta.py  # What a loom dataset's own sources state about it
│       ├── _loom_dataset_keys.py   # Loom dataset registry keys and Hash comments (incl. LFS pointer oid)
│       ├── _toml_io.py             # Shared tomllib/tomli compat import + raw TOML-file read
│       ├── _embed_overlay.py  # What an embed takes from its project directory onto the wheel metadata
│       ├── _sbom_format.py  # SBOM format detection, recommended extensions, name/version cross-check
│       ├── _sbom_io.py  # Write SBOM text with LF endings and UTF-8 on every platform
│       ├── _wheel_sbom_location.py  # Locate an SBOM already embedded in a wheel (read-only)
│       ├── embed.py                # PEP 770 wheel embedding facade
│       ├── logging_config.py       # Shared INFO:/WARNING:/ERROR: stderr formatting (configure_logging)
│       ├── loom.py                 # ML tracking SDK facade (Run context manager / decorator)
│       └── py.typed                # PEP 561 marker
├── tests/                          # Mirrors src/pitloom/<package>/ (AGENTS.md Testing section)
│   ├── assemble/                   # assemble/, embed*.py, enrich/ coverage + conftest.py
│   ├── cli/                        # one per src/pitloom/cli/ module and subcommand, + shared.py
│   ├── conformance/                # G7, CISA 2026, FSCT 2024 checker outcomes vs tests/fixtures/conformance/*-expected.tsv
│   ├── core/                       # core/, loom.py (the SDK)
│   │   ├── generator/              # Generator orchestration per target
│   │   └── models_wheel/           # Wheel file discovery: backends, build-and-read, build timeout/kill
│   ├── export/
│   ├── extract/                    # One subfolder per extractor package
│   │   ├── ai_model/               # AI model readers (formats/ for the stdlib-only readers)
│   │   ├── dataset/
│   │   ├── lock/
│   │   ├── project/
│   │   ├── remote/                 # Git URL and Hugging Face tests
│   │   │   └── hf_patches/         # Shared mock patches for HF tests
│   │   └── scanner/                # AI model scanner
│   ├── fixtures/                   # Per-format model/project fixtures (see fixtures/README.md)
│   ├── id_registry/                # Loom ID registry tests, with shared helpers
│   ├── scripts/                    # Mirrors scripts/: probe, resolver, install and Generate-step tests
│   │   └── action/
│   ├── test_*_surfaces.py          # One behaviour checked on every surface (CLI, library, hook, embed)
│   ├── _raw_archive.py             # Write zip/tar members under exact raw names on every OS
│   ├── _wheel_damage.py            # Wheels with one damaged member (bad CRC, encrypted, ...) for the refusal tests
│   ├── build_and_read_shared.py    # Shared fake build, temp-dir and simulated-signal helpers
│   ├── _spdx3_validate.py          # Offline schema/SHACL validation against fixtures/spdx-model/
│   ├── conftest.py                 # Cross-cutting fixtures (each subfolder has its own too)
│   └── warning_helpers.py          # Shared WARNING:/caplog assertion helpers
├── scripts/
│   ├── action/                     # GitHub Action helpers (install, Python probe/resolver)
│   ├── check_sbom_license.py       # Release check: root package declares and concludes the licence
│   ├── check_version_consistency.py  # CI version check; --print-version also used by the action
│   ├── compare_allow_build.py      # Manual --allow-build parity check
│   ├── extract_wheel_sbom.py       # Release check: extract the SBOM the build hook embedded in a wheel
│   ├── g7_coverage_report.py       # Checker coverage report and expected tables (--standard g7ai|cisa2026|fsct3)
│   ├── manual_cli_checks/          # Unattended manual CLI checks: _checks_*.py, CLI matrix, command sequences
│   ├── refresh_spdx_model_snapshot.py # Refresh tests/fixtures/spdx-model/ from spdx.org
│   └── retry_network.py            # Run a command, retrying only on a network failure (CI)
├── .gitattributes                  # LF for *.sh and action.yml
├── AGENTS.md                       # CLAUDE.md and GEMINI.md are symlinks to this
├── CHANGELOG.md                    # 0.19.0 and newer; add new entries here
├── CHANGELOG-archive.md            # releases before 0.19.0, condensed
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
