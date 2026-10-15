---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: path keys (plan)

See also: [id-registry-v3.md](../implementation/id-registry-v3.md) (the built
design; D- and I-numbers below refer to it),
[id-registry-v3-loom.md](../implementation/id-registry-v3-loom.md) (8.3, the
D9 path base), [id-registry-followups.md](id-registry-followups.md) (open items
this plan closes or leaves), [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md)
(G7 #3), [ai-model-id-stability.md](ai-model-id-stability.md).

**Status: plan, not built.** Immediate follow-up to registry v3 (PR #305).
Question (user, 2026-10-15): if an artifact's relative path is stable (its
place in the source tree or the wheel; moving it breaks the app), does keying
by that path reduce key collisions? Short answer, checked against the code
and by probes below: **yes for every artifact that has a file under the
registry root, provided every surface computes the same path through one
helper; no for artifacts with no path** (dependencies, Hugging Face models,
remote datasets), which keep a name key.

**Decided (user, 2026-10-15): no format version bump.** v3 was never released,
so the key semantics change inside version 3: no v4, no migration code, no new
hard `ERROR:` path. The JSON shape (`elements`/`id_counters`/`namespace`/
`project_root`/`version`, entry `{spdxId, sha256?}`) does not change. Any v3
file written by the current branch (for example
`examples/sentimentdemo-aibom/loom-id-registry.json`) is regenerated, not
migrated; docs and skills describing the v3 file shape stay valid, and only
their statements about which name an entry is keyed by change.

## 1. Problem: every collision and miss class today

Probes were run on 2026-10-15 against the working tree (registry-v3 branch
plus the uncommitted v3 fix round) in a scratch src-layout project
(`src/demo/x.py`, `models/{a,b}/model.npy`, `models/solo.npy`, `data/t.txt`),
a monorepo copy, and loom scripts. "Probed" marks a reproduced result.

Surfaces: `project` (directory, `--allow-build`, sdist target), `wheel`,
`embed-wheel`, `env`, `generate` (auto-detect, delegates), `model`, `enrich`,
the Hatchling hook, the library API (`generate_project_sbom()` and siblings),
`loom.Run` (datasets, files, script, models), `id generate`, `id import`,
merge/fragment harvest, the GitHub Action (wraps the CLI) and the skills
(`skills/sbom-generate/references/id-registry.md` and friends).

| # | Class | Surfaces | Where in the code |
| --- | --- | --- | --- |
| K1 | **src-layout split**: `id generate` keys `src/demo/x.py`; a wheel looks up `demo/x.py` (physical = `orig_filename`, distribution = normalised name). Misses unless a `project` harvest first wrote the alias key. Probed: an `id generate`-only registry gave every wheel file a document id, and the harvest then added `demo/x.py` under that **new** id, so one file has two ids in one registry. | wheel, embed-wheel, `--allow-build` | `_resolve_file_and_directory_hits` (`assemble/spdx3/_document_files.py`); `_hash_wheel_entry` (`extract/wheel.py`) |
| K2 | **Two keys, one id** (the intended alias): a `project` run writes `demo/x.py` beside `src/demo/x.py` with the same id (probed). Kept by I4's exception (`_is_alias`, `_is_files_path_alias` in `_harvest.py`); a second alias rule lives in `walk_rules.RegistryCopy`/`_DeclaredRegistry`. Reverse order (`id generate` after a wheel harvest) splits ids (order matrix `O1/src/fresh-cli`). | project, hook, wheel, id generate | `_release_stale_keys_for_id`, `_is_alias` |
| K3 | **sdist prefix**: members are `demo_pkg-1.0.0/src/demo/x.py`; nothing in the registry has that prefix. Probed: every file missed and the harvest added 21 prefixed keys. | project `<sdist>` | `_sdist_scan` (`physical_path=raw, distribution_path=name`) |
| K4 | **Registry root above the project** (monorepo): `id generate --project-dir .` keys `pkgs/demo/src/demo/x.py`; `project pkgs/demo` looks up `src/demo/x.py`. Probed: every file missed. Project-side keys are project-relative, never registry-root-relative. | project, hook, wheel, library API | `project_relative_or_fallback` callers; only loom uses `registry_key_for_path` |
| K5 | **Dataset package keyed by the caller's string** (ruling 2026-10-15): from `scripts/`, `../data/t.txt` and `./../data/t.txt` each miss the `data/t.txt` pin and mint (two `untracked entity` WARNINGs), while the `software_File` hits (probed). An absolute path string misses too. | loom | `LoomElements._package` (`_loom_dataset.py`) |
| K6 | **Same dataset, two spellings, one run**: two `dataset_DatasetPackage`s both `contains` one `software_File` (probed). The fix round's per-run cache (`LoomElements._packages`, keyed `(caller string, digest)`) merges only identical strings. | loom | `LoomElements.dataset` |
| K7 | **Case on a case-insensitive file system**: `DATA/T.TXT` on macOS keys the file `DATA/T.TXT`; both the package and the file miss (probed). `registry_key_for_path` keeps the tail as spelt. | loom (and any path a user types: `model`, `enrich`) | `registry_key_for_path` (`id_registry/resolve.py`) |
| K8 | **Unicode normalisation**: a file created NFD (`café.txt`) is keyed NFD by `id generate` (`os.walk` gives the on-disk form); a script passing NFC misses both package and file (probed on APFS). No key is normalised anywhere. | loom, id generate, wheel (member names are whatever the zip holds) | `_element_key` (`_types.py`) |
| K9 | **Shared-stem models**: `models/a/model.npy` and `models/b/model.npy` register one sha-less `ai_AIPackage model` (probed, `INFO: 2 model files share the name model`). In one document the second claimant gets the collision WARNING; across fragments (`loom model models/a/...`, `loom model models/b/...`) both get the **same** id, and a merge folds two models into one (no `verifiedUsing` before G7 #3, so the fix round's `hash_conflict` cannot keep them apart). | id generate, project, wheel, model, enrich, merge | `IdRegistry.generate`; `_model_generator` (`model_path.stem`) |
| K10 | **Model name vs stem**: `id generate` keys the stem; harvest keys `.name` (`AiModelMetadata.resolve_name()`: own name else stem); loom keys the declared `name=`; `project` tries own name, physical path, stem (`_ai_model_entity_candidates`); `model`/`enrich` try the stem only. Five candidate lists for one artifact (G7 blocker 2). | all model surfaces | listed functions |
| K11 | **PEP 503 only for packages**: `_element_key` canonicalises `software_Package` names; a model or dataset named `My_Model` vs `my-model` are two keys. Harmless for packages; for artifacts with a path the path is the better identity. | id generate `-e`, loom | `_element_key` |
| K12 | **Ambiguous-name harvest skip** (I5): two elements of one type and name in one document are not harvested. With path keys this stays for packages (two versions behind markers) and for wheel members that normalise to one name (#251). | harvest, id import | `_ambiguous_keys` (`_ambiguous.py`) |
| K13 | **Display-escaped retry**: `IdRegistrySession.lookup_id` also tries `escape_display_controls(name)`, because `id import` stores names as the SBOM shows them. A path computed from disk is raw; harvest from the SBOM is escaped: two spellings of one key. | id import, every lookup | `IdRegistrySession.lookup_id` |
| K14 | **Directory keys**: directories are looked up by distribution directory (`demo`), never by `src/demo`; `id generate` never registers one; a harvest writes them with document-namespace ids (probed). | project, wheel, sdist | `_resolve_directory_hits_for_file` |
| K15 | **`--allow-build`**: `physical_path` is absolute into a temp directory, so `project_relative_or_fallback` falls back to the distribution path: K1 again. An included file outside the project dir (`force-include ../shared/x`) is absolute too, and indistinguishable from a built one by the path alone. | project `--allow-build`, hook | `_physical_path` (`core/_models_wheel.py`) |
| K16 | **Same id, two contents in a merge**: being fixed in the working tree (uncommitted `hash_conflict` in `_fragments_unify.py`). Not a key problem; listed so this plan does not redo it. | merge | `_find_survivor` |
| K17 | **Harvest re-keys by `.name`**: a merged loom fragment's model or dataset carries the registry id it got by its loom key; harvest writes it under the element name and `_release_stale_keys_for_id` drops the other key (G7 blocker 2's mechanism). | project, wheel (merged fragments), id import | `_import_sbom_element` |

Not key problems, kept out (section 7): same-type id coincidences in a merge,
the `unknown` wheel name sentinel, `env`'s root package, the
per-document `SoftwareAgent`/`Tool` churn.

**Correction to the preliminary answer.** "Same dataset declared twice needs
a per-run package cache": the fix round already caches by `(caller string,
digest)`; what remains is K6 (two spellings), which path keys fix. "Merge
keeping two hashes on one id": the fix round's `hash_conflict`. "One artifact,
several paths": true, but the src-layout and sdist cases are derivable by rule
from one canonical path (section 2), so no stored alias table is needed for
them; only a rename needs one, and that stays a new identity (decision P6).
A further class the answer missed: K4, the registry root is not the project
root for any surface but loom.

## 2. Options

Every option keeps the v3 table `(compact type, key) -> {spdxId, sha256?}`.

### A. Path-first two-tier key (recommended)

- **Tier 1, path:** an artifact with a file or directory below the registry's
  `root_dir()` is keyed by its canonical root-relative POSIX path: a
  `software_File` (as today), a local model's `ai_AIPackage` (the model file),
  a local dataset's `dataset_DatasetPackage` (its file or directory).
- **Tier 2, name:** an artifact with no path under the root (a dependency, a
  Hugging Face model, a remote or missing dataset, a model declared without
  `path=`, anything outside the root) keeps today's name key.
- **One helper computes every key** (`id_registry/keys.py`, new public
  module): `artifact_key(registry, type, *, path, project_dir, name, built)`
  returns `(key, tier)`; `registry_key_for_path` becomes its path half. Every
  surface calls it (CLAUDE.md, "route a cross-cutting choice through one
  shared, explicit mechanism").
- **Canonical path:** root-relative, `/`-separated, `..` collapsed lexically
  then by identity (as `registry_key_for_path` today), the tail in on-disk
  case when the path exists, NFC. Re-anchored: a project-relative path is
  joined to `project_dir` and made relative to `root_dir()` (fixes K4).
- **Derived aliases, not stored ones.** The lookup (in `IdRegistrySession`)
  maps the two layout-derived spellings onto the canonical key: an sdist
  member drops its single `name-version/` root (exact); a wheel or built path
  `P` matches a key `K` when `K == P` or `K` is `P` with exactly one leading
  part (the rule `RegistryCopy` already uses), the hash is equal, and exactly
  one key qualifies (a tie is a miss with one `INFO:`). One shared predicate
  replaces `_is_files_path_alias`, `RegistryCopy`'s tail rule and
  `_DeclaredRegistry`'s check.
- **Harvest writes the lookup key.** The session records, per id it claimed or
  the caller minted after a miss, the key it looked up; `_sync_registry` passes
  that map to `harvest()`, which writes each element under it (fixes K10,
  K17). An element with no recorded key (a merged fragment, `id import`) is
  keyed by its name as today, but **never moves an id the registry already
  holds under another key of the same type** (rule R-keep, section 5); a run's
  canonical lookup key replaces a held layout alias of the same id
  (promotion).
- I4's stored-alias exception is removed: one key per id, no exception.

Against the invariants: I1 holds (harvest still never classifies; the key
source is explicit); I2/I3 unchanged (tiers are ordered candidates, gate per
lookup); I4 becomes strict; I5 extends to keys that collide after
canonicalisation (two NFC-equal names, two files with one key); I6, I8
unchanged (re-keying never mints, counters untouched); I7 needs the alias
tie-break and the case lookup to be deterministic (sorted candidates; a tie is
a miss). Sha gate: unchanged for `software_File`; `ai_AIPackage` lookups on
every surface become gated (G7 #3, section 8). Ceiling, counters, `id_count()`,
`save_registry`/`replay_changes`: unchanged. Loom API: no signature change;
`name=` stays the element's `.name` (`input_datasets=` matching relies on it),
only the key moves. File format: unchanged shape (decided).

### B. Keep keys, canonicalise only

NFC, `..`, case, sdist strip and re-anchoring, applied to today's keys. Fixes
K3, K4, K7, K8, part of K1. Leaves K5/K6 (dataset string), K9 (stems), K10/K17
(five model candidate lists, harvest by name) and the G7 blocker. Rejected:
the model and dataset classes are the ones users meet.

### C. Path as an alias set on the entry

Entry `{spdxId, sha256?, paths: [...]}`, key stays the name; lookups try the
name, then a derived path index. Fixes K10 for lookups, but not K9 (two models
with one stem still share one key, so one entry), adds state that must be
garbage-collected (a moved file leaves a stale path), changes the JSON shape,
and makes one entry reachable by many keys, the drift I4 exists to prevent.
Rejected; its one real use (keep an id across a rename) is decision P6.

## 3. Worked example: `examples/sentimentdemo-aibom`

The pipeline runs every stage from the project root and passes root-relative
strings, so today's keys happen to equal tier-1 path keys for datasets and
files. The differences:

| Entry | Before (v3 file today) | After (A) |
| --- | --- | --- |
| model | `ai_AIPackage` `sentimentdemo` (sha `754c...`): loom `set_model(name="sentimentdemo", path=MODEL_PATH)` keys the name; `loom model models/sentimentdemo.bin` hits it only because the stem equals the name | `ai_AIPackage` `models/sentimentdemo.bin` (sha `754c...`): loom, `loom model`, `id generate` and the hook all derive it from the file |
| datasets | `dataset_DatasetPackage` `data/raw/pos.txt` ... pinned with `-e` under the exact strings the scripts pass | same strings, now derived from the path: still hit when a script passes `str(RAW_DIR / "pos.txt")` (absolute) or runs from `src/` |
| files | `software_File` `src/sentimentdemo/train.py` ... | unchanged; `loom wheel dist/*.whl` alone now hits them (`sentimentdemo/train.py` is the one-leading-part alias, hash equal) |

Renaming the model (`name="sentiment-clf"`): before, the training and
evaluation fragments key `sentiment-clf` while stage 4 keys `sentimentdemo`,
so the merged SBOM has two `ai_AIPackage`s for one file (no hash on stage 4's
before G7 #3, so they do not fold); after, all key the file. The README's
stage-0 `-e` lines stay valid (decision P9). The committed registry is
regenerated by `scripts/run_pipeline.sh`; ids may renumber once.

## 4. Surface x member matrix (option A)

Tier: P = path key, N = name key. "Alias" = the derived layout rule.

| Surface | Lookup | Register | Harvest key | Alias | Canonicalisation | Messages |
| --- | --- | --- | --- | --- | --- | --- |
| `project` dir | File: P (physical, re-anchored); dir: distribution path (P8); model: P gated, else N; package: N (PEP 503) | no | recorded lookup key | no | re-anchor, NFC | unchanged |
| `project --allow-build` | File: P via `built` flag, else distribution path + alias | no | recorded key | yes (hash) | as above | alias tie: one `INFO:` |
| `project <sdist>` | File/model: P after dropping `name-version/` | no | recorded key | sdist strip | strip, NFC | unchanged |
| `wheel`, `embed-wheel` | File/model: distribution path + alias, gated; package: N | no | recorded key | yes | NFC; re-anchor with `embed-wheel --project-dir` | alias tie `INFO:` |
| Hatchling hook | as `project` dir (physical paths known) | no | recorded key | only for built files | re-anchor | unchanged |
| library API | same as the CLI surface it mirrors (one code path) | no | recorded key | as surface | as surface | as surface |
| `env` | package: N only | no | name | no | PEP 503 | unchanged |
| `model`, `enrich` (local) | model: P from the argument (cwd-relative), gated (G7 #3); outside root: N (stem) | no | n/a (fragment) | no | case, NFC | outside root: no new message (N tier is normal) |
| `model` (HF id) | N (repo id) | no | n/a | no | none | unchanged |
| loom dataset | package: P when the path exists at resolution, else N verbatim; file: P gated | no | never (D15) | no | case, NFC, re-anchor | `untracked` as today; outside root WARNING as today |
| loom model | P of `path=` gated; no `path=`: N | yes, P key on gated miss (D13) | n/a | no | case, NFC | unchanged |
| loom script | P gated | no | n/a | no | as file | unchanged |
| `id generate` | n/a | File: P + sha; model: P + sha (no stem entries); `-e`: P9 | n/a | promotes a held alias of equal hash to the canonical key | NFC; two files with one key: both skipped, `WARNING:` | stem `INFO:` removed |
| `id import` | n/a | n/a | element name, R-keep | no | NFC | content-gate lines unchanged |
| merge harvest | n/a | n/a | element name, R-keep | no | NFC | unchanged |
| GitHub Action | CLI | CLI | CLI | CLI | CLI | docs only |
| skills | text only | `-e` guidance changes | text only | n/a | n/a | update `references/id-registry.md` |

## 5. Decisions needed (recommended default first)

- **P1, format.** Decided: no bump; regenerate branch-written files.
- **P2, name fallback for an artifact that has a path.** (a) Path key only:
  K9 and K10 cannot recur, and `-e NAME:ai_AIPackage` pins only pathless
  models. (b) Path, then name under the same gate: keeps old `-e` stem pins,
  brings back the stem collision for gate-less entries. Default (a).
- **P3, dataset package key (reverses the 2026-10-15 ruling).** (a) Tier 1
  path when the dataset exists below the root when it is resolved, else the
  caller's string; output datasets resolved at run exit, as models are (closes
  the "output dataset hashed when declared" follow-up too). (b) Keep the
  string. Default (a). Sub-decision P3b: the package stays ungated (its
  `software_File` carries content identity) (default) or is gated by its
  hash or Merkle root (a refreshed dataset becomes a new dataset, as a
  retrained model is).
- **P4, case and Unicode.** (a) NFC every key in `_element_key` (the one
  canonicalisation point, next to PEP 503); an existing path's tail takes its
  on-disk spelling (one directory listing per component, only for paths a user
  typed: loom, `model`, `enrich`); never casefold, since a Linux tree may hold
  `A.txt` and `a.txt`. (b) Casefold on macOS/Windows only: keys then differ by
  platform for one committed registry. Default (a).
- **P5, anchor.** (a) Every key is relative to the registry's stored
  `project_root`; surfaces with a project directory re-anchor; `wheel` (no
  `--project-dir`) relies on the alias rule, which in a monorepo does not
  reach `pkgs/demo/src/...` from `demo/x.py`. (b) Also add `--project-dir`
  to `wheel` (new CLI option: `_matrix_plan.py` entry, skills). (c) Allow an
  alias with any number of leading parts, hash-gated and unique. Default (a)
  now, (b) as a follow-up if a monorepo user needs `wheel` alone.
- **P6, rename keeps the id?** (a) No: a moved file is a new identity (code
  and data alike); document it. (b) An explicit `id alias OLD NEW` command
  (stored alias) later. (c) Same-hash re-identification: rejected for files
  (two empty `__init__.py` files are two files). Default (a), (b) parked.
- **P7, layout alias rule.** (a) Exactly one leading part, equal hash, unique
  candidate (the `RegistryCopy` rule, already shipped). (b) Any suffix
  (`_is_files_path_alias` today). Default (a): (b) matched unrelated files in
  the review of #305.
- **P8, directory keys.** (a) Out of scope: keep distribution-path keys
  (project and wheel already agree). (b) Physical directory keys plus an
  unhashed alias rule. Default (a).
- **P9, `id generate -e PATH:dataset_DatasetPackage`.** (a) When the NAME,
  taken from `--project-dir`, exists below the root, store its canonical path
  key and say so in one `INFO:` if it differs from the text given; else store
  the text (a remote name, or a dataset written later). (b) A new
  `--dataset PATH` option. Default (a); a not-yet-written dataset given as a
  canonical relative path (`data/processed/train.txt`) matches either way.
- **P10, R-keep.** Harvest and `id import` never move an id from a key of one
  type to another key of the same type, except promoting a held layout alias
  to the run's canonical lookup key. Needed so a merged fragment or an
  imported SBOM (element names `../data/t.txt`, `sentimentdemo`) cannot evict
  the path key the id was found under. Default yes; the alternative is
  carrying the key in the SBOM (a `contains` edge to the model `software_File`,
  then reading it back), which `id import` of a foreign SBOM cannot rely on.
- **P11, G7 #3 placement.** Same PR, before the model key switch (section 8).

## 6. Risks and traps for implementers

- **Realpath on both sides, lexical first.** `registry_key_for_path` collapses
  `..` lexically before following symlinks; the fix round made
  `_resolve_id_generate_path` do the same in its fallback (`link/..` is the
  directory above the link as written). Keep the order in the new helper;
  `id generate` (`_project_relative`) realpaths the parent but not the file.
- **`built` must be an explicit flag**, not "the path is absolute": an
  included file outside the project but inside a monorepo root is absolute
  too, and `TMPDIR` may lie inside the root. Thread `ProjectFile.built`
  (CLAUDE.md, stage-scoped helpers); keep `project_relative_or_fallback` the
  only fallback.
- **sdist root:** drop exactly one leading component, the archive's single
  `name-version/` directory (normalised spelling `demo_pkg-1.0.0`); reuse the
  root detection of `_sdist_scan`, not a regex on the project name.
- **Wheel `.data/` members** (`*.data/data/...`, `scripts/`) have no project
  path: they stay distribution-path keyed. Do not let the alias rule match
  through them.
- **Alias determinism:** sort candidate keys, require one; a tie is a miss.
  Never pick by dict order (recurring pattern: unordered collections).
- **Hash objects:** never share one `spdx3.Hash` between a package and its file
  (8.1); G7 #3 copies the value into a new `Hash`.
- **NFC duplicates:** two on-disk files equal after NFC (possible on Linux)
  map to one key; `generate()` would otherwise re-mint on every run (`content
  changed` churn). Skip both with a `WARNING:`, like I5.
- **On-disk case:** obtain it by listing the parent and matching by
  `os.path.normcase` plus identity, never by `Path.resolve()` (keeps the
  caller's case on macOS); a path that does not exist keeps its spelling.
- **Windows:** keys are `/`-separated; `PureWindowsPath` drive or UNC outside
  the root is tier 2; dry-run every new path test as Windows would (CLAUDE.md
  checklist). Case-insensitive NTFS needs the same on-disk-case step.
- **Tri-state:** a lookup's recorded key is `None` (no lookup, e.g. a
  non-reader) vs a key; only the latter feeds harvest. `sha256=None` stays
  "ungated", never "empty hash".
- **Display escaping:** path keys are raw; keep the escaped retry for
  imported names, and record the raw key in the session map.
- **Re-keying is not minting:** promotion and R-keep must not touch
  `id_counters`; `Rebase.added` must not count a re-keyed id as new.
- **`replay_changes` with re-keys:** a promotion is a dropped key plus a new
  key holding the same id; the refusal loop must treat it as one change, not as
  "another run saved this id first".
- **`registry_key_for_path` calls `os.getcwd()`**, which raises when the cwd
  was deleted (open follow-up); the new helper must catch it.
- **The order-matrix invariant `_alias`** (`_order_invariants.py`) encodes
  I4's exception; update it with I4, or the harness reports false failures.

## 7. Implementation tasks (in dependency order)

Ratings: sensitivity (S: low/med/high) and the agent tier to use. Every
task: regression tests that fail on the base tree, Windows dry-run, linters.

1. **Key helper** (`id_registry/keys.py`, `resolve.py`): `artifact_key`,
   canonical path (lexical/identity/realpath, re-anchor, on-disk case, NFC,
   `getcwd` guard), the layout alias predicate replacing
   `_is_files_path_alias` and the `RegistryCopy` tail rule. Tests: parametrised
   boundaries (`..`, symlinked ancestor, outside root, other drive via
   `PureWindowsPath`, NFC/NFD, case, one vs two leading parts, tie). S high;
   Opus, high effort.
2. **`_element_key` NFC + generate ambiguity** (`_types.py`, `_format.py`,
   `_registry.generate`): NFC every key; load rejects a duplicate after NFC;
   two files with one key skipped. S high (determinism); Opus.
3. **`ProjectFile.built` flag** (`core/project.py`, `core/_models_wheel.py`,
   build-and-read): replace "absolute means built" for registry keys. S med;
   Opus or Sonnet with a precise brief.
4. **Session: alias lookup + key recording** (`_session.py`): try exact, then
   sdist strip, then layout alias (gated, unique); record id -> key for hits
   and post-miss mints (`record_key`). S high; Opus.
5. **Harvest by recorded key, R-keep, promotion; drop I4 exception**
   (`_harvest.py`, `_generators_shared._sync_registry`, `_persist.py`
   counting). Tests: merged loom fragment keeps the path key; `id import` of a
   merged SBOM keeps it; promotion of `demo/x.py` to `src/demo/x.py`;
   `replay_changes` with a promotion. S high; Opus, high effort.
6. **File surfaces** (`_document_files.py`, sdist, wheel, embed, hook):
   re-anchored physical key, sdist strip, alias for wheel/built. Drift guard:
   one fixture, `project`/`wheel`/`project <sdist>`/hook/library API all give
   each file the same id. S high; Opus.
7. **G7 #3** (`_ai_package.py`, `ai.py`, `_model_generator.py`, embed):
   `ai_AIPackage.verifiedUsing` copied (new `Hash`) from the model
   `software_File`; every model lookup gated (section 8). S high; Opus.
8. **Model keys to tier 1** (`_ai_package._ai_model_entity_candidates`,
   `_model_generator` `model`/`enrich`, `_loom_model._spdx_id`/`_record`,
   `IdRegistry.generate` registering model paths, not stems; shared-stem
   `INFO:` removed). Drift guard: one model file gets one id from loom
   (`set_model`/`use_model`), `model`, `enrich`, `project`, `wheel`, hook,
   `id generate`. S high; Opus.
9. **Dataset keys to tier 1, resolved at exit** (`_loom_dataset.py`,
   `_loom_active_run.py`): package key from the path when it exists; output
   datasets hashed and keyed at `finalize()`; per-run cache keyed by the
   canonical key. S high; Opus.
10. **`id generate -e` canonicalisation (P9)** (`cli/id.py`). S med; Sonnet.
11. **Manual checks and order matrix** (`scripts/manual_cli_checks`): a
    monorepo profile, an sdist reader op, a "run loom from a subdirectory"
    op, NFD file and upper-case spelling ops; `_alias` invariant updated;
    `_known.py` entries removed for fixed items. S med; Sonnet, then an Opus
    review of the invariants.
12. **Docs and skills** (`docs/id-registry.md` "What a registry pins",
    `docs/python-api.md`, `skills/sbom-generate/references/id-registry.md`,
    sentimentdemo README and regenerated registry, CHANGELOG one bullet,
    follow-ups/roadmap trimmed, implementation doc). S low; Haiku/Sonnet for
    the sweep, a fresh-eyes read of each changed `SKILL.md`.

Review points: after 1-2 (key shape frozen), after 5 (harvest semantics),
after 8 (cross-surface drift guards green), before merge (fresh-context
sweep of the whole range).

**Verification.** Mutation targets: the tie-break in the alias predicate,
the one-leading-part bound, the sdist strip count, NFC in `_element_key`,
R-keep, promotion, recorded-key preference in harvest, the gate on each model
lookup, the re-anchor relpath, the on-disk case step. Reversal probe corpus
(run HEAD and the branch; list every input that hit before and misses now):
flat project `generate -> project -> wheel`; src layout in all four orders of
`id generate` and `project`/`wheel`/`sdist`; monorepo root above project;
`--allow-build` src layout; `force-include` from outside the project;
`models/{a,b}/model.npy`; a GGUF/ONNX model whose own name differs from its
stem; two copies of one model at two paths; loom datasets as `data/t.txt`,
`./data/t.txt`, `../data/t.txt` from `scripts/`, an absolute path,
`DATA/T.TXT`, NFC vs an NFD file, `imdb`, `stanfordnlp/imdb`, a URL, an output
dataset declared before it is written, a directory dataset; a renamed file
with the same bytes; an edited file at the same path; a symlinked directory;
a file name with a control character via `id import`; `loom model user/repo`;
the sentimentdemo pipeline end to end (determinism: two runs, same bytes).
Expected losses to list and accept: old `-e` stem pins for pathful models
(P2a), dataset strings for datasets now found by path.

## 8. G7 #3

G7 #3 (roadmap "#3 Mechanical wiring": `ai_AIPackage.verifiedUsing` from its
model `software_File`) must land in this PR or before it, per the G7
blockers in [id-registry-followups.md](id-registry-followups.md). With path
keys it slots in as task 7, after the session alias lookup (4) and before the
model key switch (8): once every surface hashes the model, its lookup is
gated, so a retrained file at the same path misses and gets a new id (D3), and
harvest writes the recorded path key, so blocker 1 (a retrain laundered into
an old id) and blocker 2 (harvest keys `.name`, `id generate` keys the stem)
both close. Revisit the `id import` content-gate drop ruling then: an imported
project SBOM will carry the model's own hash.

## 9. Out of scope

- Same-type id coincidences and later-fragment collisions in a merge; the
  merge hash-survivor policy (follow-ups).
- Content-addressed model identity (one id for one model's bytes at any
  path): two copies at two paths stay two ids.
- `env` file-level keys, its root package, the `unknown` wheel sentinel, the
  per-document `SoftwareAgent`/`Tool` churn.
- Directory keys (P8a), wheel `.data/` members, hatch `sources` remapping
  other than one leading part, renames (P6a).
- Registry file locking, Windows `os.replace` retries, the loom
  claim-before-write race.
