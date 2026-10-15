---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry v3: what changed during the build

See also: [id-registry-v3.md](id-registry-v3.md) (the design these notes
amend; D-numbers and section numbers refer to it),
[id-registry-v3-rollout.md](id-registry-v3-rollout.md) (surfaces, messages,
commits),
[id-registry-followups.md](../design/id-registry-followups.md) (what v3
leaves open) and
[id-registry-v3-lessons.md](sbom-generator-field-notes/id-registry-v3-lessons.md).

Deviations from the design and the rollout file, in the order they
were met. Everything not listed was built as written.

- **Harvest never erases a recorded sha256 (ruling).** D12 made `register()`
  keep a recorded sha when given none; the same now holds for harvest. An
  unhashed element carrying the entry's id keeps the entry's hash; a hashed
  one replaces it (`_import_sbom_element`). Evidence: alternating `project`
  and `wheel` runs into one registry churned an entry's hash. `id import`
  is the one exception (order-matrix round, below).
- **`project_root` defaults to the registry file's directory** when none is
  set (`IdRegistry.save`, `root_dir()`), so a registry created by a harvest
  or the library, not by `id generate`/`id import`, still loads.
- **Same-stem models** (`a/model.gguf`, `b/model.gguf`) are registered by
  name only, with no hash, and one `INFO:` per run: no one file stands for
  the stem, and a gate would re-mint on every run. An existing entry is left
  as is, its hash included (ruling of the order-matrix round, below).
- **Merkle leaf details are final.** A leaf is `sha256(utf8 relpath + b"\x00"
  + raw 32-byte file digest)`, the relpath `/`-separated below the dataset
  directory (an undecodable POSIX name keeps its bytes via
  `surrogateescape`; a Windows lone surrogate via `surrogatepass`). Leaves
  are sorted by relpath bytes and combined by `core.models.merkle_root`. A
  symbolic link to a directory is not followed. The byte budget counts the
  whole directory and is enforced on every read, so a file that grows is
  caught.
- **The over-cap warning follows the shared `warn_over_cap` helper**
  (`logging_config.py`), not the `FILE=<p>: <n> bytes exceeds ...` wording of
  rollout section 11: `DIR=<p>` or `FILE=<p>: larger than the N-byte
  max-dataset-hash-bytes cap; dataset hash omitted`. Same sentence as every
  other cap.
- **`persist_registry` lives in `id_registry/_persist.py`**, not
  `_generators_shared.py`, with three differences from the plan. It
  re-reads the file before saving (`IdRegistry.rebase()`) and loom does the
  same before it mints (`LoomModels._refresh`), so a second run's ids are
  reused, not minted twice. `replay_changes` is a three-way merge (the table
  as last read, this run's table, the file now): this run's changed keys win,
  every other key keeps the file's, and a new id another run minted first
  for another key is refused with one `WARNING:` (`ID registry: another run
  saved ... first`). The save is atomic (`_sbom_io.replace_text_lf`): a
  temporary file beside the target, mode copied, a symlink at the path
  resolved first.
- **Loom writes annotations at the call and binds only their subject at
  exit.** 8.4 said provenance is captured at call time and replayed at exit.
  Replaying at exit would renumber `#Annotation-N` ids, so `declare()` emits
  the provenance at once against a provisional `urn:pitloom:loom:pending-
  model-N` id and `resolve()` sets each annotation's `subject` to the final
  id.
- **`loom.Run` now calls `configure_logging()`** (first in
  `_ActiveRun.__init__`), so its registry messages carry their `WARNING:`/
  `INFO:` tag like every other entry point (a recorded bug in
  [known-bugs.md](../design/known-bugs.md)).
- **Session API.** `IdRegistrySession.lookup_id` is the only lookup (the
  `file_id`/`entity_id` wrappers rollout commit 3 kept are gone), and
  `IdRegistrySession.register_id` is new: it registers and claims the id as a
  hit would, so a model declared twice in one run is a claim collision, not
  a second entry.
- **New modules.** `core/file_hash.py` (one chunked reader, `sha256_digest`,
  with a byte budget), `core/dataset_hash.py` (walk, leaves, root; no loom or
  registry knowledge) and `core/walk_rules.py` (`IGNORED_DIR_NAMES`,
  `same_path`, the in-tree registry warning); also `id_registry/_format.py`,
  `_persist.py`, `cli/_id_target.py`, `_loom_dataset.py` and `_loom_model.py`.
- **Messages added beyond section 11:** `loom: ID registry <p> is inside
  dataset directory <name>; left out of its Merkle root` (once per directory
  per run), `ID registry: another run saved <id> for <type> <name> first;
  not recording it for <name>`.
- **Manual checks are 20 (datasets) and 21 (models)**, as planned; the
  runner's `_checks_loom.py` holds them.
- **D11 is built in `_fragments_ids.py`** (`rename_id_clash`, also used for the digest clash below), called from
  `_MergeIndex.keep_apart` only for an element that is kept: a survivor by id
  (exact class equality, `type(a) is type(b)`, so a subclass never folds into
  its parent), licence, hash or structure is looked for first, so a same-hash
  element whose id another type holds folds by hash and is not renamed. Known
  limit: a same-type id coincidence still folds, and a re-minted id may meet
  a later fragment's id
  ([id-registry-followups.md](../design/id-registry-followups.md)).
- **Still as planned, now documented:** D7's in-tree registry exclusion
  (a `WARNING:` per run), D10 (the v2 `ERROR:`), the ceiling key and
  `pitloom_config=`, D8's `--namespace`. User-facing text:
  `docs/id-registry.md`, `docs/python-api.md`, `docs/configuration.md`,
  `docs/cli.md` and `skills/sbom-generate/references/id-registry.md`.

## Rulings of the 2026-10-15 review round

Decided by the user after the first full review; the code follows them.

- **A read-only registry is not overwritten, on any platform.** The atomic
  temp-file write would replace a `chmod 444` file on POSIX, where the old
  in-place save failed. The save fails with the failed-to-save `WARNING:`
  (`ERROR:` for `id generate`/`id import`), as before.
- **`id generate -e NAME:TYPE` splits on the last colon.** The suffix is a
  `TYPE` only when it is a known registry type (`software_File`,
  `software_Package`, `ai_AIPackage`, `dataset_DatasetPackage`); a suffix
  shaped like a compact type, or a known type in another case, is an argparse
  usage error (exit 2); otherwise the whole string is the `NAME`, so URLs and
  Windows drive paths work.
- **Harvest records a sha256 only for `software_File` and `ai_AIPackage`**,
  the two content-gated types, and never erases a recorded one. This
  narrows the first ruling above, which named every type.
- **A local dataset package is keyed by the caller's string, as passed**
  (no path normalisation): `../data/t.txt` from a subdirectory misses the
  package pin while its `software_File`, keyed by the registry-root-relative
  path, hits.
- **An output dataset is hashed when declared** (`add_output_dataset`), so it
  must be declared after the step wrote the file; otherwise it carries the
  hash of the file it replaces. Follow-up: defer to run exit, as models.
- **Two loom exits at the very same moment can write one id for different
  models into their fragments.** The claim in 8.4 of the design ("a lost
  update is never a wrong id") is corrected there; the registry itself stays
  one key per id. Follow-up: claim ids by rebase-and-save before writing the
  fragment.
- **`id generate` does not index files below a symlinked directory** (file
  symlinks are indexed), so loom keys such a path lexically and finds no
  entry.
- **Dataset directories prune the names `id generate` skips**, the one set
  `IGNORED_DIR_NAMES` in `core/walk_rules.py`, listed once in
  `docs/id-registry.md`.

## Rulings of the 2026-10-15 order-matrix round

- **A retired id is never minted again for another key** (I8 in the
  design, found by manual checks `O5/*` and deep `O2/*`). `_mint_id` took
  one more than the highest number held, so after a harvest replaced the
  top entry the next `id generate` handed that entry's old id to another
  file. Built: a required top-level `id_counters` table (format version
  stays 3: the format is unreleased), in `id_registry/_counters.py`. The
  key is the id prefix, not the type, and any prefix a mint can write is
  accepted, because `register()` takes any compact type. A missing key is
  rejected rather than derived from the held ids: deriving it is the bug,
  and a file without it was written before the fix. A counter below a held
  id is read up to it, without a message: held ids are ids seen. Counters
  stay across a namespace change (`id import` adopting a namespace, a
  rebase onto a re-created file): at worst a number is skipped. Harvest
  reserves an id skipped as ambiguous too, since an older SBOM carries it.
- **`id generate` leaves a shared stem's entry as is** (user ruling; finding
  2). `_register_ungated` dropped a recorded sha256 so that the result did
  not depend on the registry's history; that broke D12 and made loom re-mint
  the model after every `id generate`. Now the stem goes through
  `register()` with no hash: a new stem gets a sha-less entry, an existing
  one keeps its id and sha256. INFO: `ID registry: N model files share the
  name <stem>; its entry is left as is`. Accepted consequence: a fresh
  registry and one with history can differ for that stem; ids stay stable.
- **`id import` may drop a content gate, and says so** (user ruling;
  finding 3). An unhashed gated element (an `ai_AIPackage` from a project
  SBOM) whose id differs from a hashed entry: the imported id wins and the
  sha256 goes, with one INFO per key, `ID registry: content gate dropped for
  <type> '<name>': imported id <new> replaces <old>`. A run's auto-harvest
  never erases a recorded sha256: the same case leaves the entry as is, with
  `ID registry: content gate kept for <type> '<name>': harvested id <new> not
  recorded over <old>` (not met in the order matrix; kept for "no silent
  deviations"). `_harvest_elements(..., imported=)` is an explicit flag, not
  call-site discipline; both texts come from `content_gate_message`. Revisit
  after G7 #3, when the imported element carries its own hash.
- **One failed-save wording** (finding 5). `failed_to_save_message` gives
  `ID registry: failed to save <path>: <reason>` to `persist_registry` (a
  `WARNING:`) and to `id generate`/`id import` (the one `ERROR:`, exit 1;
  they printed the bare `OSError` before).

## Rulings of the 2026-10-15 review rounds (PR #305)

- **One write routine.** `save_registry` (public) rebases and saves only a
  changed file; `id generate`, `id import`, harvest and loom all call it
  through `persist_registry` or directly. `Rebase.added` makes the `INFO:`
  `added N new id(s)` count only ids new to the file. `id import` keeps the
  namespace it adopted unless another run changed it meanwhile. Not done:
  `IdRegistry.save()` called directly is still a plain write.
- **Counter reservation is bounded.** Ids from an SBOM, harvest or import
  reserve numbers up to 10**9 only; a prefix that is not a valid IRI segment
  (`/`, `?`, space, `#`, lowercase `%xx`) reserves nothing; `register("")`
  raises; the `id_counters` check also runs on save. Raw mint prefixes come
  from the library `register()` accepting any compact type, not from `-e`.
- **Strict load.** A non-integer `version` (`3.0`) and any repeated JSON
  object key (`duplicate key 'X'`) are rejected; `project_root` of a
  symlinked registry is relative to the target's directory.
- **Reads and writes degrade by level.** An unreadable file or directory
  below an `id generate` PATH is the shared `FILE=`/`DIR=` `WARNING:`
  (project-relative POSIX path); a root PATH stays an `ERROR:`. A writable
  registry in a read-only directory is written in place (not atomic);
  failed-save messages name the registry, not the `.tmp` file.
- **Shared-stem `INFO:` names what happened**: `its entry is left as is`
  (an entry existed) or `its new entry is not content-gated`.
- **`-e` is strict.** A trailing `:`, a type with surrounding white space, a
  control character or a blank NAME is a usage error (exit 2); URLs and
  `C:\path` names still work.
- **Final wheel tail rule** (supersedes the earlier "path tail" matching). A
  wheel member is the registry's copy only if its path equals the registry's
  project-relative path, or that path less exactly one leading part with a
  directory and the file left (`src/` layout). One member per archive (the
  longest) is left out; `reg.json` and `data/reg.json` are kept on every
  wheel and embed surface. The sdist rule is unchanged (whole path below
  `name-version/`). Without a project directory the base is the nearest
  directory holding the registry and a `pyproject.toml`, `setup.cfg` or
  `setup.py`, no higher than the stored root, else the stored root (monorepo
  registries now work for sdists). Rejected: matching any suffix, which
  dropped unrelated files.
- **`--allow-build` copies are recognised by origin** (a file the build
  extracted), wherever `TMPDIR` is. A build-and-read file's `physical_path`
  is always absolute, so the SBOM no longer depends on the random extraction
  directory.
- **loom** warns `ID registry ... is inside dataset directory ...` also when
  the directory gets no Merkle root.
- **New private module `_embed_overlay.py`** (`merge_file_extras`,
  `add_concluded_license`, `adopt_project_authors`), split from
  `_embed_build_sbom.py`.

## Fixes of the last review rounds (PR #305)

- **`id generate` split.** `IdRegistry.generate()` delegates to
  `id_registry/_generate.py` (`index_files(..., *, explicit)`), which keys
  a file by its project-relative path computed lexically (`normpath` of file
  and root), falling back to realpath only for a symlinked root; a file
  outside the root is `ID registry: <path> is outside the project root
  <root>`. `_types.py` has `_root_candidates` and `_eligible_files`; the
  ignored-directory test is the walk's pruning plus `_skipped_name_in` for an
  explicit PATH (`ID registry: path has a skipped directory name (<name>),
  skipping: <path>`). A registry is excluded by identity, never by file name.
- **Explicit versus implicit roots.** `explicit` (`bool(args.paths)` in
  `cli/id.py`) is threaded to the one walk: an unreadable PATH the user gave
  is `ERROR: PATH <p>: could not be read: <reason>` (rc 1, nothing written);
  an unreadable default root (`src`, `data`) is the shared `DIR=`/`FILE=`
  `WARNING:` and the run goes on.
- **CLI edges.** `--project-dir` that is not a directory: `ERROR:
  --project-dir <path> is not a directory`; `-o -` on `id generate` and
  `id import` is a usage error (exit 2).
- **Names that cannot be UTF-8 encoded** (a lone surrogate): `register()` and
  the loader reject them (`unencodable_message`); `id generate` skips the file
  with the shared `FILE=...` warning; harvest and import skip the element with
  a `WARNING:` after reserving its id.
- **Smaller API edges.** `IdRegistry.load()` of a non-path argument is a
  `TypeError`; `import_sbom` names a non-list `@graph` or a non-object
  element; `registry_key_for_path` returns `None` when the current directory
  was deleted; one `PROJECT_FILES` constant in `core/walk_rules.py`;
  `load_config_file(path, *, source=)`, loom passing `pitloom_config`.
- **Merge.** Elements with one id and type but disjoint digests of one
  algorithm are kept apart (`hash_conflict`, `_fragments_hashes.py`): the later
  gets a new id and one `Merge: ... of a different SHA256 hash; keeping both,
  it gets new id ...` `WARNING:`, after the content-hash and structural
  criteria have run. The hash-fold survivor is the id whose namespace more
  sources share (registry-pinned) over a fragment-local minted id; a tie keeps
  the earlier. All fragments load before the first merge; property helpers
  moved to `_fragments_props.py`; `sha256_of` to `export/hashes.py`.
- **Loom.** One `dataset_DatasetPackage` per (name, content digest) per run;
  `Run.__exit__` restores the enclosing run in a `finally` (recursive
  `@loom.run`); a NUL or `ValueError` in a model `path=` is the usual
  unreadable-model `WARNING:`.
- **Wheels with no identity.** `DocumentModel.identity_known` is `False` when
  the package name did not come from `METADATA`: the main package is not
  looked up, its id joins `registry_non_readers`, and a declared registry gets
  `INFO: ID registry: package identity unknown; not looked up or recorded`.
  Not fixed: the document namespace still derives from `unknown`, and the
  sdist placeholders ([id-registry-followups.md](../design/id-registry-followups.md)).
- **Size splits.** `_registry.py` is under 500 lines; tests split into
  `test_registry_generate_models.py`, `test_manual_cli_checks_order_runs.py`
  and `test_models_wheel_exclude_path_copy.py` (with
  `_exclude_path_shared.py`).
