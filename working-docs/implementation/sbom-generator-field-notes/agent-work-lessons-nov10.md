---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: lessons of the PyPI URL round for agent work (2026-11-10)

See also: [README.md](README.md) (index of these notes),
[agent-work-lessons-nov02.md](agent-work-lessons-nov02.md) and
[agent-work-lessons-oct30.md](agent-work-lessons-oct30.md) (earlier rounds),
[process-lessons.md](process-lessons.md) (review rounds and test tiers),
[remote-fetch-hardening.md](remote-fetch-hardening.md) (what the reviews of
this round found), [pypi-url-sources.md](pypi-url-sources.md),
[../recurring-bug-patterns-platform-windows.md](../recurring-bug-patterns-platform-windows.md)
(the Windows-only failures of the same PR).

PR #468 started as "PyPI URL targets" and grew, by the maintainer's
decisions during the round, into one fetch policy and shared message codes
for the Git, PyPI and Hugging Face routes. One lead session planned the
work, gave parts to sub-agents and ran the reviews. Items marked *session
record* are the lead's account of the session; items with a commit or file
name were checked in Git.

## 1. A shared checkout needs a worktree from the first edit

- *Session record.* Two other sessions worked in the same local clone at the
  same time. The round's first commits were made in the shared checkout
  before this was known; the work then moved to a Git worktree under
  `.claude/worktrees/`, listed in `.git/info/exclude` so the other sessions'
  status stays clean.
- Do: start every session in its own worktree on a branch from the remote
  default branch; never switch branches, stash or commit in a checkout that
  another session may use. The stash stack is shared by all worktrees: set
  work aside with a temporary commit instead.

## 2. Fenced file ownership made parallel agents safe

- *Session record.* Six work packages ran with written file ownership
  (resolver and HTTP client; messages; assembly and provenance; command
  line; docs and skills; changelog). No two agents edited one file; the
  messages package went first because the others import its constants. The
  integration gate (full suite, every linter) ran once, after all had
  landed.
- Do: write the ownership list into each brief, order a producer of shared
  names before its consumers, and gate after the last agent, not after each.

## 3. A review agent told "no network" still reached the network

- *Session record.* A reviewer briefed to stay offline ran `git` on a URL
  with a non-ASCII host, to test the Git route's handling of it. The test
  socket block does not cover a subprocess, so one real request left the
  machine. Nothing sensitive was sent; the lead reported it to the
  maintainer and later briefs said "do not run git or any other networked
  program; patch the runner".
- Do: in a reviewer's brief, name the programs it must not start, not only
  "no network"; a socket guard in the test process does not reach a child
  process.

## 4. Green CI, then area-split reviews, still found real faults

- **Checked in Git** (commit "Fix review findings on the HF, Git, PyPI and
  hook routes"). After every CI leg was green, four fresh-context reviewers,
  one per area, each confirmed faults the suite had not exercised; all were
  fixed in the PR with regression tests. The list is in
  [remote-fetch-hardening.md](remote-fetch-hardening.md), section 6.
- **Scope growth reset the review.** The PR grew twice after its first
  review (a shared policy; Hub caps and endpoint handling). Each growth got
  its own review round; the earlier review did not cover the new code.
- Do: when a PR's scope grows, review the new area as if it were a new PR.

## 5. Claims from agents and docs, checked against code

- *Session record.* Several statements written by agents or kept from
  earlier drafts did not match the code: a field list of skipped model-card
  keys that missed two, a doc saying the Git classifier reads `remote:` lines
  (it reads only git's own lines since the review; corrected in
  `remote-fetch-policy.md` on 2026-11-10), and a leftover note on Windows
  junctions that the review had already fixed (removed the same day).
- Do: before writing "X does Y" in a note, open the function that does Y;
  re-read the leftover list after a review round and drop what it fixed.

## 6. Mutation testing and coverage found the thin tests

- *Session record.* Mutants that survived pointed at a drift-guard test that
  compared two routes in one direction only and at boundaries tested with
  one side of a `>=`. Coverage at the end found two lines in the Git host
  check that no input could reach (`urlsplit` had already accepted the URL
  upstream): the branch was removed (commit "Drop an unreachable branch in
  the Git host check") rather than covered by a test of a private helper,
  and a test now pins the upstream refusal of the same input.
- Do: when a line is unreachable, prove it from the caller's contract and
  delete it; test the caller's refusal instead.

## 7. A merge that renames needs a sweep beyond the conflicts

- **Checked in Git** (merge of `origin/main` with #469 and #470). `main`
  renamed an option while the branch added new uses of the old name. Six
  files conflicted; the old name also survived in files that merged
  cleanly, and a generated table in `docs/cli.md` was stale.
- Do: after merging a rename, grep the whole tree for the old spelling;
  regenerate generated pages from their source instead of resolving them
  by hand.

## 8. A set-up proof must not be stricter than the claim

- **Checked in Git** (commit "Relax the refused-endpoint test's set-up
  proof"). A test first showed that the third-party library, called
  directly, sends the token to the endpoint, then that Pitloom's read sends
  nothing. Its set-up assertion required exactly one request; on one CI leg
  the library made another beside it. The proof needs only that the token
  reached the endpoint.
- Do: assert in a set-up proof the least that makes the main assertion
  meaningful; the main assertion stays exact.

## 9. Read every CI leg, and the cancelled ones

- *Session record.* Four of the round's CI failures were on the Windows leg
  only and one on Linux with the newest Python only; with fail-fast, a red
  leg cancels the others, so a fix can pass the leg that failed and still
  break one that never ran. The final head had all eleven workflows and four
  test legs green, none cancelled.
- Do: after a fix, read every leg of the next run to its end.

## 10. Notes that will be public

- *Session record.* The maintainer asked that the leftover notes be written
  with care, as all working notes are public. The leftovers name each
  limitation and what a user can do, without a sequence of steps that would
  turn a limitation into an exploit; the roadmap points at them in one line.
- Do: in a public note, state the limit, its bound and the mitigation; keep
  reproduction detail for a private channel.

## 11. A permission check on commits is a feature

- *Session record.* An automatic permission check refused the lead's first
  commit because the maintainer had not yet asked for one; the lead waited
  and committed only when asked. Every commit carries a DCO sign-off and the
  maintainer as author, checked with `git log -1 --format=%an` before each
  push.
- Do: when a guard refuses an action, do not route around it; ask.
