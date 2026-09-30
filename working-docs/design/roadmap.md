---
Created: 2026-04-14
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

## Completed

Moved to [roadmap-completed.md](../implementation/roadmap-completed.md).

## 1.0 target (2026-10-15)

Goal: ship 1.0 within one month (by mid-October 2026). GitHub milestone
`1.0.0` already exists (no issues attached yet, no due date set).
**Redefined 2026-09-17**: 1.0's headline is **G7 SBOM for AI field
coverage**, not just stability -- see
[G7 SBOM for AI field coverage](#g7-sbom-for-ai-field-coverage-10-headline)
below. Cross-platform CI is already closed
([PR #220](https://github.com/bact/pitloom/pull/220)), as is the
`--allow-build` timeout (PR #226); the remaining stability item
(versioning policy) stays in scope but no longer fills the list on its
own.

**Scope split, decided 2026-09-17**: deterministic field population
(anything a file format, a structured API response, or explicit
`loom`-decorator/SDK input can supply) belongs in core CLI/API, since it
must stay reproducible per "SBOM output" in CLAUDE.md. Fuzzy mapping
that core can't do deterministically -- e.g. turning a free-text
"producer" string into a properly-disambiguated SPDX `Person`/
`Organization` -- stays the agent/Skill's job (`sbom-enrich`), not
core's. Every G7 item below is scoped to fit the core/deterministic
side of that split; anything that would need heuristic disambiguation
is explicitly left to the Skill and not listed as a core 1.0 item.

| # | Item | Priority | Impact | Size | Status |
| :-- | :--- | :--- | :--- | :--- | :--- |
| 1 | [Real Windows CI run](#testing--ci) | P0 | High | S-M | Done -- CI added ([PR #220](https://github.com/bact/pitloom/pull/220)), fixed test fixtures it exposed |
| 2 | [Real macOS CI run](#testing--ci) | P0 | High | S | Done -- CI added ([PR #220](https://github.com/bact/pitloom/pull/220)) |
| 3 | [Mechanical G7 wiring: dataset license + `ai_AIPackage.verifiedUsing`](#g7-sbom-for-ai-field-coverage-10-headline) | P0 | High | S | Not started |
| 4 | [Fix stale gap claims in `minimum-elements.md`](#g7-sbom-for-ai-field-coverage-10-headline) | P0 | Medium | S | Done 2026-09-20 |
| 5 | [`--allow-build` timeout](#medium-term) | P0 | High | S | Done (PR #226) |
| 6 | [Model producer + parameter count (structured sources only)](#g7-sbom-for-ai-field-coverage-10-headline) | P1 | High | M | Not started |
| 7 | [`loom` SDK: dataset provenance + model training-properties capture](#g7-sbom-for-ai-field-coverage-10-headline) | P1 | High | M-L | Not started |
| 8 | [Versioning/compatibility policy decision](#versioning-and-compatibility-policy-new-for-10) | P0 | High | S | Needs a decision |

Bumped out of 1.0 by the G7 redefinition (not dropped -- moved back to
their normal roadmap sections, unstarred): `loom fragment sign` + hash
verification, generic multi-candidate field representation, JAX/Orbax
extractor, the merge-policy doc. None are stability- or G7-blocking;
revisit for 1.1.

**Why this order:**

1-2. **CI first, before anything else** -- unchanged rationale, already
   done. See git history for detail if needed.
3-4. **Mechanical G7 wiring, first among the new work** -- both are
   small, code-verified (not doc-guessed), zero design risk: a
   dataclass field already extracted and sitting unused, and a hash
   already computed elsewhere in the same pipeline. Highest
   impact-per-hour of anything on this list. Fixing the stale skill-doc
   claims right after prevents the agent/Skill from re-asking users
   about fields core already covers -- cheap, and directly protects the
   value of the wiring fix above it.
5. **`--allow-build` timeout** stayed in its original slot -- the one
   open correctness gap in shipped 1.0-era code, unrelated to G7 but
   cheap and independent. Done -- see
   [allow-build-timeout.md](../implementation/allow-build-timeout.md).
6-7. **Real extraction work, ordered by size.** Model producer (via
   structured API data, e.g. Hugging Face Hub's own author/org field --
   not free-text parsing) and parameter count (per-format, several
   formats already expose it in their own metadata) are both
   medium-sized and self-contained. The `loom` SDK expansion is larger
   (new decorator/builder surface, see
   [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md))
   and goes last among the code items so 3-6 aren't blocked waiting on
   its design to settle.
8. **Versioning/compatibility policy** moved last in sequence (not in
   priority) -- still needs deciding before the tag, but is a decision,
   not code, so it doesn't compete with the above for implementation
   time; can happen in parallel any time in the month.

### G7 SBOM for AI field coverage (1.0 headline)

Re-verified against current assembly code (2026-09-17): the skill's own
[G7 checklist](../../skills/sbom-enrich/references/minimum-elements.md#g7-sbom-for-ai-2026-additive----apply-only-when-an-ai_aipackage-is-present)
is stale in 4 places (claims "gap" for fields already wired), and most
of the real gaps are pure wiring (a dataclass field already extracted
but never read by the assembler) rather than new extraction work. Only
dataset/model provenance and training-properties need genuinely new
capture, via an expanded `loom` decorator/SDK. Full breakdown, the
core-vs-Skill scope split, and implementation order: see
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md).

Note: that checklist lists `hasDataFile` as "covered", but static detection
is now conditional on `--scan-model-usage` (off by default); update
`minimum-elements.md` together with G7.

### Versioning and compatibility policy (new for 1.0)

Not yet decided -- flagging as a required 1.0 decision, not proposing
an answer. Questions to resolve before the 1.0 tag:

- Does 1.0 commit to CLI-flag/output-format/library-API stability under
  SemVer (breaking changes only at a major version bump), replacing
  CLAUDE.md's current "no backward compat needed yet"?
- If so, which surfaces are covered by that commitment -- CLI flags and
  output shape, the public library API (`generate_project_sbom()` etc.),
  the Hatchling build hook's `[tool.pitloom]` config schema, the GitHub
  Action's inputs, the Skills/plugin surfaces -- and are they all
  covered from 1.0.0, or staggered (e.g. CLI stable at 1.0, library API
  marked experimental until 1.1)?
- Any deliberately breaking cleanup that should land *before* 1.0 while
  compat is still free, rather than waiting for a 2.0? (No specific
  candidate identified in this pass -- worth a deliberate check, not an
  assumption that none exists.)

### Cut from 1.0 (explicitly deferred)

Named here so scope doesn't creep back in mid-month: OSV.dev
vulnerability lookup, CycloneDX assembler and any other output format,
`pixi.lock`/`conda-lock.yml` support, MLflow/W&B Weave/DVC fragment
extractors and SBOM-fragments Phases 2-4, SARIF output, SCITT
integration, PEP 740 attestations, remote source ingestion
(`loom project <url>`), AI model id stability (auto-harvest), the
provenance/enrichment vocabulary revision (blocked on its own taxonomy
decision), internal codename retirement, and the ~25 other open
`enhancement`-labelled GitHub issues not named in the table above. All
stay on the roadmap; none block 1.0.

## Adoption surfaces

Pitloom's other surfaces (library API, CLI, Hatchling build hook, ML
tracking SDK) all assume the consumer already has Pitloom installed or
wired into a build backend. These two extend reach beyond that. See
[adoption-surfaces.md](../implementation/adoption-surfaces.md) for the
full picture.

- [x] **GitHub Action** (composite `action.yml`) -- generate an SBOM in CI,
  for any Python project regardless of build backend. See [github-action.md](../implementation/github-action.md).
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
- [ ] **GitHub Action hardening** (future) -- pip constraints/hash-pinning
  for Pitloom's transitive dependencies (only Pitloom itself is pinned);
  an isolated venv option; lint `scripts/` in CI (only `examples/ src/
  tests/` are); known edge cases: `args` containing a literal ASCII RS or a CR
  inside quotes, quadratic `${PL_ARGS//[[:space:]]/}` on bash 3.2. See
  [github-action.md](../implementation/github-action.md).
- [ ] **GitHub Action silently drops invalid boolean inputs** -- any
  non-empty value other than exactly `true`/`false` (`maybe`, `True`) on the
  tri-state `enrich`, `extract-file-header`, `update-id-registry`,
  `content-type`, `offline`, `use-lockfile`, and on the two-state `pretty`,
  `allow-build`, `no-build-isolation` (case-sensitive `= "true"`, so
  `allow-build: True` silently skips the build), passes no flag and prints
  no warning; `use-lockfile` in model/embed-wheel mode is dropped silently
  too. Violates "no silent deviations".
- [ ] **SARIF output** -- emit a SARIF file as a build artifact for CI
  findings (inline PR annotations, Security-tab view), fed by
  `WARNING:`/`ERROR:` output, OSV.dev results (once built), and license
  conflicts. See [sarif-output.md](sarif-output.md).

## Near-term

**Next up:**
[Generic multi-candidate field representation](#metadata-quality) --
[Non-Hatchling file discovery](#non-hatchling-file-discovery-feature-parity)
below is now closed for every backend, including `uv_build` (via the
generic `--allow-build` build-and-read mechanism, not a dedicated static
rescan -- see below).

**In progress (AI model scanning):** B -- model-candidate type and the
`--allow-build` path fix; C -- deterministic model order; D -- wheel
scanning (`--scan-model-usage` landed first, usage pass off by default). See
[cli-shared-options-ignored.md](cli-shared-options-ignored.md#still-open).

**Suggested sequencing after that** (2026-09-16, not a commitment --
superseded for the next month by [1.0 target](#10-target-2026-10-15)
below, which is the actual commitment for what ships before mid-October):

1. [Generic multi-candidate field representation](#metadata-quality)
   -- now concretely motivated: license (`deps_license.py`), dependency
   version (`deps_installed.py`), and project metadata fields
   (`extract/project/installed.py`, landed via
   [installed-dist-info-source.md](installed-dist-info-source.md)) each
   hand-build their own `ConflictCandidate` list at their own call
   site -- a third, independent instance of the same duplication is
   usually the right time to generalize.
2. [JAX/Orbax model extractor](#extractors) -- design ready (verified
   against real `orbax-checkpoint` output, not docs alone), independent
   of the item above.
3. [OSV.dev vulnerability lookup](#metadata-quality) -- **not** ready to
   hand to an implementer as-is; needed its own design pass first (SPDX3
   mapping, which dependency pool to query, PEP 440-based range
   matching) -- now resolved, see
   [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md#resolving-the-three-open-design-gaps-2026-09-14).
   Explicitly **not** in the 1.0 scope below -- too large to design,
   build, and review in the time remaining alongside everything else.

### Non-Hatchling file discovery (feature parity)

- [x] **`get_wheel_files()` file discovery is not backend-agnostic** --
  closed (2026-09-15): setuptools, Poetry, PDM-backend, and Flit-core
  each have a dedicated static rescan module; `uv_build` (and any other
  backend with no static module, or whose static discovery fails)
  resolves via a new generic, backend-agnostic build-and-read mechanism
  gated behind `--allow-build` (real PEP 517 build, opt-in, no
  `[tool.pitloom]` equivalent -- see [`docs/allow-build.md`](../../docs/allow-build.md)).
  Track B (compiled/native backends: `maturin`, `scikit-build-core`,
  `meson-python`) is already covered by the same mechanism once their
  own toolchain happens to be available -- no further Pitloom code
  needed. See [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md)
  for the full design/history.
- [x] **Unreadable file drops the whole file list silently** -- fixed
  (2026-09-30, #244): warn once, skip that file only. See
  [file-scan-unreadable-file.md](../implementation/file-scan-unreadable-file.md).
- [ ] **Unlistable directory drops its subtree silently at discovery** --
  a `chmod 000` directory is skipped by Hatchling's `safe_walk()` (`os.walk`,
  no `onerror`) before the per-file scan sees any name, so no
  `WARNING:` (found in #244). Check each backend's walk.
- [ ] **Four remaining follow-ups from PR #215's `--allow-build` review**
  -- one consolidation cleanup (a hand-rolled `tool` table walk
  repeated across 6+ modules), one low-priority dev-script dedup, one
  id-registry gap (`--allow-build`-sourced files can't match a
  `loom id generate`-pinned entry, since their `physical_path` is an
  ephemeral temp path -- **partially addressed** 2026-09-15: a separate,
  previously-unguarded AI-model registry lookup in `_ai_package.py` was
  found and fixed, but `_document_files.py`'s own `software_File` lookup
  still needs the harder fix described below), and one precision gap (a
  real static `uv_build` discoverer for `[tool.uv.build-backend]`, to
  stop the Hatchling fallback from over-including or, worse,
  zero-including files for some real packages -- already
  `WARNING:`-flagged, not silent). None block shipped work; each is
  independently fixable. See
  [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md#open-follow-up-tech-debt-from-pr-215s---allow-build-review)
  for full detail on each.

### Build backend improvements

See [build-backend-improvements.md](build-backend-improvements.md).

### PEP 770 / embed-wheel

- [x] **`loom verify-wheel` / `loom validate-wheel`** ([#202](https://github.com/bact/pitloom/pull/202))
  -- structural location check and schema/SHACL content validation for
  a wheel's embedded SBOM, plus `embed-wheel --verify`/`--validate`
  convenience flags and a pre-embed name/version enforcement check for
  `--sbom`. See
  [wheel-verification-commands.md](../implementation/wheel-verification-commands.md).
- [ ] **`embed-wheel`'s wheel-rewrite temp file isn't covered by the
  SIGTERM/SIGHUP/Ctrl-C guard above** -- a signal during
  `_rewrite_wheel_archive()`'s ZIP write (before the `os.replace()`
  swap) leaves a `<stem>.<random>.tmp` non-wheel file in the wheel's own
  directory (the original `.whl` stays intact); a `dist/*` glob like
  `twine upload dist/*` would trip on it. Cheap fix: register the temp
  path as a cleanup on the batch's `TerminationGuard`.
- [ ] **`loom wheel --embed` has no `--sbom-basename`** -- `embed-wheel`
  takes one, so the two embed surfaces can't be pointed at the same
  arcname. Found in the manual CLI checks for PR #226.
- [ ] **Archive member follow-ups** -- name-independent `--allow-build`
  extraction (case/Unicode folding, Windows path rules), archive-level wheel
  operations on `orig_filename`, tar links in sdists. See
  [archive-member-followups.md](archive-member-followups.md).
- [ ] **Re-embedding lists the previous embedded SBOM** -- `embed-wheel`
  on a wheel that already has one describes that old
  `.dist-info/sboms/*` file (with its old hash) in the new SBOM, which
  then overwrites it: a stale self-reference, and not idempotent. The
  target's own SBOM path should be left out of the file list.
  Check `S2` of `scripts/manual_cli_checks`.
- [ ] **`embed-wheel --project-dir <sdist>` runs discovery on the
  archive path** (Hatchling fails on it with a `WARNING:`): read the
  sdist's own listing, as `loom project <sdist>` does, or reject it.
- [ ] **`embed-wheel --project-dir` rejects the project's own enrichment
  fragment** -- `loom enrich --project-dir` mints the model id under the
  directory SBOM's doc uuid, but `embed-wheel` assembles under the wheel's,
  so a registered fragment fails the merge with `ERROR: 1 dangling
  reference(s)`; `loom project` on the same directory merges it fine. Same
  with a plain model name on the pre-#253 code. Identity schemes:
  [sbom-enrichment.md](sbom-enrichment.md). Found reviewing PR #253.
- [ ] **Resolve "now" once per batch in multi-wheel `embed-wheel`** --
  the CLI resolves `CreationMetadata` once per batch but leaves
  `creation_datetime` unset, so each wheel calls `now()` for its own
  `created`: two SBOMs from one command can differ by a second. Leaning:
  read `now` once, only when neither `creation-datetime` nor
  `SOURCE_DATE_EPOCH` is set, on both the CLI and the library
  `file_cache=` path. Still open: `_embed_wheel.py`'s ZIP entry timestamp
  also calls `now()`; should it share the batch's value? Found de-flaking
  PR #230.

### AI model id stability (follow-up to [#178](https://github.com/bact/pitloom/pull/178))

- [ ] **Registry v3: one typed table, content gate chosen at lookup** --
  harvest stops guessing `files` vs `entities` by shape (a hashed
  AIPackage is misfiled). Its own PR, design first, before G7. See [id-registry-v3.md](id-registry-v3.md).

- [ ] **Skill trigger coverage for `loom id generate`/`loom id import`** --
  the skills run both commands now, but no description triggers on them;
  owner skill undecided. See [id-registry-followups.md](id-registry-followups.md).
- [ ] **Deterministic same-model identification for auto-harvest** --
  `ai_AIPackage` stays out of auto-harvest; content-hash matching is an
  open design question. See [ai-model-id-stability.md](ai-model-id-stability.md).
- [ ] **Wheel/sdist targets and src-layout registry file ids** -- path keys
  differ; a `project` harvest aliases the wheel path, `id generate` alone
  does not, and an sdist finds neither. See [id-registry-followups.md](id-registry-followups.md).
- [ ] **Registry harvest rewrites per-document entities; `env`'s root
  package is never looked up.** See [id-registry-followups.md](id-registry-followups.md).
- [ ] **A declared registry inside the package tree never settles** -- the
  registry is itself a hashed file. See [id-registry-followups.md](id-registry-followups.md).

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
  - JAX (Orbax checkpoints) -- higher priority, design ready to
    implement: findings come from installing `orbax-checkpoint` and
    inspecting real output, not docs alone. See
    [jax-orbax-support.md](jax-orbax-support.md)
  - TensorFlow SavedModel and TensorFlow Lite
  - Scikit-learn (pickle/joblib; no single standard format -- complex)
  - See [model-metadata-extraction.md](model-metadata-extraction.md)
    for the full format table
- [ ] **MLflow run extractor** (`pitloom.extract.mlflow`,
  `loom.from_mlflow_run()`) -- reads a completed/active MLflow run's
  tags/params/metrics into an SPDX 3 AI BOM fragment, keyed against the
  [STAV](https://github.com/bact/stav) vocabulary with a fallback for
  non-STAV tag names; eliminates double-instrumenting a training script
  already using MLflow tracking. Fully designed, not yet built -- see
  [mlflow-extractor.md](mlflow-extractor.md). W&B Weave and DVC
  extractors are the same shape of gap; tracked together with this one
  under [SBOM fragments](#sbom-fragments-merge-system) below since all
  three feed the fragment-merge pipeline.
- [x] **Dataset-to-model relationship linking** -- `trainedOn`/`testedOn`
  `Relationship`s emitted natively, falling back to `RelationshipType.other`
  for the three relationship types SPDX 3.0.1 itself lacks. See
  [ai-dataset-linking.md](../implementation/ai-dataset-linking.md).
- [x] **Croissant dataset size calculation** -- `dataset_DatasetSize`
  extracted dynamically by summing `cr:totalItems` across `cr:recordSet`
  entries (or top-level `cr:totalItems`), with graceful `None` fallback.

### SBOM fragments (merge system)

Core merge mechanism, `FragmentConfig`, and `loom fragment list` have
shipped; several follow-ups (fragment signing/SHA-256 enforcement,
skill trigger coverage, SDK ergonomics, new extractors,
compliance/interop, element-level traceability) remain open. See
[open-items.md](sbom-fragments/open-items.md).

- [ ] **Non-directory targets silently ignore configured fragments** --
  `loom model` (and `generate` on a model file), Hugging Face, `wheel`,
  `env` and sdist runs never call `merge_fragments()`, so fragments in
  `--config`/project config are dropped with no `WARNING:` and exit 0
  (violates "no silent deviations"). Found reviewing the `sbom-enrich`
  skill; the skill now says so. Record only.
- [ ] **`env` drops an unmet requirement silently** -- a dependency
  pipdeptree reports as not installed (`installed_version: "?"`) loses
  its `dependsOn` edge with no trace, so the deployed SBOM says nothing
  about the unmet requirement. Found reviewing PR #236. Record only.
- [ ] **`env`: two installs sharing one pipdeptree `key` collide** --
  `build_deployed` keys its id map by `key`, so a second install of the
  same distribution (e.g. an editable copy next to a site-packages copy)
  overwrites the first and all edges go to one element. Not seen from
  pipdeptree yet; found reviewing PR #236. Record only.

### Metadata quality

See [metadata-quality.md](metadata-quality.md).

### Remote source ingestion

- [ ] **Remote repository and forge ingestion (`loom project <url>`)** --
  generate SBOMs directly from remote git repositories/forges (GitHub, GitLab)
  or remote release archives, capturing upstream VCS provenance (commit SHA,
  tag, repo URL) and delegating parsing to `extract.project` and `extract.lock`.
  See [remote-source-ingestion.md](remote-source-ingestion.md).

### Testing / CI

See [testing-ci-followups.md](testing-ci-followups.md).

- [ ] **Delete `_project_doc_identity` and test `enrich_model` directly** --
  `assemble/_model_generator.py`'s `_project_doc_identity()` has no
  production caller (`enrich_model()` calls `_doc_identity_of()`); only
  `tests/assemble/test_model_generator_doc_identity.py` and
  `test_explicit_config_edges.py` use it, as an oracle.

### Diagnostics / logging

See [diagnostics-logging-followups.md](diagnostics-logging-followups.md).

### Internal codenames

- [ ] **Retire the whole letter-number use-case codename taxonomy**
  (G1-G7, A1-A2, E1-E2, P1, N1-N6, and more -- 500+ occurrences as of
  2026-09-14), not just "G2" -- meaningful only against
  `use-case-catalog.md`'s own numbering, meaningless to a future reader
  in isolation. Sizeable, mechanical-but-not-trivial; an opportunistic
  path (fold into whichever `working-docs/*.md` a routine reorg already
  touches) exists alongside a dedicated-PR path. See
  [codename-retirement.md](codename-retirement.md).

## Medium-term

- [x] **CHANGELOG.md split** -- done 2026-09-30: entries condensed and merged;
  0.19.0+ stay in `CHANGELOG.md`, older releases in `CHANGELOG-archive.md`.
- [ ] `roadmap.md` itself is at the 800-line hard limit: move more detailed
  bullets into design/implementation docs.
- [ ] **CycloneDX assembler** -- add a CycloneDX serializer consuming the
  existing `DocumentModel`; no changes to extractors required.
- [ ] **AIDOC / TechOps renderer** -- additional output format consuming
  `DocumentModel`.
- [ ] **Build log extraction** -- capture compiled dependencies, linker flags,
  and bundled libraries from build output logs.
- [ ] **VEX (CSAF/OpenVEX) generation** -- consumes the OSV.dev lookup
  above (once it exists) to classify a component as affected/
  not_affected/fixed/under_investigation, rather than just listing raw
  CVE hits. Depends on the OSV enrichment item under Near-term /
  Metadata quality landing first. Open question: CSAF v2.0
  (ISO/IEC 20153:2025, OASIS-standardized, heavier, product-tree
  formalism, vendor-advisory-oriented) vs. OpenVEX (lighter JSON, the
  more common choice for tool-generated, non-vendor VEX) as the output
  format -- see
  [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md#relationship-to-csafvex).

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
- [ ] **Performance optimization** -- Rust backend for large-project log
  parsing; parallel file hashing. See
  [performance-optimizations.md](performance-optimizations.md#rust-backend--parallel-hashing).
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
