---
Created: 2026-09-19
Last-Modified: 2026-09-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `--allow-build` termination signals: implementation record

See also: [allow-build-timeout.md](allow-build-timeout.md) (the build
subprocess, its kill path and the numbered traps this refers to) and
`src/pitloom/core/build_signals.py` (`TerminationGuard`, whose module
docstring states the contract).

## The problem

- **The build tree.** `--allow-build` runs `python -m build` as a child
  process tree in its own POSIX session (trap 7), so SIGTERM/SIGHUP sent
  to Pitloom alone never reaches it. Under `SIG_DFL` a CI job
  cancellation, `timeout(1)` or a closed terminal left the whole tree and
  both temp dirs behind -- a regression against the old in-process
  build. The first version of the timeout change documented this; it was
  then fixed with a guard around `build_and_read_wheel()`.
- **The result.** A successful build's files live in a
  `pitloom-build-and-read-*` extraction dir that must outlive the build:
  `get_wheel_files()` hashes and scans them, then the callers
  (`generate_project_sbom()`, `embed_wheel_sbom()`, and a whole
  `embed-wheel` batch through `EmbedFileCache`) re-read them for AI-model
  scanning and enrichment before calling the cleanup callback. A guard
  scoped to the build left that whole period under `SIG_DFL` -- a signal
  there, or a Ctrl-C in `get_wheel_files()`'s hashing loop (which caught
  only `Exception`), leaked the dir.

## Design

One `TerminationGuard` (`pitloom.core.build_signals`) spans the
result's whole lifetime.

- **Scope, so a host application keeps control.** A handler is
  installed only for a signal whose current handler is `SIG_DFL` -- the
  process would die from it anyway, without cleanup -- and only where
  `signal.signal()` is allowed (main thread; a `ValueError` elsewhere is
  caught and the signal left alone). A host's own handler, or `SIG_IGN`
  (`nohup`), is untouched. SIGHUP (POSIX-only) and SIGBREAK
  (Windows-only) are looked up with `getattr`. Each signal is listed for
  restoring *before* its handler is installed, so an interrupt during
  installation cannot leave an unlisted handler behind.
- **One owner, nested guards join it.** The outermost guard entered in a
  thread (thread-local) owns the handling; entering another one inside it
  yields the owner, and its exit does nothing. Only the owner installs,
  restores, and acts on an exception. Guards are entered by every holder
  of the result: `get_wheel_files()` (so a direct library call is covered
  until it returns), `generate_project_sbom()` and
  `_build_sbom_from_project_and_wheel()` (from discovery to their
  `cleanup_discovery()`), and `EmbedFileCache`, now a context manager
  held around the whole `embed-wheel` batch. The outermost one sets the
  protected lifetime; `build_and_read_wheel()`'s own guard is always
  nested in practice. The owner's exit resets the guard (handlers,
  pending signal, cleanups), so an instance can be entered again;
  entering one that is entered raises `RuntimeError` (a nested exit
  would otherwise end the outer block's protection).
- **Installed lazily, at the first `hold()`.** The build is what creates
  something to clean up, so `build_and_read_wheel()`'s `hold()` installs
  the handlers, and they stay until the owner exits. The Hatchling hook
  (running inside a build frontend's process), model SBOMs and every
  static-discovery run enter a guard through `get_wheel_files()` but
  never touch signal handling.
- **Two regimes.**
  - Inside `hold()` -- creating both temp dirs and registering their
    removal, then the build subprocess -- the handler only records the
    first signal. The build's wait loop polls `raise_if_pending()` every
    slice (0.25 s, trap 8), before the build starts and right after it
    exits (a Windows Ctrl-Break reaches the build too; its exit is then a
    request to stop, not a failed build). `TerminationSignal` is a
    `BaseException`, so `build_and_read_wheel()`'s broad
    `except Exception` fallback cannot turn "terminate" into "carry on
    with static discovery". Kill tree -> reap -> leave the hold -> run
    the registered removals (work dir, then extraction dir) -> restore
    -> re-raise.
  - Outside a hold -- extracting the wheel, removing the work dir,
    hashing, AI-model scanning, enrichment, the rest of an `embed-wheel`
    batch -- the handler ends the process itself, at once: no exception
    is thrown into the running code, and a long step does not delay the
    exit. The build tree is already reaped by then. A removal the signal
    cut short (the caller's own `rmtree` of the work dir) is repeated to
    completion by the handler's run, so it is never left half-done.
- **Ending the process.** Run the registered cleanups (newest first),
  restore `SIG_DFL`, log `WARNING: Build: received SIGTERM during the
  build -- exiting after cleanup` (signal recorded in a hold) or `...
  after the build -- ...` (outside one: extraction, scanning, a later
  wheel of a batch), then `signal.raise_signal()`.
  The process dies *by that signal* -- 143 in a shell, `-15` from
  `Popen.returncode`, what a supervisor checking `WIFSIGNALED` expects.
  Callers' `finally` blocks up the stack do not run, as for the
  unhandled signal. Only if `raise_signal()` returns (PID 1 in a
  container without `--init`, where the kernel drops a `SIG_DFL` signal
  a process sends itself, or the signal is blocked in this thread) does
  it fall back to `SystemExit(128 + signum)`. A second signal while one
  is handled is ignored, so the exit status stays the first one's.
  A Ctrl-C that cuts the cleanups short still restores the handlers (a
  handler left installed with a signal pending would swallow every
  later SIGTERM); the `KeyboardInterrupt` unwinds to the owner, whose
  exit repeats the cleanups and finishes the termination by the first
  signal. The owner keys this on a flag set only once the cleanups
  completed, not on the signal being recorded.
- **Restoring.** A handler is reset to `SIG_DFL` only while it is still
  the guard's: one another library installed meanwhile replaced it on
  purpose and stays. Should that code later put the guard's handler back,
  the handler, finding the guard inactive, behaves as `SIG_DFL`.
- **Cleanup callbacks are idempotent and may run twice.** The build
  registers each temp dir's removal (`_one_shot()`) with `add_cleanup()`
  right after creating it, inside the hold; it runs on termination, or
  when the owner's block ends
  by an exception with no signal pending -- which also covers Ctrl-C
  between `get_wheel_files()` returning and the caller's `try` taking the
  callback. On a normal exit they are dropped: the owner released the
  dir itself, or handed it on (`get_wheel_files()` called on its own).
  Its callback is marked done only after the removal returns, and the
  guard never pops its list, so a handler that interrupts the caller's
  own removal repeats it to completion. The work dir stays a
  `TemporaryDirectory` (its `cleanup()` resets read-only permissions and
  repeats a removal cut short); the extraction dir, which outlives the
  call, is a plain `mkdtemp()` so no weakref finaliser removes it behind
  a library caller's back. Each callback runs under
  `contextlib.suppress(Exception)`, and so does the `WARNING:`: run from
  the handler, a log write can hit the stream write it interrupted
  (`RuntimeError: reentrant call`), which must not stop the termination.
- **`get_wheel_files()` releases on every path until it hands over.**
  Its hashing loop moved to `_scan_included_files()`; a `finally` runs
  `cleanup_discovery()` unless a result was produced, so
  `KeyboardInterrupt` and a propagating error are covered, not only
  `Exception`. Only a per-file read failure degrades to "no files"; an
  error in the pure Merkle-root computation propagates, as before this
  change.
- **A handler surviving the guard's exit** (failed restore) behaves as
  `SIG_DFL` instead of swallowing the signal.

## Library contract

`get_wheel_files()` protects the dir until it returns. After that, a
direct caller owns it: run the callback in a `finally`. A signal then
kills the process under `SIG_DFL` without it, unless the caller holds a
`TerminationGuard` around both the call and its use of the files, as
Pitloom's entry points do. `embed_wheel_sbom(file_cache=...)` callers use
`with EmbedFileCache() as cache:` around the batch; the cache's
`cleanup()` method is gone (private alpha, no shim). `resolve()` outside
the block raises `RuntimeError` before any discovery (nothing would
remove a build's dir), and so does entering the block twice. The cache
can be entered again afterwards, with a fresh guard and resolution.

## Rejected paths

- **Handler installed unconditionally, or at guard entry.** Would
  replace a host application's own handler (or `nohup`'s `SIG_IGN`)
  behind its back, and change signal handling inside a build frontend
  running the Hatchling hook for nothing. Only a `SIG_DFL` signal, and
  only once a build starts, is taken over.
- **A handler that raises `TerminationSignal` wherever the signal
  lands.** The first version. It broke out of the wait at once, but also
  out of anything else running then: it aborted a temp-dir removal
  half-way (an isolated build venv: ~18k files left, plus a misleading
  "could not fully remove" `WARNING:`), and landing between installing
  the handler and entering the `try` (or between the block's end and
  its `finally`) it escaped as a bare exception and left a handler that
  ignored every later SIGTERM. Considered again for the consumption
  phase and rejected for the same reasons, plus: the exception would
  pass through third-party scanners, where an `except BaseException`
  could swallow it.
- **Record everywhere and act at the guard's exit.** Simple, but a long
  AI-model scan or a network enrichment fetch would hold the signal for
  as long as it runs -- past `docker stop`'s 10 s, whose SIGKILL then
  leaks the dir anyway.
- **Poll at safe points in the downstream loops.** Couples AI-model
  scanning and enrichment to the guard, and one long step (a large model
  file, a network fetch) still delays the exit.
- **Independent guards per entry point.** The innermost one's exit
  would restore the handlers and end the protection while an outer
  caller still holds the result; the nested guard must join the owner.
- **`get_wheel_files()` as a context manager.** Would change its public
  return contract and every caller, and still need another wrapper for
  `EmbedFileCache`'s batch-long lifetime; the guard composes with the
  existing callback contract instead.
- **Extraction and the work dir's removal inside the hold.** The
  previous version. A signal then waited for the whole extraction -- a
  multi-GiB AI wheel on a slow CI disk can exceed `docker stop`'s 10 s,
  whose SIGKILL then leaks both dirs. Once the build is reaped nothing
  left needs protecting from being cut short: every dir is registered,
  and the handler repeats an interrupted removal.
- **Raise on re-entering an exited guard.** Simpler, but
  `EmbedFileCache` is a public, reusable object; resetting on the
  owner's exit keeps both reusable, and only a *nested* re-entry (which
  would break ownership) raises.
- **Handler scoped to `run_build_subprocess()` only.** The kill would
  run, but the re-raise would happen inside the `plb-*` work dir's
  `with` and before the extract dir's `finally` -- both left behind.
- **`SystemExit(128 + signum)` as the primary exit.** Would run every
  caller's `finally`, but any caller catching `BaseException` could
  swallow it, and a supervisor checking "killed by a signal"
  (`WIFSIGNALED`) sees an ordinary exit 143 instead. Kept only as the
  fallback when `raise_signal()` returns.

## Limitations

- **Orphaned build when Pitloom dies without cleanup.** SIGKILL, a
  non-main-thread library call, a host application's own SIGTERM/SIGHUP
  handler that ends the process without unwinding (e.g. `os._exit()`;
  one raising `SystemExit` unwinds through the wait loop, which kills
  the tree), or a build descendant that calls `setsid()` (see
  "`setsid()` escape" in allow-build-timeout.md). Under `nohup`, SIGHUP
  is ignored, so Pitloom keeps running and cleans up normally.
- **A direct `get_wheel_files()` caller after it returns** -- see
  "Library contract".
- **Ctrl-C between two statements inside the build.** `KeyboardInterrupt`
  still lands anywhere: a dir created but not yet registered (a few
  bytecodes after `mkdtemp()`) can leak. A termination signal there is
  held until the registration.
- **PID 1.** The fallback `SystemExit` is raised from the handler into
  whatever code runs; code that swallows `BaseException` would keep the
  process alive. The dir is already gone by then.
- **Windows forced termination, window close, Ctrl-Break.** SIGTERM is
  never delivered to a Windows process from outside -- `taskkill /F` or
  a job-object kill is `TerminateProcess`, which nothing can intercept,
  so the build tree survives unless the same kill reaches it. Closing
  the console window, logoff and shutdown are not handled either (the
  system ends the process a few seconds later regardless). Ctrl-C and
  Ctrl-Break reach the build directly, as it shares Pitloom's console
  process group (no `CREATE_NEW_PROCESS_GROUP`, trap 7): Ctrl-C runs the
  normal `KeyboardInterrupt` path; Ctrl-Break (SIGBREAK) is handled like
  SIGTERM. After the build, a file the interrupted code still holds open
  cannot be deleted on Windows -- during extraction the wheel in the work
  dir and the file being written, later a file a scanner has open -- so
  the handler's removal may leave that dir behind (with a `WARNING:`
  naming it). Unverified on a real Windows run.

## Tests

- `tests/core/test_build_signals.py` -- the guard: lazy install, hold vs.
  outside-hold regimes and their `WARNING:` wording, order (cleanup while
  still handled, raise under `SIG_DFL`), nesting (one install/restore,
  nested exit inert), exception exit, Ctrl-C inside the handler's
  cleanups, a handler installed meanwhile kept, reuse and nested
  re-entry, thread isolation, a failing `WARNING:`.
- `tests/core/models_wheel/test_models_wheel_termination.py` --
  `get_wheel_files()`: Ctrl-C and SIGTERM in the hashing loop, Ctrl-C
  with a cleanup not registered with the guard, a Merkle-root error
  propagating, a direct caller owning the dir after return, no handler
  without a build.
- `tests/core/models_wheel/test_models_wheel_build_and_read_cleanup.py`
  -- `build_and_read_wheel()`: a signal during the build, right after
  `mkdtemp()`, during extraction (acts at once, each dir removed once),
  during the work dir's removal, after success.
- `tests/assemble/test_embed_build_options.py` -- `EmbedFileCache`
  outside its block, entered again, entered twice.
- `tests/assemble/test_build_termination.py` -- SIGTERM during AI-model
  scanning in `generate_project_sbom()`/`embed_wheel_sbom()`, Ctrl-C right
  after `get_wheel_files()` returns, SIGTERM between `embed-wheel` batch
  wheels (one removal), and a real SIGTERM/SIGHUP to a child process
  scanning (POSIX: exit by the signal, no dir left).
- `test_hook_leaves_signal_handling_alone` in
  `tests/extract/project/test_hatch_hook_hook_basic.py`.

Against the code before this change, 8 of these fail (the hook and
no-build tests are non-regression guards and pass either way). Mutation
testing killed 12 of 13 mutants (outside-hold handler only recording,
nested guard becoming owner, eager install, no exception-exit cleanup,
re-running cleanups after termination, no thread-local owner, no guard in
`get_wheel_files()`, `generate_project_sbom()`,
`_build_sbom_from_project_and_wheel()` or `EmbedFileCache`, a non-one-shot
cleanup, no hold around the build). The survivor ran
`get_wheel_files()`'s cleanup in an `except Exception` only: a build's
dir is still removed on `KeyboardInterrupt` by the owner's
exception-exit cleanup, so it was equivalent for the one registered
cleanup. `test_interrupt_in_hashing_loop_runs_an_unregistered_cleanup`
now kills it with a discovery whose cleanup the guard does not know.

The follow-up round (Ctrl-C inside the handler's cleanups, reuse,
`EmbedFileCache` outside its block, extraction outside the hold,
restoring only the guard's own handler, the phase in the `WARNING:`,
Merkle errors propagating): 16 tests, new or with a sharpened assertion,
fail against the previous round's code, and 19 of 19 targeted mutants
were killed.
