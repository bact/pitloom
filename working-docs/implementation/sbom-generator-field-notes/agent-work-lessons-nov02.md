---
Created: 2026-11-02
Last-Modified: 2026-11-06
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: lessons of the 0.22.1 working round for agent work (2026-11-02)

See also: [README.md](README.md) (index of these notes),
[agent-work-lessons-oct30.md](agent-work-lessons-oct30.md) (the lessons this
extends: a stale premise, unpushed work lost, coverage before the push),
[ci-cost-and-two-gate-policy.md](ci-cost-and-two-gate-policy.md),
[wall-clock-bounds-on-shared-runners.md](wall-clock-bounds-on-shared-runners.md),
[bug-ledger-needs-a-severity-scale.md](bug-ledger-needs-a-severity-scale.md),
[process-lessons.md](process-lessons.md),
[open-research-questions.md](open-research-questions.md).

Items marked *session record* are the caller's account of the working
session, which I could not check in Git. Items with a source name it.

## 1. A hand-back delivered again and again

- *Session record.* One agent's final report reached the caller many times
  (the count was not given). By the caller's account the agent was "waiting
  on its own background work": each completion notice of a task it had
  started woke it, and each time it delivered the same final report.
- **Why it matters.** Every copy costs the caller's context and risks being
  read as new work. A report that arrives twice is, to a caller that cannot
  tell the copies apart, indistinguishable from two reports.
- **Remedy used:** stop the background task (the harness has a task-stop tool),
  so no further notice wakes the agent.
- Do: an agent ends with one hand-back, and only after every background task it
  started has finished or been stopped. A brief that asks for a background job
  also says who stops it.

## 2. PR numbers written before the PR exists

- **Source, verified.** Two commits of 2026-10-30 are named "Use the real PR
  number": `8688c9e8` (09:03 UTC, the CHANGELOG) and `98935f5a` (10:44, the
  model-stub family). The number space is shared with
  issues, too. #411 was a merged PR, #412 is an **issue** ("A slash in URL is
  wrongly escaped", opened 2026-10-31) and #413 is an open PR. A guess of "last
  PR plus one" would have named #412.
- *Session record.* The caller lists four numbers where a placeholder and the
  real number collided in this round: #403/#404, #406/#407, #409/#410 and #413.
  I verified the mechanism (above) but not each pair.
- **Cause.** An agent that writes `#NNN` into a CHANGELOG, a note or a commit
  message before the PR exists is predicting the next free number. Other agents
  and the maintainer open issues and PRs meanwhile.
- Do: write no number until it exists. Use a token that a grep finds (for
  example `PR-TBD`), and fix it in one commit after the PR is opened, or ask the
  caller for the number. LicenseID's `AGENTS.md` already says to link the PR
  "once it has a number (never guess one)"; Pitloom's does not.
- Open: a test or check that fails a PR when its text names a number that is an
  issue, or that is not the PR's own. Not built.

## 3. Resume or relaunch

No outcomes were supplied for this round, so I record none. The two facts of
[agent-work-lessons-oct30.md](agent-work-lessons-oct30.md) (section 3) still
bound the choice: a resumed agent keeps its conversation and any stale premise
in it; a relaunched one starts from the brief and the committed branch.

## 4. Fences held

- *Session record.* In this round parallel agents were given file ownership
  in writing ("you own only these paths; others edit these; do not touch").
  The caller reports the fences held. The brief for this note's branch
  named its directory and the paths two other agents owned.
- **Checkable from Git:** the final `git diff --stat` of a branch against
  `origin/main` shows whether it stays inside its fence. The report of the PR
  that carries this note lists its files.
- Do: write the fence in the brief; check the diff stat at hand-back.

## 5. The two-gate rule in practice

- **A premise re-measured.** The brief for these notes carried figures. I
  re-measured the ones I could: "179 entries" gave 174 checkbox lines (177 in
  the index table); "38 KB over the hard limit" gave 34,008 bytes counting both
  files; "about 48 unprioritised" matched exactly. And "~35 s stalls in several
  unrelated loopback tests" turned out, from eight macOS junit files, to be
  three standing costs and two new stalls. Of the four, one held as given and one
  held in part. The principle of
  [agent-work-lessons-oct30.md](agent-work-lessons-oct30.md) (section 1) applies
  to figures in a brief as it does to premises.
- **A local checkout was stale again.** `git worktree list` shows the main
  checkout at `df7331d2`, several merges behind `origin/main` (`c45dd72e`). A
  worktree made from `origin/main` after a fetch, as this brief ordered, avoids
  it. The Oct-30 lesson held because the command was in the brief.
- **Gate A cannot see a macOS-only failure.** Gate A is the full suite on the
  agent's machine (Linux, as root, in a sandbox). The failure of run
  41449530712 appeared on the macOS leg only. The policy leaves the CI matrix
  unchanged on purpose for that reason; the cost is visible in this round: two
  legs cancelled by `fail-fast` after about 4.5 minutes.
- **State only what is measured.** The #415 policy text states the measured
  counts (a third of `test.yml` runs; 8 of 8) and labels the saving's outcome
  as to be observed. These notes follow it: the experiment's result is "not yet
  observed" and the macOS cause is "not confirmed".

## 6. The rate-limit loss, again

- *Session record.* The pattern of 2026-10-30 recurred in this round:
  uncommitted work was lost when a run ended at the rate limit; committed work
  survived. Which agent and how much was lost were not given.
- **What Git cannot tell.** Lost work leaves nothing in the repository, so its
  frequency cannot be counted from history; only the caller keeps a tally.
- Do: as in the Oct-30 note, commit and push each finished piece to the agent's
  own branch. This brief repeated the rule ("push only this branch, retry with
  backoff").

## 7. Open

- Whether a hand-back should be an object the caller can deduplicate (an
  identifier in the first line), so a second copy is recognisable at a glance.
- Whether the placeholder rule belongs in Pitloom's `AGENTS.md` as it does in
  LicenseID's.
