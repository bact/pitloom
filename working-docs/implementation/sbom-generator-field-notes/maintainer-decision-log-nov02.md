---
Created: 2026-11-02
Last-Modified: 2026-11-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: maintainer decision log, 2026-11-02

See also: [README.md](README.md) (index of these notes),
[maintainer-decision-log-oct30.md](maintainer-decision-log-oct30.md) (the
table this continues; its rows are not repeated),
[roadmap.md](../../design/roadmap.md) (release plan),
[known-bugs.md](../../design/known-bugs.md) (planned releases and the ledger),
[ci-duplicate-run-skip-experiment.md](ci-duplicate-run-skip-experiment.md),
[bug-ledger-needs-a-severity-scale.md](bug-ledger-needs-a-severity-scale.md),
[process-lessons.md](process-lessons.md).

One developer decides, with agents proposing options. This table lists the
decisions that shaped the 0.22.1 round, each with the reason and where it is
recorded, in the form of the 2026-10-30 log. A row dated 2026-10-30 is here
because the work of 2026-11-02 carried it out or depends on it. "Session
record" marks a decision the caller reported and the repository does not
show. Status is as of 14:40 UTC on 2026-11-02.

## 1. Decisions

| Date | Decision | Why | Recorded in |
| --- | --- | --- | --- |
| 2026-10-30 | Release order: 0.21.0, 0.21.1, 0.22.0, 0.22.1, 0.23.0, 1.0; no date for 1.0 until 0.23.0 lands | not recorded | `roadmap.md`, "Order (2026-10-30)" |
| 2026-10-30 | Ship 0.22.0 at the cut: tag `v0.22.0` (`bdf668d6`, 16:56:05 UTC), PyPI upload at 17:05 UTC; what was not done goes to 0.22.1 or 0.23.0 | the cut was set earlier that day; see the Oct-30 log | `roadmap-completed.md`; [post-publish-verification-of-a-release.md](post-publish-verification-of-a-release.md) |
| 2026-10-30 | #410 (the path-in-message fix) lands before the tag | it is in the "serious" class (a raw exception in a log line, a leak); verified: its merge `17a8f6c5` (16:43:41) is an ancestor of the tag | `known-bugs.md`, planned releases |
| 2026-10-30 | 0.22.1 is small remaining bug fixes plus a re-run of the 0.22.0 release checks left to CI: the full manual CLI checks, the CHANGELOG-against-merged-PRs cross-check, the coverage-snapshot diffs and the `scripts/` lint | the checks could not all run before the tag | `known-bugs.md`, planned releases; `roadmap.md`, 0.22.1 |
| 2026-11-02 | The `0.21.2` review is dropped from the 0.22.1 checks | "The review is done for 0.22.0 and no longer needed" (commit message) | `3d9872a6` (#416) |
| 2026-11-02 | Record the PyPI verification of 0.22.0 as a dated entry, and log what it found as ledger entries for 0.22.1 | a post-publish check is part of the release checklist | #414; `wheel-sbom-verification.md` |
| 2026-11-02 | The CI duplicate-run skip is an **experiment**, `test.yml` only, fail open; the markdown-only skip is analysed and not built | a measured third of `test.yml` runs repeat a green tree; the markdown case has three unsafe conditions | #415 (merged 14:38 UTC); `testing-and-review-policy.md` |
| 2026-11-02 | Split the bug ledger into an index and eight parts by category; re-rank nothing; build the severity scale from the tags the entries already carry | `known-bugs.md` (41,233 bytes) and its `-p3` file (22,775) were over the size limit | #417; `known-bugs.md` |
| 2026-11-02 | Split `document.py` (516 lines to 411 plus a 115-line module); fix the prefetch to resolve once; fix the two `pylint` findings on `main` without a suppression | the size limit; one identity rule for what is fetched and what is built | #418; `be65a8e0`, `8223e308`, `a6d57867` |
| 2026-10-30, confirmed 2026-11-02 | A version 3 ID registry is refused, never migrated (D2) | silent loss of pins; a one-developer alpha needs no migration | `registry-key-must-carry-the-release.md` section 5; the shipped release refused it in the PyPI smoke test |
| 2026-11-02 | Regrouping top-level test files into subfolders comes **last** in the 0.22.1 order | *session record*; the ledger entry says only "group them in subfolders after 0.22.0" | `known-bugs/process-tooling-and-release-checks.md` |

## 2. The 0.23.0 scope

**Decided 2026-10-30 (`roadmap.md`, "The 0.23.0 list"):** the `licenseid` 0.7.0
adoption (`match` becomes `detect`, `resolve` becomes `match`), the licence
provenance mapping (#384), the remaining catalogue families (1b, 2b and 3 to 18,
the licence families included), and `--report` and SARIF.

**Reported for this round (*session record*), not in that list:** the remote
registry entries (the second PR of the key work, D7: a Hub model, a URL dataset)
and a separate variant for an import that is found but fails.

- **What the repository says of those two.** The registry-key note records
  the remote entries as "a second PR" and gives its reasons (its own decision
  set; a later PR would need registry format 5). The ledger has the
  import-failure entry (S, found 2026-10-30, from #404) without a release. Three
  neighbouring entries are marked "later (0.22.x or 0.23.0)". So the repository
  shows both as open and unscheduled; the caller reports 0.23.0.
- **`licenseid` 0.7.0 is still not on PyPI.** Checked 2026-11-02 through the
  index's JSON: the latest `licenseid` is 0.6.0 and `0.7.0` is absent. The cap
  `licenseid>=0.6.0,<0.7` in `pyproject.toml` stays right, and the first item
  of the 0.23.0 list waits on the release, as on 2026-10-30.
- The disagreement noted in the Oct-30 log (the plan listed the licence
  families in 0.22.0 while the maintainer had moved them) is closed: commit
  `5d249752` (2026-10-30 16:26 UTC) moved the adoption, the provenance mapping,
  the remaining families, `--report` and SARIF to 0.23.0 in the roadmap and the
  migration plan.

## 3. Notes on three rows

- **"Ship 0.22.0 first."** The verified facts are the order of events: #410
  merged at 16:43, the release PR #411 at 16:56 (which is the tag), PyPI at
  17:05. The reason for tagging with the 0.23.0 items open is the cut set earlier
  that day, not a separate decision recorded at the tag.
- **The CI row is a decision to measure.** It decides nothing about the CI
  matrix. The matrix is unchanged, as in the two-gate policy; only the rule
  "skip when the tree equals a green PR head" is trialled, with its revert path
  written down.
- **The ledger row decides a form, not a ranking.** The split moved every entry
  unchanged (174 first lines equal); how bad each entry is remains open
  ([bug-ledger-needs-a-severity-scale.md](bug-ledger-needs-a-severity-scale.md)).

## 4. Open

- As on 2026-10-30, a log written after the fact from commit messages and
  records leaves out the exchange that led to each row. Whether rows with a
  recommended option and a taken option should record both is for the authors.
- Whether 0.22.1 is complete is not recorded: it is a set of open and merged
  PRs (#414 to #419 merged by 14:38 UTC; the macOS timing fix in progress on a
  branch) and no tag.

## 5. Rulings of 2026-11-02 (later in the day)

Three rulings by the maintainer, recorded after the log above.

| Date | Decision | Why | Recorded in |
| --- | --- | --- | --- |
| 2026-11-02 | A registry package key treats only `unknown`, `NOASSERTION` and a blank version as "no version"; `none` and `n/a` do **not** count | No fixture, and no PyPI, lock-file or installed-metadata version, uses either spelling; neither is PEP 440; `foo@n/a` is a valid key and stays stable when normalised again. Add a spelling only when a real source is seen emitting it. `N/A` and `n/a` give two ids | this section |
| 2026-11-02 | The Hatchling "file discovery failed" warning is coded in catalogue PR 12, not in 0.22.1 | The migration plan gives the Hatchling hook's messages their code in its PR 12 (0.23.0 list); the maintainer ruled that this warning follows it | this section |
| 2026-11-02 | 0.22.1 was to be cut right after #422 and #423, but now **waits for #413** (the AST model-usage scan); the CHANGELOG, the coverage snapshots and the "Shipped in 0.22.1" entry of `roadmap-completed.md` are done on top of it | Not recorded beyond the ruling | this section |

The ledger entry for the Git LFS pointer licence file (fixed by #422) is ticked
in [the licences part of the ledger](../../design/known-bugs/licences-and-licenseid.md).
