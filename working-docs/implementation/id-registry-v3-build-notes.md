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
  and `wheel` runs into one registry churned an entry's hash.
- **`project_root` defaults to the registry file's directory** when none is
  set (`IdRegistry.save`, `root_dir()`), so a registry created by a harvest
  or the library, not by `id generate`/`id import`, still loads.
- **Same-stem models** (`a/model.gguf`, `b/model.gguf`) are registered by
  name only, with no hash, and one `INFO:` per run (`ID registry: N model
  files share the name X; its entry is not content-gated`): no one file
  stands for the stem, and a gate would re-mint on every run.
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
- **D11 is built in `_fragments_ids.py`** (`rename_type_clash`), called from
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
