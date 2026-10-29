---
Created: 2026-09-30
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry v3: section 8, loom datasets, keys and models

See also: [id-registry-v3.md](id-registry-v3.md) (the design; this file is
its section 8, split out for size, numbering kept),
[id-registry-v3-build-notes.md](id-registry-v3-build-notes.md) (where the
build differs), [id-registry-v3-rollout.md](id-registry-v3-rollout.md).

## 8. Loom

### 8.1 Single-file dataset (D5)

`loom.add_dataset(path)` on a regular file emits:

- a `software_File`: name = the D9 key (8.3), else the caller's string;
  `software_fileKind = file`; `verifiedUsing` = its sha256; id = gated
  lookup of `(software_File, key)`, else minted with prefix `File`;
- a `dataset_DatasetPackage`: name = the caller's string, unchanged; id =
  lookup of `(dataset_DatasetPackage, key)` (amended 2026-10-16: the path key
  when the path exists below the root, else the string; content-gated by the
  hybrid rule), else minted with prefix `DatasetPackage`; `verifiedUsing` = its own copy of the file's
  sha256 (a separate `Hash` object, never shared), the rule G7 uses for
  AIPackage;
- `DatasetPackage contains File`.

The `trainedOn`/`testedOn` relationship, and every other relationship
loom emits today, stays on the DatasetPackage. There is no
`software_File` fallback key for the DatasetPackage (D2). One name
holding one content is one `DatasetPackage` and one `software_File` per
run: `add_input_dataset("x")` then `add_dataset("x")` (or `add_output_dataset`,
or the same call twice) return the same package, cached by `(name, digest)`,
so a second lookup never raises a spurious claim collision. The roles of
every declaration attach to it (`trainedOn`, `testedOn`, `hasInput`; a
package that is both input and output gets no `hasInput` edge to itself);
a repeated `dataset_type` is added to its kinds, and an output declared
twice has the union of its `input_datasets` (`None`, every input, wins). A
rewritten file (new digest) is a new element.

### 8.2 Directory dataset (D6)

- **Output:** only the DatasetPackage, with `verifiedUsing` set to the
  Merkle root.
- **Walk:** `os.walk(onerror=...)`, not the `_iter_files`/`rglob` walker
  the first draft named: `rglob` silently skips a directory it cannot
  list, which would give a partial root. The walk prunes the shared
  ignored-name set (`IGNORED_DIR_NAMES`, moved to a new public
  `core/walk_rules.py`) and excludes the registry file (D7). A FIFO,
  socket or dangling symlink is skipped through
  `path_probe.is_regular_file` (a read would block or fail).
- **Leaf hash:** `sha256(posix_relpath_utf8 + b"\x00" + file_digest)`,
  where `file_digest` is the raw 32-byte SHA-256, not hex, and `relpath`
  is relative to the dataset directory. Leaves are sorted by relpath
  bytes (UTF-8 with `surrogateescape`, so an undecodable POSIX name still
  hashes).
  - A one-file directory's root is that single leaf, which differs from
    the file's own sha256. So a directory dataset never hash-merges with a
    single-file dataset of the same bytes (the merge hash index is keyed
    by `(type, sha256)`, and both are `dataset_DatasetPackage`). A test
    pins this.
- **Root:** a new public `core.models.merkle_root(leaves)` delegating to
  the existing `_build_merkle_tree` (its unpaired-node promotion kept: one
  tree algorithm).
- **Why the path is in the leaf:** wheel leaves are content-only, so
  renaming a file would not change a wheel root. That is acceptable for a
  wheel, but not for a dataset.
- **`Hash.comment`** (precedent: the wheel root, `assemble/spdx3/document.py`):
  `SHA-256 Merkle root over N files (path and content) in dataset
  directory, not a hash of a single artifact` ("1 file" when N is 1).
- **Reads:** chunked (1 MiB), one shared reader (`sha256_digest`, which
  `id_registry.sha256_file` also uses). Nothing is loaded whole.
- **Ceiling: `max-dataset-hash-bytes`**, default 4 GiB (4294967296),
  counting the total bytes hashed, for directory and single-file datasets
  alike. Cascade: `loom.Run(max_dataset_hash_bytes=)` >
  `pitloom_config` (D14) > default; `loom id generate -e` takes
  `--max-dataset-hash-bytes` > the project's own key > default (read only
  for a dataset without the flag). The flag is on `id generate` alone: on
  the shared SBOM parser it would be inert on every other command, and no
  Action step hashes a dataset, so there is no input or env var. Validated
  at use by `require_positive_ceiling` (a positive `int`; `bool` and `0`
  rejected); it has a `docs/configuration.md` row and a
  `_matrix_plan.py` entry. The size is checked from `stat()`
  first, so nothing over the limit is opened; a file that grows during the
  read is caught by a byte budget. Over the ceiling: no hash and one
  `WARNING:` naming the path and the limit.
- **Empty directory:** no hash, silently. This is absent data, not an
  error.
- **Unreadable member or unlistable subdirectory:** the `path_probe`
  warning (`UNREADABLE_FILE_WARNING` / `UNLISTABLE_DIR_WARNING`) and **no
  root at all**. A root over part of the directory would be wrong.
- **Probing:** every loom path check goes through
  `path_probe.is_regular_file` and `os.path.isdir`, never `Path.is_file()`
  (problem 10). A missing path gets no hash and no File; its
  DatasetPackage is still looked up by name (section 3).
- **Lookup** (amended 2026-10-16): `(dataset_DatasetPackage, path key or
  name)`, gated by the Merkle root; a hash-less pin hits any content.

### 8.3 Path base for loom keys (D9)

Loom keys a file (dataset file, script) by its path made relative to the
registry's `root_dir()`, as a POSIX string (`registry_key_for_path`):
first lexically (`normpath` of the absolute path), then via realpath. The
lexical attempt matches `id generate`'s keying of an in-project symlink.
This matches `id generate`'s keys whichever directory the script runs
from.

- **Outside the root:** the element name is the caller's string, there is
  no lookup, and one `WARNING:` per path per run.
- **No registry loaded:** the caller's string, silently (today).
- `project_root` is stored relative to the registry file's own directory
  (section 6). `id generate` writes it from `--project-dir`; `id import`
  from the cwd, the base it already resolves paths against. Both only
  when creating a registry; an existing one keeps its root. Every reader
  resolves it against the registry file's directory, so moving the
  project and its registry together keeps working.
- Only loom uses it. Project, wheel and hook lookups still key by
  `physical_path`/`distribution_path`.
- Rejected: assuming the registry file's directory is the root. That
  breaks for `-o build/reg.json`.

### 8.4 Loom models: resolved at run exit (D3, D13)

- `set_model(..., *, path=None)` and `use_model(..., *, path=None)` (on
  `loom` and on `_ActiveRun`; keyword-only, so positional order holds)
  only record a declaration: name, type, hyperparameters, `generated`,
  `path` made absolute at declaration time, and the provenance events
  captured at call time (replayed in order at exit, so annotations are
  unchanged). `run.model` is `None` until `finalize()`.
- `finalize()` resolves each declaration in order, then emits the
  relationships and writes the fragment as today, then saves the registry
  if it gained entries. A raising block never reaches `finalize()`:
  nothing is hashed, looked up, recorded or written, so a half-written
  model file is never hashed. The fragment is written before the
  registry, so a failed write never leaves an entry pointing at an id no
  fragment carries.
- Resolving one declaration:
  - **`path` is a regular file:** sha256 it (chunked; no ceiling, which is
    a dataset key). Gated lookup of `(ai_AIPackage, name)`. Hit: reuse.
    Claim rejected (declared twice in one run): the existing collision
    WARNING and a fresh id, not recorded. Raw miss: `register(...,
    sha256=)` when the registry has a file path and `update-id-registry`
    is not false; otherwise today's miss WARNING (or the `no file path
    resolved` WARNING) and a fresh id. The AIPackage gets `verifiedUsing`.
  - **No `path`, or `path` is not a regular file at exit, or unreadable:**
    one WARNING (only with a registry loaded, for the no-`path` case),
    then today's ungated name lookup; no `verifiedUsing`, no registry
    write. A sharded model directory is this fallback.
- A model's key is the **path key of its `path=` file** (amended 2026-10-16;
  originally its name, with `path` only feeding the hash), else its name when
  there is no file.
- `persist_registry` is `_sync_registry`'s tail, moved (not copied) so
  both writers log the same `ID registry: ...` lines. To survive two loom
  processes sharing one registry file, it re-loads the file just before
  saving, replays only this run's new entries, and saves atomically. No
  file locking. A lost update to the registry costs a re-mint on the next
  run, but two loom runs that exit at the very same moment can each write
  the same id for a different model into their fragments: the registry
  keeps one key per id and the run that saves second logs `another run
  saved ... first`, yet its fragment is already written. (The first draft
  said "never a wrong id"; that holds for the registry, not for fragments.
  Fix idea: claim ids by rebase-and-save before writing the fragment; see
  [id-registry-followups.md](../design/id-registry-followups.md).)
- Effect: training (`set_model(path=)`) and evaluation
  (`use_model(path=)`) fragments share one AIPackage id with no
  `id generate --entity`; a retrain gets a new id with one INFO.
