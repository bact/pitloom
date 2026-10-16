---
Created: 2026-10-16
Last-Modified: 2026-10-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# ID registry path keys: open follow-ups

See also: [id-registry-followups.md](id-registry-followups.md) (the main
list), [id-registry-followups-v3-review.md](id-registry-followups-v3-review.md),
[id-registry-path-keys.md](../implementation/id-registry-path-keys.md) (what
was built; K-numbers and P-numbers refer to it and to
[id-registry-path-keys-decisions.md](../implementation/id-registry-path-keys-decisions.md)),
[roadmap.md](roadmap.md).

Left open by the path-key PR (2026-10-16). Working notes, not a promise.

- **Layouts other than `src/` and `lib/`** (`python/`, `packages/`) get no
  alias: a wheel-only run mints its own ids for them. Add a `[tool.pitloom]`
  list only if a user needs it (`keys.LAYOUT_ROOTS`).
- **`id import` of an sdist SBOM keys by member name**, including the
  `name-version/` top directory (`id_registry/import_keys.py`).
- **`id import` from a root not containing the project** keys a model by its
  SBOM file name (no same-hash `software_File` found below the root).
- **An in-root symlinked model** is keyed by its own location (`path_key`
  never follows an in-root symlink); a project run resolves the link, so the
  two surfaces can disagree.
- **`add_output_dataset(input_datasets=)`**: matches the spellings an input
  was declared under (`_loom_dataset.names_of`), not its key; documented as a
  limit. Match through the key too.
- **`IdRegistry._mint_id` -> `_reserve_held` is O(N^2) in `id generate`**
  (pre-existing; measured 22 s for 2,000 files).
- **`id import` of a seed whose minted id equals a held id** moves the id
  silently (pre-existing).
- **`id generate -e`** hashes a dataset with the default ceiling, not
  `max-dataset-hash-bytes`.
- **NFD to NFC `INFO:`** prints two look-alike strings; show escapes.
- **The sdist-run exists-rule blind spot.** The alias rule's "shorter key
  must not exist" test looks below the registry root, which is not the
  checked-out tree of an sdist run.
- **Dataset licence wiring** (G7 #3 part 2): its own PR; see
  [roadmap.md](roadmap.md).
- **pyrefly** reports about 76 errors against a baseline of 66, all in
  `scripts/manual_cli_checks`; fix before merge.

Found in the last review rounds (2026-10-16), open:

- **Concurrent `loom.Run` blocks both minting `AIPackage-1`.** The claim is
  made before the write, so two runs against one registry race (the second
  save logs `another run saved ... first`, its fragment is already written).
- **A case-only rename leaves a stale entry** (`Data/T.txt` to `data/t.txt`):
  consistent with P6 (a moved file is a new identity); garbage collection of
  stale keys is not built.
- **`build_model` and the loom paths reserve only the ids they claimed**, not
  every held File/Package/AIPackage id as a document build does; a miss there
  can mint an id another key holds.
- **A fragment made without a registry** imports its `software_File` elements
  under their declared spellings (`id import`), not a canonical key.
- **`join_key` and sdist raw member names** such as `C:x` read differently on
  POSIX and Windows (low).
- **`id_registry/_registry.py` is exactly 500 lines**: split it before the
  next change to it.
- **A stale fragment file is recorded under its distribution-path key.** Probed:
  an old project SBOM merged as a fragment after a file changed adds `demo/x.py`
  (the old id, older SHA-256) beside `src/demo/x.py`; the newer entry is not
  rolled back, but the old id is parked under a second key. Decide whether a
  retired id may be recorded at all.
- **`id import` name-key reason.** `name_key_reason` is taken from the first
  candidate path (the same-hash file's key from the root), so a name that
  exists outside the root can say `not found` instead of `outside the project
  root` (`_dataset_key` in `import_keys.py`).
- **A renamed model keeps its `ai_AIPackage` id but its file gets a new one.**
  The stale fragment's same-SHA model folds into the renamed one, so the model
  does not follow the rename-is-new-identity rule that its file does (low; by
  the fold design).
- **Same-content SBOMs number ids differently.** A registry-less SBOM, a
  registry-backed one and a lookup-only embed of the same content share one
  namespace but assign different numbers; importing several re-keys an id over
  history (low; no duplicate inside one SBOM).
- **A model-card dataset named like a pinned loom dataset path** shares that
  id; the merge folds the two without a name conflict (low).
