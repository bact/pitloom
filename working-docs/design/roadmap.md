---
Created: 2026-04-14
Last-Modified: 2026-09-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

## Completed

Implementation detail for each item below (design decisions, function
names, PR links) lives in `working-docs/implementation/` where noted --
read the code/that doc for current state rather than this list, which
is not kept in sync with post-ship changes.

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
  (`src/pitloom/extract/_setuptools.py`; `pyproject.toml` > `setup.cfg` >
  `setup.py` conflict resolution)
- [x] Poetry support -- initial implementation
  (`src/pitloom/extract/_poetry.py`; `read_pyproject()` falls back to
  `[tool.poetry]` when `[project]` is absent, merges both when present)
- [x] **PDM-backend and Flit-core support** -- metadata extraction
  (`src/pitloom/extract/_pdm.py`, `_flit.py`: dynamic `version`/
  `description` resolved via each backend's own logic --
  `[tool.pdm.version]`'s `file`/`scm` sources, Flit's module
  `__version__`/docstring convention) and wheel file discovery
  (`src/pitloom/core/_models_wheel_pdm.py`, `_models_wheel_flit.py`),
  wired into `read_pyproject()` and `_models_wheel.py`'s
  `backend_discoverers` registry. See
  [backend-file-discovery-validation.md](../implementation/backend-file-discovery-validation.md)'s
  Flit-core/PDM-backend round.
- [x] **Multiple creators / tools per `CreationInfo` record** -- `Creator`/
  `Tool` dataclasses, repeatable `--creator-name`/`--creation-tool`,
  array-of-tables config. See [creation-metadata.md](../../docs/creation-metadata.md).
- [x] **SPDX license expression normalization and declared-vs-detected
  conflict detection (G2)** -- via [`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license).
  See [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md)
  ([PR #121](https://github.com/bact/pitloom/pull/121)).
- [x] **`[project.license-files]` support** -- PEP 639's glob-list field
  for bundling multiple license files. `ProjectMetadata.license_files`
  (resolved by `pyproject_metadata`/Hatchling, not re-globbed by Pitloom);
  each entry gets a `software_File` element at the real wheel's
  `<name>-<version>.dist-info/licenses/<path>` and a `hasDeclaredLicense`
  relationship, deduped against the package-level license element. See
  [license-pipeline.md](../implementation/license-pipeline.md#license-files-bundling-pep-639).
- [x] **Auto-sync the Loom ID registry after SBOM generation** -- `loom
  project`/`wheel`/`env` harvest newly-minted ids back into the resolved
  registry after each run. `ai_AIPackage`/`dataset_DatasetPackage`
  deliberately excluded -- see
  [Loom IDs across fragments](../../README.md#loom-ids-across-fragments-pitloom-ids).
  Open follow-ups: [AI model id stability](#ai-model-id-stability-follow-up-to-178),
  [Sort-order canonicalization](#sort-order-canonicalization-follow-up-to-178)
  below. ([PR #178](https://github.com/bact/pitloom/pull/178))

## Adoption surfaces

Pitloom's other surfaces (library API, CLI, Hatchling build hook, ML
tracking SDK) all assume the consumer already has Pitloom installed or
wired into a build backend. These two extend reach beyond that. See
[adoption-surfaces.md](../implementation/adoption-surfaces.md) for the
full picture.

- [x] **GitHub Action** (composite `action.yml`) -- generate an SBOM in CI
  with a single `uses:` line, for any Python project regardless of build
  backend. See [github-action.md](../implementation/github-action.md).
- [x] **AI-agent Skills** (`skills/sbom-generate/`, `skills/sbom-enrich/`,
  `skills/sbom-validate/`) -- generate/enrich/validate an SBOM on
  request from Claude Code, the Claude Agent SDK, or similar runtimes.
  See [agent-skill.md](../implementation/agent-skill.md) and
  [sbom-enrichment.md](sbom-enrichment.md).
- [x] **Claude Code plugin** (`.claude-plugin/`) -- bundles all three
  Skills under the `pitloom` plugin namespace (`/plugin install`,
  `/pitloom:sbom-generate` etc). See
  [claude-code-plugin.md](../implementation/claude-code-plugin.md).
- [ ] **Docker container action** (future) -- a `Dockerfile` +
  `action.yml` `using: docker` variant of the GitHub Action for hermetic
  or self-hosted-runner use.
- [ ] **SARIF output** -- emit a SARIF file as a build artifact for CI
  findings (inline PR annotations, Security-tab view), fed by
  `WARNING:`/`ERROR:` output, OSV.dev results (once built), and license
  conflicts. See [sarif-output.md](sarif-output.md).

## Near-term

**Next up:**
[Non-Hatchling file discovery](#non-hatchling-file-discovery-feature-parity)
below -- a major feature-parity gap affecting the accuracy of `loom
project`'s file inventory for any non-Hatchling project. Setuptools,
Poetry, PDM-backend, and Flit-core support are done (see priority
table in [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md));
`uv_build` is next, without a committed version yet.

### Non-Hatchling file discovery (feature parity)

- [ ] **`get_wheel_files()` file discovery is not backend-agnostic** --
  partially fixed (2026-08-27): now a per-backend dispatch facade
  (`src/pitloom/core/_models_wheel.py`), with setuptools, Poetry,
  PDM-backend, and Flit-core closed; any backend without a dedicated
  module (`uv_build`, ...) still falls back to the Hatchling heuristic,
  which can silently produce a **wrong** file list for a non-Hatchling
  layout. Two tracks remain: static/declarative backends (`uv_build`)
  need a backend-aware rescan; compiled/native backends (`maturin`,
  `scikit-build-core`, `meson-python`) need a build-and-read mechanism,
  since their files don't exist pre-build. See
  [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md)
  for the bug detail, the Track A/B split, the dependency-packaging
  (optional-extras) decision, and the full backend priority order.

### Build backend improvements

- [ ] **PEP 517 `prepare_metadata_for_build_wheel`** (opt-in) -- call the build
  backend in a subprocess to resolve dynamic metadata (Git-tag versions,
  computed deps) that static parsing cannot handle.
  See [metadata-sources.md](metadata-sources.md).
- [x] **Setuptools wheel file discovery** -- setuptools' own official
  config-resolution API (`setuptools.config.pyprojecttoml`/`setupcfg`)
  and `build_py` introspection now resolve a setuptools project's file
  set from static config, instead of Hatchling's `WheelBuilder`. See
  [setuptools-support.md](../implementation/setuptools-support.md) and
  [sbom-lifecycle-stages.md](../implementation/sbom-lifecycle-stages.md).
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
  See [metadata-sources.md](./metadata-sources.md).
- [x] **`poetry.lock`** -- done (2026-08-31): `loom project`/`loom generate`
  against a Poetry project reads a sibling `poetry.lock` for
  `main`-group resolved transitive dependencies, additive to the
  direct constraints, source-stage-only. See
  [poetry-support.md](../implementation/poetry-support.md).
- [x] **`pylock.toml` (PEP 751)** -- done (2026-09-04): `loom project`/
  `loom generate` reads a sibling `pylock.toml`, when present, for its
  resolved `[[packages]]` set, reusing `ProjectMetadata.locked_dependencies`
  and the same additive `dependsOn`/`RelationshipCompleteness.complete`
  wiring as `poetry.lock`. Build-backend-agnostic, so it's checked
  unconditionally rather than gated behind `[tool.poetry]` detection.
  See [pep751-pylock-support.md](../implementation/pep751-pylock-support.md)
  and [lock-file-cascade.md](../implementation/lock-file-cascade.md) for
  the shared priority mechanism across all lock formats.
- [x] **`uv.lock`** -- done (2026-09-04): reads a sibling `uv.lock`'s
  resolved main/runtime dependencies, ranked below `pylock.toml` and
  above `poetry.lock` in the shared priority cascade. See
  [lock-file-cascade.md](../implementation/lock-file-cascade.md).
- [x] **`pdm.lock`** -- done (2026-09-04): reads a sibling `pdm.lock`'s
  resolved `default`-group dependencies, ranked below `poetry.lock`.
  See [lock-file-cascade.md](../implementation/lock-file-cascade.md).
- [x] **`Pipfile.lock`** -- done (2026-09-05): reads a sibling
  `Pipfile.lock`'s resolved `default`-section dependencies (JSON, not
  TOML -- the one format that isn't), ranked below `pdm.lock`, lowest
  cascade priority. Reached via `read_project()`'s `setup.py`-only
  dispatch path, not just the `pyproject.toml` one, since `Pipfile.lock`
  predates PEP 621 almost entirely in real projects. See
  [lock-file-cascade.md](../implementation/lock-file-cascade.md).
- [ ] **Remaining lock formats as a resolved-dependency source**
  (`pixi.lock`, `conda-lock.yml`, pinned `requirements.txt`) -- `loom
  project` still records only the declared version specifier from
  `pyproject.toml [project] dependencies`
  (`normalize_dependency_specifier`, `src/pitloom/extract/_pyproject.py:220`,
  e.g. `requests>=2.0`) for a project with none of the five already-shipped
  lock formats present, never a concrete resolved version. Parsing one
  when present would let a Source SBOM carry the actual pinned version a
  build will use, not just the declared range -- closer to what CISA's
  Source SBOM guidance expects. `pylock.toml`/`uv.lock`/`poetry.lock`/
  `pdm.lock`/`Pipfile.lock` establish the pattern (additive
  transitive-only edges, `completeness` tagging, source-stage-only
  scoping, one shared priority cascade); each further format added
  needs its own slot in that same priority order and a provenance
  `method` tag. See [lock-files.md](./lock-files.md) for the broader
  multi-format extraction-priority roadmap (`pixi.lock`,
  `conda-lock.yml`) this item now defers to.

### PEP 770 / embed-wheel

- [x] **`loom verify-wheel` / `loom validate-wheel`** ([#202](https://github.com/bact/pitloom/pull/202))
  -- structural location check and schema/SHACL content validation for
  a wheel's embedded SBOM, plus `embed-wheel --verify`/`--validate`
  convenience flags and a pre-embed name/version enforcement check for
  `--sbom`. See
  [wheel-verification-commands.md](../implementation/wheel-verification-commands.md).

### AI model id stability (follow-up to [#178](https://github.com/bact/pitloom/pull/178))

- [ ] **Deterministic same-model identification for auto-harvest** --
  `ai_AIPackage` elements are excluded from the Loom ID registry's
  auto-harvest since `ai_model.name` is extraction-dependent. Open
  design question: whether a content-hash match (narrower than "same
  model" for re-exported/re-quantized models) plus a non-identifying
  "machine ID" scoping tag could safely extend auto-harvest to AI
  models. No implementation direction chosen yet. See
  [ai-model-id-stability.md](ai-model-id-stability.md).

### Sort-order canonicalization (follow-up to [#178](https://github.com/bact/pitloom/pull/178))

- [x] **Audit where element/entry sort order feeds hash or id
  construction.** Every `sorted()`/`.sort()` call in the
  assemble/id-registry path audited; the one genuinely canonical
  (hash/id-affecting) key was renamed and documented as such, the
  non-canonical ones marked as not affecting output. No behavior
  changed. See
  [sort-order-canonicalization.md](../implementation/sort-order-canonicalization.md).

### Extractors

- [ ] **Additional AI model format extractors**
  - JAX (Orbax checkpoints) -- higher priority
  - TensorFlow SavedModel and TensorFlow Lite
  - Scikit-learn (pickle/joblib; no single standard format -- complex)
  - See [model-metadata-extraction.md](model-metadata-extraction.md)
- [x] **Dataset-to-model relationship linking** -- `AiModelMetadata` carries
  dataset references (`DatasetReference`, `pitloom.core.dataset_metadata`);
  `add_datasets_for_model()` (`src/pitloom/assemble/spdx3/dataset.py`)
  emits `trainedOn`/`testedOn` `Relationship`s natively, falling back to
  `RelationshipType.other` + an explanatory comment for the three SPDX
  3.0.1 lacks (`finetunedOn`, `validatedOn`, `pretrainedOn`). Wired in from
  `assemble/spdx3/ai.py` and `_document_model.py`. See
  [sbom-enrichment.md](sbom-enrichment.md).
- [ ] **Croissant dataset size calculation** -- `dataset_DatasetSize` is
  currently always `0` (see `_extract_croissant_core_fields()` in
  `_croissant.py`); needs real logic summing `cr:totalItems` across
  `cr:recordSet` entries (and handling the string-vs-int value variance
  seen in real Croissant files).

### Metadata quality

- [ ] **Revise and publish the provenance/enrichment vocabulary reference**
  -- draft `docs/vocabulary.md` page reverted out of `docs/` pending a
  `role`/`method` taxonomy revision; once settled, publish and
  consolidate every place that documents this vocabulary ad hoc into
  one canonical source. See
  [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md).
- [ ] **Generalize multi-source conflict detection beyond license**
  (priority) -- `build_conflict_annotation`
  (`src/pitloom/assemble/spdx3/provenance.py:169`) is the only place the
  `conflict` Annotation kind (Section 5.7/G2,
  [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md))
  is constructed, and it has exactly one caller:
  `src/pitloom/assemble/spdx3/deps_license.py:256`. The independent-detection
  vs. declared-value comparison mechanism this implements is general --
  obtain a fact two independent ways, normalize, compare, emit `conflict`
  only on genuine disagreement -- but today it exists for license only.
  Dependency version (declared specifier vs. lock-file-resolved version,
  once the lock file item above ships) is the most obvious next
  candidate: the same "don't let two sources silently disagree" argument
  applies, and the comparison/normalization scaffolding already built for
  license is largely reusable.
- [ ] **Enhanced dependency analysis** -- transitive dependencies, optional
  extras, development dependencies.
- [ ] **Auto-discover default license files when `[project.license-files]`
  is undeclared** -- setuptools' `_finalize_license_files()` and
  Hatchling's `CoreMetadata.license_files` both fall back to the same
  glob (`LICEN[CS]E*`, `COPYING*`, `NOTICE*`, `AUTHORS*`, citing the
  `wheel` package's own documented convention) and bundle whatever
  matches into a real wheel's `.dist-info/licenses/`, even with no
  explicit field. Pitloom's `resolve_license_file_entries()`
  (`src/pitloom/extract/_license.py`) deliberately does *not* replicate
  this today -- both extraction paths only trust an explicit
  `[project.license-files]` declaration (see
  [license-pipeline.md](../implementation/license-pipeline.md)'s
  "License-files bundling" section) --
  because the default glob is a build-backend auto-bundling convenience,
  not something PEP 639 itself defines, and because `NOTICE`/`AUTHORS`
  matches don't obviously belong under a `hasDeclaredLicense` relationship
  the way `LICENSE`/`COPYING` do. If this is picked up, it needs its own
  design pass: which stems to trust, whether it holds for every backend
  (only setuptools and Hatchling are confirmed so far), and a provenance
  label that clearly distinguishes "inferred default" from "explicitly
  declared."
- [x] **SBOM enrichment from external sources** (the `enrich/` subpackage)
  -- MVP shipped: local README/model-card YAML frontmatter parsing,
  gated by `[tool.pitloom] enrich` (default off). Code-level and
  deterministic -- distinct from the agent-facing `sbom-enrich` Skill
  above. Exposed across every generation surface (`loom enrich` CLI,
  `--enrich`/`--no-enrich` flags, Hatchling build hook, GitHub Action
  input). Still not started: OpenSSF Scorecard, Hugging Face Hub and
  PyPI metadata sources, per-source enable/disable config.
  See [sbom-enrichment.md](sbom-enrichment.md).
- [ ] **OSV.dev vulnerability lookup** (`--enrich-cve` or similar) -- static
  enrichment only (no exploitability judgement); VEX generation under
  Medium-term is the follow-on triage step. See
  [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md).

### Diagnostics / logging

- [x] **Surface `DEBUG:`-level output on request** -- shipped both
  triggers rather than choosing one: a new top-level `--debug` flag
  (parsed before the subcommand, like `-V`; `cli/verbose.py`'s existing
  `--verbose` was left alone since it does something unrelated) and the
  `PITLOOM_DEBUG` environment variable, which also covers entry points
  that don't parse CLI flags themselves (the Hatchling build hook, every
  public library-API generator). `configure_logging(debug=...)`
  resolves `None` (every existing no-argument call site) against the
  env var; an explicit `True`/`False` (the CLI's `--debug`) wins outright.
  See `pitloom.logging_config`. ([PR #201](https://github.com/bact/pitloom/pull/201))
- [x] **Promote silent-data-loss `DEBUG:` messages to `WARNING:`** --
  18 messages across the HF Hub, PyTorch/PT2, fastText, README
  enrichment, and sdist extractors, plus `pitloom.loom` caller-provenance
  detection, now surface by default (not just under `--debug`) when a
  failure drops or degrades an SBOM/AIBOM field. Each names the affected
  field(s) via one shared, grep-able helper, `field_loss_suffix()`
  (`pitloom.logging_config`), instead of hand-duplicated suffix text per
  call site. ([PR #201](https://github.com/bact/pitloom/pull/201))

## Medium-term

- [ ] **CycloneDX assembler** -- add a CycloneDX serializer consuming the
  existing `DocumentModel`; no changes to extractors required.
- [ ] **AIDOC / TechOps renderer** -- additional output format consuming
  `DocumentModel`.
- [ ] **Build log extraction** -- capture compiled dependencies, linker flags,
  and bundled libraries from build output logs.
- [ ] **VEX (VEX/OpenVEX) generation** -- consumes the OSV.dev lookup
  above (once it exists) to classify a component as affected/
  not_affected/fixed/under_investigation, rather than just listing raw
  CVE hits. Depends on the OSV enrichment item under Near-term /
  Metadata quality landing first.

## Long-term

- [ ] **PEP 740 attestations** -- cryptographic signing and provenance
  tracking for generated SBOMs.
- [ ] **IETF SCITT integration** -- submit a generated SBOM as a signed
  SCITT statement to a transparency service (`loom scitt submit`),
  receive a receipt back as proof of registration; verify a
  dependency's own receipt on consume. Complementary to (not a
  replacement for) the PEP 740 item above. See <https://scitt.io/> and
  [scitt-integration.md](scitt-integration.md) for the receipt-placement
  decision, Pitloom's client-only role, and the tooling landscape.
- [ ] **Performance optimization** -- Rust backend for large-project
  log parsing; parallel file hashing for Merkle root computation.
- [ ] **Agentic skill governance (guardrail mode)** -- extend the
  existing AI-agent Skills (Adoption surfaces above) from "generate an
  SBOM on request" to "veto/flag a coding agent's own action" -- e.g.
  block or require override when an agent attempts to pull an unvetted
  Hugging Face model. Distinct capability from the current Skills:
  needs a hook into the calling agent's tool-use loop, not just a
  callable Skill.
- [ ] **Runtime reachability ("living SBOM")** -- evolve `loom env`
  (currently a static environment graph, see Market signals above)
  toward tracking which dependencies are actually loaded/executed at
  runtime (`sys.modules` introspection or eBPF), to suppress
  vulnerability noise from installed-but-unreachable code. Large scope
  -- needs its own design doc before estimating.
