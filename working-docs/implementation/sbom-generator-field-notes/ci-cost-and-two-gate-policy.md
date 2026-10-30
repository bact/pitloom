---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: what the CI repeats, measured, and the two-gate rule

See also: [README.md](README.md) (index of these notes),
[process-lessons.md](process-lessons.md) (review rounds and test tiers
before this policy), [agent-work-lessons-oct30.md](agent-work-lessons-oct30.md)
(the same day's lessons on agents),
[testing-and-review-policy.md](../testing-and-review-policy.md) (the policy,
PR 406), [ci-test-speed.md](../ci-test-speed.md) (earlier speed work),
[testing-traps.md](testing-traps.md),
[open-research-questions.md](open-research-questions.md).

On 2026-10-30 the maintainer asked whether the test and review machinery
repeated itself more than it needed to. The answer was a measurement, then
a policy (#406, merged 13:15 UTC). This note keeps the numbers with their
sample sizes and says which are measured and which are estimated. The CI
measurement is a read-only report made from the GitHub API (session
scratch, not in the repository; its figures are copied into the policy
page); the policy page is the record.

## 1. Two premises of the brief were wrong

The brief to the measuring agent proposed two savings: turn on parallel
test workers (`-n auto`) and cache the licence database. Both were already
in place:

- `pyproject.toml` `addopts` has `-n auto --dist=worksteal`; the logs show
  4 workers on Ubuntu and Windows, 3 on macOS, 17,867 test items
  (measured). The candidate saved 0.
- The licence database is cached (`actions/cache` on
  `~/.local/share/licenseid`, key `hashFiles(pyproject.toml)`); the
  `Build licenseid database` step took 0 s to 2 s a leg (measured, one
  run).
- **Cause: a stale local copy.** The report states that the local
  `origin/main` copy of the workflow was stale (it lacked the cache and
  database steps) and that the live `test.yml` had them; the brief's
  premises fit that stale copy (*inference*). The report's first section
  is "Corrections to the brief (from the live repo, not local
  origin/main)".
  Do: before sizing a saving, read the workflow on the live repository
  (the API, or a fresh fetch), not a clone that may be behind; and have the
  measuring agent verify each premise it is given before it measures.

## 2. What was measured

Window: 2026-10-29 16:50 to 2026-10-30 11:40 UTC, about 19 hours. All
times in seconds, step times at 1 s resolution.

| Fact | Value | Label | n |
| --- | --- | --- | --- |
| `test.yml` job total, Ubuntu 3.10 | 352 median, 381 max | measured | 12 runs per leg |
| Windows 3.11 | 401 median, 420 max | measured | 12 |
| macOS 3.13 | 322 median, 362 max | measured | 12 |
| Ubuntu 3.14 with coverage | 350 median, 393 max | measured | 12 |
| pytest share of each job | 89 to 91 % | measured | 12 |
| Time to green of a PR | the Windows leg, about 400 s | measured (the slowest leg) | 12 |
| Other workflows | shorter: Pylint 124, type checks 76, `build.yml` 86 to 112 a leg, Action self-test 112 to 130 | measured | 6 runs each |
| Runs per merged PR | about 2.9: 1.9 on the PR, 1.0 on the push to `main` | measured | 10 merged PRs |
| Push run repeats a green tree | 8 of 8 merges checked: merge commit tree equals the PR head's tree, and that head's run was green | measured | 8 |
| PR runs from a commit that changed only Markdown | 4 of 19 (21 %) | measured | 19 PR runs |
| PR runs cancelled by a newer push | 3 of 19, 1 to 2 minutes in | measured | 19 |
| PR runs failed | 3 of 19, all real test failures; two on Windows only | measured | 19 |
| One PR sync, all workflows | about 55 runner minutes (Ubuntu 38, Windows 9, macOS 8) | estimated from job medians, rounded up per job | n/a |
| Private-repository what-if | about 136 minutes with OS multipliers | estimated | n/a |

Further facts from the policy page (a wider window, 60 `test.yml` runs):

- 41 runs on a PR, 19 on a push (18 to `main`); 44 succeeded, 11 were
  cancelled by a newer push, 5 failed (measured). A successful run took 5.1
  to 7.4 minutes from creation to finish, median 6.6.
- The last 25 PRs merged (#378 to #405) held 145 commits (median 5 per PR,
  most 24) and 33 merges of `main` into a branch; 18 of the 25 PRs had at
  least one (measured from first-parent history).
- Observed in the agent sessions, not measurable from Git: a PR's agents
  ran the full local suite five or more times, and the full manual CLI
  checks more than once; a merge of `main` that brought only `CHANGELOG.md`
  link lines, a baseline or a generated page still got a full run.

The repository is public, so the standard runners cost no money and the
Windows and macOS multipliers do not apply: the cost is capacity and
waiting. The 55-minute figure is for reasoning about the queue, and the
136-minute figure only for a private repository.

## 3. Why the repetition exists (two mechanisms)

- **The push run repeats a green tree.** In 8 of 8 checked merges the tree
  that `main` received was byte-identical to the tree of the PR head that
  had passed. *Inference:* the branches had merged `main` in before the
  merge (18 of the last 25 PRs did, 33 merges in all), so `main` had not
  moved; the other 7 PRs are not explained by this. A merge after `main`
  moved would give a different tree and
  deserve the run. The saving of skipping the identical case is about one
  third of `test.yml` runs (10 of 29, measured count) and about 25 runner
  minutes a merge (estimated); it costs no PR latency.
- **`paths-ignore: **/*.md` does not skip a Markdown-only commit on a PR.**
  GitHub evaluates a `pull_request` path filter on the whole PR diff, not on
  the new commit, so a `CHANGELOG.md` commit after code commits runs every
  workflow. Of the 4 such runs in the sample one (run 1620) was cancelled
  by the next push and three (1621, 1624, 1629) ran to green, about 7
  minutes each; the report's own sentence ("2 of those 4 were later
  cancelled or superseded") does not match its run list, so the split is
  *as listed*, not re-checked. The list excludes merge commits, whose
  first-parent diff is not meaningful.
  Do: check how a CI filter's event evaluates a path before relying on it.

## 4. The decision: two gates per PR (#406)

Adopted by the maintainer on 2026-10-30 for 0.22.0, adapted from the sister
project `licenseid` (its PR #137, the pre-release review of 0.7.0).

- **Gate A, once before the first push:** full suite (`-n 4`), every CI
  linter, each new regression test failing on the base tree, branch
  coverage of the changed files, the area's manual CLI checks.
- **Gate B, once before handoff:** mutation testing, the full manual CLI
  checks, the parity and determinism harness, the Windows dry-run, one
  fresh-context sweep, a fresh read of each changed `SKILL.md`.
- **Between the gates:** the touched tests, a diff against `main` of what
  the change can move (SBOM bytes, stderr lines), the invariants that
  apply, the linters of the touched files. A merge of `main` that brought
  only `CHANGELOG.md` link lines, a ratchet baseline or a generated page
  needs the tests that read those files, not the full suite.
- **Reviewers read only**, and never see another reviewer's findings; each
  finding comes with a severity and a reproducer. Fixes go in batches by
  file, output-changing fixes first, docs last.
- **Local workers: `-n 4`, not `-n auto`**, on a machine that runs several
  agents. `ci-test-speed.md` measured 4 workers at 63 to 72 s for the suite
  and 10 workers at 46.5 s: more workers buy little, and two agents on four
  cores run eight workers, which fails the timing-sensitive tests from
  load (the 20-second build-timeout tests).
- **What did not change:** the four-leg matrix on every push, no test
  dropped or marked slow to save time, every rule of the testing section
  of `AGENTS.md`.

The policy's own statement: the slow checks run at two gates only, not in
every loop, and CI on the PR stays the cross-platform check between the
gates (push when a batch is done, not after each fix). It was adopted
together with the measurement above and has not been measured since.

## 5. Trim candidates, rejected or not yet built

Each needs a PR with a before and after measurement; none was changed by
the policy.

| Candidate | Saving | Basis |
| --- | --- | --- |
| Skip the push run when the merged tree equals a green PR head's tree | about a third of `test.yml` runs; about 53 runner minutes a merge over all workflows | counts measured; minutes estimated |
| Skip tests and build for a Markdown-only PR commit (a gate job, so required checks still report) | about a fifth of PR runs | counts measured |
| Run `build.yml` and the Action self-test only when their inputs change | not sized; the hit rate was not measured | unmeasured |
| Validate SBOMs once, not in both `build.yml` and the self-test (26 to 46 s a step, twice a leg) | about 60 to 80 s per leg, in parallel, so no PR latency | measured steps, estimated billing |
| Fewer PR legs (Windows and macOS on `main` only) | about half of `test.yml` minutes, about 50 s of PR time | measured; **not recommended**: 2 of the 3 PR failures seen were Windows-only |
| Reduce the suite's volume | the only lever on the 400 s critical path | `--durations=20` shows, in some legs, 8 or more licence-corpus cases of 6 to 19 s each, and `test_import_order` at 10 to 20 s; a `--durations=0` aggregation by file is the first step |

The slowest tests are not the wall-clock driver: the three deliberate
timeout tests take about 51 CPU-seconds but run in parallel, so they set a
straggler floor of about 20 s (measured, one run per leg).

## 6. Limits of the numbers

The timing sample is 12 successful runs per leg, with no failed run in it;
the others 6 runs; the durations are one run per leg; the window is 19
hours with 10 merges, one busy day, so no daily or monthly figure should
be derived. Billing rounding and the runner OS of the self-test, Hatch and
lint jobs were assumed Ubuntu and not checked per job. Older runs of two
PRs (#387, #402) fall outside the window, so runs per PR is an undercount.
The policy page's wider 60-run window and this 12-run timing sample are
different samples; the numbers are not meant to agree.

## 7. What generalises

- Count the runs before tuning one: a pipeline that runs 2.9 times per
  merged change is a bigger lever than a pipeline that is 20 % faster.
- Measure which tool is already on. Two of the first candidates saved
  nothing because the tools were already configured.
- A filter on paths is a statement about an event, not about a commit.
- Stale state of the repository you are advising on is the cheapest error
  to prevent (section 1).

## 8. Open

- How much of the repetition is *needed* signal? The post-merge push run
  is the only run on the exact commit that becomes `main`; skipping it when
  the tree equals a green head's loses nothing only if the PR's run really
  tested that tree on all four legs. Not measured: how often a green PR
  run is itself a partial or cancelled one.
- Which share of agent-side repetition (the full local suite five or more
  times per PR) the two gates removed. The policy is adopted but not yet
  measured; a before and after count over the next PRs is the check.
