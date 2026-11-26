---
Created: 2026-11-25
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CI hang in the link-loop guard (2026-11-21)

See also: [roadmap.md](../design/roadmap.md) ("Unexplained CI hang"),
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md),
`src/pitloom/core/_models_wheel_guard.py`.

Evidence levels: **measured** (run and observed), **read** (read from code or
a log), **guessed** (an inference not checked).

## The incident

- Run 44923751734, attempt 1, job "Test on Python 3.14 (ubuntu-latest)",
  head `0892993d` of PR #507: cancelled after 30 minutes (the job's
  `timeout-minutes`), coverage on, `-n auto` gave 4 workers, Python 3.14.10,
  coverage 7.17.4, pytest 9.2.0, xdist 3.8.0. Attempt 2 passed. (read: the
  job log)
- Two tests started and never reported: `test_a_link_loop_in_a_clone_is_
  stopped_by_the_cap[setuptools-find]` at 16:24:20.97 and
  `test_allow_build_settings_reach_build_and_read_registered_backend` at
  16:24:34.77; nothing else was printed until the cancel at 16:48. (read)
- gw1's last report was `[setuptools-auto]` of the same test at 16:24:20.50,
  so gw1 ran `[setuptools-find]`; `[setuptools-package-data]` never started
  (held as gw1's next item). (read; worker attribution inferred from the
  timestamps)
- The second test's worker cannot be told from the log (gw0 or gw2). Its
  hang is **not explained** here (see "Open").

## Root cause (first hang)

The cap is one shot, and a generator closed by its finaliser swallows the shot.

1. `_Deadline._check` raises `_Expired` from a `sys.setprofile` hook. When a
   profile hook raises, CPython removes it (`profile_trampoline` calls
   `_PyEval_SetProfile(tstate, NULL, NULL)`). (measured on 3.10.19 and
   3.14.10: `sys.getprofile()` is `None` after, the hook raises once)
2. setuptools' package filter is
   `any(fnmatchcase(item, pat) for pat in self._patterns)`
   (`setuptools/discovery.py`, `_Filter.__call__`). `any()` cuts the
   generator expression short; dropping it closes it, and the close emits a
   profile `call` event for the generator's frame. (measured: event log on
   3.10 and 3.14)
3. If that `call` is the first one past the cap, `_Expired` is raised inside
   the close and reported as "Exception ignored while closing generator"
   (unraisable), and the hook is gone. (measured: 8 of 8 swallowed stops in
   the stress run below had exactly this site)
4. The walk then runs uncapped. With two folder links to `.`, the walk is
   about 2^40 directories: in effect endless. (measured: faulthandler dumps
   of workers spinning in `os.walk` under `_find_iter` past 30 and 120 s)

Not Linux-specific: the shot lands where the thread happens to be when the
cap passes. A pure-Python reproducer (no Pitloom; the `_Filter` loop shape
under a one-shot hook with a 10 ms cap) ran uncapped in 64 of 200 runs on
macOS 3.10.19 and 55 of 200 on macOS 3.14.10. (measured) In the real test
most of the time is spent elsewhere, so the window is narrow; why CI saw it
on Linux 3.14 first is chance plus a slower coverage leg. (guessed)

## Reproduction

Linux `python:3.14` container (3.14.8, aarch64 on Apple silicon, CI is
x86_64; coverage 7.17.5), installed as `install-pitloom` does (uv, groups
`test`, `.[ai,content-type]`, no build isolation), non-root user, `--init`
(without it, PID 1 does not reap and two process-tree tests fail).

- `tests/core/models_wheel -n 4 --cov=pitloom` (branch on, from
  pyproject), `--cpus 2`: 24 loops, 23 green, **loop 13 hung** in
  `[setuptools-find]` (faulthandler at 120 s: `relpath` in the walk; the
  worker was later reported crashed). Loops stopped at 24 of 30 on request
  (machine load). (measured)
- Stress harness (scratch, not committed): the link-loop discovery with a
  random cap of 0-0.4 s, then a held-lock check and a plain local discovery,
  `-n 4 --cov`, `--cpus 4`: hangs in 3 of about 650 tests (all four
  variants) and 7 of about 350 (`setuptools-find` only); every hang a
  `setuptools-find` walk. (measured)
- No process-wide lock was left held after any capped discovery in the
  stress runs that completed (`_CONFIG_LOCK`, discovery lock, capture locks,
  `tempfile._once_lock`, logging locks, the import lock). (measured)
- Fault injection at the k-th call event (every 7th or 97th call up to
  20,000 calls, `setuptools-find`, 605 points): no swallow, no lock left.
  (measured) The swallow needs the cap to land on the generator close,
  which a fixed-stride sweep missed.

## Hypotheses considered

Ranked by evidence after the runs.

1. **One-shot stop swallowed by a generator finaliser** -- confirmed
   (above).
2. **A lock left held by the stop** (the stop raised at the `c_call` of a
   `release()` or a `with` exit): real in principle (measured: a profile
   hook raising there leaves a `threading.Lock` held, both for `with` and
   `try/finally`), and `_CONFIG_LOCK` (`log_once`) is a plain lock that
   would hang the next caller. Not seen: no lock held in any stress run.
   The discovery lock and the setuptools relay are entered outside the
   capped block, so the unwinding runs with the hook off. (read, measured)
3. **The cap not installed** (`sys.getprofile()` already set):
   coverage 7.17 on 3.14 uses `sys.monitoring` (sysmon), not a profile
   hook; the diagnostic run logged `profile-before=None` at every cap
   entry. Ruled out. (read, measured)
4. **A C call blocked** (the cap is cooperative): the dumps show Python
   frames spinning at 92-100 % CPU, not a blocked call. Ruled out for this
   hang. (measured)
5. **xdist/execnet**: the receiver thread was idle in `read` in every dump.
   (measured)

## Fix

`_check` no longer stops at a `call` event of a generator, coroutine or
asynchronous generator frame (a start, a resume, or a close by a
finaliser); a `c_call` in such a frame still stops, so a walk inside
`os.walk` (a generator) is still capped at its next C call.

- The reproducer with that rule: 0 of 200 uncapped on macOS 3.10 and 3.14.
  (measured)
- Regression tests: `test_a_generator_closed_past_the_cap_does_not_
  swallow_the_stop` (drops a started generator as the first call past the
  cap; the generator sits in a dict because Python 3.10 hands a profile
  hook a snapshot of the locals, which kept a local alive) and three new
  `test_the_hook_stops_a_call_past_the_cap_only` cases. All four fail on
  `main` (macOS 3.10 and Linux 3.14.8 container) and pass with the fix
  (macOS 3.10). (measured)
- The generator-close test is **vacuous on Python 3.13**: a finaliser's close
  of a handler-free suspended generator emits no `call` event there, so the
  unfixed hook already stops (measured on 3.13.5). It bites on 3.10, 3.11,
  3.12 and 3.14 (a fresh reviewer's checks; this branch measured only
  3.10 and 3.14.8, above). It is not skipped: the three
  `test_the_hook_stops_a_call_past_the_cap_only` cases still test the rule.
- **Known trade-off:** with the `call` of a generator frame exempt, a loop made
  only of generator frames, with no C call and no plain Python call inside
  (`for _ in count_gen()`, nested generator expressions, `yield from`
  recursion), is not capped until the first call after the loop (300,000
  iterations past the cap were measured); the unfixed hook stopped it at
  once. Realistic walks are unaffected: each `os.walk` step calls
  `scandir` or `join`, which still stop. (measured; read in `_check`)
- Not run with the fix: the Linux container loops and the stress harness
  (stopped for machine load), and the new tests on 3.14. (not verified)

### Residual risk

Three classes of finaliser that call past the cap still swallow the stop
(the stop is raised inside the finaliser, reported as unraisable, and the
hook is gone):

- a `__del__` method (measured with a synthetic `__del__` loop: 1 of 20 runs
  uncapped);
- a weakref callback;
- generator cleanup that makes a call (a `try/finally`, or
  an `except GeneratorExit`, calling `len("x")` or a Python function) when
  the generator is dropped past the cap. A possible real site, **guessed**
  from reading the standard library (not run): `pathlib`'s
  `_RecursiveWildcardSelector._select_from` on 3.10 and 3.11 and
  `_DoubleRecursiveWildcardSelector._select_from` on 3.12 end in
  `finally: yielded.clear()` (a C call), so an early-dropped
  `Path.glob("**/...")` could swallow the stop there.

None was seen in any setuptools/PDM walk here. A persistent stop would
close it, for example an audit hook on `os.scandir`/`os.listdir` that keeps
raising in the capped thread past the cap (every walk step lists a
directory, and an audit hook is never removed). Re-arming the profile hook
from `sys.unraisablehook` does not work: the re-armed hook fires inside the
unraisable hook and is swallowed again. (measured) Not built: a design
change for the user to decide.

## Open

- The second CI hang (`..._registered_backend`): not reproduced in 24 loops
  plus the stress runs; no shared state across workers explains it. A
  faulthandler dump would have named it.
- Diagnostics: pytest's `faulthandler_timeout` is not set in pyproject; a
  dump on the next hang needs `-o faulthandler_timeout=...` in CI. Not added
  here (a pytest option change needs a full-suite smoke, which machine load
  ruled out).
- The sweep-A flake (`test_no_other_thread_runs_while_the_parse_stack_size_
  is_set`): kept separate. The quoted coverage `RuntimeError` text was not
  found in CPython 3.14.8/3.14.10 or coverage 7.17.5 binaries; the parse
  thread takes `threading.getprofile()`/`gettrace()`, never the cap's
  `sys.setprofile` hook, so the two share no code path. (read, measured)

## Roadmap entry (moved 2026-11-26)

- [ ] **Unexplained CI hang** (2026-11-21, PR #507's first 3.14 ubuntu run):
  two xdist workers stopped for 23 minutes in `tests/core/models_wheel`
  (`test_models_wheel_guard.py::test_a_link_loop_in_a_clone_is_stopped_by_the_cap[setuptools-find]`
  and `test_models_wheel_build_timeout.py::test_allow_build_settings_reach_build_and_read_registered_backend`),
  then passed on a re-run of the same commit; the diff touched neither. Not
  reproduced on macOS 3.14 (full suite, coverage on, `-n 4`). Cause of the
  first test: a generator `close()` swallowed the guard's stop; fixed in #538
  (see [ci-hang-link-loop-guard.md](../implementation/ci-hang-link-loop-guard.md)).
  Open: the second test (`..._reach_build_and_read_registered_backend`) is
  unexplained, and the audit-hook persistent stop is deferred (it would also
  cover generator cleanup that calls and generator-only loops). A repeat hang:
  run with `-o faulthandler_timeout=300` for the stack.
