---
Created: 2026-11-11
Last-Modified: 2026-11-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: running only the OS-dependent tests on Windows and macOS in a PR

See also: [README.md](README.md) (index of these notes),
[ci-cost-and-two-gate-policy.md](ci-cost-and-two-gate-policy.md) (what the CI
repeats, with the numbers),
[ci-duplicate-run-skip-experiment.md](ci-duplicate-run-skip-experiment.md)
(the post-merge skip this change had to be reconciled with),
[agents-md-rationale.md](../agents-md-rationale.md#tests-platform-and-ci)
(the rules that came out of it).

PR #467 (merged 2026-11-11), modelled on the LicenseID PRs 201 to 204. On a
pull request Windows and macOS run only the tests marked `platform`; Linux, a
push to `main` and a PR with the label `test-all-os` run all of them. This
note records what was measured, what broke on the way and what a reader
copying the idea should check first.

## 1. The result

- About 20,000 tests; 473 of 790 test files (about 60 %) are marked.
- Full run, with the label: Windows 8m14s, macOS 6m41s. Subset run: about
  4.5 to 5 minutes each. The saving is modest (roughly 40 %) because the rule
  is deliberately broad; a narrower rule saves more and misses more.
- The full run with the label on the merged head passed on all four test legs
  and all four wheel-build legs.

## 2. The marker rule reads source text, so it needs a test of its own

A file is marked when it is under `tests/cli/` or `tests/scripts/`, matches a
regular expression of OS-sensitive tokens, or imports (transitively) a
`tests.*` helper that does. Three findings:

- **The first rule marked 36 %** and missed what mattered: Windows drive and
  UNC literals in path tests, and helpers that hold the OS-sensitive code
  while the test file itself looks plain. An independent review (Opus agent)
  found both; the transitive import scan and the literals took it to 60 %.
- **The rule fails open.** A path outside the tests root, or a file it cannot
  read, counts as marked. A rule that fails closed would hide a test.
- **Known gap, accepted and documented:** a behaviour that is OS-sensitive
  only through a Pitloom function, with no token in the test file (CRLF
  through `write_text` plus a digest, a case-insensitive file system, a path
  helper given a plain string). Such a bug shows on `main` after the merge.
  The check against drift is the label plus the push run on `main`, not the
  rule.

After a later merge of `main` (#468 to #473) the rule was run over both trees:
one new unmarked file (pure logic, correctly unmarked), no other change. Run
that comparison whenever `main` moves a helper under `tests/`.

## 3. Three workflow hazards

- **A skipped duplicate push removed the only full Windows and macOS run.**
  The post-merge skip (see the experiment note) assumed the PR run tested the
  same tree on every leg. With a subset on a PR that is false for two legs.
  Fix: a skip shrinks the matrix to Windows and macOS instead of skipping it,
  so `main` still runs them in full. Review found it before it shipped.
- **A label is an event.** With `labeled` in `types`, every unrelated label
  starts a run, and with `cancel-in-progress` that run cancels the one testing
  the branch. The concurrency group is the run id for an unrelated label and
  the ref otherwise, and the job `if` runs only for `test-all-os`.
- **A workflow that reads the label must be one of all the workflows that
  gate on it.** `build.yml` had no `labeled` trigger, so the label restored
  the tests but not the Windows and macOS wheel builds. Found by asking "will
  that be an issue?", not by a check. A matrix expression reading
  `github.event.pull_request.labels.*.name` works on `synchronize` too, so a
  push after labelling needs no second label event.

## 4. A flake that was a race, and a wrong explanation of it

`test_ctrl_c_kills_what_git_started` failed on Ubuntu / 3.10 only. The first
explanation (a killed child seen as alive because `os.kill(pid, 0)` succeeds
on a zombie) was plausible, was partly true, and was not the cause. An Opus
review reproduced the real one: `_capture` started the timer and the reader
thread before its `try` block, so a Ctrl-C landing in `Thread.start()` skipped
`_kill(proc)` and left git running. Fix: start both inside the `try`; a
regression test whose `Thread.start()` raises `KeyboardInterrupt` fails on the
old code. The zombie finding became a shared `tests/_pid.py` (a Linux zombie
is gone; a Windows path through `tasklist`).

Lesson: a flake with a plausible mechanism still needs a reproduction that
fails on the unfixed code; "I can explain it" was the unverified claim.

## 5. Process notes

- **A refactor moved a helper and broke an import in another test file**,
  seen first as a macOS collection error and reported as "7 tests failed".
  Cause: two test files were run before the first commit. Run the full suite
  before the first push (the two-gate policy says so).
- **The worktree changed branch under the session** twice (another session or
  the user switched it). Read `git branch --show-current` before an edit that
  is meant for one branch.
- **Verify the premise of a "does it work" question against the run, not the
  design.** The label fix was confirmed by listing the checks of the run, not
  by reading the workflow.

## 6. Open

- Whether the 40 % saving is worth the miss risk is unmeasured over a longer
  window: count Windows or macOS-only failures that first appeared on `main`.
- The rule is a regular expression; a marker declared in the file
  (`pytestmark`) is explicit but relies on the author remembering. AGENTS.md
  tells agents to classify each new test.
- `scripts/manual_cli_checks/_checks_build.py::_pid_gone` keeps its own copy
  of the liveness check and can raise if the process exits between `exists()`
  and `read_text()`.
