---
Created: 2026-04-14
Last-Modified: 2026-07-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

## Completed

- [x] SPDX 3.0 SBOM generation (JSON-LD)
- [x] Hatchling metadata extraction (`pyproject.toml`)
- [x] Dependency tracking and SPDX relationship elements
- [x] Format-neutral internal representation
  (`DocumentModel` -- see [format-neutral-representation.md](format-neutral-representation.md))
- [x] AI/ML package profiles
  (`software_Package` with AI BOM profile, `dataset_DatasetPackage`)
- [x] PEP 770 support (`.dist-info/sboms/` via `build_data["sbom_files"]`)
- [x] Hatchling build hook (`pitloom.plugins.hatch`) with fragment merging
- [x] ML tracking SDK (`pitloom.loom` -- context manager / decorator)
- [x] Metadata provenance tracking (per-field source attribution)
- [x] CLI (`loom`) with verbose mode and creator info options
- [x] Setuptools support -- initial implementation
  - `read_setup_cfg()`, `read_setup_py()`, `read_setuptools()`,
    `merge_metadata()`, `detect_build_backend()`
    in `src/pitloom/extract/setuptools.py`
  - Conflict resolution: `pyproject.toml` > `setup.cfg` > `setup.py`
  - CLI and `generate_sbom()` work without `pyproject.toml`
  - `[tool:pitloom]` config section in `setup.cfg`
- [x] Poetry support -- initial implementation
  - `read_poetry()`, `extract_poetry_metadata()`
    in `src/pitloom/extract/poetry.py`
  - Reads `[tool.poetry]` and `[tool.poetry.dependencies]`
  - `[tool.poetry.group.*]` dev/deploy dependency groups intentionally excluded
  - Poetry version specifiers (`^`, `~`, bare versions) converted to PEP 440
  - `read_pyproject()` falls back to `[tool.poetry]` when `[project]` is absent;
    merges both sections when both are present (`[project]` wins field-by-field)
- [x] **Multiple creators / tools per `CreationInfo` record** -- `Creator` /
  `Tool` dataclasses replace the old scalar `creator_name`/
  `creation_tool` fields; `CreationMetadata.creators: list[Creator]` and
  `.tools: list[Tool] | None` allow ≥1 Agents in `createdBy` and 0+
  Tools in `createdUsing`, matching what SPDX 3 allows. CLI: repeatable
  `--creator-name` (stateful -- `--creator-type`/`--creator-email` bind to
  the most recently named creator) and repeatable `--creation-tool`.
  Config: `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]`
  array-of-tables in `pyproject.toml` (Poetry too); `setup.cfg` keeps
  single-creator/-tool support only (INI can't express array-of-tables).
  `suppliedBy` on the main package -- single-valued in SPDX 3 -- is set to
  the first named creator. See
  [creation-metadata.md](../../docs/creation-metadata.md).

## Adoption surfaces

Pitloom's other surfaces (library API, CLI, Hatchling build hook, ML
tracking SDK) all assume the consumer already has Pitloom installed or
wired into a build backend. These two extend reach beyond that. See
[adoption-surfaces.md](adoption-surfaces.md) for the full picture.

- [x] **GitHub Action** (composite `action.yml`) -- generate an SBOM in CI
  with a single `uses:` line, for any Python project regardless of build
  backend. Dogfooded on Pitloom itself in
  `.github/workflows/action-selftest.yml`.
  See [github-action.md](../implementation/github-action.md).
- [x] **AI-agent Skills** (`skills/sbom/`, `skills/enrich/`) -- lets
  Claude Code, the Claude Agent SDK, or similar runtimes generate an SBOM
  on request, and optionally enrich it (README/model-card inference
  contributed back as a provenance-marked fragment). Independently
  triggerable by natural language or explicit invocation.
  See [agent-skill.md](../implementation/agent-skill.md) and
  [sbom-enrichment.md](sbom-enrichment.md).
- [x] **Claude Code plugin** (`.claude-plugin/`) -- bundles both Skills
  under the `pitloom` plugin namespace so they install with
  `/plugin install` directly from this repository, with namespaced
  explicit invocation (`/pitloom:sbom`, `/pitloom:enrich`). See
  [claude-code-plugin.md](../implementation/claude-code-plugin.md).
- [ ] **Docker container action** (future) -- a `Dockerfile` +
  `action.yml` `using: docker` variant of the GitHub Action for hermetic
  or self-hosted-runner use.

## Near-term

### Build backend improvements

- [ ] **PEP 517 `prepare_metadata_for_build_wheel`** (opt-in) -- call the build
  backend in a subprocess to resolve dynamic metadata (Git-tag versions,
  computed deps) that static parsing cannot handle.
  See [metadata-sources.md](metadata-sources.md).
- [ ] **Setuptools wheel file discovery** -- use setuptools' own file inclusion
  logic to compute a Merkle root for setuptools projects (currently
  `get_wheel_files()` returns `None` for non-Hatchling projects).
- [ ] **Installed `.dist-info` / `.egg-info` as metadata source** -- treat
  an existing installed package as a high-fidelity source when present
  (editable installs, virtual environments).
  See [metadata-sources.md](metadata-sources.md).

### Extractors

- [ ] **Additional AI model format extractors**
  - JAX (Orbax checkpoints) -- higher priority
  - TensorFlow SavedModel and TensorFlow Lite
  - Scikit-learn (pickle/joblib; no single standard format -- complex)
  - See [model-metadata-extraction.md](model-metadata-extraction.md)
- [ ] **Dataset-to-model relationship linking** -- extend `AiModelMetadata`
  with dataset references; emit SPDX 3 relationship types (`trainedOn`,
  `testedOn`, `finetunedOn`, `validatedOn`, `pretrainedOn`).
  See [sbom-enrichment.md](sbom-enrichment.md).

### Metadata quality

- [ ] **License expression support** -- PEP 639 compliance, SPDX license
  expression parsing via `license-expression` library, license relationship
  modeling.
- [ ] **Enhanced dependency analysis** -- transitive dependencies, optional
  extras, development dependencies.
- [ ] **SBOM enrichment from external sources** -- README / model card parsing
  (local, no network), OpenSSF Scorecard (public API), Hugging Face Hub and
  PyPI metadata (user opt-in), per-source enable/disable via
  `[tool.pitloom.enrich]`.
  See [sbom-enrichment.md](sbom-enrichment.md).

## Medium-term

- [ ] **CycloneDX assembler** -- add a CycloneDX serializer consuming the
  existing `DocumentModel`; no changes to extractors required.
- [ ] **AIDOC / TechOps renderer** -- additional output format consuming
  `DocumentModel`.
- [ ] **Build log extraction** -- capture compiled dependencies, linker flags,
  and bundled libraries from build output logs.
- [ ] **PDM / Flit extractors** -- extend `detect_build_backend()` and
  add per-backend extractor functions following the same
  `read_X() -> (ProjectMetadata, PitloomConfig)` pattern.

## Long-term

- [ ] **PEP 740 attestations** -- cryptographic signing and provenance
  tracking for generated SBOMs.
- [ ] **Performance optimization** -- Rust backend for large-project
  log parsing; parallel file hashing for Merkle root computation.
