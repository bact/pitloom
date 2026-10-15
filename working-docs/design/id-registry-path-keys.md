---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: path keys (plan)

See also: the parts of this plan,
[problem](id-registry-path-keys-problem.md),
[design](id-registry-path-keys-design.md) and
[implementation](id-registry-path-keys-implementation.md);
[id-registry-v3.md](../implementation/id-registry-v3.md) (the built
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

## Map of the plan

The plan keeps one numbering across its files; "section N" in any file means
the section below.

| Section | File |
| --- | --- |
| 1. Problem: every collision and miss class today (K1-K17) | [id-registry-path-keys-problem.md](id-registry-path-keys-problem.md) |
| 2. Options (A recommended, B, C) | [id-registry-path-keys-design.md](id-registry-path-keys-design.md) |
| 3. Worked example: `examples/sentimentdemo-aibom` | [id-registry-path-keys-design.md](id-registry-path-keys-design.md) |
| 4. Surface x member matrix (option A) | [id-registry-path-keys-design.md](id-registry-path-keys-design.md) |
| 5. Decisions needed (P1-P11) | this file, below |
| 6. Risks and traps for implementers | [id-registry-path-keys-implementation.md](id-registry-path-keys-implementation.md) |
| 7. Implementation tasks (in dependency order) | [id-registry-path-keys-implementation.md](id-registry-path-keys-implementation.md) |
| 8. G7 #3 | [id-registry-path-keys-implementation.md](id-registry-path-keys-implementation.md) |
| 9. Out of scope | [id-registry-path-keys-implementation.md](id-registry-path-keys-implementation.md) |

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
