---
Created: 2026-09-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry v3: one typed table, content gate chosen at lookup

See also: [id-registry-v3-build-notes.md](id-registry-v3-build-notes.md)
(what changed during the build), [id-registry-v3-rollout.md](id-registry-v3-rollout.md) (surfaces,
messages, commits, verification, out of scope; sections 10-14 continue
this file's numbering),
[id-registry-autosync.md](id-registry-autosync.md)
(v2 as built: harvest, stale-key release, ambiguity, claims),
[id-registry-followups.md](../design/id-registry-followups.md) (items v3 leaves
open), [ai-model-id-stability.md](../design/ai-model-id-stability.md),
[g7-ai-sbom-coverage.md](../design/g7-ai-sbom-coverage.md) (G7 #3 builds on this),
[id-registry-v3-loom.md](id-registry-v3-loom.md) (section 8),
[roadmap.md](../design/roadmap.md).

**Amended 2026-10-16 by [id-registry-path-keys.md](id-registry-path-keys.md):**
keys are path keys for anything with a file below the root (D3, D9, D16, I3,
I4 and the lookup table of section 7 are amended in place below); the file
shape is unchanged.

**Amended 2026-10-30 (#407, file version 4):** a `software_Package` key holds
the package's version (Q-D, [section 6.1](#61-package-keys-q-d-version-4)); D10,
section 4 and the package row of section 7 are amended in place.

**Status: built (PR #305, 2026-10-15).** The body below is the design as
agreed (user, 2026-09-30; D10 and the ceiling key confirmed 2026-10-14);
[id-registry-v3-build-notes.md](id-registry-v3-build-notes.md) records where
the code differs. The `file:line` anchors and "does not exist yet" remarks
were written against `5962a968` (post-#300), before the build: the code is
the authority. Registry v3 is its own PR, independent of G7 (order and base
branch: rollout, top). Lessons for the paper:
[id-registry-v3-lessons.md](sbom-generator-field-notes/id-registry-v3-lessons.md).

## 0. Revisions to the first draft (user, 2026-09-30)

The body reads as final. Moved since the first draft: D3 (the model sha256
is a gate), D12 (`register()` is uniform), D13 (loom resolves models at run
exit and **writes the registry**), D14 (`loom.Run(pitloom_config=)`), D15
(hashed AIPackages are auto-harvested). Decided: D10, the ceiling key, the
directory `Hash.comment` (8.2), and commit 2 fixing the ignored-name
check (rollout section 12).

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
   `tests/id_registry/shared.py`). One merged document can then
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
   (`IdRegistry.new`).
9. **Fragment merge by id ignores type** (`_MergeIndex.find_by_id`). A loom
   DatasetPackage and a project `software_File` that both hit `files[path]`
   fold together: `dataset_datasetType`/`dataset_dataPreprocessing` are
   lost, `trainedOn` points at a `software_File`, and the survivor depends
   on merge order.
10. **Loom probes with `Path.is_file()`, not `path_probe.is_regular_file`**,
    so a permission error differs per Python version (AGENTS.md).
11. **Loom's fallback ids are never stable.** Without a registry a loom id
    is `generate_spdx_id("DatasetPackage", name, doc_uuid)`: the name
    becomes the *document* name, and `doc_uuid` is a fresh UUID4 per run.
    Out of scope; recorded for the loom SDK work (G7 #7).

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
- **D3 (revised; amended by path keys: the entry is keyed by the model
  file's path key, not the stem, and no stem entry exists): `id generate`
  records the model file's sha256 on the `ai_AIPackage` entry, and the sha is
  a gate once recorded.** A
  retrained, re-exported or re-quantised model (different bytes) is a new
  model with a new id. Only a model with no single hashable file
  (sharded directory, remote, declared without `path=`) falls back to a
  name-only entry. Why (user): a retrained model is a new model.
  Rejected: the first draft's "record only, never a gate", which kept the
  id across retrains (the open question in
  [ai-model-id-stability.md](../design/ai-model-id-stability.md)). A stem
  several model files share has no one file to stand for it: `id generate`
  registered it with no hash (user ruling, 2026-10-15, per D12). Superseded:
  two models with one stem now have two path keys and two ids.
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
- **D10: no migration.** A v2 file, and since version 4 a v3 one, fails to
  load with one `ERROR:` telling the user to delete it and re-run `loom id
  generate` or `loom id import`; the file is left as it is. Why: private
  alpha, no compatibility code. Rejected for v3 (2026-10-30): loading a v3
  file and dropping its package entries with one `INFO:` (a silent loss of
  pins, and a second load path to keep).
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
  to a long-standing id). Harvest keeps a recorded sha too, with one
  exception (user ruling, 2026-10-15): `id import` of an unhashed gated
  element whose id differs from a hashed entry writes the imported id with
  no sha, with one INFO `content gate dropped`; a run's harvest leaves such
  an entry as is. To revisit after G7 #3
  ([build notes](id-registry-v3-build-notes.md)).
- **D13: loom resolves models at run exit and records them.** See 8.4.
- **D14: loom takes an explicit config.** `loom.Run(pitloom_config=
  PitloomConfig | str | Path | None)`. A path is loaded like `--config`
  (relative to cwd; missing -> `ValueError`). Loom reads three keys from
  it: `max-dataset-hash-bytes`, `update-id-registry`, and `id-registry`
  when the `id_registry=` argument is not passed. An explicit argument
  wins (the cascade). Every other key is documented as not applying to
  loom (a config key a surface can't use is documented, never warned).
  Loom never reads an implicit `[tool.pitloom]`. `load_config_file` raises
  `FileNotFoundError`; loom converts it to `ValueError`. It resolves a
  relative `id-registry` against the config file's directory, so a
  config-sourced registry path is config-file-relative, while an
  `id_registry=` argument stays cwd-relative (document both). Loom never
  saved the registry before and has no `update-id-registry` notion: both
  are new behaviour (D13). Why: parity with the
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
- **D16: the other AIPackage lookups stayed ungated in this PR** (project,
  wheel, `loom model`, embed). Superseded 2026-10-16: every model lookup is
  gated by the model file's SHA-256 and `ai_AIPackage.verifiedUsing` is
  emitted (G7 #3 part 1).

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
- **DatasetPackage key and lookup scope** (amended 2026-10-16): the key is
  the dataset's path key when it exists below the root, else the caller's
  string (also its `.name`, which `input_datasets=` matching relies on); a
  remote or missing name stays a name key, so `-e imdb:dataset_DatasetPackage`
  pins a remote dataset. The lookup is content-gated by the hybrid rule: a pin
  with no SHA-256 hits any content, an entry with one is gated.
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
key   = (compact type, name)   # _element_key(type, name): name@version for software_Package
entry = {spdxId, sha256?}      # sha256 only on software_File / ai_AIPackage, when the element has one
```

- **I1, harvest records and never classifies.** Every named element with
  an `spdxId` and a compact type other than `"object"` is written under
  its own key. Only `software_File` and `ai_AIPackage` entries (the
  content-gated types) get `sha256_of(obj)` or no hash; every other type
  never keeps one. `sha256_of()` lives in `export/hashes.py`,
  lowercases, and replaces both extractors (problem 5).
- **I2, the lookup chooses the gate.** A gated lookup passes `sha256=`
  and hits only when the entry's sha256 is equal (case-insensitive). An
  entry with no sha256 never satisfies a gated lookup. An ungated lookup
  ignores the entry's sha256.
- **I3, candidate keys are ordered, and the first gated hit wins** (amended:
  one lookup key per element, raw, then display-escaped, then a layout alias).
  A lookup takes one type, so mixing types cannot even be written.
- **I4, one key per id** (strict since 2026-10-16: the src-layout alias
  exception and `_is_files_path_alias` are gone). A run's harvest writes the
  key its lookup used; promoting a held layout alias replaces it.
- **I5, ambiguity covers every key**, file paths included (problem 4).
  Both elements are skipped and any existing entry is left unchanged;
  `import_sbom` returns the key in its skipped set. A wheel whose two
  members normalise to one name (#251) is therefore no longer harvested
  for that name.
- **I6, typed ids (D2).** `register()` mints `type_id_prefix(type)`. A
  lookup can only return an id stored under the requested type (I3).
- **I7, determinism.** `save()` sorts every level and writes LF with a
  trailing newline, as today. Two saves of an unchanged registry are
  bit-for-bit identical, and `load(save(R)) == R`, `project_root` and
  `id_counters` included.
- **I8, a retired id is never minted again** (user ruling, 2026-10-15,
  found by the order matrix). An id leaves the table when a harvest
  replaces its entry (a changed file's `project` run writes a document
  id) or a content change re-mints it; the number is still in older SBOMs
  and fragments, so minting it for another key would give two files one id
  across versions, and a same-type merge by id would fold them. The file
  keeps `id_counters`: for each id prefix, the highest number minted or
  seen in the registry's namespace. A mint takes one more than the
  counter and than every held id, and raises the counter at once; a
  harvest or `id import` raises it for every id of the registry's
  namespace it reads (stored, or skipped as ambiguous); an id in another
  namespace leaves it alone. `rebase()` merges counters by maximum, so no
  run lowers one, and a run that minted saves its counter even when its
  entries were replaced or refused. A harvest, `id import` or SBOM reserves
  numbers only up to 10**9 (a larger one cannot be minted past), and an id
  whose prefix is not a valid IRI segment (`/`, `?`, space, `#`, a
  lowercase `%xx`) reserves nothing; `register("")` raises. The
  `id_counters` check also applies on save. Rejected: deriving the counter from the
  held ids alone (that is the bug), and a counter per type rather than per
  prefix (the id text is what collides).

## 5. API

The `id_registry/_*.py` modules are private; public names are re-exported
from `id_registry/__init__.py`. Load/save moves to a new `_format.py` so
`_registry.py` (309 lines) stays well under the limit.

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
- New `id_counters: dict[str, int]` (also an `IdRegistry(...,
  id_counters=)` keyword) and `reserve_id(spdx_id)`, which harvest calls
  for every id it reads (I8).
- `harvest() -> (new_files, new_entities, changed)` -> `harvest() ->
  (new_ids, changed)`.
- `generate(paths, project_root, *, exclude=None)`: `exclude` is D7.
- `_entity_key(name, type)` -> `_element_key(type, name)`, still the
  single place where PEP 503 canonicalisation happens. **The argument
  order flips**; both are `str`, so a swapped call type-checks.
- `IdRegistrySession.file_id(...)`, `.entity_id(...)` ->
  `.lookup_id(claimant, type, names, *, sha256=None, on_miss=None)`. First
  claimant wins, unchanged.
- New public helpers: `save_registry(registry) -> Rebase`, the one routine
  every write goes through (`id generate`, `id import`, harvest, loom): it
  calls `rebase()` and saves only when the file differs. `Rebase` is
  `(refused, pending, added)`; `added` counts the distinct ids a save adds
  to the file that the table last read did not hold, under keys it did not
  hold. `persist_registry(registry, new_ids, changed)` (the
  save-and-log tail of `_sync_registry`, shared with loom; 8.4), now calls
  it and logs `added` (at most `new_ids`),
  `registry_key_for_path(registry, path)` (D9; 8.3), `type_id_prefix`,
  and the constants `FILE_TYPE`, `PACKAGE_TYPE`, `AI_PACKAGE_TYPE`,
  `DATASET_PACKAGE_TYPE` (replacing the hand-typed literals and
  `DIRECTORY_ENTITY_TYPE`/`PACKAGE_ENTITY_TYPE`).

`generate()` registers `(software_File, rel_path, sha256)` for each file,
and `(ai_AIPackage, stem, sha256)` for each model file (D3).

v2 behaviours v3 keeps:

- `IdRegistrySession` lookup retries each name display-escaped
  (`escape_display_controls`).
- `generate()` registers only files passing `is_model_candidate_name` plus
  `detect_ai_model_format != UNKNOWN` as models.
- `save()` writes via `canonical_json_indented`.

## 6. File format, version 3 (4 since #407)

As `save()` writes it (keys sorted at every level):

```json
{
  "elements": {
    "ai_AIPackage": {"tiny": {"sha256": "...", "spdxId": "...#AIPackage-4"}},
    "dataset_DatasetPackage": {"data/train": {"spdxId": "...#DatasetPackage-5"}},
    "software_File": {
      "src/demo": {"spdxId": "...#File-1"},
      "src/demo/x.py": {"sha256": "...", "spdxId": "...#File-6"}
    },
    "software_Package": {"requests": {"spdxId": "...#Package-3"}}
  },
  "id_counters": {"AIPackage": 4, "DatasetPackage": 5, "File": 6, "Package": 3},
  "namespace": "https://spdx.org/spdxdocs/demo-<uuid>",
  "project_root": ".",
  "version": 3
}
```

- Nested by type, as v2's `entities` was. Top-level keys are exactly
  `elements`, `id_counters`, `namespace`, `project_root`, `version`; any
  other is rejected.
- `id_counters` (I8) is required, `{}` in a registry that never minted or
  read an id of its namespace. A key is an id prefix as a mint writes it
  (`iri_segment` output: `File`, `Package`, ...; any prefix, since the
  library's `register()` takes any type); a value is a whole number from 1
  to 2^53 - 1 (the largest integer RFC 8785 writes as a number). A
  non-object, a key no mint could write, a boolean, zero, a negative, a
  float, a string or a larger number is rejected. A counter below a held
  id's number is read as that number, not rejected. In the example above
  `File-2` to `File-5` were issued once and have left the table. A mint
  past 2^53 - 1 is a `ValueError`; a harvested id with a larger number, a
  leading zero or non-ASCII digits is not a mint's shape and reserves
  nothing.
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
- Version error (D10), one `ERROR:` on every surface (version 4 and later
  wording; a v2 file says `version 2`):

  ```text
  ID registry file <path>: version 3, expected 4 (no migration support -- delete it and re-run `loom id generate` or `loom id import`)
  ```

### 6.1 Package keys (Q-D, version 4)

Built in #407. Version 4 differs from 3 only in the `software_Package` key:
`<PEP 503 name>[@<canonical PEP 440 version>]` (`package_key` in
`id_registry/_types.py`, re-exported from `keys.py`). Rulings (user,
2026-10-30):

- D1: a range dependency is keyed by the version the SBOM states (resolved
  from the lock file or the environment), not by its range.
- D2: no migration; a v3 file is the D10 `ERROR:` (above), never rewritten.
- D3: a `project` run of a dynamic-version project states `unknown` and keys
  its own package bare; a wheel or hook run states the version: two ids,
  documented in `docs/id-registry-keys.md`.
- D4: local and dev versions are distinct releases (`1.0+cu121` is not `1.0`).
- D5: old releases are never pruned.
- D6: the version part is `canonicalize_version` of
  `pitloom.core.pep440.parse_version` (bounded), the text as given when it
  does not parse, NFC; the bare key only for no stated version (`unknown`,
  `NOASSERTION`, blank). A bare key never matches a versioned one, with no
  fallback and no table scan. `@` and `%` in a non-PEP 508 name are written
  `%40`, `%25`, so the first `@` separates. Rejected: purl as the key (a
  second spelling of the same two facts), exact pins only (ranges would
  share ids), stripping local or dev labels.

`_element_key` rebuilds a package key from what it states
(`split_package_key`), so a load, `-e`, `get` and `register` normalise one
key to one fixed point (v3 stored `-e Requests@2.31.0` as `requests@2-31-0`).
The lookup (`IdRegistrySession.lookup_package`) records the key it used, and
harvest, `id import` and a merged fragment derive the same key from the
element's name and `software_packageVersion` (`_ambiguous._element_key_of`);
a drift test holds the two equal. `document.build` resolves and groups the
dependency strings once (`_dep_groups.group_dependencies`), before the
lookups, and both the pre-resolution and `add_dependencies` use those
groups: resolving twice repeated the conflict `WARNING:` lines and could let
two identity rules drift. Two versions of one dependency in one document are
two keys now, no longer an ambiguous name.

## 7. Lookup table after v3 (every caller)

| Caller (v2 anchor) | Type | Candidate names, in order | Gate |
| --- | --- | --- | --- |
| Project file (`_document_files.py`) | `software_File` | `keys.file_lookup_key` (path key, layout alias) | sha256 |
| Directory (`_document_files.py`) | `software_File` | directory path | none |
| Own, dependency, phantom package (`_package_ids.py`); deployed package (`_document_deployed.py`) | `software_Package` | `package_key(name, version)` (6.1) | none |
| AI model in a project or wheel (`ai.py`) | `ai_AIPackage` | its own `software_File`'s key | sha256 |
| `loom model` / `enrich` (`assemble/_model_generator.py`) | `ai_AIPackage` | `artifact_key(path=, name=stem)` | sha256 |
| loom model (`_loom_active_run.py`, `set_model`; 8.4) | `ai_AIPackage` | path key of `path=` (else name), at `finalize()` | sha256 of the `path=` file if it is a regular file, else none |
| loom script (`_loom_active_run.py`) | `software_File` | D9 key (8.3) | sha256 |
| loom dataset package (new) | `dataset_DatasetPackage` | path key if it exists, else the caller's string | digest (file sha256 / Merkle root); hash-less pin hits any content |
| loom dataset file (new, single-file dataset) | `software_File` | D9 key (8.3) | sha256 |

**Who writes the registry.** `id generate`/`id import`; the auto-harvest
in `_sync_registry` (`assemble/_generators_shared.py`), which excludes unhashed
`ai_AIPackage` and every `dataset_DatasetPackage` (D15); and, new, loom's
`finalize()`, which writes only `(ai_AIPackage, name, sha256)` on a gated
miss (D13). Loom never writes dataset, file or script entries.

## 8. Loom

Moved to [id-registry-v3-loom.md](id-registry-v3-loom.md), numbering kept:
8.1 single-file dataset (D5), 8.2 directory dataset (D6), 8.3 path base
for loom keys (D9), 8.4 loom models resolved at run exit (D3, D13).

## 9. Registry namespace (D8)

Today `IdRegistry.new` mints `doc_namespace(project, uuid4())`
(`IdRegistry.new`), and `id import` into an empty registry adopts the
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

## What changed during the build

Moved to [id-registry-v3-build-notes.md](id-registry-v3-build-notes.md), with
the rulings of the 2026-10-15 review round.
