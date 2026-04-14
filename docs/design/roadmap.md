---
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
- [x] Format-neutral internal representation (`DocumentModel` — see [format-neutral-representation.md](format-neutral-representation.md))
- [x] AI/ML package profiles (`software_Package` with AI BOM profile, `dataset_DatasetPackage`)
- [x] PEP 770 support (`.dist-info/sboms/` via `build_data["sbom_files"]`)
- [x] Hatchling build hook (`pitloom.plugins.hatch`) with fragment merging
- [x] ML tracking SDK (`pitloom.loom` — context manager / decorator)
- [x] Metadata provenance tracking (per-field source attribution)
- [x] CLI (`loom`) with verbose mode and creator info options

## Near-term

### Build backend improvements

- [ ] **Setuptools support**
  - Conflict resolution between `pyproject.toml`, `setup.cfg`, `setup.py`
- [ ] **Setuptools wheel file discovery** — use setuptools' own file inclusion
  logic to compute a Merkle root for setuptools projects (currently
  `get_wheel_files()` returns `None` for non-Hatchling projects).
- [ ] **PEP 517 `prepare_metadata_for_build_wheel`** (opt-in) — call the build
  backend in a subprocess to resolve dynamic metadata (Git-tag versions,
  computed deps) that static parsing cannot handle.
  See [metadata-sources.md](metadata-sources.md).
- [ ] **Installed `.dist-info` / `.egg-info` as metadata source** — treat
  an existing installed package as a high-fidelity source when present
  (editable installs, virtual environments).
  See [metadata-sources.md](metadata-sources.md).

### Extractors

- [ ] **Additional AI model format extractors**
  - JAX (Orbax checkpoints) — higher priority
  - TensorFlow SavedModel and TensorFlow Lite
  - Scikit-learn (pickle/joblib; no single standard format — complex)
  - See [model-metadata-extraction.md](model-metadata-extraction.md)
- [ ] **Dataset-to-model relationship linking** — extend `AiModelMetadata`
  with dataset references; emit SPDX 3 relationship types (`trainedOn`,
  `testedOn`, `finetunedOn`, `validatedOn`, `pretrainedOn`).
  See [sbom-enrichment.md](sbom-enrichment.md).

### Metadata quality

- [ ] **License expression support** — PEP 639 compliance, SPDX license
  expression parsing via `license-expression` library, license relationship
  modeling.
- [ ] **Enhanced dependency analysis** — transitive dependencies, optional
  extras, development dependencies.
- [ ] **SBOM enrichment from external sources** — README / model card parsing
  (local, no network), OpenSSF Scorecard (public API), Hugging Face Hub and
  PyPI metadata (user opt-in), per-source enable/disable via
  `[tool.pitloom.enrich]`.
  See [sbom-enrichment.md](sbom-enrichment.md).

## Medium-term

- [ ] **CycloneDX assembler** — add a CycloneDX serializer consuming the
  existing `DocumentModel`; no changes to extractors required.
- [ ] **AIDOC / TechOps renderer** — additional output format consuming
  `DocumentModel`.
- [ ] **Build log extraction** — capture compiled dependencies, linker flags,
  and bundled libraries from build output logs.
- [ ] **Poetry / PDM / Flit extractors** — extend `detect_build_backend()` and
  add per-backend extractor functions following the same
  `read_X() → (ProjectMetadata, PitloomConfig)` pattern.

## Long-term

- [ ] **PEP 740 attestations** — cryptographic signing and provenance tracking
  for generated SBOMs.
- [ ] **Performance optimization** — Rust backend for large-project log parsing;
  parallel file hashing for Merkle root computation.
