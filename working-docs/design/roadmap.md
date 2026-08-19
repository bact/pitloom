---
Created: 2026-04-14
Last-Modified: 2026-08-19
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
    in `src/pitloom/extract/_setuptools.py`
  - Conflict resolution: `pyproject.toml` > `setup.cfg` > `setup.py`
  - CLI and `generate_project_sbom()` work without `pyproject.toml`
  - `[tool:pitloom]` config section in `setup.cfg`
- [x] Poetry support -- initial implementation
  - `read_poetry()`, `extract_poetry_metadata()`
    in `src/pitloom/extract/_poetry.py`
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
- [x] **SPDX license expression normalization and declared-vs-detected
  conflict detection (G2)** -- compound SPDX license expressions
  (`"MIT AND MIT"`, `"(MIT AND Apache-2.0) OR BSD-3-Clause"`) are parsed,
  deduped, and canonically reordered via
  [`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license) (not
  the `license-expression` library originally envisioned here), so a
  casing difference or an equivalent-but-differently-written expression
  is never misreported as a conflict. The project directory
  (`CITATION.cff`, `codemeta.json`, `LICENSE` files) is independently
  scanned even when a license is already declared, uniformly across all
  four project-metadata extraction paths (CLI/library, Hatchling build
  hook, poetry-only, setuptools-only). On genuine disagreement, both
  `hasDeclaredLicense` and `hasConcludedLicense` are recorded alongside a
  generic `provenance/conflict/1` Annotation (reusable for any field, not
  license-specific). See
  [annotation-provenance.md](../implementation/provenance/annotation-provenance.md)'s
  G2 section. ([PR #121](https://github.com/bact/pitloom/pull/121))
  Remaining, narrower scope than "PEP 639 compliance" originally implied:
  `[project.license-files]` (the glob-list field for bundling multiple
  license files) is not specifically parsed.

## Adoption surfaces

Pitloom's other surfaces (library API, CLI, Hatchling build hook, ML
tracking SDK) all assume the consumer already has Pitloom installed or
wired into a build backend. These two extend reach beyond that. See
[adoption-surfaces.md](../implementation/adoption-surfaces.md) for the
full picture.

- [x] **GitHub Action** (composite `action.yml`) -- generate an SBOM in CI
  with a single `uses:` line, for any Python project regardless of build
  backend. Dogfooded on Pitloom itself in
  `.github/workflows/action-selftest.yml`.
  See [github-action.md](../implementation/github-action.md).
- [x] **AI-agent Skills** (`skills/sbom-generate/`, `skills/sbom-enrich/`,
  `skills/sbom-validate/`) -- lets Claude Code, the Claude Agent SDK, or
  similar runtimes generate an SBOM on request, optionally enrich it
  (README/model-card inference contributed back as a provenance-marked
  fragment), and validate any SPDX 3 document's schema/shape conformance.
  Independently triggerable by natural language or explicit invocation.
  See [agent-skill.md](../implementation/agent-skill.md) and
  [sbom-enrichment.md](sbom-enrichment.md).
- [x] **Claude Code plugin** (`.claude-plugin/`) -- bundles all three
  Skills under the `pitloom` plugin namespace so they install with
  `/plugin install` directly from this repository, with namespaced
  explicit invocation (`/pitloom:sbom-generate`, `/pitloom:sbom-enrich`,
  `/pitloom:sbom-validate`). See
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
- [ ] **`get_wheel_files()` option to skip Merkle root computation** --
  `_build_sbom_from_project_and_wheel` (`src/pitloom/embed.py`) already
  discards `get_wheel_files()`'s own `merkle_root` return value in favor
  of one computed from the wheel's own (post-merge) file hashes (see
  `_compute_wheel_merkle_root`), so that work is wasted for its one
  current caller. Worth adding only when both `extract_file_header` and
  `content_type` are off too -- otherwise every file's bytes get read
  off disk anyway for header/content-type scanning, and skipping just
  the hash/tree-build step on top of bytes already in memory saves
  little. With both scanners off, though, `get_wheel_files()` currently
  reads every file's full bytes solely to hash them for the discarded
  root -- real, avoidable I/O for large projects.
- [ ] **Installed `.dist-info` / `.egg-info` as metadata source** -- treat
  an existing installed package as a high-fidelity source when present
  (editable installs, virtual environments).
  See [metadata-sources.md](metadata-sources.md).

### PEP 770 / embed-wheel

- [ ] **`loom embed-wheel --verify`** -- check that a wheel's embedded SBOM
  is at the correct `.dist-info/sboms/<basename>` location and passes
  schema/SHACL validation, as a single CLI command. Right now
  `.github/workflows/pypi-publish.yml`'s "Check SBOM is at the PEP 770
  location" step hand-rolls this in bash (`unzip -Z1` + a glob match)
  against the same path convention `pitloom._embed_wheel._plan_embed`
  already encodes in Python, plus a separate `spdx3-validate` call -- two
  independently-maintained representations of one convention that could
  drift if `_plan_embed`'s layout ever changes. A `--verify` flag would
  consolidate both checks into the tool itself, reusable by any CI
  pipeline (not just this repo's own release workflow) without
  reimplementing the path convention.
  Since `spdx3-validate` 0.0.7, it's usable as a Python library, not just
  a CLI (see [using-as-a-library](https://github.com/JPEWdev/spdx3-validate#using-as-a-library)) --
  `--verify` could call it in-process instead of shelling out, avoiding a
  second subprocess/dependency-install step in CI.

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

- [ ] **`[project.license-files]` support** -- PEP 639's glob-list field
  for bundling multiple license files (narrower remainder of the old
  "License expression support" item -- expression parsing/normalization
  and conflict detection shipped, see Completed above).
- [ ] **Enhanced dependency analysis** -- transitive dependencies, optional
  extras, development dependencies.
- [x] **SBOM enrichment from external sources** (the `enrich/` subpackage)
  -- MVP shipped: local README/model-card **YAML frontmatter** parsing
  (`enrich/readme.py`, license + dataset gaps only, not prose), gated by
  `[tool.pitloom] enrich` (**default off** -- opt-in until more
  sources ship). Not to be confused with the agent-facing `sbom-enrich`
  *Skill* above -- this is code-level, deterministic, non-agent. Also
  what [annotation-provenance.md](../implementation/provenance/annotation-provenance.md)'s
  N3 ("who/when enriched") needed to exist first -- now shipped too, see
  its own entry there.
  Exposed as a first-class capability across every generation surface,
  not just `generate_model_sbom()`: a standalone `loom enrich`
  CLI/`enrich_model()` API (writes a mergeable fragment, no full SBOM),
  `--enrich`/`--no-enrich` on `loom model`/`loom project`/`loom generate`,
  project-level enrichment for every AI model `loom project`/`loom
  generate` discovers (previously silently skipped), automatic
  inheritance in the Hatchling build hook, and a `enrich` input on the
  GitHub Action. See [sbom-enrichment.md](sbom-enrichment.md)'s
  "Surfaces" section.
  Still not started: OpenSSF Scorecard (public API), Hugging Face Hub and
  PyPI metadata (user opt-in), per-source enable/disable via additional
  `[tool.pitloom]` enrich-related keys added when each lands (`enrich`
  itself is a flat bool now, not a table -- a per-source toggle scheme
  will need its own naming, decided when the first extra source ships).
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
