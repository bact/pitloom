---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue: migration plan and release cuts

See also: [message-catalogue-and-skills.md](message-catalogue-and-skills.md)
(the design and decisions A to M), [roadmap.md](roadmap.md) (0.23.0 focus),
[known-bugs.md](known-bugs.md),
[licenseid-0-7-adoption.md](licenseid-0-7-adoption.md),
[licence-resolution-provenance.md](licence-resolution-provenance.md).

Status: plan, 2026-10-30; 0.22.0 shipped. Done: `lfs-pointer` (#390),
`over-cap` (#396), the model-stub causes (#404, PR 1a) and unreadable files and
directories (#408, PR 2a).
This file is the reference for what remains and what ships in which release.

## Shipped in 0.22.0 (2026-10-30)

1. Catalogue PR 1a, the model-stub causes (#404).
2. Catalogue PR 2a, unreadable files and directories (#408).
3. The serious known bugs fixed: a file name that is not UTF-8 and a `:` in
   plain provenance text (#402), a direct-URL dependency looked up on PyPI
   (#405), a package key without a version (#407, ID registry format 4).

Earlier in the release: `lfs-pointer` (#390, #395) and `over-cap` (#396).
`licenseid` stays at `>=0.6.0,<0.7`. The grammar ratchet keeps new uncoded
messages out meanwhile (`tests/test_message_ratchet.py`).

## Moved to 0.22.1 and 0.23.0 (decided 2026-10-30)

0.22.1: the path-site fixes (`fix-path-sites`) and the small remaining bug
fixes (below).

0.23.0:

1. `licenseid` 0.7.0 adoption (`match` becomes `detect`, `resolve` becomes
   `match`).
2. The licence provenance mapping (PR #384, the T14 design).
3. The remaining catalogue PRs: 1b, 2b and 3 to 18, PR 18 (licence families)
   included, after the adoption.
4. `--report` and SARIF.

## Sizes

62 families in the inventory (983 emission sites at `b18e2cce`; 718 in
scope). Counts below are the inventory's. After #390 and #396 the tool counts
598 sites in scope, 42 coded and 556 uncoded. Of the 60 remaining families,
20 (243 sites) have text that skills quote today.

## Remaining catalogue PRs

"Cut" is the release: shipped in **0.22.0**, or **0.23.0**.

| # | PR | Families (sites) | Cut | Notes |
| - | - | - | - | - |
| 1 | Model stub | model-unreadable (18), model-field-unread (28), missing-library (8), not-a-model (5), parameter-count (7), model-scan-decision (2) | 1a: 0.22.0 (#404); 1b: 0.23.0 | 68 sites; completes the stub diagnosis page for skills |
| 2 | Unreadable files and dirs | unreadable-file (28), unlistable-dir (4), source-unreadable (5), card-unreadable (3), lock-file-unreadable (3) | 2a: 0.22.0 (#408); 2b: 0.23.0 | 43 sites; 2a (#408): `file-unreadable` (`/not-utf8`, `/outside-project`), `dir-unlistable`, evidence PR-D and the raw-exception bug, 511 to 498; 2b: the cards, `fetch_json` (the first `ERROR` template, recommended), `text-malformed`,, `file-unreadable` in the model table, and a dataset member vanishing mid-walk (stays silent), all 0.23.0 (see known-bugs). The ID registry's `PATH` error waits for PRs 5-7 |
| 3 | Caller actor | usage-error (15), input-not-found (25), option-no-effect (7), sbom-input-invalid (7) | 0.23.0 | 54 sites; first use of `actor=caller`; `input-not-found` needs a helper first |
| 4 | Frames | command-failed-wrapper (13), command-summary (6), hook-status (6), env-decision (4), env-tool-failed (2), interrupted (1) | 0.23.0 | 32 sites; the uniform `loom <command>:` frame; about 47 stderr tests change |
| 5-7 | Registry (three PRs) | registry-file-invalid (24), registry-key-decision (21), registry-collision (11), registry-left-out (8), registry-miss-new-id (8), registry-not-saved (8), registry-summary (8) | 0.23.0 | 88 sites |
| 8-9 | Config (two PRs) | config-invalid (46), config-file-unusable (6), config-moved (6), config-unknown-key (4), config-value-ignored (1) | 0.23.0 | 63 sites; `config-invalid` has 44 templates and needs a helper first |
| 10-11 | Lock and dependencies (two PRs) | lock-entry-skipped (40), lock-file-ignored (28), dependency-skipped (20) | 0.23.0 | 88 sites |
| 12 | Project | project-metadata-unreadable (31), project-value-ignored (22), file-discovery-fallback (19) | 0.23.0 | 72 sites |
| 13-14 | Git, Hub and build (two PRs) | git-fetch-failed (11), git-decision (12), git-redirect (2), network-refused (4), hub-fetch-failed (5), hf-decision (3), hf-input-invalid (2), hf-unpinned (1), build-subprocess (11), temp-left-behind (2) | 0.23.0 | 53 sites; adds `timeout` and `network-failed`; pairs with evidence PR-C1 |
| 15-16 | Fragments, merge and wheel (two PRs) | fragment-unusable (14), merge-conflict-kept (12), source-conflict-kept (9), wheel-sbom-check (13), wheel-embed-action (6), archive-member-refused (10) | 0.23.0 | 64 sites |
| 17 | Misc | author-split (13), escaped-text (13), dataset-field-invalid (13) | 0.23.0 | 39 sites |
| 18 | Licence | licence (8), licence-file-read (5) | 0.23.0 | 13 sites; after the `licenseid` adoption |

Total 60 families, 677 sites, 18 to 22 PRs (the grouped rows split into the
PR counts shown).

## Serious known bugs

"Serious" means a crash, silently wrong data or identity, or a leak. The
entries are in [known-bugs.md](known-bugs.md). List decided 2026-10-30:

- Shipped in 0.22.0: a project file whose name is not valid UTF-8 crashed
  generation (#402); a plain-text provenance value with a `:` read as a key
  (#402); a direct-URL dependency was looked up on PyPI by name (#405); a
  package key without a version gave every release one id (#407); an
  unreadable project file was logged with the raw exception (#408).
- 0.22.1: the Hatchling hook finds no licence database in an isolated build.
- 0.23.0, to re-check after the `licenseid` adoption: a top match that holds
  only part of its licence is concluded; two `SPDX-License-Identifier` tags,
  one stated, conclude only the stated one.

## Other items outside the cuts

Evidence work only where it pairs with a family (PR-D shipped with catalogue
PR 2a). The rest of the evidence plan (model over the cap, `Evidence: declared`
on pointers, Hub failures, directory sizes) and the roadmap items under
"0.23.0" (`loom` SDK dataset provenance, `pkg:git` identifiers, support-tier
gaps, `contentIdentifier`) are 0.23.0 or later.
