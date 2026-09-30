---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry v3: one typed table, content gate chosen at lookup

See also: [id-registry-autosync.md](../implementation/id-registry-autosync.md)
(v2 as built: harvest, stale-key release, ambiguity, claims),
[id-registry-followups.md](id-registry-followups.md) (open v2 items),
[ai-model-id-stability.md](ai-model-id-stability.md),
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md) (G7 #3 builds on this),
[id-registry-v3-rollout.md](id-registry-v3-rollout.md) (surfaces, commits,
verification), [roadmap.md](roadmap.md).

**Status: design, not built. This file and its rollout file are the
implementers' brief.**
Registry v3 is its own PR, independent of G7. It is cross-cutting and
touches every surface. Decisions marked **(user)** are final. Items
marked **(proposed)** need the user's confirmation before the commit
that uses them.

Order (user): PR D (step 10, #251, step 9) -> small follow-up PRs -> **this
PR** -> surface-parity/config/docs sweep -> 0.20.0 -> G7. Base the branch
on a main that already has:

- **D:** its fixture carries `demo/tiny.safetensors` and `demo/load.py`,
  and usage `hasDataFile` edges are off by default.
- **#251 / DQ-2:** wheel member names are normalised, and those names
  become file keys.
- **The IRI-encoding change:** `core/iri.doc_namespace` and
  `iri_segment`, which `IdRegistry.new` and `generate_spdx_id` use.

Re-verify every `file:line` below against that main before coding. The
anchors here are from `bbf5808`/`fe9f366`.

## 0. Open items (handed off 2026-09-30)

D8, D9 and D11 are decided (user, 2026-09-30). The next session assesses
the rest and asks the user about each:

- **D10:** no v2 migration.
- **Ceiling key (8.2):** its name (proposed `max-dataset-hash-bytes`), its
  default, and whether it gets a CLI flag.
- **Wording:** the dataset directory `Hash.comment` (8.2).
- **Commit 2:** whether it also fixes the `_is_eligible_file`
  absolute-path bug (rollout, section 14).

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
otherwise.

Problems:

1. **Misfiling by shape.** No shape rule is right for every caller: a
   hashed AIPackage needs `entities`, a hashed loom dataset needs `files`.
2. **Ids cross types.** `files` has no type in its key, so loom reuses
   `id generate`'s `#File-N` id for a `dataset_DatasetPackage` (see
   `tests/id_registry/shared.py`). One merged document can then hold two
   elements of different types under one id.
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
   (`_registry.py:69`).
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
    (`_loom_active_run.py:68`). This is out of scope here, but record it
    for the loom SDK work (G7 #7).

## 3. Decisions

- **D1 (user): one table, typed keys.**
  - Key: `(compact type, name)`, where the name is the path for a file
    or directory.
  - Entry: `{spdxId, sha256?}`.
  - Harvest never classifies.
  - Each lookup decides whether the content has to match.
- **D2 (user, Q2): ids are typed.**
  - Inside our own namespace, an spdxId's fragment prefix equals the
    element's type prefix (`_type_id_prefix`; e.g. `File`, `Package`,
    `AIPackage`, `DatasetPackage`).
  - The registry never hands an id to another type.
  - A drift test covers our namespace only. Imported or foreign ids are
    exempt.
- **D3 (user, Q3):** `id generate` records the model file's sha256 on the
  `(ai_AIPackage, stem)` entry. It is recorded only, never used as a gate
  (see [ai-model-id-stability.md](ai-model-id-stability.md)).
- **D4 (user, Q4):** one count in the log line: `added N new id(s)`.
  - logfmt quoting of `KEY=VALUE` lines is a separate PR (P1), not this
    one.
- **D5 (user, Q1): loom datasets become packages that contain files.** See
  section 8. This is the last code commit of this PR.
- **D6 (user): directory dataset.**
  - Emit only the DatasetPackage, with a path-aware Merkle root.
  - Per-member `software_File` elements are a later opt-in.
  - The hashing ceiling is its own new config key.
- **D7 (user, P13): the resolved registry file is itself excluded** from
  project file discovery and from `id generate` indexing. It lands as a
  commit of this PR unless it has already merged on its own.
- **D8 (user): the namespace for `id generate`.** Keep a UUID4 minted once
  at creation, and add `--namespace`. See section 9.
- **D9 (user): loom path base.** The registry stores `project_root`.
  Loom keys a file relative to it. See section 8.3.
- **D11 (user): merge by id requires the same type (problem 9).**
  A fragment element whose id matches an existing element of another type
  logs one `WARNING:` and gets a freshly minted id. It is never folded in.
  - Under D2 this can only happen with foreign ids, or registries from
    before v3.
  - The reason for a new id: a WARNING plus a remap matches the
    registry's claim-collision rule (`warn_claim_collision`), loses no
    data, and never leaves two elements with one id.
  - Hash merge is already type-scoped (`(type, sha256)` index), so it
    does not change.
- **D10 (proposed): no migration.** A v2 file raises the existing version
  error ("delete it and re-run `pitloom id generate` or `pitloom id
  import`"). This is a private alpha, so there is no compatibility code.

## 4. v3 model and invariants

```text
key   = (compact type, name)   # _element_key(type, name): PEP 503 name for software_Package
entry = {spdxId, sha256?}      # sha256 whenever the harvested/registered element has one
```

- **I1, harvest records and never classifies.** Every named element with
  an `spdxId` and a compact type is written under its own key, with
  `sha256_of(obj)` or no hash. `sha256_of()` lives in
  `export/spdx3_json.py` and replaces both extractors (problem 5).
- **I2, the lookup chooses the gate.**
  - A gated lookup passes `sha256=` and hits only when the entry's sha256
    is equal.
  - An entry with no sha256 never satisfies a gated lookup.
  - An ungated lookup ignores the entry's sha256.
- **I3, candidate keys are ordered, and the first raw hit wins.** This is
  the same rule as today's `paths`/`names`. A caller may list keys of one
  type only (D2): a helper builds the keys from one type and a list of
  names, so mixing types cannot even be written.
- **I4, one key per id.** `_release_stale_keys_for_id` is kept over the
  one table. The src-layout alias exception keeps a second key for the
  same id only when all three hold:
  - the types are equal;
  - the sha256 values are equal and not empty;
  - the names are `_is_files_path_alias` suffixes of each other.
- **I5, ambiguity covers every key**, file paths included (problem 4).
  Directories and packages keep today's behaviour.
- **I6, typed ids (D2).** `register()` mints with `_type_id_prefix(type)`.
  A lookup can only return an id stored under the requested type (I3).
- **I7, determinism.** `save()` sorts every level and writes LF with a
  trailing newline, as today. Two saves of an unchanged registry are
  bit-for-bit identical.

## 5. API

The `id_registry/_*.py` modules are private. The public names are
re-exported from `id_registry/__init__.py`.

v2 -> v3:

- `IdRegistry.files`, `.entities` -> `IdRegistry.elements:
  dict[tuple[str, str], RegistryEntry]`.
- `FileEntry`, `EntityEntry` -> `RegistryEntry(spdx_id: str, sha256: str
  | None = None)`. The sha256 is lowercased in `__post_init__`, as
  `FileEntry` does.
- `lookup_file(path, sha256)`, `lookup_entity(name, type)` ->
  `lookup(type, names, *, sha256=None) -> str | None`.
- `register_file(path, sha256)`, `register_entity(name, type)` ->
  `register(type, name, *, sha256=None) -> str`.
  - It reuses the id when the key exists and any given sha256 is equal.
  - Otherwise it mints a new id. When it replaces a changed entry, it
    logs the existing `content changed ... minting a new spdxId` INFO.
- `has_entity_named(name)` -> `has_name(name)` (any type).
- `harvest() -> (new_files, new_entities, changed)` -> `harvest() ->
  (new_ids, changed)`.
- `_entity_key` -> `_element_key`, still the single place where PEP 503
  canonicalisation happens.
- `IdRegistrySession.file_id(...)`, `.entity_id(...)` ->
  `.lookup_id(claimant, type, names, *, sha256=None, on_miss=None)`. First
  claimant wins, unchanged.
- `_SpdxIdIndex.files`/`.entities` -> `_SpdxIdIndex.keys: dict[str,
  set[tuple[str, str]]]`.

`generate()` registers `(software_File, rel_path, sha256)` for each file,
and `(ai_AIPackage, stem, sha256)` for each model file (D3).

## 6. File format, version 3

```json
{
  "version": 3,
  "namespace": "https://spdx.org/spdxdocs/demo-<uuid>",
  "project_root": ".",
  "elements": {
    "ai_AIPackage": {"tiny": {"spdxId": "...#AIPackage-1", "sha256": "..."}},
    "dataset_DatasetPackage": {"data/train": {"spdxId": "...#DatasetPackage-1"}},
    "software_File": {
      "src/demo": {"spdxId": "...#File-1"},
      "src/demo/x.py": {"spdxId": "...#File-2", "sha256": "..."}
    },
    "software_Package": {"requests": {"spdxId": "...#Package-3"}}
  }
}
```

- The file is nested by type, as v2's `entities` was.
- `project_root` (D9) is required, and must be a relative POSIX path
  string. An absolute path, a backslash or a non-string raises
  `registry_file_error`.
- `sha256` is omitted when absent, never written as `null`. `load()`
  rejects `null` or a non-string value through `_require_scalar_str`, and
  rejects any unknown entry key with `registry_file_error` (keys: `spdxId`,
  `sha256`).
- `load()` keeps every existing failure path unchanged: not found,
  unreadable, bad JSON, not an object, namespace, version, malformed
  entry, and a duplicate, which here means the same key after
  `_element_key` canonicalisation.

## 7. Lookup table after v3 (every caller)

Format: caller (v2 anchor) -- type -- candidate names, in order -- gate.

- Project file (`_document_files.py:342`) -- `software_File` -- physical
  path (via `project_relative_or_fallback`), then distribution path --
  sha256.
- Directory (`_document_files.py:291`) -- `software_File` -- directory
  path -- none.
- Own, dependency or phantom package (`_package_ids.py:71`) and deployed
  package (`_document_deployed`) -- `software_Package` -- canonical name
  -- none.
- AI model in a project or wheel (`ai.py:95`) -- `ai_AIPackage` -- name,
  path, stem (`_ai_model_entity_candidates`) -- none.
- `loom model` (`_model_generator.py:176/271`) -- `ai_AIPackage` -- stem
  -- none.
- loom model (`_loom_active_run.py:119`) -- `ai_AIPackage` -- name --
  none.
- loom script (`_loom_active_run.py:407`) -- `software_File` -- path
  (8.3) -- sha256.
- loom dataset package (new) -- `dataset_DatasetPackage` -- dataset name
  -- none.
- loom dataset file (new, single-file dataset) -- `software_File` -- path
  (8.3) -- sha256.

Auto-harvest's `_AUTO_HARVEST_EXCLUDED_TYPES` (`ai_AIPackage`,
`dataset_DatasetPackage`, `_generators_shared.py:40`) stays unchanged: a
run still never writes those two types. `id import` and `id generate`
still do.

## 8. Loom datasets (D5, D6)

### 8.1 Single-file dataset

`loom.add_dataset(path)` on a regular file emits:

- a `software_File`:
  - name: the path (section 8.3);
  - `verifiedUsing`: the sha256;
  - id: gated lookup of `(software_File, path)`, else minted with prefix
    `File`;
- a `dataset_DatasetPackage`:
  - name: the dataset name;
  - id: ungated lookup of `(dataset_DatasetPackage, name)`, else minted
    with prefix `DatasetPackage`;
  - `verifiedUsing`: a copy of the file's sha256, which is the same rule
    G7 uses for AIPackage;
- `DatasetPackage contains File`.

The `trainedOn`/`testedOn` relationship, and every other relationship
loom emits today, stays on the DatasetPackage.

There is no `software_File` fallback key for the DatasetPackage (D2).

### 8.2 Directory dataset

- **Output:** only the DatasetPackage, with `verifiedUsing` set to the
  Merkle root (D6).
- **Leaves:** the files under the directory, walked with the shared
  `_iter_files` rules (`_IGNORED_DIR_NAMES`), with the registry file
  excluded (D7).
- **Leaf hash:** `sha256(posix_relpath_utf8 + b"\x00" + file_digest)`,
  where `file_digest` is the raw 32-byte SHA-256, not hex. Leaves are
  sorted by relpath (bytewise UTF-8), and `relpath` is relative to the
  dataset directory.
  - A one-file directory's root is that single leaf, which differs from
    the file's own sha256. So a directory dataset never hash-merges with a
    single-file dataset of the same bytes: the merge hash index is keyed
    by `(type, sha256)`, and both are `dataset_DatasetPackage`.
  - A test pins this.
- **Root:** the leaves pass through the existing
  `core.models._build_merkle_tree`. Its rule that an unpaired node is
  promoted unchanged is kept, so there is one tree algorithm.
- **Why the path is in the leaf:** wheel leaves are content-only, so
  renaming a file would not change a wheel root. That is acceptable for a
  wheel, but not for a dataset.
- **`Hash.comment`:** the precedent is the wheel root at `document.py:166`.
  Proposed wording: `SHA-256 Merkle root over <n> files in the dataset
  directory (leaf = sha256(relpath NUL file sha256)), not a hash of a
  single artifact`.
- **Reads:** chunked, through `sha256_file` (1 MiB chunks). Nothing is
  loaded whole.
- **Ceiling:** a new config key (D6), counting the total bytes hashed.
  - Proposed name: `max-dataset-hash-bytes`.
  - Its default and a CLI flag need a decision.
  - Over the ceiling: no hash and one `WARNING:` naming the directory and
    the limit.
  - It goes into the cascade (CLI > config > default) and gets an entry
    in `scripts/manual_cli_checks/_matrix_plan.py`.
  - It also gets a row in the inert-options table for every target kind
    it doesn't apply to.
- **Empty directory:** no hash, silently. This is absent data, not an
  error.
- **Unreadable member:** the `path_probe` warning (`UNREADABLE_FILE_WARNING`)
  for that file, and **no root at all**. A root computed over part of the
  directory would be wrong.
- **Probing:** every loom path check (file, directory, missing) goes
  through `path_probe.is_regular_file` and `os.path.isdir`, never
  `Path.is_file()` (problem 10). A missing path stays silent: no hash, no
  lookup, as today.
- **Lookup:** `(dataset_DatasetPackage, name)`, ungated. A directory
  dataset's id is pinned by name only.

### 8.3 Path base for loom keys (D9, user)

Loom keys a file by the absolute path resolved from the process cwd, made
relative to the **registry's project root**, as a POSIX string. The
registry's project root is the directory `id generate` indexed against.

This matches `id generate`'s keys whichever directory the script runs
from.

- **Outside the root, or no registry loaded:** keep the caller's string
  as the element name, and make no lookup. When a registry is loaded,
  log one `WARNING:`.
- **Decided (user):** the v3 format stores `project_root` as a POSIX path
  relative to the registry file's own directory (section 6).
  - `id generate` writes it from its `--project-dir`. `id import` writes
    it from the cwd, which is the same base `id import` resolves paths
    against today.
  - Every reader resolves it against the registry file's directory, so
    moving the project and its registry together keeps working.
  - Rejected: assuming the registry file's directory is the root. That
    breaks for `-o build/reg.json`.

## 9. Registry namespace (D8, user)

Today `IdRegistry.new` mints `doc_namespace(project, uuid4())`, and `id
import` adopts the imported document's namespace.

- **Decided (user):** keep the UUID4, minted once when the registry is
  created.
  - The registry is an *input*: a committed registry gives
    bit-for-bit-identical SBOMs, so determinism holds.
  - A name-derived namespace would give two unrelated projects called
    `demo` the same ids. SPDX ids must be globally unique.
- **Add `id generate --namespace IRI`** for an explicit, reproducible
  namespace. It is validated as an IRI through `core/iri`.
- The alternative, `uuid5(PITLOOM_NS, project_name)`, is rejected for the
  collision reason above. Record that rejection in the implementation doc.

Rollout (surface impact, messages, commits, verification, out of scope):
[id-registry-v3-rollout.md](id-registry-v3-rollout.md).
