---
Created: 2026-09-30
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap -- completed items

See also: [roadmap.md](../design/roadmap.md) (open items).

Implementation detail for each item below (design decisions, function
names, PR links) lives in `working-docs/implementation/` where noted --
read the code/that doc for current state rather than this list, which
is not kept in sync with post-ship changes.

- [x] SPDX 3.0 SBOM generation (JSON-LD)
- [x] Hatchling metadata extraction (`pyproject.toml`)
- [x] Dependency tracking and SPDX relationship elements
- [x] Format-neutral internal representation
  (`DocumentModel` -- see [format-neutral-representation.md](../design/format-neutral-representation.md))
- [x] AI/ML package profiles
  (`software_Package` with AI BOM profile, `dataset_DatasetPackage`)
- [x] PEP 770 support (`.dist-info/sboms/` via `build_data["sbom_files"]`)
- [x] Hatchling build hook (`pitloom.plugins.hatch`) with fragment merging
- [x] ML tracking SDK (`pitloom.loom` -- context manager / decorator)
- [x] Metadata provenance tracking (per-field source attribution)
- [x] CLI (`loom`) with verbose mode and creator info options
- [x] Setuptools support -- initial implementation
  (`src/pitloom/extract/project/setuptools.py`; `pyproject.toml` > `setup.cfg` >
  `setup.py` conflict resolution)
- [x] Poetry support -- initial implementation
  (`src/pitloom/extract/project/poetry.py`; `read_pyproject()` falls back to
  `[tool.poetry]` when `[project]` is absent, merges both when present)
- [x] **PDM-backend and Flit-core support** -- metadata extraction and
  wheel file discovery for both backends. See
  [backend-file-discovery-validation.md](backend-file-discovery-validation.md)'s
  Flit-core/PDM-backend round.
- [x] **Multiple creators / tools per `CreationInfo` record** -- `Creator`/
  `Tool` dataclasses, repeatable `--creator-name`/`--creation-tool`,
  array-of-tables config. See [creation-metadata.md](../../docs/creation-metadata.md).
- [x] **SPDX license expression normalization and declared-vs-detected
  conflict detection (G2)** -- via [`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license).
  See [multi-source-conflict.md](provenance/multi-source-conflict.md)
  ([PR #121](https://github.com/bact/pitloom/pull/121)).
- [x] **`[project.license-files]` support** -- PEP 639's glob-list field
  for bundling multiple license files, each getting its own
  `software_File` element and `hasDeclaredLicense` relationship (PR #207).
  Later removed: an SBOM lists nothing under the wheel's own
  `.dist-info`. See
  [license-pipeline.md](license-pipeline.md#license-files-are-not-listed-pep-639).
- [x] **Auto-sync the Loom ID registry after SBOM generation** -- `loom
  project`/`wheel`/`env` harvest newly-minted ids back into the resolved
  registry after each run. See
  [id-registry-autosync.md](id-registry-autosync.md)
  ([PR #178](https://github.com/bact/pitloom/pull/178)).
- [x] **Lock/pin formats as a resolved-dependency source** -- `poetry.lock`,
  `pylock.toml` (PEP 751), `uv.lock`, `pdm.lock`, `Pipfile.lock`, and pinned
  `requirements.txt` feed `locked_dependencies` via one shared cascade
  ([#208](https://github.com/bact/pitloom/pull/208)). See
  [lock-file-cascade.md](lock-file-cascade.md).
- [x] **Explicit Loom ID registry** (declared only, one `ERROR:`, package
  ids pinned; #234, #235). See [id-registry-autosync.md](id-registry-autosync.md).
- [x] **Agent Skills portable across clients** (#235). See
  [skills-trigger-coverage.md](skills-trigger-coverage.md).
- [x] **Release SBOM licence guard** -- `pypi-publish.yml` fails unless
  the release SBOM (wheel + standalone) declares and concludes Apache-2.0
  (`scripts/check_sbom_license.py`); `embed-wheel` now emits the concluded
  licence (#243). See [release-checklist.md](release-checklist.md).
- [x] **PR-time SBOM licence check** -- `build.yml` runs
  `scripts/check_sbom_license.py` on every push/PR and no longer ignores
  `CITATION.cff`/`codemeta.json` (#248). See
  [release-checklist.md](release-checklist.md).

- [x] **GitHub Action** (composite `action.yml`) for any Python project.
  See [github-action.md](github-action.md),
  [docs/github-action.md](../../docs/github-action.md).
- [x] **AI-agent Skills** (`sbom-generate`, `sbom-enrich`, `sbom-validate`)
  and the **Claude Code plugin** bundling them. See
  [agent-skill.md](agent-skill.md), [claude-code-plugin.md](claude-code-plugin.md),
  [docs/agent-skills.md](../../docs/agent-skills.md).
- [x] **`loom verify-wheel` / `loom validate-wheel`** (#202). See
  [wheel-verification-commands.md](wheel-verification-commands.md).
- [x] **Backend-agnostic file discovery** (2026-09-15): static rescans for
  setuptools, Poetry, PDM-backend, Flit-core; `--allow-build` for the rest.
  See [non-hatchling-file-discovery.md](../design/non-hatchling-file-discovery.md),
  [docs/allow-build.md](../../docs/allow-build.md).
- [x] **Dataset-to-model relationships** (`trainedOn`/`testedOn`) and
  **Croissant dataset size**. See [ai-dataset-linking.md](ai-dataset-linking.md).
- [x] **Sort-order audit** of the assemble/id-registry path. See
  [sort-order-canonicalization.md](sort-order-canonicalization.md).

## Shipped for 0.20.0 (unreleased)

Grouped by area; user-facing detail in `docs/`, decisions in the linked
implementation docs, every change in `CHANGELOG.md` `[Unreleased]`.

- [x] **`--allow-build` timeout and signal-safe builds** (#226, #250, #262)
  -- `--build-timeout`, the whole build tree killed on SIGTERM/Ctrl-C,
  `ERROR: interrupted`. See [allow-build-timeout.md](allow-build-timeout.md),
  [allow-build-termination.md](allow-build-termination.md),
  [docs/allow-build.md](../../docs/allow-build.md).
- [x] **One config cascade on every surface** (#227, #228, #231, #232,
  #247, #249, #280) -- `--config` everywhere, explicit config sources, an
  sdist reads its own config, typed `setup.cfg` keys, unknown keys warn.
  See [config-sources.md](config-sources.md),
  [sdist-own-config.md](sdist-own-config.md),
  [docs/configuration.md](../../docs/configuration.md).
- [x] **Explicit ID registry, collision-free ids** (#234, #235, #255
  design) -- declared only, one `ERROR:`, `loom id`, registry format v2.
  See [id-registry-autosync.md](id-registry-autosync.md).
- [x] **`loom env` reads `pipdeptree --json`** (#236). See
  [deployed-env-pipdeptree.md](deployed-env-pipdeptree.md).
- [x] **AI model scanning: candidates, order, usage gate, wheels, bounds,
  outcome parity** (#239, #240, #252, #263, #267, #270) -- one
  `ModelCandidate`, deterministic order, `--scan-model-usage` (off by
  default), wheel scanning with `--trust-wheel-model`, bounded readers,
  one entry per confirmed model on every surface. See
  [ai-model-scanning.md](ai-model-scanning.md),
  [ai-model-scan-bounds.md](ai-model-scan-bounds.md),
  [docs/ai-model-scan-limits.md](../../docs/ai-model-scan-limits.md).
- [x] **Unreadable files and directories warn, never vanish** (#244, #257,
  #258). See [file-scan-unreadable-file.md](file-scan-unreadable-file.md),
  [file-discovery-unlistable-dir.md](file-discovery-unlistable-dir.md).
- [x] **Archive member names and wheel identity the same on every OS**
  (#251, #266, #278). See [archive-member-names.md](archive-member-names.md),
  [wheel-identity.md](wheel-identity.md).
- [x] **Valid IRIs for any name** (#253). See
  [iri-name-encoding.md](iri-name-encoding.md).
- [x] **Payload-only wheel SBOMs; embedded hashes stay valid** (#269 issue,
  #271, #277). See [wheel-embedding.md](wheel-embedding.md).
- [x] **sdist member order and `sbom-basename` extension** (#272, #273).
- [x] **Release SBOM is the build hook's, signed and attested** (#275). See
  [release-checklist.md](release-checklist.md).
- [x] **Licence element typing** (#276) -- canonical `LicenseExpression`,
  `NoAssertionLicense`/`NoneLicense` individuals, classifiers as a source,
  declared vs concluded by whose statement. See
  [license-typing.md](license-typing.md),
  [license-pipeline.md](license-pipeline.md).
- [x] **sdist licence detection** (#282, #283) -- `PKG-INFO` headers read
  bounded, one in-package rule for every reader. See
  [license-pipeline.md](license-pipeline.md).
- [x] **Fragment merge: id references, licence unification, document
  envelope** (#284). See
  [fragment-merge-unification.md](fragment-merge-unification.md),
  [docs/fragments.md](../../docs/fragments.md).
- [x] **CLI stdout is `KEY=VALUE` data only** (#281). See
  [docs/cli.md](../../docs/cli.md).
- [x] **Network-flaky tests skip with the cause; CI validation retries
  network failures** (#238, #259). See
  [recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md).
- [x] **Import cycles fixed; pylint covers test subfolders** (#260, #268).
- [x] **Windows and macOS CI** (#220), the earlier 1.0-table items 1-2;
  stale G7 gap claims in `minimum-elements.md` fixed (2026-09-20), item 4.
  See [windows-macos-ci.md](windows-macos-ci.md).
- [x] **CLI split, test modularization, coverage** (closed 2026-08-21). See
  [cli-test-coverage-roadmap.md](../design/cli-test-coverage-roadmap.md).
- [x] **CHANGELOG split** (2026-09-30) -- 0.19.0+ in `CHANGELOG.md`, older
  in `CHANGELOG-archive.md`.

