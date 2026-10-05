---
Created: 2026-10-03
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: testing traps

See also: [README.md](README.md) (index of these notes),
[platform-and-toolchain.md](platform-and-toolchain.md) (section 3, the
first test-harness items),
[recurring-bug-patterns-platform.md](../recurring-bug-patterns-platform.md),
[testing-ci-followups.md](../../design/testing-ci-followups.md).

Ways a test passes, fails or floods the log for the wrong reason.

- **"Network is unreachable" is a plain `OSError`.** `OSError(ENETUNREACH)`
  is not a `ConnectionError`, while `ECONNREFUSED` maps to
  `ConnectionRefusedError`; `EHOSTUNREACH` behaves like `ENETUNREACH`. A
  flake classifier keyed on `ConnectionError` fails a test on a
  DNS-but-no-route runner instead of skipping it. Pitloom's classifier
  holds an errno set, a winerror set (10050 to 10054, 10060, 10061,
  10065, 11001 to 11004) and a text regex including `HTTP Error
  (?:429|5\d\d)` (#238).
  Do: classify network failure by errno and winerror, not by class alone.
- **A closed-port proxy makes a cheap, deterministic "offline".**
  `HTTPS_PROXY=http://127.0.0.1:9` fails every proxied fetch at once with
  `URLError <urlopen error [Errno 61] Connection refused>`, for urllib
  and subprocesses alike. In the #238 check the `-m network` run gave
  1 passed, 11 skipped with causes and 11 failed under strict mode.
  Do: test the skip-on-network-error path with the proxy on a closed port,
  not by unplugging.
- **`pytest.skip`'s exception is a `BaseException`.**
  `issubclass(pytest.skip.Exception, Exception)` is False, so a skip
  raised inside `pytest.raises(pytest.fail.Exception)` or
  `pytest.raises(HTTPError)` escapes and the test reports skipped, not
  failed; mutants that broke strict mode passed as "27 passed, 3
  skipped". Fixed by a report hook that fails any skipped `network` test
  under strict mode, and pytest exit code 5 when nothing is collected
  (#238).
  Do: in a must-not-skip gate, fail on skip outcomes at report level.
- **A `str` parameter is the test id, verbatim.** A 2,000-character `"["`
  parameter gave a 2,038-byte collect-only line; the 1,000,000-level
  deep-JSON fixture gave about 1 MB node ids and 4.0 MB of `-v` CI output
  for one file, 25 KB after adding `id=` (#270). On Windows a long id also
  fails setup, via the 32,767-character `PYTEST_CURRENT_TEST`; see
  [recurring-bug-patterns-platform.md](../recurring-bug-patterns-platform.md)
  (#276).
  Do: give every large or generated parameter an explicit short `id=`.
- **`tracemalloc.start()` is a no-op when tracing is already on.** Under
  `PYTHONTRACEMALLOC=5` a test's peak included 25 MB of earlier
  allocations (88 MB measured against a 32 MB limit; `reset_peak()` gave
  4.1 MB), and the test's `stop()` switched off the caller's tracing
  (#266).
  Do: record `is_tracing()`, `reset_peak()`, measure peak minus baseline,
  and `stop()` only if you started it.
- **A `FILE=(\S+?):` regex captures `C` on Windows.**
  `re.search(r"FILE=(\S+?):", r"FILE=C:\Users\x\bad.onnx: failed")`
  gives `C`, so a "no temp path in FILE=" assertion passed vacuously
  there. Fixed with `FILE=(\S+): ` in one shared helper (#239).
  Do: delimit `KEY=VALUE` values with `": "` or quoting, never `:`.
- **`PurePosixPath(str(windows_path)).name` is the whole path.**
  `PurePosixPath(r"C:\a\b\m.pt").name == r"C:\a\b\m.pt"`, since `\` is not
  a POSIX separator; a test taking a name this way failed on Windows only
  (#263).
  Do: take `.name` from the native `Path`; use `PurePosixPath` only on
  strings known to be `/`-separated.
- **Make a write fail with a file as the parent, not `/nonexistent/`.** A
  root or administrator runner can create `/nonexistent-dir`; writing
  `afile/r.json` where `afile` is a file raises `NotADirectoryError`
  (`ENOTDIR`) for everyone (#235).
  Do: build "unwritable" fixtures from a file-as-directory, never from an
  absolute path assumed absent.
- **A standard `.gitignore` rule silently drops fixtures.** `*.egg-info/`
  swallowed every fixture `.egg-info`: tests passed locally and found zero
  candidates in CI's clone. Fixed with
  `!tests/fixtures/projects/**/*.egg-info/`; 10 such files are tracked.
  setuptools writes a src-layout one at `src/<name>.egg-info`, a level
  down (#214).
  Do: list fixtures that look like build output, then `git check-ignore`
  them.
- **An `assert` in a `threading.Thread` target does not fail the test.**
  pytest 9.1.1 reports 1 passed with a
  `PytestUnhandledThreadExceptionWarning`; it fails only under
  `-W error` or `filterwarnings=error`, and then names the warning.
  `join()` returns normally either way (#215).
  Do: record results in `Event`s or lists and assert after `join()`.
- **Coverage of a version-gated import flips with the interpreter.**
  `tomllib` against `tomli` shows as uncovered on 3.10 and the opposite
  line on 3.14, and CI collects coverage on one leg only. One test forces
  both branches through a reload helper
  (`tests/test_toml_io_tomllib.py`; PR not identified).
  Do: test both sides of every `sys.version_info` or `ImportError` gate.
- **Take real-world fixtures without the network.** Commit each project's
  published sdist (21 `.tar.gz` tracked), record the real wheel's file
  list in `expected.json` with documented `known_gaps`, and exclude
  `tests/fixtures/` from your own sdist and wheel so vendored code is not
  redistributed (#215).
  Do: take ground truth from the published artefact, not your own reader.
- **`thread.is_alive()` just after a lock release is a race.** Linux CI
  failed 2 of 72 runs; locally 0 of 14,400, and with an injected 0.3 s
  delay the old test failed 40 of 40. `EmbedFileCache.__exit__` waits for
  the lock, not for thread exit
  (`tests/assemble/test_embed_file_cache_threads.py`; PR not identified).
  Do: assert on the effect (cleanup ran once, on which thread), not on
  liveness before `join()`.
