---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Testing and review policy: two gates per PR

See also: [CLAUDE.md](../../CLAUDE.md) ("Testing": the short rule this
expands), [manual-cli-checks.md](manual-cli-checks.md) (the `--only` map
by area), [ci-test-speed.md](ci-test-speed.md) (earlier CI speed work),
[release-checklist.md](release-checklist.md) (the release steps the
pre-release review runs before),
[recurring-bug-patterns-review-rounds.md](recurring-bug-patterns-review-rounds.md)
(what review rounds found).

How much of the test and review machinery runs, and when, for one PR and
for a release. Adopted by the maintainer on 2026-10-30, for 0.22.0. The
idea is adapted from the sister project `licenseid` (its PR #137, the
pre-release review of its 0.7.0); Pitloom has more surfaces to cover (CLI,
Hatchling hook, library, GitHub Action, skills, Claude Code plugin), a
byte-level determinism rule and slower checks of its own.

## The problem

Measured on 2026-10-30 from `.github/workflows/`, `gh run list` and the
first-parent history of `main`:

- `test.yml` runs the whole suite (`-m "not network"`) on four legs
  (Ubuntu 3.10, Windows 3.11, macOS 3.13, Ubuntu 3.14 with coverage) on
  every push to a PR and again on every push to `main`. `lint.yml`,
  `typecheck.yml`, `build.yml`, `hatch-integration.yml` and
  `action-selftest.yml` run on the same events. Their `paths-ignore:
  **/*.md` skips a push to `main` that changes only Markdown, but not a
  PR push: GitHub filters a `pull_request` event on the whole PR diff,
  so a `CHANGELOG.md`-only commit after code commits runs all of them.
- pytest in CI already runs in parallel: `pyproject.toml`'s `addopts`
  sets `-n auto --dist=worksteal`. The cost is the number of runs, not
  the lack of workers.
- The last 60 `test.yml` runs (2026-10-29 to 2026-10-30): 41 on a PR, 19
  on a push (18 to `main`); 44 succeeded, 11 were cancelled by a newer
  push, 5 failed. A successful run took 5.1-7.4 minutes from creation to
  finish, median 6.6.
- The last 25 PRs merged into `main` (#378-#405, 2026-10-29 to
  2026-10-30) held 145 commits (median 5 per PR, most 24) and 33 merges
  of `main` into the branch; 18 of the 25 had at least one. Each merge
  pushed is another full four-leg run, and the merge into `main` one
  more.

Observed in the agent sessions, not measurable from Git: a PR's agents
ran the full local suite five or more times (after each review round,
each fix batch and each merge of `main`), and the full manual CLI checks
more than once. A merge of `main` that only brought `CHANGELOG.md` link
lines, a ratchet baseline or a generated page still got a full run.

CI timings, from a measurement of the 2026-10-29 16:50 to 2026-10-30
11:40 UTC window (12 successful `test.yml` runs per leg; 10 merged PRs;
medians in seconds, step times at 1 s resolution):

| `test.yml` leg | Job | Of which `Run tests` | Set-up and install |
| --- | --- | --- | --- |
| Ubuntu 3.10 | 352 | 322 | about 16 |
| Windows 3.11 | 401 | 348 | about 35 |
| macOS 3.13 | 322 | 292 | about 20 |
| Ubuntu 3.14, coverage | 350 | 321 | about 15 |

- pytest is 89-91 % of each job; xdist runs 4 workers (3 on macOS) over
  about 17,900 tests. The licenseid database comes from a cache (0-2 s).
- The PR's time to green is the Windows leg, about 6.7 minutes; the
  other workflows run beside it and finish sooner (Pylint 124 s, type
  checks 76 s, `build.yml` 86-112 s a leg, Action self-test 112-130 s).
- About 2.9 `test.yml` runs per merged PR: 1.9 on the PR, 1.0 on the
  push to `main`. In 8 of 8 merges checked, the merge commit's tree was
  the tree of the PR head that had already passed.
- 4 of 19 PR runs came from a commit that changed only Markdown; 3 of
  19 were cancelled by a newer push, 1-2 minutes in; 3 of 19 failed on
  a real test failure, 2 of them on Windows only.
- One PR sync runs about 55 runner minutes over all workflows (Ubuntu
  38, Windows 9, macOS 8), estimated from the job medians; the
  repository is public, so the cost is capacity and waiting, not money.

## The policy for a PR

### Two gates

The slow checks run at two gates only, not in every loop.

- **Gate A, once before the first push.** Full suite (`pytest -n 4`),
  every CI linter (the list in CLAUDE.md, pyrefly and bandit included),
  each new regression test failing on the base tree, branch coverage of
  the changed files, the area's manual CLI checks (`--only`, see
  [manual-cli-checks.md](manual-cli-checks.md#when-to-run)).
- **Gate B, once before handoff.** Tier 3: mutation testing (a mutant
  runs only its module's tests), the full manual CLI checks (`-j 8`;
  `--network` when network code changed), the parity/determinism
  harness, the Windows dry-run, one fresh-context sweep, a fresh read of
  every changed `SKILL.md`. Gate B includes Gate A's full suite and
  linters if anything but docs changed since Gate A.

Between the gates (review rounds, fix batches), a change runs:

- the targeted tests of the files it touched (`pytest tests/<area> -k`,
  `--lf`);
- a diff against `main` of what the change can move: the SBOM bytes of
  the affected fixtures, the stderr lines of the affected commands
  (`INFO:`/`WARNING:`/`ERROR:`), their `KEY=VALUE` and `--json` output;
  an unexplained line in the diff is a finding;
- the invariants that apply (below);
- the linters of the touched files (ruff, mypy; pylint and pyrefly on
  the touched directories).

CI on the PR stays the cross-platform check between the gates: push when
a batch is done, not after each fix.

### Merges of `main`

After a merge of `main` into the branch:

- **No full-suite run** when the merge brought only `CHANGELOG.md` link
  lines, a ratchet baseline (`tests/fixtures/message-inventory/`) or a
  generated page. Run the tests that read those files
  (`tests/test_message_ratchet.py`; `grep -rl <file> tests/` for others)
  and the generator's check (`scripts/generate_message_reference.py
  --check`).
- Otherwise, the targeted tests of the files both sides touched, plus
  the full manual CLI checks if the merge reached `assemble/`,
  `extract/`, `core/`, `embed.py`, `__main__.py` or `plugins/hatch.py`
  (the rule that was already in CLAUDE.md).
- A merge after Gate B that brought code repeats Gate B's full suite
  before handoff.

### Review and fixes

- **Reviewers read only.** A reviewer gets the code, its area and the
  Gate A report; never another reviewer's findings, so the reviews stay
  independent. Every finding comes with a severity and a reproducer: a
  command, a fixture or a test that fails.
- **Batch the fixes.** Reproduce each finding first; drop what does not
  reproduce. Fix in batches by file: output-changing fixes first
  (SBOM bytes, stderr, exit codes, `--json`), then internal ones, docs
  and skills last, so one docs sweep describes the final output.
- **One owner per file.** Parallel agents work in a worktree each, on a
  fenced list of files (CLAUDE.md, "Parallel agents").

### Agents sized to the work

| Work | Model and effort |
| --- | --- |
| Planning, design, open questions; the ID registry, provenance and evidence, archive and model-scan safety, the public contract (CLI output, catalogue codes, SBOM shape), release | Opus, high or max |
| A bounded fix or test with a clear reproducer; a review of one area | Sonnet, medium |
| Mechanical work: renames, link and size checks, a ratchet regeneration, CHANGELOG lines | Haiku, or a low effort |

### Local parallelism

`pytest -n 4` at most, not `-n auto`, on a machine that runs several
agents at once. `-n auto` starts one worker per core in every worktree:
two agents on a 4-core machine run 8 workers, and the timing-sensitive
tests (the 20 s build-timeout tests, the subprocess ones) then fail from
load, not from the change. [ci-test-speed.md](ci-test-speed.md) measured
4 workers at 63-72 s for the suite and 10 workers at 46.5 s: more
workers buy little.

## Pre-release review

For a release with many merged changes, after each had its own review.
Per-PR reviews each see one diff; the bugs they miss sit where changes
meet (a catalogue code and a skill quoting it, a registry key and the
hook's path). It runs before the steps of
[release-checklist.md](release-checklist.md).

1. **Finish in-flight work.** Merge every PR meant for the release.
   Anything merged after the freeze churns the golden files.
2. **Freeze and gate once.** The release candidate is one commit on
   `main`. Run Gate A and Gate B on it once, plus the network tests
   (`pytest -m network`), and keep the outputs as the reviewers' report.
3. **Build the harness** (one PR, parallel agents, a file each):
   - golden snapshots: the SBOM of every fixture project, model and
     wheel the manual checks use, and every subcommand's stdout, stderr
     and `--json` output on them; files under the size limit; a diff
     test that accepts only listed changes; also diffed against the last
     release, to list every intended change;
   - invariants: SBOM bytes identical across two runs and across
     surfaces (CLI, library, hook) with a pinned `SOURCE_DATE_EPOCH`;
     every SBOM valid against SPDX 3; no command raises a traceback on
     any input; one level tag per stderr line; the message ratchet
     holds; generated pages in sync (`--check`); every command, flag and
     message a `SKILL.md` quotes exists;
   - one seeded adversarial generator for hostile names, paths, URLs,
     versions and licence values (quotes, control characters, `..`,
     Unicode, case variants, PEP 440 spellings), shared by the tests,
     the reviewers and the fixers;
   - mechanical health first: file sizes, complexity ceilings
     re-measured, names left over from a rename, lint, links.
   Run the harness on the candidate before merging it: its failures are
   the first findings.
4. **Review**, read-only and in parallel, one agent per surface: CLI
   (every subcommand), library API, Hatchling hook, GitHub Action,
   skills and plugin, user docs (`docs/`), ID registry. Add a downstream
   trial: an agent that reads only `docs/` and `skills/`, uses the
   release as a user would, and reports where the docs and the
   behaviour differ.
5. **Triage.** Reproduce each finding; drop what does not reproduce;
   sort the rest into release blockers, cheap fixes for this release,
   and the next release.
6. **Fix in batches by file**, as for a PR: per batch the targeted
   tests, the golden diff, the invariants, then CI.
7. **Final gate.** Gate A and Gate B again on the final commit, then the
   steps of [release-checklist.md](release-checklist.md).

Performance is out of scope unless the release is about it. A guard
against a hang or unbounded memory on hostile input is correctness and
stays in.

## What runs where

| Check | Tier 1 | Between gates | Gate A | Gate B | CI per push | CI on `main` | Release gate | Nightly / live |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Touched tests | yes | yes | (full) | (full) | (full) | (full) | (full) | no |
| Full suite, not network | no | no | yes | if code changed | 4 legs | 4 legs | 4 legs | no |
| Network tests | no | no | if network code | if network code | no | no | yes | weekly |
| ruff, mypy | yes | touched | all | all | yes | yes | yes | no |
| pylint, pyright, pyrefly, flake8, bandit | no | touched | all | all | yes | yes | yes | no |
| Golden / stderr / SBOM diff vs `main` | no | yes | yes | yes | no | no | yes (vs last release) | no |
| Invariants | no | the ones that apply | yes | yes | as tests | as tests | yes | no |
| Manual CLI checks | no | no | area | full | slice | slice | full | no |
| Mutation testing | no | no | no | yes | no | no | no | no |
| Parity/determinism harness | no | no | no | yes | no | no | yes | no |
| Windows dry-run | no | no | no | yes | Windows leg | Windows leg | yes | no |
| Fresh-context sweep | no | no | no | yes | no | no | per surface | no |
| Hatch integration, Action self-test | no | no | no | no | yes | yes | yes | no |
| Fuzzing | no | no | no | no | no | no | no | on dispatch |

"Slice" is what `tests/scripts/test_manual_cli_checks.py` runs inside
pytest. "Weekly" is `live-tests.yml` (Mondays); the release gate is
`pypi-publish.yml`, which also runs the network tests strictly.

## What does not change

- The CI matrix keeps its four legs and runs on every push to a PR and
  to `main`; it is the release gate's cross-platform evidence.
- No test is dropped, skipped or marked slow to save time. A slow test
  is made faster or moved to a gate, never removed.
- Every rule in CLAUDE.md's "Testing" section still holds: a regression
  test fails on the base tree, mutation testing runs once per PR, the
  manual CLI checks run in full before handoff.

## CI trim candidates

Not changed by this policy: each needs a PR of its own with a before and
after measurement. From the measurement above, largest first:

- **Skip the push run on `main` when the merged tree is the tree of a
  green PR head** (8 of 8 merges checked): about a third of `test.yml`
  runs and about 53 runner minutes a merge, at no cost to PR latency.
  It still runs when `main` moved between the PR's last run and the
  merge.
- **Skip the test and build workflows for a PR commit that changes only
  Markdown** (a first-step diff against the previous push, behind a
  gate job so required checks still report): about a fifth of PR runs.
- **Run `build.yml` and the Action self-test only when their inputs
  change** (`src/`, `action.yml`, `scripts/action/`, `pyproject.toml`);
  the hit rate is not measured yet. Both validate the same kind of SBOM
  twice a leg (26-46 s a step).
- **Fewer PR legs** (Windows and macOS on `main` only) saves about half
  of `test.yml`'s runner minutes and about 50 s of PR wall time, but 2
  of the 3 PR failures seen were Windows-only: it would move those
  findings after the merge. Not recommended for now.
- **Suite volume** is the only lever on the 400 s critical path: the
  licence-corpus cases (6-19 s each) and `test_import_order` (10-20 s)
  lead `--durations=20`; a `--durations=0` run aggregated by file comes
  first.

## Record

- 2026-10-30: adopted for 0.22.0, with the CI measurement above.
