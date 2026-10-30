---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: lessons of one day of agent work (2026-10-30)

See also: [README.md](README.md) (index of these notes),
[process-lessons.md](process-lessons.md) (earlier rounds: parallel PRs,
stash by path, concurrent suites),
[ci-cost-and-two-gate-policy.md](ci-cost-and-two-gate-policy.md) (the
measurement behind section 1),
[testing-traps.md](testing-traps.md) (a Codecov item from #300 that this
extends), [raw-exception-text-leaks-paths.md](raw-exception-text-leaks-paths.md)
(the PR whose tests section 4 describes),
[open-research-questions.md](open-research-questions.md).

Items marked *session record* come from the working session, not from the
repository; they could not be checked in Git.

## 1. A brief can carry a stale premise

- The CI measurement of 2026-10-30 started from two proposed savings
  (parallel workers, a cached licence database). Both were already in the
  live workflow; the agent's local copy of `origin/main` was stale
  ([ci-cost-and-two-gate-policy.md](ci-cost-and-two-gate-policy.md),
  section 1). The agent's first act was to read the live repository, and
  its report opens by correcting the brief.
- **What made it cheap:** the agent measured instead of assuming, and the
  report says which numbers are measured and which estimated.
- Do: a brief that proposes a change names the evidence it came from; the
  agent checks the evidence against the live source (`git fetch`, or the
  API) before sizing the change, and says so when the premise fails.

## 2. Uncommitted work is lost when the session stops

- *Session record:* an agent's work was lost when the API rate limit ended
  its run, because the edits sat uncommitted in a worktree and nothing was
  pushed; work that had been committed (and pushed) survived. I could not
  find which run it was, how much was lost, or a log of it; the claim is
  the caller's account, *unverified*.
- **A tension with a project rule.** `AGENTS.md` says never to auto-commit:
  leave changes uncommitted for the user to review, unless they ask. That
  rule protects a person's review of their own checkout. It does not
  describe an agent that works in its own worktree on its own named branch
  for someone else to merge; there, an uncommitted tree is the only state
  that a stopped run cannot recover. The resolution on this day was in
  each brief: commit with a sign-off, push only the agent's own branch,
  never open a pull request or an issue.
- Do: a brief to an agent that will run long states whether it commits and
  pushes, on which branch, and that it does so early and often (a commit
  per finished piece, a push per commit), because only pushed work
  survives the end of the run.
- Open: whether committing to a private branch and pushing it is itself
  the right default for agents, and what a "WIP" commit should look like
  when the project's history is read as paper material.

## 3. Resuming an agent or launching a new one

*Session record, not sourced:* the caller asked these notes to cover when
to resume an agent and when to relaunch it. No record of the outcome was
available to me, so this section holds only the two facts that bear on it
and no recommendation: a resumed agent keeps the conversation (and any
stale premise in it, section 1); a relaunched agent starts from its brief
and the committed branch (section 2). Which is better for which kind of
work was not measured.

## 4. A patch-coverage gap is derivable before the push

- **The check.** The coverage service (Codecov) reports coverage of the
  *changed lines* of a PR, not only of a file. A PR can pass its own tests
  and still fail that check on a branch only a failing system call reaches.
  An older note (testing-traps, #300) records that the service's file
  report gives the missed lines after the fact, without a login. The new
  practice finds them before the push.
- **The method.** Run the suite with branch coverage and write the JSON
  report; take the changed new-side line ranges of each file from `git
  diff origin/main -U0` (the hunk headers `@@ -a,b +c,d @@`); intersect
  with the report's `missing_lines` and `missing_branches`. The session's
  script (`pr2a_intersect.py`, session scratch) does exactly this per
  module. For #408 I re-ran it at the end of the session on six of the
  PR's modules (`dataset_hash`, `_license_detect`, `_model_generator`,
  `_models_wheel`, `scanner`, `id_registry/_types`) against a coverage
  report made earlier: it listed changed lines missing in three of the six
  and a changed branch missing in all six (*indicative only*: the agent's
  worktree had moved on since the report was made).
- **Why the gaps were there.** The ones I looked at were arms that only a
  failing call reaches: a directory that vanished while walked
  (`dataset_hash` line 354), a directory that cannot be listed
  (`id_registry/_types` lines 216 to 218), and the licence-file name
  fallback when no project root is given (`_license_detect` line 215),
  read in the worktree.
- **The fix was tests that fake the failing call.** A later commit in the
  agent's worktree (07415213, 15:05 UTC, *not on origin when I looked*)
  tests "the absent-versus-unreadable split at each emitter" and says each
  case "runs on every platform and as root, by faking the failing call".
- **A root sandbox hides them.** The agents run as root. Root bypasses
  permission bits, so a test that does `chmod 000` and expects a failure
  passes nothing and is skipped. `tests/_unreadable.py` (on the #408
  branch) therefore has four modes: `open` and `stat` monkeypatch the call
  to raise `PermissionError` on every platform, and `chmod-file` and
  `chmod-dir` use the real bits where the user is not root and not Windows
  (`POSIX_NON_ROOT`, short-circuited so `os.geteuid` is never evaluated on
  Windows). The `stat` mode matters beyond coverage: `Path.is_file()` on an
  unsearchable directory raises on Python 3.10 to 3.13 and returns `False`
  on 3.14 (a comment in that file), so one failing syscall exercises a
  different branch per version.
- **Real bits as a manual check.** Check 25 of the manual CLI checks
  (`scripts/manual_cli_checks`, commit 378d6d91) runs `loom project` on a
  project with a `chmod 000` file and directory and expects one coded line
  each, exit 0 and no absolute path on stderr. It skips on Windows and as
  root; `unshare -U` gives a non-root view in a root sandbox.
- Do: before a push, intersect branch coverage with the diff; drive each
  failing syscall with a monkeypatch so the test runs as root and on
  Windows, and keep one real-permission test for the platforms that have
  them.
- Open: whether the intersection belongs in the repository (a script under
  `scripts/`) so every agent runs one command; it lives in session scratch.

## 5. Other small observations

- **A fresh read-only reviewer is a cheap and independent check**, as in
  earlier days; the policy of 2026-10-30 now writes it down (reviewers read
  only, never another's findings, each finding with a reproducer).
- **Plan first, in the repository.** The registry key, the unreadable-file
  family and the model-stub family each had a read-only plan (one agent,
  session scratch) before the code; the plans listed counts (sites, files,
  tests) that the builds then matched or corrected (the unreadable plan's
  "about 497" became 498 by the ratchet). A plan is an estimate; the
  ratchet is the measurement.
