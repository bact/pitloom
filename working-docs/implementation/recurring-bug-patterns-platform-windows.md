---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: Windows-only CI findings (from PRs #468 and #464)

See also: [recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md)
(the main platform, concurrency, test-harness and CI list, at its size
limit), [recurring-bug-patterns.md](recurring-bug-patterns.md),
[CLAUDE.md](../../CLAUDE.md) ("Recurring bug patterns" -- the short summary),
[pypi-url-targets.md](pypi-url-targets.md) (the feature whose tests found
the first), [recurring-bug-patterns-ci-matrix.md](recurring-bug-patterns-ci-matrix.md)
(findings of dependency and interpreter versions).

Findings that only the `windows-latest` leg of CI showed. Entries follow the
format of the platform list; new Windows findings of the same kind go here
until this file is large enough to be merged back on a split of that list.

- **Windows does not end a pending, or a later, `recv` on a socket shut for
  reading (`socket.shutdown(SHUT_RDWR)`): the read waits for its timeout.**
  POSIX returns `b""` at once. A test that shuts a socket and then asserts
  `sock.recv(1) == b""` therefore passes on Linux and macOS and blocks to its
  socket timeout on Windows (here 5 s, then a failure). Production code is
  safe because its read loop re-checks the deadline flag after every read and
  every request has a per-operation timeout (`Watch` in
  `pitloom.extract.remote._http_watch`; the docstring says so). In the test,
  spy the shutdown call itself (`monkeypatch.setattr(_http_watch,
  "shut_socket", spy)` and assert the sockets it was given) on every OS, and
  keep the end-of-stream read behind a POSIX-only condition
  (`sys.platform != "win32"`). The same hazard applies to any test that
  expects a blocked reader to be released by a shutdown from another thread.
  Surfaced by PR #468's first Windows run
  (`tests/extract/remote/test_pypi_http_fetch.py`).
- **The Windows monotonic clock is coarse (about 15.6 ms), so a deadline of
  zero seconds can read exactly 0, not below it.** `time.monotonic()` called
  twice in a row can return the same value there. A test asserting
  `watch.remaining() < 0` right after `Watch(0.0)` passes on Linux and macOS
  (a fresh nanosecond reading is later) and fails on Windows with `0.0`.
  Compare expiry as `<= 0` in the test, as production does (`_request_once`
  raises the timeout at `remaining <= 0`); a deadline check written as `< 0`
  in production code would let a spent deadline start one more request. Never
  assert a strict ordering between two clock reads on any code path a Windows
  runner runs; if strictness is needed, build a larger gap than the clock's
  tick. Surfaced by PR #468 (same test file).
- **A cleanup that retries counts twice on Windows.** `rmtree_quietly`
  (`pitloom.core.temp_dirs`) makes a directory writable and calls
  `shutil.rmtree` again when the first pass leaves it. On Linux and macOS
  the first pass succeeds; on Windows a file still held open (an interrupted
  extraction) makes it fail, so a spy on `shutil.rmtree` sees two calls for
  one removal. A test asserting "each directory removed once" by counting
  `rmtree` calls then fails on Windows only. Count removals per directory
  path there (`dict.fromkeys(calls)`), and keep the exact one-call count where
  the removal is known to succeed. Surfaced by PR #468
  (`tests/core/models_wheel/test_models_wheel_build_and_read_cleanup.py`).
- **A short deadline shared by every case of a parametrised test turns the
  slow cases into timeouts on Windows.** A loopback round trip on a Windows
  runner can take longer than on Linux or macOS. A test that set a 0.3 s
  fetch deadline for all three cases (over the cap, an HTTP 503, a slow
  drip) passed elsewhere and, on Windows, reported the over-cap and 503
  cases as timeouts, so the asserted code was wrong. Give the short deadline
  only to the case that tests the timeout (a `deadline` parameter, `None` for
  the others, which keep the production value), and make that case's server
  slow by a wide margin (a drip far longer than the deadline). Surfaced by
  PR #468 (`tests/extract/remote/test_shared_fetch_codes.py`).
- **`os.path.realpath` does not raise for a NUL on Windows, and `isabs` is
  true for `"/a\0b"` there.** A guard that dropped an unreadable `sys.path`
  entry by catching `ValueError`/`OSError` from `realpath` kept `"/a\0b"` on
  Windows 3.11 (the test row passed on Linux, where `realpath` raises
  `ValueError`). Check `"\0" in path` before `isabs` and `realpath`, and keep
  the `except` for what is left (a link loop). The `except` then cannot be
  reached on Linux: stub the module's `os` in one test to cover it, not the
  shared stdlib. Surfaced by PR #464
  (`tests/core/models_wheel/test_models_wheel_guard.py`).
- **A deadline checked with a strict `>` against `time.monotonic()` is not
  past after one call on a runner whose clock ticks in 15.6 ms steps.** A test
  that set the cap to `0.0` and made one `time.sleep(0.001)` call expected the
  stop at once; on Windows the clock had not moved, so nothing was raised
  (`DID NOT RAISE`). Production (a 60 s cap) is unaffected. Give the test a
  small cap (0.05 s) and poll in a loop bounded by a generous give-up time, so
  it passes at any tick size. Surfaced by PR #464 (same file).
