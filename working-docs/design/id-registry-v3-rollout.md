---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry v3: rollout (surfaces, messages, commits, verification)

See also: [id-registry-v3.md](id-registry-v3.md) (the design: decisions
D1-D11, invariants I1-I7, API, format, lookup table, loom datasets,
namespace) -- read it first; section numbers continue from it.

## 10. Surface impact

Every surface reads or writes the registry through `IdRegistry`,
`IdRegistrySession` and `_sync_registry`. None touches the JSON directly,
so the format change stays inside `id_registry/`.

| Surface | Reads | Writes (harvest) | v3 changes |
| --- | --- | --- | --- |
| `project` (directory and sdist), `wheel`, `env`, `generate` | yes | yes (not ai/dataset) | caller keys; `added N new id(s)` |
| `model` (local) | yes (stem) | no | caller keys |
| `model` on Hugging Face | ignored (WARNING) | no | none |
| `enrich`, `embed-wheel`, `wheel --embed`, Hatchling hook | yes | no | caller keys |
| `embed-wheel --sbom` (external SBOM) | no | no | none |
| `id generate` | - | yes | `register`; model sha256 (D3); `--namespace` (D8); excludes the registry file (D7); summary line |
| `id import` | - | yes | harvest over one table; summary line |
| Library API (`generate_*_sbom`, `embed_wheel_sbom`) | same as the CLI | same as the CLI | none beyond the callers |
| loom SDK (`loom.Run(id_registry=...)`) | yes | no | section 8; path base (D9) |
| GitHub Action | via CLI | via CLI | none in `action.yml`; `docs/github-action.md:126-235` commits a registry file, so note the format bump |
| Skills | - | - | `sbom-generate/references/id-registry.md` (what is pinned, log lines, datasets) |
| `docs/` | - | - | `docs/cli.md:335-416`; `docs/python-api.md` (loom datasets); `docs/api.md:84-100` lists `FileEntry`/`EntityEntry`, a public API change |
| `examples/sentimentdemo-aibom` | loom + `id generate` (`scripts/run_pipeline.sh`) | commits a v2 `loom-id-registry.json` | regenerate with its own workflow (never by hand); dataset ids change (D5) |

Implementers must re-derive this table from the code on the base branch,
then check each row with a test (section 12).

`tests/id_registry/test_surfaces.py` already has completeness guards to
extend rather than duplicate:

- every CLI subcommand that takes `--id-registry` has a runner (:238);
- every public callable with an `id_registry` parameter has a runner
  (:262);
- the inert rows (:291);
- the `action.yml` inputs (:302).

Only `_sync_registry` (`_generators_shared.py:51`) and `id
generate`/`import` write to the registry.

## 11. Messages

Keep the `ID registry: ...` sub-prefix, and change only what the
redesign changes:

- **Run harvest:** `INFO: ID registry: added N new id(s) to <path>` (D4).
  `updated stale entries in <path>` stays.
- **`id generate` / `id import` summaries** (`cli/id.py:313`, `:357`),
  both on stdout, not tagged log lines:
  - `pitloom id: wrote N id(s) to <path>`;
  - `pitloom id: imported into <path> (N id(s))`.
- **loom misses:**
  - `loom: registry entry for %r exists but its SHA-256 no longer matches`
    and `... not found in registry` stay. They are now keyed by type.
  - `has_entity_named`'s "exists but under a different type" branch
    becomes `has_name`.
- **New:**
  - the dataset ceiling WARNING (8.2);
  - the "outside the registry project root" WARNING (8.3).

  Match the wording of an existing sibling message before inventing any.

grep `skills/` and `docs/` for every changed string in the same commit.

## 12. Commits (own PR)

Each commit passes the full suite and every linter on its own, so it can
be bisected.

1. **Share one sha256 extractor.**
   - `sha256_of()` in `export/spdx3_json.py`, used by
     `_fragments_unify` and the registry.
   - One parametrised test: none, a non-sha256 algorithm, an empty value
     then the next one, uppercase.
   - The stopped G7 partial has this, and it applies cleanly: take only
     its `sha256_of` part, not `_is_file_entry`.
2. **Exclude the declared registry file from scans (D7).** Skip this
   commit if P13 has already merged.
3. **Registry v3: one typed table.**
   - `_types`, `_registry`, `_harvest` and `_ambiguous`: the section 4
     invariants, the section 5 API and the section 6 format.
   - `file_id` and `entity_id` stay as thin wrappers over `lookup_id`,
     so callers compile.
   - Tests: load/save round trip, every `load()` failure path, and I2,
     I4, I5, I7.
4. **Typed candidate keys at every caller.**
   - Migrate the section 7 rows and remove the wrappers.
   - D3 and D8 in `id generate`; new summary lines (D4).
5. **Registry drift guards.**
   - One table test over section 7: every caller's type is a type
     harvest writes back.
   - D2's typed-id invariant over every element in our namespace, on
     every surface's output.
   - A round trip for each section 7 row, register or harvest then
     lookup. Include the src-layout alias and a hashed AIPackage through
     `id import`.
   - The cross-surface runners in `tests/id_registry/surfaces_shared.py`
     (`test_surfaces_same_ids.py`).
6. **Merge by id requires the same type (D11).**
   - `_fragments_unify._merge_fragment_set`.
   - Regression test: a DatasetPackage and a File sharing one id. It
     fails on main, where the DatasetPackage is folded in silently.
7. **Loom datasets as a package plus its files (D5, D6, D9).**
   - Section 8: the single-file and directory cases, the new ceiling key
     (cascade, `_matrix_plan.py`, inert table), `Hash.comment`, the path
     base and the `path_probe` probing.
   - Update the tests that encode today's shared `File-N` dataset id:
     `tests/core/test_loom_registry.py:94`,
     `tests/core/test_fragments_misc.py:87-90` and
     `tests/id_registry/shared.py:52`.

8. **Update the examples to registry v3 (user).**
   - Regenerate `examples/sentimentdemo-aibom/loom-id-registry.json`
     through its own workflow, `scripts/run_pipeline.sh` (the `id generate
     data src --entity sentimentdemo` stages). Never edit it by hand.
   - Check that the result has `"version": 3` and a `project_root`, and
     that its datasets are DatasetPackages with their own ids that
     `contains` their files (D5).
   - Update the example's prose to the new behaviour: `README.md`, the
     comments in `.gitignore` and `run_pipeline.sh`, and the `loom.run`
     calls in `train.py`/`preprocess.py`/`evaluate.py` if their comments
     describe ids.
   - Re-run the whole pipeline once to confirm that every stage loads the
     v3 registry.
   - Nothing in the tests or CI loads this example (checked 2026-09-30),
     so commits 3 to 7 stay green without it. Still, it ships in this PR.
   - Grep `examples/` for any other registry file or v2-shaped JSON
     before closing the commit.
9. **Docs.**
   - Fix two claims that are already wrong today:
     - `skills/sbom-generate/references/id-registry.md:28-30` says a
       directory dataset can be pinned with `id generate <dir>`. It
       cannot: `add_dataset("data")` never looks up the registry.
     - `skills/sbom-enrich/references/minimum-elements.md:131` says a
       dataset has no hash. Loom datasets do.
   - Also update `README.md:385-460`, which covers the registry and
     "looked up by file path and hash", and `docs/python-api.md:338-434`.
   - Move this file to `implementation/` and update
     `id-registry-autosync.md`.
   - Close the matching entries in `id-registry-followups.md` and the
     roadmap bullet.
   - Update the skills reference (with a fresh-eyes full read),
     `docs/cli.md` and `docs/python-api.md`.
   - `docs/api.md:84-100`: replace `FileEntry`/`EntityEntry` with
     `RegistryEntry`.
   - `docs/github-action.md`: note that a committed v2 registry must be
     regenerated.
   - CHANGELOG: registry format version 3 (Changed, breaking; this
     supersedes the v2 line at `CHANGELOG.md:81`), and loom datasets as
     packages (Changed).

## 13. Verification

- **Regressions, each failing on main:**
  - a hashed AIPackage survives `id import` and later lookup;
  - a loom dataset keeps its id across two runs;
  - a File and a DatasetPackage at one path get two different ids (D2);
  - two elements sharing a file path are reported as ambiguous (I5).
  - a fragment element sharing an id with an element of another type is
    re-minted with one WARNING and not folded in (D11).
- **Boundary tests:**
  - the entry has no sha256 but the lookup is gated;
  - sha256 case differences;
  - `null` or a non-string sha256 in the file;
  - an unknown entry key;
  - a duplicate after canonicalisation;
  - an empty directory, a directory over the ceiling, and an unreadable
    member;
  - relpath ordering and a renamed file changing the root;
  - a path outside the project root.
- **Mutation targets (run in an rsync copy):**
  - the gate comparison;
  - the candidate order;
  - each of the alias condition's three conjuncts;
  - the ambiguity count including files;
  - omitting a missing sha256 versus writing `null`;
  - the leaf separator and the relpath sort;
  - the unreadable-member abort;
  - the ceiling comparison (`>` versus `>=`).
- **Manual CLI checks:**
  - the registry round trip (check 9) and a declared-but-invalid registry
    (check 14);
  - a v2 file fails the same way on every surface;
  - determinism over two runs with a committed registry.
- **Validation:** spdx3-validate each surface's output with a loom
  dataset, via `tests/_network.py` (`network` marker).
- **Size:** keep every file at 500 lines or fewer.
  - `_harvest.py` has 291 lines and `_registry.py` has 297. Split the
    load/save format code into `_format.py` if either would pass about
    450.
  - About 60 test files touch the registry. Most go through the API and
    need no change.
- **Tests that must change:**
  - These depend on the on-disk JSON shape:
    - `tests/id_registry/test_registry.py:75-277`, including the
      old-version test, which becomes "v2 rejected";
    - `test_registry_harvest.py:258-270` (`_write_registry_entities`);
    - `tests/cli/test_cli_id_path_validation.py:185-260`, which reads
      `json["files"]`.
  - These build the in-memory shape directly (`IdRegistry(files=,
    entities=)`, `.files`/`.entities`):
    - `test_loom_registry.py`, `test_loom_caller.py`;
    - `test_assemble_ai_metadata.py`, `test_explicit_config_edges.py`,
      `test_generator_no_implicit_config.py:78-90`;
    - `test_generator_registry_sync_claim.py:249-380`;
    - `test_fragments_misc.py:75-162`, `test_wheel_pipeline_e2e.py`;
    - `tests/core/conftest.py:124-130`.
  - Migrate all of these in commits 3 and 4. Add a small test helper that
    builds a v3 registry, so each test doesn't hand-build one.
- **Manual checks and the matrix:** none assert the JSON keys. Checks 12
  and S4 compare raw bytes, and the matrix masks the UUID4 namespace
  (`_matrix_run.py:145-155`), so they hold across the format change. This
  also depends on D8 keeping UUID4 (decided).

## 14. Out of scope

- Using the model's sha256 as a gate, and auto-harvesting AIPackages.
  See [ai-model-id-stability.md](ai-model-id-stability.md).
- Per-member `software_File`s for a directory dataset (a later opt-in,
  D6).
- The sdist/wheel alias gap for a registry seeded only by `id generate`.
  See [id-registry-followups.md](id-registry-followups.md).
- Per-document entries (Agents, Tools, Licences) rewritten on harvest.
  The same follow-up doc covers them.
- logfmt quoting of `KEY=VALUE` output (separate PR P1).
- Loom fallback ids that change every run (problem 11): G7 #7.
- **Found by the scan, not fixed here:**
  - `_types._is_eligible_file` checks `_IGNORED_DIR_NAMES` against the
    *absolute* path's parts, so a project under `/x/build/...` is skipped
    entirely.
    - It is a small real bug in the function commit 2 touches.
    - Fold it into commit 2 only with the user's approval. Otherwise add
      it to [id-registry-followups.md](id-registry-followups.md).
  - A stale comment in `tests/core/test_models.py:206-209` calls the
    distribution path the Merkle "tree-combination input". It is only the
    sort key.
  - There is no direct unit test of `_build_merkle_tree`. Commit 7 adds
    one: empty list is the caller's job, one leaf, an odd count, and
    determinism.
- Any v2 migration (D10).
