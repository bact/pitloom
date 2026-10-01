---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry v3: one typed table, content gate chosen at lookup

See also: [id-registry-v3-rollout.md](id-registry-v3-rollout.md) (surfaces,
messages, commits, verification, out of scope; sections 10-14 continue
this file's numbering),
[id-registry-autosync.md](../implementation/id-registry-autosync.md)
(v2 as built: harvest, stale-key release, ambiguity, claims),
[id-registry-followups.md](id-registry-followups.md) (items v3 leaves
open), [ai-model-id-stability.md](ai-model-id-stability.md),
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md) (G7 #3 builds on this),
[roadmap.md](roadmap.md).

**Status: design, not built.** The code on `main` is still registry v2.
This file (the design) and the rollout file (how it lands) are the
implementers' brief. Every decision is final (user, 2026-09-30); nothing
is open. Registry v3 is its own PR, independent of G7 (order and base
branch: rollout, top). The `file:line` anchors were checked on `main` at
`4c052dd`; re-verify each against the post-#263 base before coding.

## 0. Revisions to the first draft (user, 2026-09-30)

The body reads as final. What moved since the first draft: D3 (the model
sha256 is now a gate), D12 (`register()` is uniform), D13 (loom resolves
models at run exit and **writes the registry**), D14 (`loom.Run(
pitloom_config=)`), D15 (hashed AIPackages are auto-harvested); and the
former open items are decided: D10, the ceiling key and the directory
`Hash.comment` (8.2), and commit 2 also fixing `_is_eligible_file`
(rollout section 12).

## 1. Why

G7 #3 gives `ai_AIPackage` a `verifiedUsing` hash. v2's harvest then files
it under `files`, while every model lookup reads `entities`. As a result,
`loom id import` loses the model's id.

The narrower fix, "only a hashed `software_File` is a file", moves the
bug rather than removing it. A loom dataset is a hashed
`dataset_DatasetPackage` whose lookup reads `files`. The cause is
structural: harvest guesses an element's table from its shape, but only
the lookup side knows which table it reads.

## 2. v2 as it is

| | `files` | `entities` |
| --- | --- | --- |
| Key | `path` (no type) | `(compact type, name)`; PEP 503 name for `software_Package` (`_types._entity_key`) |
| Entry | `spdxId`, `sha256` | `spdxId` |
| Lookup | `lookup_file(path, sha256)`: hits only if the hash matches | `lookup_entity(name, type)` |
| Session | `IdRegistrySession.file_id(claimant, paths, sha256)` | `entity_id(claimant, names, type)` |
| Writers | `register_file` (`id generate`), harvest | `register_entity` (`id generate` model stems, `--entity`), harvest |

Harvest (`_harvest._import_sbom_element`) puts an element in `files` when
it is hashed and is not a `software_Package`, and in `entities`
otherwise. Its docstring says a key already mapped to a different id
"keeps its own entry"; the code overwrites it. v3 keeps the code's
behaviour (the harvested id wins) and fixes the docstring.

Problems:

1. **Misfiling by shape.** No shape rule is right for every caller: a
   hashed AIPackage needs `entities`, a hashed loom dataset needs `files`.
2. **Ids cross types.** `files` has no type in its key, so loom reuses
   `id generate`'s `#File-N` id for a `dataset_DatasetPackage` (see
   `tests/id_registry/shared.py:51-58`). One merged document can then
   hold two elements of different types under one id.
3. **One fact per entry.** An entry is either name-keyed or content-gated,
   so an AIPackage's hash cannot be kept.
4. **Ambiguity covers `entities` only.** `_ambiguous_entity_keys` never
   counts two elements with the same `files` path.
5. **Two identical sha256 extractors.** `_types._sha256_from_verified_using`
   and `_fragments_unify._sha256_hash`.
6. **Loom keys a file by the path the caller passed**, relative to the
   process cwd, while `id generate` keys files relative to the project
   root. A dataset path pinned by `id generate` only matches when the
   script happens to run from the project root.
7. **A directory dataset gets no hash and no registry lookup.**
   `_loom_caller._hash_and_registry_lookup` returns `(None, None)` when
   `Path(name).is_file()` is false.
8. **Namespace.** `IdRegistry.new` mints a random UUID4 namespace
   (`_registry.py:68-70`).
9. **Fragment merge by id ignores type.** `_fragments_unify._MergeIndex.find_by_id`
   matches by id alone. Take a loom DatasetPackage and a project
   `software_File` that both hit `files[path]`. The DatasetPackage is
   folded into the File: `dataset_datasetType`/`dataset_dataPreprocessing`
   are silently lost, and `trainedOn` points at a `software_File`. Which
   element survives depends on the merge order.
10. **Loom probes with `Path.is_file()`, not `path_probe.is_regular_file`.**
    As a result, a permission error behaves differently per Python
    version (see AGENTS.md, `Path.exists()`/`.is_file()`).
11. **Loom's fallback ids are never stable.** Without a registry, a loom
    id is `generate_spdx_id("DatasetPackage", name, doc_uuid)`: the dataset
    name becomes the *document* name (a path puts `/` into the
    namespace), and `doc_uuid` is a fresh UUID4 on every run
    (`_loom_active_run.py:73`). Out of scope here; recorded for the loom
    SDK work (G7 #7).

## 3. Decisions (user, 2026-09-30)

Each decision gives its reason; rejected alternatives follow "Rejected".

- **D1: one table, typed keys.** Key `(compact type, name)`, where the
  name is the path for a file or directory; entry `{spdxId, sha256?}`.
  Harvest never classifies; each lookup decides whether the content has
  to match. Why: only the lookup side knows which gate it needs (section
  1).
- **D2: ids are typed.** Inside our own namespace, an spdxId's fragment
  prefix equals the element's type prefix (`type_id_prefix`, promoted
  from `_type_id_prefix`: `File`, `Package`, `AIPackage`,
  `DatasetPackage`). The registry never hands an id to another type. A
  drift test covers our namespace only; imported or foreign ids are
  exempt.
- **D3 (revised): `id generate` records the model file's sha256 on the
  `(ai_AIPackage, stem)` entry, and the sha is a gate once recorded.** A
  retrained, re-exported or re-quantised model (different bytes) is a new
  model with a new id. Only a model with no single hashable file
  (sharded directory, remote, declared without `path=`) falls back to a
  name-only entry. Why (user): a retrained model is a new model.
  Rejected: the first draft's "record only, never a gate", which kept the
  id across retrains (the open question in
  [ai-model-id-stability.md](ai-model-id-stability.md)).
- **D4: one count in the log line:** `added N new id(s)`, where N counts
  distinct ids (a src-layout alias adds a key, not an id). logfmt quoting
  of `KEY=VALUE` lines is a separate PR (P1).
- **D5: loom datasets become packages that contain files.** See 8.1.
- **D6: directory dataset.** Emit only the DatasetPackage, with a
  path-aware Merkle root; per-member `software_File`s are a later opt-in.
  The hashing ceiling is a new config key, `max-dataset-hash-bytes`
  (8.2).
- **D7: the resolved registry file is excluded** from project file
  discovery and from `id generate` indexing, at every discovery site
  (rollout commit 2). Why: an in-tree registry otherwise rewrites the SBOM
  and itself on every run.
- **D8: the namespace for `id generate`.** Keep a UUID4 minted once at
  creation, and add `--namespace IRI`. See section 9.
- **D9: loom path base.** The registry stores `project_root`; loom keys
  a file relative to it. See 8.3.
- **D10: no v2 migration.** A v2 file fails to load with one `ERROR:`
  telling the user to delete it and re-run `pitloom id generate` or
  `pitloom id import`. Why: private alpha, no compatibility code.
- **D11: merge by id requires the same type (problem 9).** A fragment
  element whose id matches an existing element of another type logs one
  `WARNING:` and gets a freshly minted id in the main document's
  namespace; it is never folded in. Why: a WARNING plus a remap matches
  the registry's claim-collision rule (`warn_claim_collision`), loses no
  data, and never leaves two elements with one id. Under D2 this happens
  only with foreign ids or pre-v3 registries. Hash merge is already
  type-scoped (`(type, sha256)` index) and does not change.
- **D12: `register()` is uniform** (the full table is in section 5). No
  entry: mint. No sha on either side, or an equal sha: reuse. A differing
  sha, **including a sha-less entry receiving a sha**: INFO `content
  changed`, then mint and replace. An ungated registration never erases a
  recorded sha. No per-type exception. Why: one rule, and "no sha" is no
  evidence the bytes are the same. Trade-off: a user who pinned `-e
  m:ai_AIPackage` and then declares `path=` gets one new id, once, with the
  INFO; docs tell users to declare `path=` wherever a file exists and not
  to mix the two for one model. Rejected: keep the id and adopt the first
  sha (a special case that silently binds whichever file is present first
  to a long-standing id).
- **D13: loom resolves models at run exit and records them.** See 8.4.
- **D14: loom takes an explicit config.** `loom.Run(pitloom_config=
  PitloomConfig | str | Path | None)`. A path is loaded like `--config`
  (relative to cwd; missing -> `ValueError`). Loom reads three keys from
  it: `max-dataset-hash-bytes`, `update-id-registry`, and `id-registry`
  when the `id_registry=` argument is not passed. An explicit argument
  wins (the cascade). Every other key is documented as not applying to
  loom (a config key a surface can't use is documented, never warned).
  Loom never reads an implicit `[tool.pitloom]`. Why: parity with the
  library API's `pitloom_config=`, and the ceiling needs a way in without
  a CLI. Rejected: removing `id_registry=` in favour of
  `PitloomConfig(id_registry=...)`; reading only the ceiling and
  `update-id-registry` and documenting `id-registry` as ignored.
- **D15: hashed `ai_AIPackage` elements are auto-harvested.** Why: under
  D3 a hashed AIPackage is content-gated, so harvesting it by name cannot
  hand its id to another model file. Unhashed AIPackages stay excluded
  (their name depends on extraction), and so does every
  `dataset_DatasetPackage` (a dataset id is pinned deliberately, by `id
  generate -e NAME:dataset_DatasetPackage` or `id import`, never from a
  run's fallback id). Loom `software_File` children in merged fragments
  are harvested.
- **D16: the other AIPackage lookups stay ungated in this PR** (project,
  wheel, `loom model`, embed). Why: those surfaces do not hash AIPackages
  until G7 #3; gate them then, so every surface agrees with loom. Until
  then a project SBOM reuses a name-matched id even after a retrain
  ([id-registry-followups.md](id-registry-followups.md)).

Smaller decisions (user, 2026-09-30):

- **`id generate` into a registry whose `project_root` differs** from
  `--project-dir`: one `ERROR:`, exit 1. Mixing keys from two roots
  silently breaks loom keys. Rejected: WARNING and re-root (invalidates
  existing keys).
- **Unknown top-level key in a v3 file:** rejected at load. A v3 file
  carrying `files` is a botched hand edit that would silently lose pins.
- **`--namespace` on an existing registry with another namespace:** one
  `ERROR:` ("delete it to change the namespace"). The same namespace is a
  no-op. Silently keeping the old one would ignore an explicit flag.
- **DatasetPackage key and lookup scope:** the key is the caller's string
  as passed (it is also `.name`, which `input_datasets=` matching relies
  on), looked up ungated for **every** dataset, missing and remote names
  included, so `-e imdb:dataset_DatasetPackage` pins a remote dataset.
  With a registry loaded, each unpinned dataset logs one `untracked
  entity` WARNING.
- **The in-tree registry exclusion is a `WARNING:`**, once per run: it
  deviates from "list every packaged file".
- **The ceiling covers single-file datasets too**, not only directories.
- **Ignored directory names** (`build`, `dist`, `.venv`, VCS and cache
  names ...) are pruned inside a dataset directory too: one rule, shared
  with `id generate`, documented in `docs/python-api.md`. Rejected:
  pruning only VCS/cache names for datasets.
- **The "no `path=`" model WARNING fires only with a registry loaded.**
  Without one the hash only fills `verifiedUsing`, and a missing hash is
  normal absence (AGENTS.md "absent source data"), not a deviation.

## 4. v3 model and invariants

```text
key   = (compact type, name)   # _element_key(type, name): PEP 503 name for software_Package
entry = {spdxId, sha256?}      # sha256 whenever the harvested/registered element has one
```

- **I1, harvest records and never classifies.** Every named element with
  an `spdxId` and a compact type other than `"object"` is written under
  its own key, with `sha256_of(obj)` or no hash. `sha256_of()` lives in
  `export/spdx3_json.py`, lowercases, and replaces both extractors
  (problem 5).
- **I2, the lookup chooses the gate.** A gated lookup passes `sha256=`
  and hits only when the entry's sha256 is equal (case-insensitive). An
  entry with no sha256 never satisfies a gated lookup. An ungated lookup
  ignores the entry's sha256.
- **I3, candidate keys are ordered, and the first gated hit wins**, the
  same rule as today's `paths`/`names`. A lookup takes one type and a list
  of names, so mixing types cannot even be written.
- **I4, one key per id.** `_release_stale_keys_for_id` is kept over the
  one table. The src-layout alias exception keeps a second key for the
  same id only when all three hold: the types are equal; the sha256
  values are equal and not empty; the names are `_is_files_path_alias`
  suffixes of each other.
- **I5, ambiguity covers every key**, file paths included (problem 4).
  Both elements are skipped and any existing entry is left unchanged;
  `import_sbom` returns the key in its skipped set. A wheel whose two
  members normalise to one name (#251) is therefore no longer harvested
  for that name.
- **I6, typed ids (D2).** `register()` mints `type_id_prefix(type)`. A
  lookup can only return an id stored under the requested type (I3).
- **I7, determinism.** `save()` sorts every level and writes LF with a
  trailing newline, as today. Two saves of an unchanged registry are
  bit-for-bit identical, and `load(save(R)) == R`, `project_root`
  included.

## 5. API

The `id_registry/_*.py` modules are private; public names are re-exported
from `id_registry/__init__.py`. Load/save moves to a new `_format.py` so
`_registry.py` (303 lines) stays well under the limit.

v2 -> v3:

- `IdRegistry.files`, `.entities` -> `IdRegistry.elements:
  dict[tuple[str, str], RegistryEntry]`, plus `project_root: Path |
  None` (absolute, realpath'd). The keyword call shapes
  `IdRegistry(namespace=..., path=...)` and `IdRegistry.new("demo",
  path=...)` stay valid.
- `FileEntry`, `EntityEntry` -> `RegistryEntry(spdx_id: str, sha256: str
  | None = None)`; the sha256 is lowercased in `__post_init__`.
- `lookup_file(path, sha256)`, `lookup_entity(name, type)` ->
  `lookup(type, names, *, sha256=None) -> str | None`; `get(type, name)
  -> RegistryEntry | None`.
- `register_file(path, sha256)`, `register_entity(name, type)` ->
  `register(type, name, *, sha256=None) -> str`, by this table (D12):

  | existing entry | given `sha256` | result |
  | --- | --- | --- |
  | none | any | mint, store the sha (if any) |
  | yes, no sha | `None` | reuse, unchanged |
  | yes, with sha | `None` | reuse, unchanged (never erases a sha) |
  | yes | equal | reuse |
  | yes | differs, or entry had none | INFO `content changed`, mint, replace |

- `has_entity_named(name)` -> `has_name(name)` (any type).
- New `id_count()`: distinct spdxIds, the one count every summary uses.
- New `root_dir()`: `project_root`, else the registry file's directory,
  else cwd (all realpath'd).
- `harvest() -> (new_files, new_entities, changed)` -> `harvest() ->
  (new_ids, changed)`.
- `generate(paths, project_root, *, exclude=None)`: `exclude` is D7.
- `_entity_key(name, type)` -> `_element_key(type, name)`, still the
  single place where PEP 503 canonicalisation happens. **The argument
  order flips**; both are `str`, so a swapped call type-checks.
- `IdRegistrySession.file_id(...)`, `.entity_id(...)` ->
  `.lookup_id(claimant, type, names, *, sha256=None, on_miss=None)`. First
  claimant wins, unchanged.
- New public helpers: `persist_registry(registry, new_ids, changed)` (the
  save-and-log tail of `_sync_registry`, shared with loom; 8.4),
  `registry_key_for_path(registry, path)` (D9; 8.3), `type_id_prefix`,
  and the constants `FILE_TYPE`, `PACKAGE_TYPE`, `AI_PACKAGE_TYPE`,
  `DATASET_PACKAGE_TYPE` (replacing the hand-typed literals and
  `DIRECTORY_ENTITY_TYPE`/`PACKAGE_ENTITY_TYPE`).

`generate()` registers `(software_File, rel_path, sha256)` for each file,
and `(ai_AIPackage, stem, sha256)` for each model file (D3).

## 6. File format, version 3

As `save()` writes it (keys sorted at every level):

```json
{
  "elements": {
    "ai_AIPackage": {"tiny": {"sha256": "...", "spdxId": "...#AIPackage-4"}},
    "dataset_DatasetPackage": {"data/train": {"spdxId": "...#DatasetPackage-5"}},
    "software_File": {
      "src/demo": {"spdxId": "...#File-1"},
      "src/demo/x.py": {"sha256": "...", "spdxId": "...#File-2"}
    },
    "software_Package": {"requests": {"spdxId": "...#Package-3"}}
  },
  "namespace": "https://spdx.org/spdxdocs/demo-<uuid>",
  "project_root": ".",
  "version": 3
}
```

- Nested by type, as v2's `entities` was. Top-level keys are exactly
  `elements`, `namespace`, `project_root`, `version`; any other is
  rejected.
- `project_root` (D9) is required: a POSIX path relative to the registry
  file's directory (`..` allowed, e.g. a registry in `build/`). A
  non-string, `""`, a backslash, an absolute POSIX path or a Windows
  drive/UNC form raises `registry_file_error`. It is written with
  realpath on both sides and `.as_posix()`.
- `sha256` is omitted when absent, never written as `null`. `load()`
  rejects `null`, `""` or a non-string value, and any entry key other
  than `spdxId`/`sha256`.
- `load()` keeps every existing failure path unchanged: not found,
  unreadable, bad JSON (parsed from bytes, so a UTF-8 BOM still works),
  not an object, namespace, version, malformed entry, and a duplicate,
  which here means the same key after `_element_key` canonicalisation.
- Version error (D10), one `ERROR:` on every surface:

  ```text
  ID registry file <path>: version 2, expected 3 (no migration support -- delete it and re-run `pitloom id generate` or `pitloom id import`)
  ```

## 7. Lookup table after v3 (every caller)

| Caller (v2 anchor) | Type | Candidate names, in order | Gate |
| --- | --- | --- | --- |
| Project file (`_document_files.py:342`) | `software_File` | physical path (`project_relative_or_fallback`), then distribution path | sha256 |
| Directory (`_document_files.py:291`) | `software_File` | directory path | none |
| Own, dependency, phantom package (`_package_ids.py:71`); deployed package (`_document_deployed.py`) | `software_Package` | canonical name | none |
| AI model in a project or wheel (`ai.py:95`) | `ai_AIPackage` | name, path, stem (`_ai_model_entity_candidates`; a wheel's path is the raw archive name) | none (D16) |
| `loom model` / `enrich` (`_model_generator.py:151`, `:246`) | `ai_AIPackage` | stem | none (D16) |
| loom model (`_loom_active_run.py:109-126` today; 8.4) | `ai_AIPackage` | name, at `finalize()` | sha256 of the `path=` file if it is a regular file, else none |
| loom script (`_loom_active_run.py:407`) | `software_File` | D9 key (8.3) | sha256 |
| loom dataset package (new) | `dataset_DatasetPackage` | the caller's string | none, every dataset kind |
| loom dataset file (new, single-file dataset) | `software_File` | D9 key (8.3) | sha256 |

**Who writes the registry.** `id generate`/`id import`; the auto-harvest
in `_sync_registry` (`_generators_shared.py`), which excludes unhashed
`ai_AIPackage` and every `dataset_DatasetPackage` (D15); and, new, loom's
`finalize()`, which writes only `(ai_AIPackage, name, sha256)` on a gated
miss (D13). Loom never writes dataset, file or script entries.

## 8. Loom

### 8.1 Single-file dataset (D5)

`loom.add_dataset(path)` on a regular file emits:

- a `software_File`: name = the D9 key (8.3), else the caller's string;
  `software_fileKind = file`; `verifiedUsing` = its sha256; id = gated
  lookup of `(software_File, key)`, else minted with prefix `File`;
- a `dataset_DatasetPackage`: name = the caller's string, unchanged; id =
  ungated lookup of `(dataset_DatasetPackage, name)`, else minted with
  prefix `DatasetPackage`; `verifiedUsing` = its own copy of the file's
  sha256 (a separate `Hash` object, never shared), the rule G7 uses for
  AIPackage;
- `DatasetPackage contains File`.

The `trainedOn`/`testedOn` relationship, and every other relationship
loom emits today, stays on the DatasetPackage. There is no
`software_File` fallback key for the DatasetPackage (D2). One file
content is one element per run: `add_input_dataset("x")` then
`add_dataset("x")` share one `software_File` (a per-run cache), so a
second lookup never raises a spurious claim collision. A rewritten file
(new digest) is a new element.

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
- **`Hash.comment`** (precedent: the wheel root, `document.py:167-171`):
  `SHA-256 Merkle root over N files (path and content) in dataset
  directory, not a hash of a single artifact` ("1 file" when N is 1).
- **Reads:** chunked (1 MiB), one shared reader (`sha256_digest`, which
  `id_registry.sha256_file` also uses). Nothing is loaded whole.
- **Ceiling: `max-dataset-hash-bytes`**, default 4 GiB (4294967296),
  counting the total bytes hashed, for directory and single-file datasets
  alike. A config key only: no CLI flag, so no `_matrix_plan.py` entry and
  no INERT row. It reaches loom through `loom.Run(pitloom_config=...)`
  (D14), is validated at use (a positive `int`; `bool` and `0` rejected)
  by one validator generalised from `require_max_model_extract_bytes`, and
  gets a `docs/configuration.md` row. The size is checked from `stat()`
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
- **Lookup:** `(dataset_DatasetPackage, name)`, ungated. A directory
  dataset's id is pinned by name only.

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
- A model's key is its **name**, never the D9 path key; `path` only feeds
  the hash.
- `persist_registry` is `_sync_registry`'s tail, moved (not copied) so
  both writers log the same `ID registry: ...` lines. To survive two loom
  processes sharing one registry file, it re-loads the file just before
  saving, replays only this run's new entries, and saves atomically. No
  file locking; a lost update would only cause a re-mint on the next run,
  never a wrong id.
- Effect: training (`set_model(path=)`) and evaluation
  (`use_model(path=)`) fragments share one AIPackage id with no
  `id generate --entity`; a retrain gets a new id with one INFO.

## 9. Registry namespace (D8)

Today `IdRegistry.new` mints `doc_namespace(project, uuid4())`
(`_registry.py:68-70`), and `id import` into an empty registry adopts the
imported document's namespace (unchanged).

- Keep the UUID4, minted once when the registry is created. The registry
  is an *input*: a committed registry gives bit-for-bit-identical SBOMs,
  so determinism holds.
- **Add `id generate --namespace IRI`** (and `IdRegistry.new(...,
  namespace=)` for library parity) for an explicit, reproducible
  namespace. It must be an absolute IRI with a scheme and no `#`,
  validated through a new `core/iri.require_namespace_iri`; an invalid
  value exits 2 like any bad argument. `id import` has no `--namespace`.
- Rejected: `uuid5(PITLOOM_NS, project_name)`. Two unrelated projects
  called `demo` would get the same ids, and SPDX ids must be globally
  unique. Record this rejection in the implementation doc.
