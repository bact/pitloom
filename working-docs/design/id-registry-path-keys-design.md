---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: path keys, options and matrix (plan)

See also: [id-registry-path-keys.md](id-registry-path-keys.md)
(overview, status, decisions P1-P11),
[id-registry-path-keys-problem.md](id-registry-path-keys-problem.md)
(problem classes K1-K17),
[id-registry-path-keys-implementation.md](id-registry-path-keys-implementation.md)
(risks, tasks, G7 #3, out of scope).

Part of the path-keys plan (see the overview for status and the section map).
Section numbers are the plan's own; D- and I-numbers refer to
[id-registry-v3.md](../implementation/id-registry-v3.md).

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
