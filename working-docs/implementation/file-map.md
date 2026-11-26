---
Created: 2026-08-17
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom - project file map

See also: [summary.md](summary.md) (implementation summary) and
[cli-test-coverage-roadmap.md](cli-test-coverage-roadmap.md)
(the CLI, test-suite, and source modularisation this tree reflects);
[file-map-src.md](file-map-src.md) (the `src/` subtree).

This tree is the canonical reference for the repository's file/directory
layout; `README.md` and design docs point here rather than duplicating
it. `docs/` is the published GitHub Pages site (flat, user-facing);
`working-docs/design/` and `working-docs/implementation/` are the
internal design/progress docs, including this file.

The `src/` subtree is in [file-map-src.md](file-map-src.md).

```text
pitloom/
├── docs/  # Published site (mkdocs.yml at repo root); flat, user-facing
│   ├── agent-skills.md
│   ├── ai-model-formats.md
│   ├── ai-model-scan-limits.md
│   ├── ai-model-scan-limits-known-limitations.md
│   ├── allow-build.md  # --allow-build/--no-build-isolation/--build-timeout, split from cli.md
│   ├── api.md
│   ├── claude-code-plugin.md
│   ├── cli.md
│   ├── configuration.md
│   ├── creation-metadata.md
│   ├── dependency-sources.md
│   ├── fragments.md
│   ├── g7-sbom-for-ai.md
│   ├── git-urls.md  # Git URL targets
│   ├── github-action.md
│   ├── hatchling-build-hook.md
│   ├── id-registry.md
│   ├── id-registry-keys.md
│   ├── index.md
│   ├── mascot.png
│   ├── message-codes.md  # Index of the codes, generated (scripts/generate_message_reference.py); pages: message-codes-{models,model-fields,targets,files,pypi,network,licences,values}.md (values: what each `<name>` stands for)
│   ├── messages.md
│   ├── metadata-provenance.md  # Also metadata-provenance-{artifact-metadata,authors,licences}.md
│   ├── metadata-reading-back.md
│   ├── python-api.md
│   ├── resources.md
│   └── wheel-sbom.md  # Plus slide decks, a diagram and posters (pdf/pptx/key)
├── working-docs/  # Internal notes; topic-first kebab-case files, grouped in subfolders at 3+ related files
│   ├── design/  # Unbuilt plans and follow-ups; roadmap.md is the canonical roadmap
│   │   └── sbom-fragments/  # 6 files, start at README.md
│   ├── implementation/  # What was built: decisions, why, rejected paths; this file, summary.md
│   │   ├── g7-coverage-history/  # Coverage-report snapshots (JSON)
│   │   ├── provenance/  # Provenance annotation docs, start at README.md
│   │   └── sbom-generator-field-notes/ # Paper notes, start at README.md
│   └── archive/  # Wholesale-rejected paths (protobom-evaluation.md)
├── skills/  # Claude Code Skills (also bundled by .claude-plugin/)
│   ├── sbom-generate/  # Generate an SBOM/AIBOM
│   ├── sbom-enrich/  # Enrich an existing SBOM with agent-inferred facts
│   └── sbom-validate/  # Schema/SHACL conformance check
├── .claude-plugin/
│   ├── plugin.json  # Plugin manifest
│   └── marketplace.json  # Self-hosted marketplace entry
├── examples/
│   └── sentimentdemo-aibom/  # Worked AI-pipeline SBOM example
├── src/  # Package source (src/pitloom/): see file-map-src.md
├── tests/  # Mirrors src/pitloom/<package>/ (AGENTS.md Testing section)
│   ├── assemble/  # assemble/, embed*.py, enrich/ coverage + conftest.py
│   ├── cli/  # one per src/pitloom/cli/ module and subcommand, + shared.py
│   ├── conformance/  # G7, CISA 2026, FSCT 2024 checker outcomes vs tests/fixtures/conformance/*-expected.tsv
│   ├── core/  # core/, loom.py (the SDK)
│   │   ├── generator/  # Generator orchestration per target
│   │   └── models_wheel/  # Wheel file discovery: backends, build-and-read, build timeout/kill
│   ├── export/
│   ├── extract/  # One subfolder per extractor package
│   │   ├── ai_model/  # AI model readers (formats/ for the stdlib-only readers)
│   │   ├── dataset/
│   │   ├── lock/
│   │   ├── project/
│   │   ├── remote/  # Git URL and Hugging Face tests
│   │   │   └── hf_patches/  # Shared mock patches for HF tests
│   │   └── scanner/  # AI model scanner
│   ├── fixtures/  # Per-format model/project fixtures (see fixtures/README.md)
│   ├── id_registry/  # Loom ID registry tests, with shared helpers
│   ├── messages/  # Message catalogue, drift guards, per-family tests
│   ├── scripts/  # Mirrors scripts/: probe, resolver, install and Generate-step tests
│   │   └── action/
│   ├── test_*_surfaces.py  # One behaviour checked on every surface (CLI, library, hook, embed)
│   ├── _raw_archive.py  # Write zip/tar members under exact raw names on every OS
│   ├── _wheel_damage.py  # Wheels with one damaged member (bad CRC, encrypted, ...) for the refusal tests
│   ├── build_and_read_shared.py  # Shared fake build, temp-dir and simulated-signal helpers
│   ├── _spdx3_validate.py  # Offline schema/SHACL validation against fixtures/spdx-model/
│   ├── conftest.py  # Cross-cutting fixtures (each subfolder has its own too)
│   └── warning_helpers.py  # Shared WARNING:/caplog assertion helpers
├── scripts/
│   ├── action/  # GitHub Action helpers (install, Python probe/resolver)
│   ├── ci/  # CI helpers (skip_duplicate_push.py)
│   ├── check_sbom_license.py  # Release check: root package declares and concludes the licence
│   ├── check_version_consistency.py  # CI version check; --print-version also used by the action
│   ├── compare_allow_build.py  # Manual --allow-build parity check
│   ├── extract_wheel_sbom.py  # Release check: extract the SBOM the build hook embedded in a wheel
│   ├── generate_message_reference.py # Generate the message reference: docs/message-codes*.md and the skills' messages*.md
│   ├── g7_coverage_report.py  # Checker coverage report and expected tables (--standard g7ai|cisa2026|fsct3)
│   ├── licence_adoption_sweep.py  # Sweep licenseid's parity corpus through the declared-licence path
│   ├── manual_cli_checks/  # Unattended manual CLI checks: _checks_*.py, CLI matrix, command sequences
│   ├── message_inventory/  # Message emission-site inventory and ratchet baseline (--check)
│   ├── refresh_spdx_model_snapshot.py # Refresh tests/fixtures/spdx-model/ from spdx.org
│   └── retry_network.py  # Run a command, retrying only on a network failure (CI)
├── .gitattributes  # LF for *.sh and action.yml
├── AGENTS.md  # CLAUDE.md and GEMINI.md are symlinks to this
├── CHANGELOG.md  # 0.19.0 and newer; add new entries here
├── CHANGELOG-archive.md  # releases before 0.19.0, condensed
├── CITATION.cff
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── SECURITY.md
├── action.yml  # GitHub Action wrapper (loom project/model/embed-wheel)
├── codemeta.json
├── mkdocs.yml  # docs/ site config
└── pyproject.toml  # Project config and Hatchling build settings
```
