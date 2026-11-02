---
Created: 2026-11-02
Last-Modified: 2026-11-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: skipping a repeated CI run as a measured, fail-open experiment

See also: [README.md](README.md) (index of these notes),
[ci-cost-and-two-gate-policy.md](ci-cost-and-two-gate-policy.md) (the
measurement and the numbers this note relies on, not repeated),
[testing-and-review-policy.md](../testing-and-review-policy.md) ("CI trim
candidates" and its Record), [wall-clock-bounds-on-shared-runners.md](wall-clock-bounds-on-shared-runners.md)
(a macOS failure seen on this PR's own runs),
[open-research-questions.md](open-research-questions.md).

On 2026-10-30 the CI measurement found that the push run after a merge
repeated a tree a green PR run had already tested (8 of 8 merges checked).
PR #415 turns that into an experiment on one workflow. At the time of
writing #415 is **in review**: branch `ci-skip-duplicate-runs`, one feature
commit (`42ac6372`, 2026-11-02 12:38 UTC) and two merges of `main`, head
`256a39c7` at 14:21 UTC. Its diff against `main`: 5 files, 623 insertions, 5
deletions (the script 172 lines, its tests 345, the composite action 34, the
workflow 28, the policy page 49). **The outcome of the experiment has not
been observed.**

## 1. The decision rule

A `decide` job runs on a push to `main` only
(`scripts/ci/skip_duplicate_push.py`, called from the composite action
`.github/actions/skip-duplicate-push`). It writes `skip=true` only when all
of these hold:

1. the event is a push and the ref is `refs/heads/main`;
2. `HEAD` is the checked-out `GITHUB_SHA` and a merge commit with exactly two
   parents;
3. `HEAD^{tree}` equals `HEAD^2^{tree}`, the tree of the PR head;
4. the Actions API lists a **completed, successful `pull_request` run of
   `test.yml`** whose `head_sha` is `HEAD^2`.

The `test` job has `needs: decide` and
`if: !cancelled() && needs.decide.outputs.skip != 'true'`. On a PR `decide` is
skipped, and the `!cancelled()` form lets `test` run anyway, so the PR path
is unchanged and gains no latency.

- **Fail open.** Anything else runs the matrix: another event or ref, a tag,
  `workflow_dispatch`, a schedule, a release, a squash or rebase merge (one
  parent), an octopus merge, a git error, an API error or any exception
  (`decide()` catches all and returns "run"). The script exits 0 in every case,
  and its log line says why (`INFO: duplicate-push check: run: <reason>`).
- **Nothing from the API is echoed.** Only the status code or the exception's
  type name is logged, so response text cannot place a `::` workflow command on
  the runner log (the project rule for scripts that log tool output).
- **Inputs are shape-checked** before use: the SHA, the repository name and the
  workflow file name each match a pattern, and the API URL must be HTTPS (the
  one exception is a `127.` URL, for the test server).
- **Scope.** `test.yml` only. `pypi-publish.yml` is untouched. `build.yml`,
  hatch and the Action self-test are not covered; "one more `decide` job each,
  if the experiment holds".

Why this rule and not a shorter one: a green PR run says "this tree passed"
only when the merged tree is that tree. Comparing trees, not commit ids, is
what makes a merge commit that adds nothing eligible; requiring a successful
run of the same workflow at the second parent is what makes "that tree passed"
a fact from the API rather than an assumption.

## 2. Residual holes, stated in the policy page

- **A PR run tests the PR merge ref, not the head tree alone.** GitHub's
  `pull_request` event checks out the head merged into `main` as it was at
  the time. If `main` changed and the change was then reverted before the merge,
  the equal-tree test cannot see that the tested tree had been different. The
  page records this as known residual risk; no mitigation was built.
- **A skipped matrix reports under its unexpanded name.** The four `Test on
  Python ${{ matrix.python-version }} (${{ matrix.os }})` jobs show as
  "skipped" under that literal name. It only shows on the push run, which no
  merge waits for, so a required PR check cannot be left "Expected". If a
  push run ever became a required check this would block.
- **Squash and rebase merges never skip.** Their commit has one parent. The
  project merges with merge commits, so this costs nothing today.
- **Revert path.** Delete the `decide` job and the `needs` and `if` lines of
  `test`.

## 3. A measurement that did not repeat

The 2026-10-30 figure was 8 of 8 merges with an equal tree. On 2026-11-02 three
PRs merged within 45 seconds (#416 at 14:19:58, #417 at 14:20:20, #418 at
14:20:43 UTC). I compared the trees (`git rev-parse <merge>^{tree}` against
the second parent's), and the PR head run of each in the Actions API:

| Merge | Tree equals PR head's tree | PR head `Unit tests` run | Push `Unit tests` run on the merge |
| --- | --- | --- | --- |
| #416 `1710298e` | no | success (12:59 UTC) | cancelled by a newer push |
| #417 `e93078cb` | no | success (14:12 UTC) | none (docs-only merge; `paths-ignore`) |
| #418 `c45dd72e` | no | success (14:13 UTC) | success |

- 0 of 3 would have skipped. The likely reason (*inference*, not examined
  branch by branch): the three PRs were open together, so each head lacked
  what the earlier merges added to `main`. The rule would have run the matrix,
  which is the designed result for "`main` moved", not a failure.
- 1 of 3 push runs was cancelled by the next push under the existing
  `concurrency` setting (the other workflows of the #416 push were cancelled
  too: Lint, Type checking, Build, Action self-test); 1 was never created
  because `paths-ignore: **/*.md` applies on a push (it compares with the
  previous commit). Only #418's push run ran to the end.
- Reading: the 2.9 runs per merged PR of 2026-10-30 will fall where merges are
  serial (each PR updated from `main` before merging, so the tree is the PR's)
  and will not where they queue. The saving depends on merge habits as much as
  on the rule. That day gives n = 3 and no estimate of the proportion.

## 4. The markdown-only follow-up: analysed, not built

The same measurement found 4 of 19 PR runs started from a commit that changed
only Markdown. `paths-ignore` on `pull_request` is judged against the whole
PR diff, so a CHANGELOG-only commit re-runs the matrix. The policy page now
records why the cheap fix is not safe, as three conditions:

1. The skip must also require that the previous head (`github.event.before`)
   has a successful run. Otherwise a red code commit followed by a docs commit
   shows green on the new head.
2. `before` is unreachable after a force-push (fail open again).
3. A skipped matrix job reports under its unexpanded name, which can leave a
   *required* check "Expected" and block the PR. The jobs would have to run and
   skip their steps (the runner start-up is still paid), or a stable gate job
   would have to become the required check. That needs the branch-protection
   settings in view first.

Condition 3 is why the push-run skip is safe and this one is not: the same
reporting quirk is harmless on a run nobody waits for and harmful on one a
merge waits for.

## 5. Experiment protocol (from the policy page)

- **Expect to see**, after the next merge whose tree equals a green PR head's:
  `Decide whether to run` green with `INFO: duplicate-push check: skip: ...`
  in its log and the four `Test on Python` jobs skipped.
- **Expect the matrix to run** after a merge where `main` moved, and after a
  direct push.
- Not stated in the page, my addition: three skip observations and one
  deliberate run observation before extending to another workflow (the CI
  measurement report proposed "confirm skipped runs on 3 merges").
- **Status: not yet observed.** Three merges have happened since the branch
  was written and none was eligible (section 3).

## 6. What generalises

- A CI skip should be a **decision from checked facts with a reason in the
  log**, with every unknown mapped to "run". A skip that fails open costs
  minutes at worst; one that fails closed hides a failure.
- **State the equivalence you rely on and where it breaks.** "Same tree" is an
  equivalence for *content*; the PR run's content was the merge ref, so the
  equivalence has a hole the rule cannot close.
- **A measured proportion belongs to a window.** The 8-of-8 held for serial
  merges on one day; the same rule saw 0 of 3 on a day of queued merges.

## 7. Open

- Is the equal-tree skip sound across all merge shapes? See
  [open-research-questions.md](open-research-questions.md).
- What fraction of merges over a month is eligible, given how often merges
  queue? Not measured.
- Would a required-check gate job (an always-run job that reports pass when the
  matrix is skipped) remove the reporting quirk and so allow the markdown-only
  skip? The branch-protection settings were not examined.
