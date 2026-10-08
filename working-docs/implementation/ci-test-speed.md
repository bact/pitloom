---
Created: 2026-10-09
Last-Modified: 2026-10-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CI test speed: measurements and decisions

See also: [ci-install-composite-action.md](ci-install-composite-action.md)
(the uv install switch, its cache and interpreter decisions),
[windows-macos-ci.md](windows-macos-ci.md) (the matrix),
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md)
(the env leak `worksteal` exposed),
[testing-ci-followups.md](../design/testing-ci-followups.md) (open items).

**Status (2026-10-09):** PR [#295](https://github.com/bact/pitloom/pull/295)
merged; PR [#297](https://github.com/bact/pitloom/pull/297) makes the
Windows temp-drive change and the junit upload permanent.

## What was built

- **#295:** pytest `--dist=worksteal` (was `loadscope`); CI installs with
  `uv pip` instead of pip; Pylint in its own job, the Ruff/flake8 job
  installs no package; `--durations=20` in `test.yml`.
- **#297:** every `test.yml` leg uploads `pytest-junit.xml` (per-test
  times, 14 days, about 0.13 MB zipped per leg); the Windows leg runs with
  `TMP`/`TEMP` on `RUNNER_TEMP` (`D:`, the checkout's drive) instead of
  `C:\Users\RUNNER~1\AppData\Local\Temp`.

## Measurements

Wall-clock is the slowest leg of `test.yml`, the Windows one. CI times
vary about +/-25 % between identical runs (main's Ubuntu 3.14 pytest step:
97-160 s), so a single run cannot show a pytest change below that.

| Change | Measured | Where |
|---|---|---|
| uv instead of pip | install step 10-53 s -> 1-15 s (warm cache; Windows tests 40-53 s -> 15 s) | 2 PR runs vs 3 main runs, every leg |
| Pylint job split | lint workflow 107-139 s -> about 95 s; Ruff job 16-26 s | same |
| `worksteal` | local, 4 workers: 100 s -> 63-72 s; 10 workers: 55 s -> 46.5 s | local; on CI within noise |
| Windows `TEMP` on `D:` | -47 test-seconds (-8 %), all in `tmp_path` tests; step 10-15 s faster in 3 of 4 attempts, 32 s slower in 1 | #297, 4 attempts (per-test data: attempt 4 only) |

`worksteal` gave no measurable CI gain: on 4 vCPU runners the per-test cost
dominates, and the local gain does not show through the noise. It stays:
it is never slower, and it exposed a real test leak.

## Where Windows spends its time

From #297's junit files (attempt 4; test-seconds = sum of per-test times,
wall is about a quarter with 4 workers):

- About 19 s before the first test: interpreter start, imports, collection
  of 9,600 tests in every worker (4.2 s locally in one process).
- No straggler: the 4 workers finish within 6 s of each other. macOS (3
  workers) has one: the two 20 s timeout tests start late.
- Every test is about 2x slower than on macOS (median, tests over 20 ms):
  pure compute x1.93, subprocess x2.17, `tmp_path` x2.35, spdx3-validate
  x2.9-3.2. The baseline is the runner and interpreter, not a few tests.
- Share of Windows test-seconds (566 s with `TEMP` on `D:`):
  spdx3-validate tests about 135 s (24 %), licence-corpus tests about 70 s
  (12 %; `licenseid` matching takes 0.7-1.4 s per file locally, warm or
  cold), the rest spread at about 2x macOS.

## Decisions

- **Windows `TEMP` on `D:`, kept.** Free, lower variance. Trade-off: CI no
  longer runs under an 8.3 short temp path (`RUNNER~1`); no test depended
  on it (all 9,319 Windows tests passed on both legs), and real users'
  temp paths are rarely short names.
- **junit upload, kept.** The next timing question is a download, not a
  measurement PR. Re-running a workflow replaces the artifacts, so
  download after each attempt to keep more than one sample.
- **`-v` kept.** Output goes through a pipe, not a console; about 1 MB of
  text is not a measurable cost.
- **Parallel Pylint (`-j`), rejected.** 28 s -> 16 s locally, but it
  reported a C1803 that a serial run does not.
- **Shorter build-timeout tests, rejected.** The 20 s is headroom for the
  backend to start on a slow runner; shortening it risks flakes for about
  10 s of wall-clock.
- **`.pyc` compilation at install, not added.** uv does not compile at
  install, pip does; no measured cost.

## How to measure

- Step times per job: `gh run view <id> --json jobs`.
- Per-test times: `gh run download <id> --pattern 'pytest-junit-*'`, then
  sum `testcase/@time` by file or category; compare legs on the tests
  they share (Windows skips about 240 more).
- Order dependence: rerun the suite with `-n 2`, `-n 4`, `-n 8`.
