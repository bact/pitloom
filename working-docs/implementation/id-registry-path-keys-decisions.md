---
Created: 2026-10-16
Last-Modified: 2026-10-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: path keys, decisions and review rounds

See also: [id-registry-path-keys.md](id-registry-path-keys.md) (what was
built: problem classes, design, mechanisms),
[id-registry-v3.md](id-registry-v3.md) (D- and I-numbers),
[id-registry-followups.md](../design/id-registry-followups.md) (open items).

## 1. Decisions P1-P11 (final answer)

| # | Question | Final answer |
| --- | --- | --- |
| P1 | Format | No bump (user 2026-10-15): v3 never released; branch-written files regenerated |
| P2 | Name fallback for an artefact that has a path | Path only. Old `-e STEM:ai_AIPackage` pins are an accepted loss; pathless models keep the name key |
| P3 | Dataset package key | Path key when the file or directory exists below the root at declaration (user; reverses the 2026-10-15 "caller's string" ruling), else the caller's string |
| P3b | Dataset gate | Gated first (user), then **hybrid** (user, after the `-e` pin clash, section 3) |
| P4 | Case and Unicode | NFC every key; on-disk spelling only for user-typed paths; never case-fold |
| P5 | Anchor | Keys relative to the registry's stored `project_root`; project prefix computed once per document; `--project-dir` on `wheel`/`project <sdist>` built (P5b) |
| P6 | Rename keeps the id? | No: a moved file is a new identity; a stored `id alias` parked |
| P7 | Layout alias | Narrower than planned: `src`/`lib` only, shorter key must not exist on disk, hash equal, unique (see the built doc, section 3) |
| P8 | Directory keys | Out of scope; distribution-path keys kept |
| P9 | `id generate -e PATH:dataset_DatasetPackage` | Canonical path key when NAME exists below the root, with one `INFO:` if it differs; extended to `ai_AIPackage` and `software_File` |
| P10 | R-keep | Yes: harvest and `id import` never move an id between same-type keys, except promoting a held alias |
| P11 | G7 #3 placement | Same PR; `verifiedUsing` plus gated lookups first, key switch second |

Also decided, no number: embed-wheel and the hook stay lookup-only (no
harvest into the source tree's registry); output datasets resolved at run exit
stay out of scope; a dataset package is never auto-harvested (D15).

## 2. Rejected options

- **B, keep keys, canonicalise only** (NFC, `..`, case, sdist strip,
  re-anchoring on today's name keys): fixes K3, K4, K7, K8 and part of K1 but
  leaves the dataset string (K5/K6), stems (K9), five model candidate lists
  (K10) and harvest by name (K17), the classes users meet.
- **C, path as an alias set on the entry** (`{spdxId, sha256?, paths: [...]}`,
  key stays the name): does not fix K9 (two models with one stem still share
  an entry), changes the JSON shape, needs garbage collection for a moved
  file, and makes one entry reachable by many keys, the drift I4 exists to
  prevent. Its one real use (an id across a rename) is P6.
- **Strict dataset gate** (every dataset package entry needs a SHA-256):
  rejected for `-e` pins (section 3).
- **Name fallback for pathful models (P2b)**: keeps old `-e` stem pins but
  brings back the stem collision for gate-less entries.
- **Case-fold on macOS and Windows only (P4b)**: one committed registry would
  hold different keys per platform; a Linux tree may hold `A.txt` and `a.txt`.
- **Stored alias table**: state to garbage-collect and a second source of
  truth; the src/lib layout is derivable by rule from one canonical path.
- **Same-hash re-identification for files**: two empty `__init__.py` files
  are two files.
- **Alias with any leading part, or any suffix**: the loose rule of
  `_is_files_path_alias` (matched unrelated files in the #305 review) and the
  plan's own "any one leading part" (section 4 below).

## 3. The hybrid dataset gate

User decided "Gated" (a refreshed dataset is a new package id, as a retrained
model is), then "Hybrid" after this clash: `-e data/new.txt:dataset_DatasetPackage`
pins a dataset that does not exist yet (the pipeline writes it later), so the
pin cannot hold a hash; a strict gate would never hit it, and the first run
after the data exists would mint a different id than the pinned one.

Scenarios of the hybrid rule:

| Entry in the registry | Dataset at lookup | Result |
| --- | --- | --- |
| pin with no SHA-256 (`-e` of a not-yet-existing name, `id import`, old pin) | any content | hit, `INFO:` "content not checked" |
| entry with SHA-256 | same digest | hit |
| entry with SHA-256 | file refreshed, or a file added to a directory | miss: new package id |
| none | any | mint; loom never writes the entry (only `id generate -e` and `id import` do) |
| dataset not hashed (missing, over the ceiling, unreadable) | no digest | ungated lookup with an `INFO:` |

Trade-off: pins made before data exists are honoured once; a pin whose NAME
exists when `-e` runs gets the digest immediately and is gated from then on.
Documented consequence: adding a file to a directory dataset changes its
Merkle root and re-mints the package id.

## 4. Review rounds

- **Plan review (before building)** corrected the old design on code:
  `IncludedFile.built` dropped when building `ProjectFile`; no alias rule in
  `_DeclaredRegistry`; model stem logic in `_generate.index_files`; `_ambiguous`
  keyed by name, not the WRITTEN key; call sites missed (`_embed_overlay`, the
  scanners, `_loom_caller`, `enrich --project-dir`, sdist `physical_path`).
- **R1 (key shape).** `LookupKey` frozen before the session and harvest work.
- **R2 (code review of the first implementation).** (1) `id generate` promotion
  ran both directions and could demote a canonical key or steal a real file's
  id; (2) a CANONICAL alias took the held key of another REAL file in the same
  run (empty `__init__.py`, `zebra/__init__.py` vs `src/zebra/__init__.py`): the
  root file lost its id permanently; (3) alias candidates scanned the whole
  registry on every miss (15 s at 20k x 20k): now at most three dict lookups;
  (4) a wheel member `foo/__init__.py` could take the id of
  `tests/foo/__init__.py` (generic one-part alias): narrowed to a leading
  `src`/`lib`, with the exists rule; (5) ambiguity was computed before R-keep,
  skipping a legitimate write; (6) the alias tie `INFO:` repeated per lookup.
- **R3a (cross-surface review).** loom, `model` and `enrich` typed paths lacked
  the layout alias (loom registered a second key next to a wheel's);
  `--allow-build` in a monorepo keyed built files without the project prefix;
  `id generate PATH` stored the path as typed, not as the disk spells it;
  `id import` of a loom fragment left dataset pins dead (declared spelling, no
  digest) and of a project SBOM did not pin its models; `-e` treated datasets
  and models differently without a message; a symlinked in-root model path keys
  differently from `project`; `input_datasets=` matches declared spellings
  only; five stale docstrings.
- **R3b (HEAD-vs-tree probe sweep, 20 cases).** No crash, no new `ERROR:`, no
  new non-determinism; 24 src-layout orders now give one id per file where HEAD
  split sdist ids. Found: wheel-alone in a monorepo splits (known P5b limit); a
  force-included file inside the root but outside the project missed; name pins
  for models were unused without an `INFO:`.
- **T11 (manual runner monorepo profile)** found `embed-wheel --project-dir`
  missing silently in a monorepo; it now keys below the project prefix.
- **R4a (fresh review of the whole change).** (1) A merged loom fragment's
  element with an older SHA-256 rolled a newer entry back: now left as is, with
  `content gate kept ... element id X with an older SHA-256`; (2) a retrained
  model was re-harvested under a name key next to its file key: a hashed
  fragment model is recorded only under its same-hash file's key, else `model X
  not recorded: no unique file with its SHA-256`; (3) `id import` keyed files
  under their declared spelling instead of their distribution path or one held
  layout alias; (4) one spdxId was handed to two files in one namespace:
  a document now reserves every id held under a `software_File`,
  `software_Package` or `ai_AIPackage` key (`SoftwareAgent` and `Tool` are
  excluded: reserving them renumbers harvested ids); (5) `id import` of a loom
  fragment declaring `../data/t.txt` did not round-trip: datasets and models
  are keyed by their same-hash file, and a name found nowhere says so
  (`IMPORT_NOT_FOUND`).
- **R4b (documentation against the code, then probes).** A hash-less dataset
  pin re-run with `-e` once the data existed minted a new id: it now adopts the
  digest (`pin now gated by its SHA-256`) and a different recorded digest still
  mints. A fresh reviewer found doc claims the code contradicted: `input_datasets=`
  matching through the key (it matches declared spellings), `project <sdist>`
  "given a project directory" (no such route), INFO wordings (`-e` of a missing
  dataset says `pinned without SHA-256: not found`, the gate-miss line differs
  by surface, the alias line counts elements and showed on `project`/`wheel`
  only, now on loom, `model` and `enrich` too), directory keys described as
  path keys, `-e NAME` described as "the exact string the script passes"
  (it resolves against `--project-dir`; a script's `../data/t.txt` is a path
  key). The example registry's second pipeline run adds the two
  `data/processed` digests; the committed file is that steady state (checked:
  runs 1, 2 and 3 from the committed registry, ids unchanged).
- **R5 finding 3 (`loom model`/`enrich`).** `loom model` and `loom enrich`
  now reserve the registry's held ids in the model document's namespace as
  `project` does (`_reserved_ids.reserve_held_ids`), except those under its
  model card datasets' names and the model's own name (the key `id import`
  gives a `loom model` SBOM's model), so a `-e` dataset pin is never minted
  again, an `enrich` fragment names the document's model id, and no imported
  id renumbers.
- **What unit tests missed.** Every finding came from an independent review or
  an end-to-end probe: surface interactions, run order, on-disk existence.
- **Mutation targets**: alias tie-break, one-leading-part bound, `.data` guard,
  sdist strip count, NFC in `_element_key`, R-keep, promotion, recorded-key
  preference, `record_key` first-wins, each per-lookup gate, the re-anchor path,
  the on-disk case step, the `LAYOUT` held-key choice, `_fragments_unify` move.

## 5. Expected losses

Documented once, factually:

- Old `-e STEM:ai_AIPackage` and own-name model pins.
- Dataset string pins that differ from the canonical path (`./data/t.txt`).
- Multi-part Hatch `sources` remaps for wheel-only lookups.
- Raw un-normalised archive member names.
- Registries written by the earlier v3 branch are regenerated (no
  migration); ids may renumber once.
- A retrained model logs "content changed" for the file and the package.

## 6. Order of work that mattered

`verifiedUsing` and the gated lookups on existing keys landed as their own
step before the model key switch, so a regression from either was attributable.
Harvest by recorded key came before any surface changed its key, because the
surfaces' keys are only meaningful once harvest writes what lookup used.
Reserve and mint ids before any skip guard (the PR #305 lesson) held again in
the harvest rewrite.

## Digest-less model lookup misses a hashed entry (R5 finding 2, 2026-10-16)

A pathless `loom.set_model("stem")` (or a `path=` that cannot be hashed)
reused any entry under that name, including a hashed `ai_AIPackage` that
`id import` or a model outside the root had left there: a retrained model's id
came back by name. `IdRegistry.lookup(miss_hashed=True)` (threaded through
`IdRegistrySession.lookup_key`, set only by `_loom_model._spdx_id` when no
digest exists) now skips an entry recording a SHA-256, with its own
`WARNING:` (`records a SHA-256 but no content was hashed`). Rejected: the
global rule "no SHA, no hashed hit" (breaks the deliberate ungated dataset
lookup and the registry read API), and refusing the name entry in `id import`
(it cannot tell a loom fragment model declared with an in-root path from a
`loom model` SBOM of a file outside the root, whose name entry is the
documented reuse route). Cost: a pathless model no longer reuses a hashed id
held by its name.

## A loom model name renames the project's model (2026-10-16)

User decision: a `loom.set_model("name", path=...)` name that differs from
the project model's (its file stem or own name) used to lose the merge, with
`WARNING: Merge: conflicting 'name'` on every run. Both elements share the
file key's id and fold; explicit user intent beats a name derived from the
file. Built in `_fragments_model_names.py`: `_MergeIndex` notes the base
document's `ai_AIPackage` elements; a fold into one defers `name` and, after
the last fragment, `ModelNames.finish()` applies the rule. One distinct
fragment name (not equal, not the same path at another depth) wins with one
`INFO: Merge: 'name' on ...`, and the base's `name` provenance is dropped
from its comment (recomputed from the base comment and the fragments' in fold
order) and from its `fields` Annotations (an Annotation left empty goes), so
no record claims `file_name_stem` for a loom name. Two distinct fragment
names keep the base name with today's warning per name, sorted: order
independent. "Fragment" means any configured fragment, not only a loom run's
(a fragment carries no reliable loom marker); `loom merge` has no base
document, so every model is a fragment's and today's earlier-wins merge
stays. Registry keys come from `registry_keys`, not names: run 2 harvests
under the file key and is byte-identical (test). Probe (10 scenarios, HEAD
vs tree): only the renamed cases changed (name, WARNING to INFO); same-name,
no-path, disagreeing runs and `loom merge` are unchanged.
