---
Created: 2026-09-30
Last-Modified: 2026-09-30
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
  `software_File` element and `hasDeclaredLicense` relationship. See
  [license-pipeline.md](license-pipeline.md#license-files-bundling-pep-639).
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
