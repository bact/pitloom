---
Created: 2026-10-15
Last-Modified: 2026-10-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: path keys (built)

See also: [id-registry-path-keys-decisions.md](id-registry-path-keys-decisions.md)
(decisions P1-P11, rejected options, review rounds, expected losses),
[id-registry-v3.md](id-registry-v3.md) (the design this extends; D- and
I-numbers refer to it),
[id-registry-v3-loom.md](id-registry-v3-loom.md),
[id-registry-followups.md](../design/id-registry-followups.md) (open items),
[g7-ai-sbom-coverage.md](../design/g7-ai-sbom-coverage.md) (G7 #3 part 1),
[ai-model-id-stability.md](../design/ai-model-id-stability.md).

**Status: built 2026-10-16** on top of registry v3 (PR #305); uncommitted
when this was written. The plan this records was a four-file design under
`design/` (removed); what follows is what the code does and why.

Question that started it (user, 2026-10-15): if an artifact's relative path
is stable (moving it breaks the app), does keying by that path reduce key
collisions? Answer, probed and then built: **yes for every artifact that has
a file under the registry root, provided every surface computes the key
through one helper; no for artifacts with no path** (dependencies, Hugging
Face models, remote datasets), which keep a name key. It also unblocked G7
#3 part 1 (gated model lookups, `ai_AIPackage.verifiedUsing`).

**No format bump** (user, 2026-10-15). v3 was never released, so key
semantics changed inside version 3: no v4, no migration code. The JSON shape
is unchanged; a registry written by the earlier v3 branch is regenerated, and
ids may renumber once.

## 1. Problem classes (K1-K17)

Probed 2026-10-15 in a scratch src-layout project (`src/demo/x.py`,
`models/{a,b}/model.npy`, `data/t.txt`), a monorepo copy and loom scripts.

| # | Class | Result |
| --- | --- | --- |
| K1 | src-layout split: `id generate` keys `src/demo/x.py`, a wheel looks up `demo/x.py` | Fixed: layout alias (section 3) |
| K2 | Two keys for one id (the I4 alias exception) | Fixed: strict one key per id; promotion replaces the alias key |
| K3 | sdist members carry a `name-version/` prefix nothing in the registry has | Fixed: the reader strips the top directory (section 6) |
| K4 | Registry root above the project (monorepo): project-side keys were project-relative | Fixed for `project` on a directory, the hook, `--allow-build`, `embed-wheel --project-dir`; **not** for plain `wheel`, `project <sdist>` (no `--project-dir` option, `_generators.py` never sets `project_dir` for an sdist), `embed-wheel` without `--project-dir` (follow-up P5b) |
| K5 | Dataset package keyed by the caller's string (`../data/t.txt` missed) | Fixed: path key when the path exists below the root |
| K6 | One dataset, two spellings, one run: two packages | Fixed: one package per (key, digest) per run |
| K7 | Case on a case-insensitive file system (`DATA/T.TXT`) | Fixed for user-typed paths: on-disk spelling; never case-folded |
| K8 | Unicode normalisation (NFD file, NFC script) | Fixed: every key is NFC |
| K9 | Shared-stem models (`models/a/model.npy`, `models/b/model.npy`) shared one id | Fixed: a model is keyed by its file's path; no stem key |
| K10 | Five candidate lists for one model (name, stem, path, own name) | Fixed: one model rule (section 2) |
| K11 | PEP 503 only for packages; a model or dataset `My_Model` vs `my-model` | Fixed for artifacts with a path (the path is the identity); name-keyed ones unchanged |
| K12 | Ambiguous-name harvest skip (I5) | Kept for packages and members that normalise alike; ambiguity is now judged on the WRITTEN key |
| K13 | Display-escaped retry (`id import` stores names as shown) | Kept: raw lookup first, escaped second, aliases after both |
| K14 | Directory keys (`demo` vs `src/demo`) | Not fixed (P8): a directory `software_File` keeps its distribution-path key (`demo`) and `id generate` does not index directories; the public docs state it as the exception to path keys |
| K15 | `--allow-build`: `physical_path` is a temp path | Fixed: `ProjectFile.built` flag; built files are keyed by distribution path |
| K16 | Same id, two contents in a merge | Fixed earlier (#305: `hash_conflict`, `rename_id_clash`) |
| K17 | Harvest re-keys by `.name`: a merged loom fragment's model lost its key | Fixed: harvest by recorded lookup key (section 4) |

G7 blockers 1 (retrains laundered into old ids through ungated lookups) and
2 (harvest keys `.name`, `id generate` keys the stem) are closed by K17 and
the content gate (section 5).

## 2. Design

**Two-tier key.** Tier 1, a path key: root-relative (the registry's stored
`project_root`), `/`-separated, NFC, never case-folded; on-disk spelling for
a path a user typed (a loom path, the `model`/`enrich` argument,
`id generate PATH` and `-e`). Used for every `software_File`, a model's
`ai_AIPackage` (the key of its model file, the same text as its
`software_File`) and a loom dataset package whose path exists below the root
at declaration. Tier 2, a name key (unchanged): packages (PEP 503), Hugging
Face and pathless models, URL, remote or missing datasets, anything outside
the root.

**One helper** (`pitloom.id_registry.keys`: `path_key`, `artifact_key`,
`file_lookup_key`, `project_prefix`, `join_key`, `alias_candidates`,
`is_layout_alias`) computes every key; a surface never spells one by hand.
`LookupKey(key, alias, path, base)` carries the alias mode (`NONE`,
`CANONICAL`, `LAYOUT`) and the project prefix below which the alias is taken.

**One model rule.** One model file gets one id on every surface (project,
`--allow-build`, wheel, `embed-wheel`, hook, library API, `model`, `enrich`,
loom `set_model`/`use_model`, `id generate`, `id import`). A scanned model's
key is the key of its own `software_File` in the same document. No stem keys,
own-name keys or candidate lists; two models with one stem now have two keys
and two ids; the shared-stem `INFO:` is gone. `id generate` registers each
model under its file's key with the file's SHA-256. A model not among the
document's files (outside the root) is not looked up.

**Lookup order** in `IdRegistrySession.lookup_key`: raw exact, display-escaped
exact, alias (only when the mode is not `NONE` and a SHA-256 is given), claim,
then record the key (a hit under `LAYOUT` records the HELD key; `CANONICAL`
records the lookup key).

## 3. Derived layout alias

A derived rule, not a stored table: the same file under a `src/` or `lib/`
layout and its installed path. Rules, all four required:

1. The first part below the project prefix is exactly one of `LAYOUT_ROOTS`
   (`src`, `lib`); two parts remain (a directory and a file).
2. Not a `*.data` member (a wheel `.data` file installs outside the package).
3. Equal SHA-256 (an alias lookup needs a hash; an ungated lookup has none).
4. Unique candidate (a tie is a miss with one `INFO:`), and the SHORTER key
   must not exist as a real file or directory under the registry root: two
   real files are never an alias.

Candidates are O(1) dict lookups (`registry.get`), never a scan. Directions:
a wheel, built or embed key `demo/x.py` hits a held `src/demo/x.py`
(`LAYOUT`; the held key is kept); a canonical lookup `src/demo/x.py` hits a
held `demo/x.py` and promotes it (`CANONICAL`; harvest then replaces the held
key). `id generate` promotes a held alias to the canonical key (one `INFO:`
count). Typed paths (loom model/file, `model`, `enrich`) use `CANONICAL` so
they reuse a wheel-minted id. Other layouts (`python/`, `packages/`) get no
alias: a wheel-only run mints its own ids for them (two keys).

**Why it was narrowed.** The plan said "exactly one leading part, any
directory". An independent review found three failures of that loose rule at
once: (a) identity theft: with `tests/foo/__init__.py` and `foo/__init__.py`
both real and equal bytes (`__init__.py` empty), the wheel's `foo/__init__.py`
took the id held for `tests/foo/__init__.py`; (b) a candidate search over
every held key made a lookup quadratic in the registry; (c) zebra empty
`__init__.py` files: every empty file is equal to every other, so hash
equality alone binds unrelated files. Fix: restrict the first part to
`src`/`lib`, build the candidates by construction (at most one held key per
root), and require the shorter key to be absent on disk (the stale-key case
that remains is a real alias). Mutation targets: the `LAYOUT_ROOTS` check, the
on-disk existence test, the tie-break.

## 4. Harvest

- **Recorded key.** A run writes each element under the key its lookup used
  (`session.recorded_keys()` into `exporter.registry_keys`), not its `.name`.
- **R-keep.** An element with no recorded key (a merged loom fragment,
  `id import`) never moves an id the registry holds under another key of the
  same type. Merged fragments keep the path key (K17). Decided once before
  the writing pass (`_harvest._r_kept`, repeated until no pair is added: a
  skipped element frees no key): a live check made `id import` depend on
  spdxId order and need a second run to settle.
- **Strict one key per id.** Promotion replaces the alias key; the I4 alias
  exception (`_is_alias`, `_is_files_path_alias`) is gone.
- Ambiguity (two elements with one written key) is skipped as before.
- Promotion and R-keep never mint and never touch `id_counters`;
  `Rebase.added` does not count a re-keyed id; `replay_changes` treats a
  promotion as one change.
- Models are harvested (hashed). Dataset packages are never auto-harvested.
- `id import`: a hashed model takes the key of the unique same-hash
  `software_File` in the same document, else its name plus an `INFO:`; a
  dataset package takes its path key when the name exists below the root
  (`id_registry/import_keys.py`).

## 5. Content gates (G7 #3 part 1)

- **Models.** `ai_AIPackage.verifiedUsing` carries the model file's SHA-256
  (project, wheel, embed, hook, `model`; an `enrich` fragment has no
  `AIPackage`, so only the gate applies). Every model lookup is gated by it:
  retrained bytes at the same path are a new id; a hash-less model entry
  never hits. A fresh `Hash` per element, never shared with the file.
- **Datasets: hybrid gate.** A package pin with NO SHA-256 (`-e`/`id import`
  of a name that did not exist yet, old pins) hits any content, with an
  `INFO:` that content was not checked. An entry WITH a SHA-256 is
  content-gated (file SHA-256 or directory Merkle root from
  `core/dataset_hash.py`, the same digest as the package `verifiedUsing`): a
  refreshed dataset is a new package id; adding a file to a directory dataset
  changes its Merkle root and re-mints the id. `id generate -e
  NAME:dataset_DatasetPackage` stores the canonical path key and the digest
  when NAME exists; `id import` of a loom fragment records dataset package
  digests (a run's auto-harvest never does).
- **Per run**: one package per (key, digest): `data/t.txt`, `./data/t.txt`,
  `../data/t.txt` from `scripts/`, absolute, another case and NFC/NFD are one
  package when the path exists below the root; a missing or outside-the-root
  dataset is keyed by the exact string, so two spellings are two packages.
  `input_datasets=` does NOT match through the key: `names_of` returns the
  spellings the input was declared under, so `data/t.txt` after
  `add_input_dataset("../data/t.txt")` warns and skips the link (probed
  2026-10-16; open item in the follow-ups).

## 6. Other mechanisms

- **sdist.** `ProjectFile.physical_path` is project-relative (the top
  `name-version/` directory stripped: the directory holding the first root
  `PKG-INFO`); `distribution_path` is unchanged and no provenance `Source:`
  string changed.
- **`ProjectFile.built`** marks a file extracted from a just-built wheel
  (no source path); `FilesOrigin(project_dir, archive, sdist)` on
  `DocumentModel` says how a file list was produced. Both are explicit flags
  because "an absolute path means built" is wrong for an included file outside
  the project but inside a monorepo root. Set at every `DocumentModel(`
  site from one shared helper.
- **`-e NAME:TYPE`** with `dataset_DatasetPackage`, `ai_AIPackage` or
  `software_File` and NAME an existing regular file (a dataset: file or
  directory) below the root stores the canonical path key and digest, `INFO:`
  when the key differs from the text; otherwise by name with an `INFO:` naming
  the reason (an `ai_AIPackage` name pin applies only to a model with no
  file). Other types verbatim.
- **R4 rules** (2026-10-16, after the review rounds in the decisions doc).
  A merged fragment's element with an older SHA-256 than its entry never rolls
  the entry back (`content gate kept ... element id X with an older SHA-256`);
  a hashed fragment model is recorded only under its same-hash file's key,
  else `model X not recorded: no unique file with its SHA-256`; `id import`
  keys a fragment's datasets and models by their same-hash file and files
  under their distribution path or one held layout alias; `id generate -e` on
  a hash-less dataset pin adopts the digest and keeps the id (`pin now gated
  by its SHA-256`), another recorded digest mints a new id; each document
  reserves every id held under a `software_File`, `software_Package`,
  `dataset_DatasetPackage` or
  `ai_AIPackage` key (`_document_deployed._LOOKED_UP_TYPES`), so a miss never
  mints a held id. `SoftwareAgent` and `Tool` are not reserved: their held ids
  are their own and reserving them renumbers harvested ids; nor is the id held
  under a model card dataset's name (`_model_dataset_keys`, minted with no
  lookup: reserving it renumbered an imported model card dataset on every
  `id import`).
- **NFC.** Every registry key is NFC (a load of an NFD key becomes NFC); two
  on-disk files equal after NFC are both skipped by `id generate` with one
  `WARNING:`.
- **Monorepo** (registry root above the project): `project` on a directory,
  the hook, `--allow-build` and `embed-wheel --project-dir` key below the
  project prefix (`pkgs/demo/...`), the alias taken below that prefix. Limit:
  plain `wheel`, `project <sdist>` and `embed-wheel` without `--project-dir`
  key by the archive's own paths, so they miss with no `INFO:` and a harvest
  writes root-level keys (`demo/x.py` beside `pkgs/demo/src/demo/x.py`, probed
  2026-10-16); a registry root equal to the project
  root works everywhere. A force-included file outside the project but inside
  the root is keyed from the root; under `--allow-build` built files have no
  source path and cannot match their `id generate` key.
- **`INFO:` for every deviation** (user rule): every fallback, cap or
  deviation prints one `INFO:` with the `ID registry:` prefix, once per
  document, element or pin, never per file in a loop. The family is in the
  code (`FALLBACK_KEYS_INFO`, `NAME_KEY_INFO`, `DATASET_NAME_KEY_INFO`,
  `MODEL_GATE_MISS_INFO`, `HASHLESS_PIN_INFO`, `LAYOUT_ALIAS_*`,
  `ENTITY_*`, `MODEL_NAME_KEY_INFO`); grep the constants, do not retype the
  wording here.

## 7. Closed by this work

Items moved from [id-registry-followups.md](../design/id-registry-followups.md):

- Wheel/sdist targets and src-layout ids (K1-K3, K15), both orders.
- G7 blockers 1 and 2; the `id import` sha-drop revisit (an imported model
  now carries its own hash).
- "AIPackage lookups outside loom stay ungated".
- A local dataset package keyed by the caller's string (K5, K6); the same
  dataset declared in several spellings.
- Case-insensitive file system keys (K7); NFC (K8).
- Two model files with one stem registered name-only (K9).
- Two alias rules for one fact (`_is_files_path_alias` and `_DeclaredRegistry`
  now share `keys.is_layout_alias`/`walk_rules.shortened_by`).

Final counts: full suite 13461 passed / 63 skipped / 100% branch; manual
runner 524 pass / 0 fail / 29 known / 23 skip (baseline 504/0/14/23; the 15
new known entries are the existing per-document-entity entry on new
profiles); pyrefly about 76 against a baseline of 66 (all in `scripts/`; to be
fixed).
