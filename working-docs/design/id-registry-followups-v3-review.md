---
Created: 2026-10-15
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# ID registry v3: low-priority findings of the last review round

Not fixed in PR #305; each is small. Split from
[id-registry-followups.md](id-registry-followups.md) (see also there, and
[id-registry-path-keys.md](../implementation/id-registry-path-keys.md) for the
built path-key redesign; items it closed are marked).

The section "Registry v3: follow-ups (2026-10-15)" below moved here from
[id-registry-followups.md](id-registry-followups.md) for size.

## Registry invariants and file I/O

- **`register()` and the loader do not enforce** "a sha only on `software_File`
  and `ai_AIPackage`" nor "two keys never share an id". Loom registers a sha
  on dataset packages; the rules hold for harvest only.
- **Parallel first runs can write a mixed-namespace file**: rebase adopts the
  other run's namespace and keeps its own ids.
- **`save_registry` after the file was deleted fails by design** (one
  `WARNING:`; tests expect it).
- **`replace_text_lf` and long names.** The temp name adds about 22 characters,
  so a 230 to 255 character registry name gives `ENAMETOOLONG`; a dangling
  symlink gives a temp-path error text; `IsADirectoryError` names the temp
  file, not the registry.
- **`resolve_registry` raises a bare `TypeError`** for a non-path argument.
- ~~**A missing `--id-registry` is named absolute**~~: done in PR #482; the
  CLI flag and a `--config` key keep their spelling (`GivenPath`) and
  `resolve_registry` names the path as given.
- **`id import` of a non-SPDX JSON object not named `.spdx3.json`**
  (`{"a": 1}` as `s.json`) still fails with the deserialiser's uncoded
  `TypeError`; `embed-wheel` accepts such a file (its cross-check skips it).
  A `.spdx3.json` one is `sbom-wrong-format` on both since PR #482.
- **NFC/NFD is not normalised in `RegistryCopy`** (registry keys are NFC since
  path keys; the copy match is not).

## Paths and walks

- **Directory-dataset pruning** of ignored names (`build`, `dist`, ...) below a
  dataset root skips subtrees silently, and `Hash.comment` does not say so.
- **`..` through a symlinked directory in `registry_key_for_path`** collapses
  lexically, but the OS opens the real parent: key and hash can describe
  different files.
- **Nearest-project-file root heuristic** for a wheel or sdist with no
  `--project-dir` misfires on a stray `setup.py` beside the registry; surfaces
  then differ in Merkle root.
- **The drop-one-leading-part rule** for a registry copy in a wheel can drop an
  unrelated member.
- **`_SKIPPED_LOOM_FILENAMES` matches the basename `loom.py`** (pre-existing).

## Loom and merge

- **Loom datasets register a sha on the dataset package** (see the invariant
  above): since path keys a hashed dataset package is content-gated, so the
  invariant is now "hash on file, model and dataset package"; enforce or
  document it in `register()`.
- **`set_model_hyperparameters` keeps stale annotation statements**
  (pre-existing).
- **Unified `rename_id_clash`**: one helper now words both the different-type
  and the conflicting-digest clash; the older name-only warning in
  `_fragments_hashes.py` (`appears with two different SHA-256 hashes`) is a
  separate wording for a different case. Align the two if they stay.
- **Unidentified wheels and sdists**: see the `unknown` item in
  [id-registry-followups.md](id-registry-followups.md#wheel-identity-and-archive-readers).
- **Non-UTF-8 byte in a directory above the project**: `_shown` /
  `_unstorable_name_error` (`id_registry/_types.py`) judge the project-relative
  name only, so a surrogate in a parent directory above the project root is
  not seen there; the absolute path then reaches log text through
  `loggable()` only. Decide whether the project root itself must be checked.

## Registry v3: follow-ups (2026-10-15)

Found while building and reviewing v3 (commits 0b to 7b). Facts were checked
by the implementers against the tree; code locations are given where an item
is easy to lose. D-numbers refer to [id-registry-v3.md](../implementation/id-registry-v3.md).

### G7 blockers (Day 2)

Closed by the path-key work (blockers 1 and 2, and the `id import` sha-drop
revisit: an imported model now carries its own hash and takes the key of its
same-hash `software_File`). See
[id-registry-path-keys.md](../implementation/id-registry-path-keys.md).

### Security and edge cases

Dataset hashing and paths:

- **Directory-dataset hashing has no file-count cap.** Millions of tiny files
  stay under the byte ceiling (`max-dataset-hash-bytes`) while the walk and
  the member list grow without bound: measured 88.8 MB peak for 200,000
  files, about 440 bytes per file. Add a count cap beside the byte one.
- **An output dataset is hashed when declared** (`add_output_dataset`), so
  one declared before the step wrote the file carries the hash of the file it
  replaces. Defer output-dataset hashing to run exit, as models are.
- **The same dataset declared twice is hashed twice.** The package is now one
  per `(name, digest)` per run (2026-10-15), but `hash_dataset` still runs on
  every declaration. Cache the digest per run, keyed on the real path.
- **`id generate` does not index files below a symlinked directory** (a file
  symlink is indexed), so a `loom.Run` keys such a path lexically and finds no
  entry. Documented in `docs/id-registry.md`; decide whether it is a gap.
- **A dataset member that vanishes between listing and hashing** warns
  `could not read`; a single vanished file is silent. Align the two.
- **Symlinked subdirectories of a directory dataset are not followed.**
  Documented in `docs/python-api.md`; decide whether it is a gap.
- ~~**Case-insensitive file system.**~~ Resolved by path keys: a user-typed
  path takes its on-disk spelling.
- ~~**`registry_key_for_path` raised when the current directory was
  deleted**~~ Resolved 2026-10-15: it returns `None`, as for "outside root".

Registry file I/O:

- **Windows: `os.replace` fails while another process has the registry
  open.** The save logs the failed-to-save `WARNING:` and the update is lost.
- **A killed process can leave `.<registry>.<hex>.tmp`** beside an in-tree
  registry, and a later scan would list it: D7 excludes by exact path only.
- **A registry replaced mid-run by a file with another namespace.**
  `rebase()` adopts the new namespace; ids already replayed keep the old one.

Loom:

- **`loom` never configured logging before 7b.** `loom.Run` now calls
  `configure_logging()`, which replaces handlers a user had set on the
  `pitloom` logger. Documented in `docs/python-api.md`; or add to the
  handlers instead.
- **A model declared twice under one name with different files:** the last
  declaration owns the entry.
- **`run.model` is `None` inside the `with` block** (resolved at exit, D13),
  so user code reading it there breaks. Document it or expose a provisional
  value.
- **Two truly simultaneous loom exits can write the same id for different
  models into their fragments.** The registry stays one key per id (the later
  save is refused, `WARNING: another run saved ... first`), but the fragment
  is already written, so the claim "a lost update is never a wrong id" was
  false for it (corrected in
  [id-registry-v3-loom.md](../implementation/id-registry-v3-loom.md) 8.4; documented in
  `docs/id-registry.md`). Fix idea: claim ids by rebase-and-save before
  writing the fragment.
- ~~**Two model files with the same stem**~~ and ~~**a local dataset package
  keyed by the caller's string**~~: resolved by path keys (a model is keyed
  by its file, a dataset package by its path when it exists).
- **A hashless `-e path:software_File` pin, then a regeneration,** logs
  `content changed` and mints a new id (the D12 trade-off). Consider adopting
  the hash on first sight for file pins.
- **Bootstrap from an empty registry** logs two `untracked file` `WARNING:`s,
  for the `data/processed/` files the pipeline creates later.
- ~~**`IdRegistry.load` type handling**~~ Resolved 2026-10-15: a non-`str`,
  non-path-like argument is a `TypeError`.

Merge and warnings:

- **`loom fragment list` now computes the registry exclusion**, so an invalid
  declared registry reports `SAME_DOCUMENT` unknown instead of an id.
- ~~**`load_config_file` says "--config file"**~~ Resolved 2026-10-15: the
  no-`[tool.pitloom]` warning names `pitloom_config` when loom is the caller.
- ~~**Merge hash-survivor policy.**~~ Resolved 2026-10-15: for equal SHA-256
  the registry-pinned id wins (the namespace more inputs share beats a
  fragment-local minted one; a tie keeps the earlier); see `docs/fragments.md`.
- **`id import` of an SBOM whose `ai_AIPackage` name differs from the file
  stem** releases the stem key `id generate` made, and its hash gate (a
  pre-existing behaviour). It matters more now that hashes gate ids: see the
  G7 blocker on harvest keys above.
- **A loom retrain logs `added 1 new id(s)`** for the replacement id of the
  retrained model, although the key already existed; the count is by ids
  under keys the registry did not hold elsewhere. Align the wording or count.
- ~~**Two alias rules for one fact.**~~ Resolved: `keys.is_layout_alias`
  and `walk_rules.shortened_by`.
- **Harvest churn.** Harvest now never erases a recorded sha (ruling
  2026-10-14); a package whose lock sha changes replaces it, so alternating
  runs with and without the lock can still rewrite the registry.

### Found by the order matrix (manual checks `O*`, 2026-10-15)

Each failed its `O*` check until decided; repro scripts are in the
runner's `ord-repro-*` directories (manual-cli-checks.md, "Order
matrix").

- ~~**A registry id is minted again for another file** once it has left
  the registry.~~ `_mint_id` took one more than the highest number the
  registry held; when a harvest replaced the highest-numbered entry's id
  (a `project` run after that file changed mints a document id), the
  next mint reused the number: `id generate`, edit `b.py`, `project`,
  edit `a.py`, `id generate` gave `a.py` the id `b.py` had in the first
  run (`O5/flat`, `O5/stems`, deep `O2/*`). Resolved 2026-10-15: the
  file keeps a per-prefix `id_counters` table, never lowered, and a mint
  takes one above it (I8 in
  [id-registry-v3.md](../implementation/id-registry-v3.md); ruling in
  [id-registry-v3-build-notes.md](../implementation/id-registry-v3-build-notes.md)).
- ~~**`id generate` erases the sha256 loom recorded for a shared-stem
  model**~~ (`_register_ungated`, on purpose: "the result does not depend on
  the registry's history"). D12 says an ungated registration never erases
  a recorded sha, and the effect is churn: loom's next gated lookup misses
  and re-mints the model id after every `id generate` (`O2/stems/*`,
  `O1/stems/fresh-loom`). Resolved 2026-10-15 (user ruling): a shared stem's
  entry is left as is, its sha256 included (D12); a stem with no entry gets
  a sha-less one. A fresh registry and one with history can differ for that
  stem; its id stays stable (D3 in
  [id-registry-v3.md](../implementation/id-registry-v3.md)).
- ~~**`loom wheel --id-registry R` lists and harvests the copy of R that a
  wheel built from an in-tree registry carries.**~~ The D7 exclusion
  (`_DeclaredRegistry`) ran only in `get_wheel_files`; build-then-`wheel`
  never settled (`updated stale entries` every run, the wheel's document
  uuid and its per-document ids changed each time) (`O3/intree`,
  `O1/intree/surfaces`). Resolved 2026-10-15: every reader of wheel or
  sdist members (`wheel`, `wheel --embed`, `embed-wheel` with or without
  `--project-dir`, `project <sdist>`, their library functions) leaves out
  a member whose path is the registry's path below `--project-dir`, else
  below the registry's stored `project_root`, or (a wheel only) a tail of
  it; no hash, as the copy is the registry at build time
  (`walk_rules.RegistryCopy`, shared with `_DeclaredRegistry`). The copy
  is out of the Merkle root; one `WARNING:` per run, an `embed-wheel`
  batch included. A registry rooted at its own directory does not match
  a copy under a package directory, so that copy stays.
- ~~**`id import` of an unhashed `ai_AIPackage` whose id differs from a
  hashed entry drops the entry's sha256**~~ (the harvested id wins). So the
  order of `id generate` and `id import` decides whether the model entry
  stays gated, and importing a pre-retrain SBOM reverts the model to its
  pre-retrain id. The ruling "harvest never erases a recorded sha256"
  says to keep it, which would bind the imported id to bytes it never
  described (`O1/flat/fresh-cli`). Decided 2026-10-15 (user ruling): the
  imported id wins and the sha256 goes, with one `INFO: ID registry: content
  gate dropped for <type> '<name>': imported id <new> replaces <old>` per
  key; a run's harvest never erases one (it leaves such an entry as is,
  `content gate kept`). The order matrix counts the resulting difference
  as order-dependent, not a violation. Revisit after G7 #3 (below).
- ~~**A read-only registry on `id generate`/`id import`**~~ gives `ERROR:
  [Errno 13] Permission denied: '<path>'`, without the `ID registry:
  failed to save <path>` wording every other surface uses (`O4/*`).
  Resolved 2026-10-15: one helper (`failed_to_save_message`, since #492 `say_save_failure`) words it on
  every surface; `id generate`/`id import` print it as the one `ERROR:`
  and exit 1, the file untouched.

### Found by the review rounds (PR #305, 2026-10-15)

Resolved:

- ~~**Registry writes took several paths**~~ (`id generate`/`id import`
  rewrote an unchanged file; `id import` could overwrite a namespace changed
  meanwhile). Resolved: one `save_registry` (rebase, save only when the file
  differs); `Rebase.added` counts the ids a save adds, for the `INFO:`.
- ~~**Hostile or huge ids reserved counter numbers**~~ (and `register("")`,
  a non-integer `version`, a repeated JSON key, a `project_root` through a
  symlink). Resolved: reservation stops at 10**9 and skips a prefix that is
  not an IRI segment; `register("")` raises; `load()` rejects `3.0` and
  `duplicate key`; the root is relative to the symlink target's directory.
- ~~**An unreadable file below an `id generate` PATH aborted with
  `ID registry: could not read <abs>`**~~. Resolved: the shared `FILE=`/
  `DIR=` `WARNING:`, project-relative; a root PATH stays an `ERROR:`.
- ~~**A registry copy in a wheel was matched by any tail**~~ (`reg.json`
  dropped beside `src/demo/data/reg.json`), and a monorepo registry missed
  an sdist. Resolved: path, or path less one leading part with a directory
  and the file left; one member (the longest) per archive; no project
  directory: nearest project directory up to the stored root. Build-and-read
  copies are recognised by origin and keep an absolute `physical_path`.
- ~~**The loom registry-in-dataset warning needed a Merkle root**~~. Resolved:
  it also fires when the directory gets none.
- ~~`cli/_id_target.py` repeated the project-marker list~~. Resolved: one
  `PROJECT_FILES` in `core/walk_rules.py`.
- The remaining fixes of the later rounds (explicit versus implicit unreadable
  roots, UTF-8-unencodable names, `-o -`, the `_generate.py` split) are in
  [id-registry-v3-build-notes.md](../implementation/id-registry-v3-build-notes.md).

Open:

- `IdRegistry.save()` called directly by a library user is still a plain
  write; only the CLI, harvest and loom use rebase and replay.
- A retired id above the 10**9 reservation ceiling could in theory be minted
  again after a billion mints.
- The in-place write for a writable registry in a read-only directory is not
  atomic.

### Design questions for the user

1. ~~Should a local dataset's package be keyed by its D9 path too?~~ Decided
   2026-10-15: no; reversed 2026-10-16 (user): yes, its path key when the path
   exists below the root, gated by content (hybrid), see
   [id-registry-path-keys-decisions.md](../implementation/id-registry-path-keys-decisions.md).
2. ~~"Harvest never erases a sha" for every type.~~ Decided 2026-10-15:
   harvest records a sha256 only for `software_File` and `ai_AIPackage` (the
   two content-gated types) and never erases a recorded one.
3. **Default `project_root` when none is set is the registry file's
   directory** (commit 3). Confirm.

### Path keys: follow-ups (2026-10-16)

Split out: [id-registry-followups-path-keys.md](id-registry-followups-path-keys.md).

### Tooling

- **pyrefly cannot resolve the sibling imports in `scripts/manual_cli_checks`**
  (about 30 baseline errors, plus 2 from `_checks_loom`). Adding that
  directory to pyrefly's `search-path` would clear them.
- **`core/model_extract_limit.py` no longer fits its name:** it now also holds
  the dataset ceiling validator `require_positive_ceiling`. Rename (for
  example `core/ceilings.py`) in a small PR.
- **`_embed_build_sbom.py` and `EmbedFileCache`** are over the soft limit; the
  split is blocked by 12 test patch targets. `_embed_overlay.py` took the
  overlay helpers.
- **Local command traps:** `pytest -p no:xdist` fails because the config
  passes `-n` (use `-n0`); a bare `.venv/bin/mypy` exits 2 here, as no
  targets are configured (use `mypy src tests`); a bare `flake8` crashes on
  `.venv` (scope it to `examples src tests`).
