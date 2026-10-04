---
Created: 2026-09-30
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry v3: rollout (surfaces, messages, commits, verification)

See also: [id-registry-v3.md](id-registry-v3.md) (the design: decisions
D1-D16, invariants I1-I7, API, format, lookup table, loom datasets and
models, namespace) -- read it first; section numbers continue from it;
[id-registry-followups.md](id-registry-followups.md) (what v3 leaves
open).

**Status: plan, not built.** Anchors were checked on `main` at `4c052dd`;
re-verify each on the post-#263 base.

Registry v3 is its own PR, independent of G7. It is cross-cutting and
touches every surface. Order (user): PR D (step 10, #251, step 9 = #263)
-> small follow-up PRs -> **this PR** -> surface-parity/config/docs sweep
-> 0.20.0 -> G7. Base the branch on a `main` that already has:

- **D:** its fixture carries `demo/tiny.safetensors` and `demo/load.py`,
  and usage `hasDataFile` edges are off by default.
- **#251 / DQ-2:** wheel member names are normalised, and those names
  become file keys.
- **The IRI-encoding change:** `core/iri.doc_namespace` and
  `iri_segment`, which `IdRegistry.new` and `generate_spdx_id` use.
- **#263 (wheel AI model scan):** wheel and standalone-embed AIPackages
  now reach the registry through `resolve_ai_model_entity_hits`, and
  `core/model_extract_limit.require_max_model_extract_bytes` is the
  validator the new ceiling key generalises (design 8.2).

## 10. Surface impact

Every surface reads or writes the registry through `IdRegistry`,
`IdRegistrySession` and `persist_registry`. None touches the JSON
directly, so the format change stays inside `id_registry/`.

| Surface | Reads | Writes | v3 changes |
| --- | --- | --- | --- |
| `project` (directory and sdist), `wheel`, `env`, `generate` | yes | harvest (not datasets, not unhashed AIPackages) | caller keys; hashed AIPackages harvested (D15); `added N new id(s)`; in-tree registry excluded (D7) |
| `model` (local) | yes (stem) | no | caller keys |
| `model` on Hugging Face | ignored (WARNING) | no | none |
| `enrich`, `embed-wheel`, `wheel --embed`, Hatchling hook | yes | no | caller keys; in-tree exclusion threaded (D7) |
| `embed-wheel --sbom` (external SBOM) | no | no | none |
| `id generate` | - | yes | `register`; model sha256 (D3); `--namespace` (D8); `exclude` (D7); `project_root` (D9); summary line |
| `id import` | - | yes | harvest over one table; `project_root` from cwd; summary line |
| Library API (`generate_*_sbom`, `embed_wheel_sbom`, `enrich_model`) | same as the CLI | same as the CLI | `IdRegistry.new(namespace=)` |
| loom SDK (`loom.Run`) | yes: datasets, files, script; the model at `finalize()`, gated by the `path=` sha | **yes, new:** `(ai_AIPackage, name, sha256)` on a gated miss, saved once after the fragment | section 8; `pitloom_config=` (D14); `path=` (D13) |
| GitHub Action | via CLI | via CLI | none in `action.yml`; `docs/github-action.md:126-234` commits a registry file, so note the format bump |
| Skills | - | - | `sbom-generate/references/id-registry.md`; triggers for id management (commit 9) |
| `docs/` | - | - | `docs/cli.md:335-416`; `docs/python-api.md`; `docs/configuration.md`; `docs/api.md:84-100` lists `FileEntry`/`EntityEntry` (a public API change) |
| `examples/sentimentdemo-aibom` | loom + `id generate` (`scripts/run_pipeline.sh`) | commits a v2 `loom-id-registry.json` | regenerate with its own workflow (commit 8) |

Implementers re-derive this table from the code on the base branch, then
check each row with a test (section 13).

`tests/id_registry/test_surfaces.py` already has completeness guards to
extend rather than duplicate: every CLI subcommand that takes
`--id-registry` has a runner (:238); every public callable with an
`id_registry` parameter has a runner (:262); the inert rows (:291); the
`action.yml` inputs (:302).

D10 needs no per-surface code: every surface already turns the load
`ValueError` into one message (CLI `ERROR:` and exit 1; `id` commands the
same; the hook `ERROR:` and a failed build; the library a `ValueError`;
`loom.Run` a `ValueError` at `__enter__`, nothing written).

## 11. Messages

Keep the `ID registry: ...` and `loom: ...` sub-prefixes, change only what
the redesign changes, and match an existing sibling's wording before
inventing any. grep `skills/` and `docs/` for every changed string in the
same commit.

- **Harvest and loom save** (`persist_registry`): `INFO: ID registry:
  added N new id(s) to <path>` (D4). `updated stale entries in <path>`,
  `no file path resolved; skipping auto-update.` and `failed to save`
  stay.
- **`id generate` / `id import` output** (`cli/id.py`
  `_report_registry_written()`): stdout `PITLOOM_ID_REGISTRY_PATH=<path>`;
  the count is `INFO: ID registry: holds N file(s) and M entit(y/ies)`,
  becoming `holds N id(s)`, N = `id_count()`.
- **Kept:** `ID registry: content changed for %s; minting a new spdxId
  (old: %s).` (now also for a model retrain); loom's `registry entry for
  %r exists but its SHA-256 no longer matches ...`, `... exists but under
  a different type ...` (via `has_name`) and `%s %r not found in registry
  ...`, emitted by one shared `warn_registry_miss` helper, now keyed by
  type.
- **New WARNINGs:**
  - `ID registry: <path> is inside the project's file set; left out of
    the SBOM's files and Merkle root` (D7, one shared place, so every
    surface gets it identically);
  - `loom: file %r is outside the ID registry's project root %s; minting
    a new spdxId` (8.3);
  - `FILE=<p>: <n> bytes exceeds the <max>-byte max-dataset-hash-bytes
    ceiling; dataset hash omitted` (and `DIR=` for a directory; a file
    that grows mid-read says `read more than <max> bytes, over`),
    mirroring `scanner.py`'s two-form ceiling sentence (8.2);
  - `loom: model %r has no path=; not hashed, looked up by name only`
    (8.4, only with a registry loaded);
  - `loom: model %r: %s is not a file at exit; not hashed, looked up by
    name only` (8.4);
  - `Merge: %s %r shares spdxId %s with a %s; keeping both, it gets new
    id %s` (D11).
- **New ERRORs:** the D10 version message (section 6); `ID registry file
  <path>: namespace <old> is not --namespace <new>; delete it to change
  the namespace`; `id generate` into a registry whose project root is not
  `--project-dir`.

## 12. Commits (own PR)

Each commit passes the full suite and every linter (`examples/ src/
tests/`) on its own, so it can be bisected.

0. **Docs only: record the decisions** in these design files. Done
   2026-09-30.
1. **Share one sha256 extractor.** `sha256_of()` in
   `export/spdx3_json.py` (lowercased; used by `_fragments_unify` and the
   registry). One parametrised test (none, a non-sha256 algorithm, an
   empty value then the next, uppercase). Effect: merge-by-hash now
   unifies an uppercase and a lowercase hash of the same bytes.
2. **Exclude the declared registry from scans (D7) and fix
   `_is_eligible_file`** (approved): it matches ignored names against the
   *absolute* path's parts, so a project under `/x/build/...` is skipped
   entirely; match the project-relative parts instead. New
   `core/walk_rules.py` (`IGNORED_DIR_NAMES`, `same_path` with realpath on
   both sides: the CLI keeps the registry path lexical while the project
   dir is resolved, and macOS `/tmp` is `/private/tmp`). Thread
   `exclude_path` through every `get_wheel_files` caller that has a
   registry (generator, hook, `_doc_identity_of`, embed, and the embed
   discovery cache key) so the project SBOM and an enrich fragment
   compute the same Merkle root. Skip the exclusion part if P13 has merged
   on its own.
3. **Registry v3: one typed table.** `_types`, `_registry`, new
   `_format`, `_harvest`, `_ambiguous`, `_session`: section 4 invariants,
   section 5 API, section 6 format, D10. D4's summary and log lines land
   here (commit 3 removes the attributes they read). `file_id`/`entity_id`
   stay as thin wrappers over `lookup_id` so callers compile. A test
   helper `tests/registry_helpers.make_registry(...)` replaces
   hand-built registries. Tests: round trip, every `load()` failure
   (including the v2 file on every surface), I2-I5, I7, the `register`
   table row by row, the `harvest` return.
4. **Typed candidate keys at every caller.** Migrate the section 7 rows,
   remove the wrappers and the `*_ENTITY_TYPE` aliases, replace the type
   literals with constants. D3 (the model sha in `generate`) and D8
   (`--namespace`, a `_matrix_plan.py` entry). The loom dataset keeps its
   v2 behaviour until commit 7.
5. **Registry drift guards.** Every lookup type is a type harvest writes
   back (spy on `lookup` across project, wheel-with-model, model and loom
   runs); D2's typed-id invariant on every surface's output; a round trip
   per section 7 row, including the src-layout alias and a hashed
   AIPackage through `id import`; manual check 14 gains a `v2` label.
6. **Merge by id requires the same type (D11).**
   `_fragments_unify._merge_fragment_set`; the new id avoids the base's
   and the current fragment's ids; the element is renamed before it is
   registered and not added to `remap` (references are linked objects);
   hash unification still applies after. Regression: a DatasetPackage and
   a File sharing one id.
7. **Loom datasets as a package plus its files (D5, D6, D9) and the
   ceiling key.** New `core/dataset_hash.py` (digest with a byte budget,
   walk, root; no loom or registry knowledge) and `_loom_dataset.py`
   (added to `_SKIPPED_LOOM_FILENAMES`, or caller provenance names it);
   `core.models.merkle_root`; `registry_key_for_path`;
   `loom.Run(pitloom_config=)` (D14); the config key with its generalised
   validator; `docs/configuration.md` rows (the new key; `id-registry`'s
   "loom.Run never reads any `[tool.pitloom]` config" sentence becomes
   "reads only an explicit `pitloom_config=`"). New manual check 16 (ids
   stable across runs and from a subdirectory, a `contains` edge, a stable
   directory root).
7b. **Deferred model resolution in loom (D13, D15).** New
   `_loom_model.py` (also in `_SKIPPED_LOOM_FILENAMES`); `path=` on
   `set_model`/`use_model`; `persist_registry` moved out of
   `_generators_shared.py`; `_harvestable` admits hashed AIPackages. New
   manual check 17 (train/eval scripts share one id; a retrain re-mints
   with one INFO; a raising script leaves the registry unchanged). Must
   land before commit 8, which uses `path=`.
8. **The example to registry v3.** Regenerate
   `examples/sentimentdemo-aibom/loom-id-registry.json` only through
   `scripts/run_pipeline.sh`, in a scratch copy (delete the v2 file first,
   per D10; never hand-edit). In the script: `--namespace` with the
   current namespace (smaller diff), `-e <path>:dataset_DatasetPackage`
   for the four datasets, and drop `--entity sentimentdemo`: `train.py`
   and `evaluate.py` pass `path=MODEL_PATH`, so loom records the model at
   stage 2 and reuses it at stage 3. Check: `"version": 3`,
   `"project_root": "."`, one AIPackage id across both fragments and the
   wheel SBOM, each dataset package `contains` its file, no `untracked` or
   `has no path=` WARNING, and a second pipeline run leaves the registry
   bytes unchanged (or, if training is not deterministic, one `content
   changed` INFO; record which). Update the example's prose and grep
   `examples/` for any other v2-shaped JSON. Nothing in the tests or CI
   loads this example, but it ships in this PR.
9. **Docs, skills, CHANGELOG.**
   - Fix claims already wrong today:
     `skills/sbom-generate/references/id-registry.md:28-31` (a dataset
     directory cannot be pinned with `id generate <dir>`; v3 pins it by
     `-e NAME:dataset_DatasetPackage`),
     `skills/sbom-enrich/references/minimum-elements.md:131` (loom
     datasets do have a hash), `README.md:415` ("looked up by file path
     and hash").
   - `docs/cli.md` (format, `project_root`, datasets, `--namespace`; the
     file is already long, add little), `docs/python-api.md` (datasets,
     `path=`, `pitloom_config=`, ignored names in dataset directories),
     `docs/api.md` (`RegistryEntry`), `docs/github-action.md` (a committed
     v2 registry must be regenerated).
   - Skills (user decision): when the user asks to pin ids, the agent runs
     `loom id generate`/`import` itself and reports what it ran; the
     "never pass a registry the user did not name" rule stays for unasked
     runs. Add id-management triggers to `sbom-generate`'s `description`
     (budget: 951 of 1024 chars on `main`; re-measure after #263). A
     fresh-eyes full read of `id-registry.md` against the code.
   - `working-docs/`: move both files to `implementation/` as the record
     of what was built, keeping the split (folded together they would
     pass the 800-line hard limit), and add what changed during the
     build; point `implementation/id-registry-autosync.md` at them; close
     the resolved roadmap bullet and the followups entries v3 resolves.
   - CHANGELOG: fold the format change into the v2 bullet
     (`[#234], [#235]`); new Changed bullets for loom datasets and loom
     `path=`; one Fixed bullet (hashed AI model
     survives `id import`, in-tree registry settles, `id generate` under a
     `build/` ancestor, merge keeps different-type same-id elements
     apart). Needs the PR number first.

## 13. Verification

- **Regressions, each failing on `main`** (reproduced on `4c052dd`):
  - a hashed AIPackage survives `id import` and a later typed lookup;
  - two elements sharing a file path are ambiguous (I5);
  - a File and a DatasetPackage at one path get two ids (D2);
  - a loom single-file dataset is a package with its own id that
    `contains` the File; a directory dataset gets a root and comment;
  - a loom dataset path from a subdirectory (`../data/t.txt`) hits the
    registry (D9);
  - a fragment element sharing an id with an element of another type is
    re-minted with one WARNING and not folded in (D11);
  - a declared registry inside the package tree settles (run 2 == run 3,
    SBOM and registry bytes) with one WARNING per run;
  - `id generate` indexes a project under a `build/` ancestor;
  - `id generate` records the model sha256; a retrained model gets a new
    id.
- **Boundary tests:** a gated lookup on a sha-less entry; sha256 case;
  `null`/`""`/non-string sha256 in the file; an unknown entry or
  top-level key; a duplicate after canonicalisation; every `project_root`
  rejection and `..`; an empty directory; `max_bytes == total` (hashes)
  and one byte over; a file growing mid-read; an unreadable member and an
  unlistable subdirectory (no root); a FIFO (no block); a symlink loop; a
  renamed file changing the root; a path outside the project root; a
  model file written after `set_model`; a relative `path=` followed by a
  `chdir`; a raising block; `update-id-registry = false` in
  `pitloom_config`; an in-memory registry with no path; two interleaved
  runs sharing one registry file (both entries survive).
- **Mutation targets** (in an rsync copy, pytest from inside it, stale
  `.pyc` removed): the gate comparison; the candidate order; each alias
  conjunct; the ambiguity count including files; `null` versus omission;
  each `register` row; `new_ids` counting keys; the leaf separator and
  the relpath sort; the abort on an unreadable member; the ceiling `>`
  versus `>=`; `onerror` dropped; `exclude` dropped; the per-run file
  cache; a shared `Hash` object; resolving the model at declaration;
  dropping the model gate; hashing on the exception path; saving the
  registry before the fragment; `same_path` -> `==`; the embed cache key;
  D11's `is` -> `is not`.
- **Manual CLI checks:** the registry round trip (check 9); a
  declared-but-invalid registry, now with `v2` (check 14); determinism
  over two runs with a committed registry (checks 12 and S4 compare raw
  bytes and the matrix masks the UUID4 namespace, so they hold across the
  format change); new checks 16 and 17. Run the whole runner after
  commits 3, 4, 7 and 7b.
- **Validation:** spdx3-validate each surface's output with a loom
  dataset, via `tests/_network.py` (`network` marker).
- **Size:** every file at 500 lines or fewer. Split `_format.py` out of
  `_registry.py` (303 lines); `cli/id.py` (453) moves its config-slot
  helpers to `cli/_id_target.py` if it passes about 480;
  `tests/core/test_loom_registry.py` (514) sheds its script-file tests.
  About 60 test files touch the registry; most go through the API.

**Traps** worth naming before coding:

- `_element_key`'s argument order flips; call it with keywords and keep
  the PEP 503 test that kills a swap.
- realpath on both sides for `project_root`, `same_path` and
  `registry_key_for_path`; `.as_posix()` on Windows `relpath`, which also
  raises across drives (let `id generate`/`import` report it as one
  `ERROR:`).
- Never share one `spdx3.Hash` object between two elements.
- Do not rename `_build_merkle_tree`: a test monkeypatches it and
  `_models_wheel.py` imports it lazily so the patch works.
- The "outside the root" WARNING is per path per run; cache it on the run.
- New import edges (`id_registry` -> `export.spdx3_json`,
  `_fragments_unify` -> `id_registry`, `core.dataset_hash` ->
  `core.models`) must pass `tests/test_import_order.py` in both modes.

## 14. Out of scope

- Gating the project, wheel, `loom model` and embed AIPackage lookups by
  sha256 (D16; with G7 #3).
- Per-member `software_File`s for a directory dataset (a later opt-in,
  D6).
- The sdist/wheel alias gap for a registry seeded only by `id generate`,
  and per-document entries (Agents, Tools, Licences) rewritten on
  harvest. See [id-registry-followups.md](id-registry-followups.md).
- logfmt quoting of `KEY=VALUE` output (separate PR P1).
- Loom fallback ids that change every run (problem 11): G7 #7.
- Any v2 migration (D10).
- Found by the scan and fixed in passing: a stale comment in
  `tests/core/test_models.py:227` calls the distribution path the Merkle
  "tree-combination input" (it is only the sort key); there is no direct
  unit test of `_build_merkle_tree` (commit 7 adds one: empty is the
  caller's job, one leaf, an odd count, determinism).
