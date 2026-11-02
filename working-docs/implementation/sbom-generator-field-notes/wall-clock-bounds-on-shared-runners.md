---
Created: 2026-11-02
Last-Modified: 2026-11-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: wall-clock assertions on a shared CI runner (a macOS stall)

See also: [README.md](README.md) (index of these notes),
[testing-traps.md](testing-traps.md) (other ways a test fails for the wrong
reason), [platform-and-toolchain.md](platform-and-toolchain.md),
[ci-duplicate-run-skip-experiment.md](ci-duplicate-run-skip-experiment.md)
(the PR on whose runs this was seen),
[ci-cost-and-two-gate-policy.md](ci-cost-and-two-gate-policy.md) (the macOS
setup phases measured on 2026-10-30),
[open-research-questions.md](open-research-questions.md).

**Status: cause not confirmed.** A fix is in progress on a branch
(`fix-flaky-macos-timing`); at the time of writing that branch holds no
commit beyond `main`. This note records the facts, three hypotheses marked as
such, and what to measure next. It does not describe the fix.

## 1. The failure

Run 41449530712 of `test.yml` (event `pull_request`, PR #415, head
`f3c9ec07`, created 2026-11-02 13:02 UTC). The macOS leg (Python 3.13.17,
`macos-latest`, 3 xdist workers) ended `1 failed, 18037 passed, 85 skipped in
267.05s`. The one failure:

```text
tests/extract/remote/test_git_hardening.py:454
    assert time.monotonic() - started < 30
E   assert (269.80524275 - 209.576210166) < 30
60.26s call  ...test_a_call_that_writes_more_than_the_cap_is_stopped[running]
```

- **What the test says.** A fake `git` shell script writes 200,000 bytes into
  the watched directory (cap 100,000) and then `sleep 60`. The runner's size
  poll (set to 0.1 s by the test) should kill the call at once and raise
  `git.too-large`; the test asserts the error and then that "quickly, not after
  the sleep" holds, with a 30 s bound. The error assertions passed; only the
  time assertion failed.
- **What the number says.** 60.23 s measured by the test, 60.26 s by pytest,
  against about 0.1 to 0.2 s in 7 other macOS runs. The elapsed time equals the
  `sleep 60`, to a quarter of a second. Whatever delayed the stop lasted as long
  as the sleep, or the stop did not reach the sleeping process until it ended.
- **Collateral.** `fail-fast` cancelled the Windows and Ubuntu 3.10 legs in
  their `Run tests` step at about 13:07:30, some 4.5 minutes in; the Ubuntu
  3.14 leg passed. The
  two cancelled legs' runner time is lost (*estimated* at about 9 runner minutes;
  not measured).

## 2. What the same leg did to other tests

The macOS "slowest 20 durations" of that run list four tests at 35 s or more.
I read the per-test durations from the `pytest-junit-*` artifacts (uploaded by
each `test.yml` leg that reaches the step) of eight macOS runs, 2026-10-30 to
2026-11-02. A test's time there is setup plus call plus teardown. Seconds,
`test_` prefixes dropped:

| Run (branch) | `a_call_that_writes_more_than_the_cap_is_stopped[running]` | `a_redirect_that_names_no_place_is_said_not_ignored` | `a_url_run_names_no_temporary_directory[g/manifest]` | `fetch_json_sends_the_token_and_parses` |
| --- | -: | -: | -: | -: |
| 41094340654 (`main`, 10-30) | 0.1 | 0.5 | 38.0 | not yet written |
| 41227636400 (PR, 10-31) | 0.2 | 0.5 | 38.5 | not yet written |
| 41447191106 (#415, 12:44) | 0.1 | 0.5 | 37.4 | 35.0 |
| 41449157394 (#416, 12:59) | 0.1 | 0.5 | 38.5 | not yet written |
| **41449530712 (#415, 13:02)** | **60.3** | **35.5** | 37.4 | 35.0 |
| 41459743309 (#417) | 0.2 | 0.5 | 36.9 | not yet written |
| 41459874848 (#418) | 0.1 | 0.5 | 36.7 | not yet written |
| 41461059420 (`main`, 14:20) | 0.2 | 0.5 | 38.0 | not yet written |

In the same runs' junit files the same tests take at most 3.3 s on Ubuntu (3.10
and 3.14) and at most 0.8 s on Windows (those columns are not tabulated).

- **Three of the four are not flakes; they are standing macOS costs.** The
  `g/manifest` test takes 36.7 to 38.5 s on macOS in all 8 runs, of which 35.8 s
  is its fixture set-up in the failed run. The 2026-10-30 CI measurement report
  (session scratch, not in the repository; run 41043964793) saw two such 35.3 s
  `setup` phases on macOS, in this test and in `test_over_cap_surfaces`. The
  `fetch_json` test, new in #415, takes 35.0 s in both macOS runs that contain
  it and 0.0 to 0.1 s on Linux; #415 merged at 14:38 UTC, so the test is now on
  `main`. Nothing about 35 s on macOS is new.
- **Two of the four are new in the failed run:** the redirect test (35.5 s, 0.5
  s elsewhere) and the hardening test (60.3 s, 0.1 to 0.2 s elsewhere).
- **The three standing 35 s tests start a local HTTP server.** `g/manifest`
  (through `serve_git` in `tests/_git_http_server.py`), the redirect test and
  the `fetch_json` test each use `http.server.ThreadingHTTPServer` or
  `HTTPServer` on `127.0.0.1`. The hardening test does not; it runs a shell
  script.
- **A silence across all workers.** In the failed run's log the only gap of 8 s
  or more between two lines of the pytest step (apart from collection) is 17.4
  s, from 13:06:43.824 to 13:07:01.210: no worker printed a line. It ended
  within 5 ms of the redirect test's `PASSED` line. The test printed just before
  the gap, `test_readable_bytes[1025-1025 bytes]`, is trivial and its own
  recorded time in the junit file is 0.0 s. So that quiet period is not inside
  any test's measured time.
- **The sum does not stand out.** The macOS leg's summed test time was 712 s in
  the failed run against 581 to 871 s in the seven others (junit sums; the sums
  are CPU-seconds across workers, not wall time).

## 3. Hypotheses (none confirmed)

1. **A name lookup in `HTTPServer.server_bind`.** The standard library's
   `HTTPServer.server_bind` calls `socket.getfqdn(host)` (read from the
   interpreter's source on 2026-11-02). If `getfqdn` stalls on the macOS runner
   (a reverse lookup or a host-name resolution with a timeout), each test that
   starts such a server pays it. *For:* the three standing 35 s tests all start
   one; the value is repeatable (35.0 twice). *Against:* the four modules that
   start these servers hold 77 tests on macOS, only one or two are slow in any
   run, and the slow one differs by run (the redirect test is 0.5 s in 7 of 8
   runs); the hardening test starts no server and still took 60 s.
2. **A host-level pause (a noisy neighbour or a descheduled runner VM).** The
   17.4 s silence of all workers fits this. *Against:* a pause should also
   lengthen the tests that were running inside it by about the same amount, and
   the hardening test is 60 s, more than the silence.
3. **A race in killing the grandchild.** The call is killed by process group
   (`os.killpg(..., SIGKILL)`, `start_new_session=True` in `_git_run.py`), but
   if the stop were late or missed the `sleep`, the wait would last until the
   `sleep 60` ended: 60.26 s fits. *Against:* the same test is 0.1 s in seven
   other runs and the error was still raised correctly.

These are not exclusive. What each predicts:

| Hypothesis | A direct measurement that would confirm or reject it |
| --- | --- |
| 1 | Time `socket.getfqdn("127.0.0.1")` in a throwaway macOS job, repeated; and the same tests with `server_bind` patched to skip it |
| 2 | Log `time.monotonic()` and `time.process_time()` in a sampler thread of the CI job; a pause shows as wall time with no CPU time for every process |
| 3 | In the failed test's script, record the PIDs of the shell and the `sleep`, and the time each ends, in the test's output |

## 4. Why a 30 s bound was not generous enough

The project rule says generous `time.monotonic()` bounds are fine, and that
generosity is meant to absorb noise. This bound has a second job. The test
exists to tell "stopped now" from "stopped after the sleep", and the sleep is
60 s; a bound above 60 s could never fail when the stop is broken. So the
bound sits between the good case (0.1 s) and the bad case (60 s), and the
room for noise is what is left under 60 s. On this macOS leg standing
stalls of 35 to 38 s already take up most of that room: the margin is under
twofold.

- **There are two kinds of wall-clock bound in the suite.** A *hang ceiling*
  (the test must finish at all; 60 s, 90 s) can be as generous as the CI job
  allows. A *discriminating bound* (the test must be fast, not merely finish;
  here 30 s against 60 s) cannot be generous without losing its meaning.
- **A grep inventory** (`monotonic() - x <` and `elapsed <` in `tests/`; a
  heuristic pattern that may miss other forms) finds 13 such assertions, with
  bounds of 0.8, 2, 2, 3, 5, 5, 5, 5, 30, 30, 60, 90 s and one of "timeout plus
  5". The tightest, 0.8 s, is the concurrent-prefetch test, which compares 6
  fetches of 0.2 s run in parallel with 1.2 s run in turn: also a discriminating
  bound, with a margin of 0.6 s over the ideal.
- **The comment on that test, "generous bound to absorb CI/scheduler noise",
  is true of 0.8 s against a scheduler hiccup and false of a 35 s stall.** A
  bound is generous against one distribution of delay only.

## 5. Options that do not depend on the clock (not tried)

- Assert the behaviour that the time stands for: the child is gone (its PID no
  longer exists) when the error is raised. That tests "stopped" directly.
- Replace the real `sleep` by a wait on a file or event the test controls, so
  the "bad" case is "never", not "60 s", and a hang ceiling can be high.
- Compare two timings taken in the same process and run (the stop call against
  a baseline call), so a slow host slows both.

Each costs something: the first is platform-specific; the second changes what
the test exercises (a real `sleep` child holding a pipe open is the point of
the 60 s); the third is still a clock test.

## 6. What to measure next

- The junit files are already uploaded by every leg as `pytest-junit-<os>-py<ver>`
  (artifacts). A script over the last N runs per leg can list tests whose
  duration is above a multiple of their own median. That would have flagged the
  redirect and hardening tests in this run at once, and shown that `g/manifest`
  and `fetch_json` are slow every time.
- Whether the suite's wall-clock assertions fail more often on macOS than on
  other legs over a month. One failure in the eight macOS runs read here; the
  sample is small.
- The cost of the standing 35 s tests: three of them are about 105 s of worker
  time out of about 800 worker-seconds (3 workers over 267 s), roughly 13 %
  (*estimated*; the `g/manifest` figure includes work besides the wait, and the
  tests run beside others).

## 7. What generalises

- **Read the CI log's own duration list before blaming a test.** The log's
  `slowest 20 durations` already named the four stalls; a failure on a time
  assertion is a symptom, and the list is the context.
- **A time bound has a distribution it is safe against; say which.** "Generous"
  without that is a claim the next stall disproves.
- **A test added to a PR can add its own standing cost to a platform leg.** The
  `fetch_json` test of #415 was 35 s of macOS CPU time in each run; no one
  asked for it, and the PR that adds a CI saving of about 25 runner minutes a
  merge also adds a macOS cost to every PR run (*the two are of different
  size and nature; not netted*).
- **A "flaky" label is a hypothesis too.** Before calling it that, look at the
  same test's history: here three of four 35 s tests were not flaky at all.

## 8. Open

- How to detect an environment-induced stall automatically (see
  [open-research-questions.md](open-research-questions.md)).
- Whether a 35 s standing cost on three macOS tests should be fixed (the server
  name lookup, if hypothesis 1 holds) before or after the flaky test.
- Whether `fail-fast: true` should cancel the other legs when the failing test
  is a time assertion on a leg known to stall. The policy page has not
  discussed this.
