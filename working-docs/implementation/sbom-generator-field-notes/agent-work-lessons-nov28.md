---
Created: 2026-11-28
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: a lead session and a fix session over five PRs (2026-11-28)

See also: [README.md](README.md) (index of these notes),
[agent-work-lessons-nov10.md](agent-work-lessons-nov10.md) (worktree per
session, fenced ownership), [process-lessons.md](process-lessons.md)
(review rounds and test tiers),
[dependency-licences-declared-and-concluded.md](dependency-licences-declared-and-concluded.md)
(what the work found).

One lead session verified 0.25.0 and ran PRs #568 to #572; a second
session, started by the lead, owned #569's branch. Items marked *session
record* are the lead's account; items with a PR or file were checked in
Git or on GitHub.

## 1. An isolated worktree cannot touch another's branch

- *Session record.* The lead's session was confined to its own worktree:
  edits to #569's worktree and any git command naming another path were
  refused. The fix went to a second session, which kept its own branch
  and pushed with `git push origin HEAD:dependency-licence-files`, a
  fast-forward. A branch name containing "git" also tripped the guard;
  `git push origin HEAD` avoided naming it.
- *Session record.* A commit the user had not asked for was refused by the
  permission classifier, though earlier commits in the session had been
  approved. Each commit needed its own request.

## 2. Relayed rulings cross; restate them and check every push

- *Session record.* Messages between the two sessions crossed four times:
  a ruling arrived after the work it changed had been pushed, or while the
  other session was asking the question it answered. Restating every
  ruling in full in each message kept the second session from acting on a
  stale one.
- **A report is not proof.** Checks of each push found: a "correction" of
  the ledger index that was wrong (11 fixed entries, 2 of them ticked but
  left under `## Open`; the rule counts every ticked entry); two
  follow-ups reported as recorded that were not; a handoff file written
  outside the repository; a count of "15 of 15" that was 14 (one package
  did not exist).
- **A brief can contradict the design doc.** The lead's brief said a
  licence detected from a dependency's file stays concluded (an earlier
  user ruling); the design doc, ruled two weeks before, said declared. The
  brief's "stop if the doc and this brief disagree" made the fix session
  ask instead of guess; the user chose the doc.

## 3. Green tests, killed mutants, and still a bug

- Four Opus review rounds on #569 and #571 each found a real defect after
  the tests passed: a drift-guard test the lead had not run (CI would
  have failed), dot segments past a URL check, a dual licence narrowed to
  one, one value with two relationship types, and a note lost when a
  licence element already existed.
- Every mutant of the fixes was killed. Mutation testing shows the tests
  check what the code does; it did not show the fixture covered the
  shape that failed (a new element only, never an existing one).
- Do: give each review the code, not the conclusion; ask for a writer
  inventory and a before/after on real data; reproduce each finding
  before relaying it.

## 4. "Merge-ready" was checked, not assumed

- Each "it is green" was checked: the `test-all-os` label time against
  the head's run start, and each leg's test count (31,762 to 31,827, the
  same on every OS per run). Twice the green head was not the head that
  carried the review fixes.
