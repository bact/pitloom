---
Created: 2026-11-24
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: test harness

See also: [recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md)
(platform, concurrency and CI traps; this file was split out of it on
2026-11-24 when it passed the size limit, entries moved unchanged),
[recurring-bug-patterns.md](recurring-bug-patterns.md) (data and
semantics),
[CLAUDE.md](../../CLAUDE.md) ("Recurring bug patterns" -- the short
summary of these files).

Failure modes in the test suite itself: a fixture, mock, guard or helper
that hides or causes the failure it is meant to catch.

- **A hardcoded POSIX-style path literal in a test silently stops
  exercising the "genuinely absolute path" branch on Windows.**
  `pathlib.PureWindowsPath.is_absolute()` requires a drive letter --
  a literal like `"/tmp/xyz"` is *not* absolute under Windows semantics,
  even though the equivalent real value from `tempfile.mkdtemp()` on
  Windows always carries a drive letter and is genuinely absolute. Build
  the literal from the real `tempfile.gettempdir()` at test-run time
  instead of hand-typing a POSIX path (see `tests/conftest.py`'s
  `fake_build_and_read_path()`). Surfaced by PR #220's first real
  `windows-latest` CI run across 7 call sites in 3 test files -- see
  [windows-macos-ci.md](windows-macos-ci.md).
- **A bit-for-bit POSIX permission assertion is unwinnable on Windows --
  NTFS only tracks a single read-only attribute, not owner/group/other
  bits.** `os.chmod(path, 0o644)` round-trips as `0o666` on Windows, not
  bit-for-bit; no black-box `stat()`-based check can distinguish
  "permissions restored" from "never touched" there. Spy on the
  `os.chmod` call's own arguments instead
  (`unittest.mock.Mock(wraps=os.chmod)` + `assert_called_once_with(...)`)
  on Windows, keep the real bit-for-bit `stat()` assertion on POSIX. A
  first attempt using `current_mode & stat.S_IWRITE` was vacuously true
  regardless of whether the real chmod-restore call ran -- caught by a
  later review round, not by the person writing the fix. See
  [windows-macos-ci.md](windows-macos-ci.md) and
  `tests/assemble/test_embed_core.py::test_embed_sbom_preserves_file_permissions`.
- **A monkeypatched stdlib method's fake must match the real method's
  actual signature, or mypy --strict rejects its forwarding call.**
  `pathlib.Path.stat()` is `stat(self, *, follow_symlinks: bool = True)`.
  A test fake written as
  `def fake_stat(self, *args: object, **kwargs: object)` forwards with
  `real_stat(self, *args, **kwargs)`, and that call fails
  `mypy --strict`: `object` cannot fill `follow_symlinks: bool`
  (PR #217, commit 622085dd, `test_fragments_merge_required.py`). Write
  the fake against the real method's actual signature (check it, don't
  guess), not a generic passthrough shim.
- **Monkeypatching a function on a shared stdlib module reaches every
  thread in the process.** `test_backoff_triples` (PR #259) recorded
  `scripts/retry_network.py`'s back-off with
  `monkeypatch.setattr(module.time, "sleep", sleeps.append)`.
  `module.time` is the process-wide `time` module, so a background thread
  left by an earlier test in the same xdist worker, polling with
  `time.sleep(0.001 .. 0.05)`, appended its own sleeps: the test passed
  alone and locally, then failed on two CI legs with
  `[0.001, 0.002, ...] == [10, 30]`. The code under test now does
  `from time import sleep` and the test patches `module.sleep`, a name
  only that module reads. Reproduce with a daemon thread calling
  `time.sleep` in a loop while the test runs. The same holds for any
  stdlib callable a test fakes to *record* calls (`time.monotonic`,
  `os.kill`, `subprocess.run`): patch the importing module's own name, or
  inject the callable.
- **A logging handler bound during a test outlives the test's capture
  stream.** `configure_logging()` builds `logging.StreamHandler(sys.stderr)`
  and installs it on the `pitloom` logger. Called while `capsys`/`capfd`
  is active (e.g. by `tests/test_logging_config.py` or any CLI test), that
  `sys.stderr` is pytest's capture file, which is closed when the test
  ends; the handler stays. The next test on the same xdist worker that logs
  through `pitloom` hits `ValueError: I/O operation on closed file`, and
  `logging` prints `--- Logging error ---` plus a traceback to the current
  stderr. `test_fickling_stderr_becomes_one_bounded_escaped_warning`
  asserts an empty stderr, so it failed on the 3.10 CI leg of PR #263 and
  in 1 of 10 local runs, by xdist ordering only. Repro:
  `pytest -n0 tests/test_logging_config.py <the fickling test>`. Fix: an
  autouse fixture in `tests/conftest.py` (`_restore_pitloom_logger`) puts
  the logger's handlers and level back after every test. Production keeps
  binding at configure time on purpose: it keeps Pitloom's own warnings out
  of the fickling stderr capture (`stderr_capture.py`). Any other
  process-global state a test can change (logger handlers, `sys.stderr`
  proxies, signal handlers, `warnings` filters) needs the same restore.
  Revised in PR #449: the fixture snapshotted the logger when a test
  started, but a module- or session-scoped fixture (a `WheelBuilder` build,
  the G7 AI scenario SBOMs) runs `configure_logging()` before it, so the
  snapshot took `INFO` plus a handler for the clean state and kept it for
  the rest of the worker. On macOS 3.13 CI, `test_persist_registry.py`
  then captured `INFO` records logged outside its `caplog.at_level` block,
  and `test_over_cap_archive_names.py` lost its `DEBUG` ones. Repro:
  `pytest -n0 tests/assemble/test_wheel_integration.py
  tests/id_registry/test_persist_registry.py`. The fixture now sets a fixed
  unconfigured state before and after each test (`tests/_logger_state.py`):
  a restore of process-global state restores a known baseline, never a
  snapshot taken after broader-scoped fixtures ran.
- **`--dist=loadscope` hides cross-module leaks that `worksteal` shows.**
  loadscope keeps a module on one worker, so a leak only reaches tests of
  modules that happen to follow it. Switching to worksteal (for speed)
  exposed `PITLOOM_DEBUG=1` leaking from
  `test_ctrl_c_is_one_error_line_and_exit_130[debug-flag]` (a `delenv` on
  an absent name records no restore; `--debug` then writes `os.environ`
  directly) into `test_stdout_is_key_value_only`. Found by an autouse probe
  that diffs `os.environ` against the session start at each test's setup
  and names the previous test on that worker. Fix: `tests/_environ.py`
  restores `os.environ` after every test (autouse in `tests/conftest.py`),
  and the test uses `setenv("0")`.
- **A test helper that normalises what it captures hides the bug class
  under test.** `StubBin.run` used `subprocess.run(text=True)`, whose
  universal newlines turn CRLF into LF, so every "Windows CR is dropped"
  assertion in `tests/scripts/action/` passed even with the stripping code
  deleted. A mutation pass (18 one-line breaks of `action.yml` and
  `scripts/action/*`, rerun after each fix) exposed it; reviewers had not.
  Decode bytes without newline translation. Survivors left on purpose:
  defensive fallbacks, error wording, and the Python-step `if:`
  expressions (covered only by `action-selftest-install.yml` in CI)
  (PR #224).
- **A `skipif` decorator's condition is evaluated at import time, on
  every platform, however certain the skip is.**
  `@pytest.mark.skipif(os.geteuid() != 0, ...)` raises
  `AttributeError: module 'os' has no attribute 'geteuid'` on Windows
  while the module is being collected, so the *whole file* errors out
  before any skip applies -- one red CI leg, every other one green, and
  the failure names a test that was never meant to run there. Compute a
  single short-circuited module constant instead and pass that:

  ```python
  # One condition, not two decorators: a decorator's argument is
  # evaluated at import time, so a bare os.geteuid() call would fail the
  # whole module on Windows, where it does not exist.
  _POSIX_PERMISSION_BITS = sys.platform != "win32" and os.geteuid() != 0
  ```

  Same trap for any POSIX-only name (`os.getuid`, `signal.SIGKILL`,
  `os.killpg`) referenced in a decorator argument, a default argument,
  or a module-level `parametrize` list. Verify by importing the module
  with `sys.platform` forced to `"win32"` and the attribute deleted,
  rather than waiting for the Windows leg.
- **Mutation testing has two silent ways to lie.**
  - *An equivalent mutant is not a surviving mutant.* Reproducing the
    bug "in spirit" proves nothing: moving a `clear()` call inside the
    `try` block it used to precede is semantically equivalent, so the
    test that was supposed to kill it could not. Reinstate the exact
    pre-fix shape, character for character, or the check is worthless.
  - *A lazily-installed side effect makes an assertion blind.*
    `TerminationGuard` installs its signal handlers at the first
    `hold()`, so a test asserting "the guard was released" observed
    nothing at all until it was widened to assert on the *next* block's
    cleanup fallback. When an assertion cannot distinguish the fix from
    its absence, the fault is usually that the thing being observed is
    created later than the test assumes.
- **A test that reaches the network through a subprocess or library
  bypasses `tests/conftest.py`'s socket block, and a flake there is
  invisible.** `spdx3-validate` downloads its JSON Schema and SHACL
  model from spdx.org on every run (no cache, no offline mode in 0.0.7),
  so the wheel-validation tests failed on a TLS handshake error on one
  CI leg while the block, which patches only the in-process
  `socket.socket`, never applied. `_fetch_pypi_release_info` swallows
  every failure into `None`, so the live PyPI test reported
  `None is not None` with no cause. One `network` marker now covers every
  real-network test, and `tests/_network.py` turns a network cause
  (recognised from the exception chain or the stderr text) into
  `pytest.skip("network unavailable: <cause>")`; any other failure, and any
  fetch that returns data, still asserts in full. Where the code hides the
  cause (`--allow-build` logs a truncated warning), probe the host up
  front with `require_reachable()` instead. No retry loop: a retry only
  hides how often the network fails. (The `build.yml` validation steps do retry,
  through `scripts/retry_network.py`, but log every failed attempt and
  still fail the job when all of them hit the network, PR #259.) The default CI
  job leaves `network` tests out (`-m "not network"`: a slow Savannah or
  labs.etsi.org failed three runs of one PR) and runs the local-server tests
  as `loopback` (lenient: a missing `git http-backend` skips them quietly, also on
  Windows, where `tests/_git_http_server.py` looks for it without `.exe`);
  `live-tests.yml` runs the `network` ones weekly and on demand.
  The release workflow is a strict gate: its `network-quality-gate` job sets
  `PITLOOM_REQUIRE_NETWORK=1` (a network failure, or any skipped
  `network` test, fails the job), and its `build` job runs
  `spdx3-validate` on the release SBOM as a step. Both must pass before
  `publish`, because publishing an SBOM generator whose output was never
  schema-checked is not acceptable. Not a replacement for offline tests:
  content the code can mock should be mocked. `python -m spdx3_validate`
  (0.0.7) exits 0 on invalid input because `__main__` drops `main()`'s
  return code; call the console-script entry `main()` and use its code.
  A module-level skip (`importorskip`) is a collect report, so the strict
  gate hooks `pytest_make_collect_report` too. A directory-level
  `importorskip` in a `conftest.py` (`tests/extract/conftest.py`) is a
  skipped directory collect report; the hook fails it when any `.py`
  beneath declares the marker. Classification
  lives in `tests/_network_classify.py`: one errno/winerror set and one
  message pattern shared by the exception and text paths.
- **A long parametrize value becomes the test id, and Windows caps the
  environment.** pytest sets `PYTEST_CURRENT_TEST` to the node id at setup
  and teardown; Windows limits an environment variable to 32,767
  characters. `@pytest.mark.parametrize("body", ["MIT and Apache-2.0 " *
  2500, ...])` made a 48 KB id: every other leg passed, `windows-latest`
  errored at setup (PR #276). Give a long string or bytes value a short
  explicit `ids=`. `tests/conftest.py`'s autouse `_short_nodeid` fixture
  fails any test whose node id is over `MAX_NODEID_LENGTH` (1,000), on
  every platform. A fixture, not a `pytest_collection_modifyitems` hook
  that raises: pytest-xdist drops the message of an exception raised in
  that hook (an `INTERNALERROR` naming only a node id).
- **On Python 3.14, `zipfile.ZipFile.writestr()` with a plain name stamps the
  entry from `SOURCE_DATE_EPOCH`, and ZIP cannot hold a date before 1980.**
  A test that sets `SOURCE_DATE_EPOCH=0` and then builds a zip passes on
  3.10 to 3.13 and fails on 3.14 only (`struct.error: 'H' format requires
  0 <= number <= 65535`), and a red leg skips the Codecov upload, so the
  coverage shown goes stale (PR #294: three tests, only the 3.14 leg). Use
  `315532800` (1980-01-01) in such a test; production code passes an explicit
  `ZipInfo(date_time=...)`. Five other tests set `"0"` and build no zip today.
- **`Path.write_text("data\n")` writes `\r\n` on Windows.** A test that
  wrote a fixture that way and registered `hashlib.sha256(b"data\n")` as its
  digest failed on `windows-latest` / 3.11 only: the file's real digest
  differed, the registry lookup missed and the File got a minted id
  (`tests/core/test_loom_dataset_dedup.py`, PR #305, four parametrised cases,
  one leg; the Windows dry-run checked paths, symlinks and permissions, not
  newlines). Write the fixture with `write_bytes(b"data\n")`, or hash the
  bytes read back (`Path.read_bytes()`), whenever a digest of known bytes is
  asserted. Same family: `read_text()` on a file that holds CRLF, and
  `splitlines()` on text-mode output. A dry-run checklist for a new test
  must list "any literal bytes hashed or compared against a text-mode write".
- **Coverage is collected on one CI leg (Linux, Python 3.14), so a branch
  only another OS or interpreter reaches is "missing" there.**
  `RegistryCopy._at` returned its case-insensitive match only on macOS;
  Codecov showed 97.72% for `core/walk_rules.py` while 3.10 / macOS / Windows
  runs showed 100%. A macOS case-sensitive APFS image reproduces the Linux
  view (`hdiutil create -size 64m -fs "Case-sensitive APFS" ...`; `pytest
  --basetemp <volume>/bt --cov-branch`). Detail and the fix:
  [recurring-bug-patterns-review-rounds.md](recurring-bug-patterns-review-rounds.md).
- **Python 3.14 reports a temporary file closed by the garbage collector as an
  unraisable error; `urllib.error.HTTPError` holds one.** The redirect probe
  read `exc.code` and `exc.headers` and let the error go: 47 tests failed on
  Ubuntu / 3.14 only (PR #317; `filterwarnings = error` turns it into a failure
  of whichever test the collector happens to run in). Close the error
  (`with exc:`), and call `gc.collect()` inside the regression test so the
  finaliser runs there.
- **A fixed sleep before an interrupt, a wall-clock bound and "a port nothing
  listens on" are flakes.** Wait for the condition (a pid file, an event),
  assert the message rather than the duration, bind and close a socket for a
  free port (#317).
- **A guard that raises inside a stdlib call must raise what that call
  cleans up on, or clean up itself; a third-party warning in a flaky test
  is first suspect for our own harness.** `tests/conftest.py`
  `_loopback_only` refused `socket.connect` with a non-`OSError`, and
  `socket.create_connection` closes its socket on `OSError` only, so the
  socket stayed open. Python reported `ResourceWarning: unclosed socket`
  in whichever test ran when it was freed, and `filterwarnings = error`
  made that a failure in an unrelated place (a line of
  `huggingface_hub/utils/_detect_agent.py`). It was flaky because the
  library caches its first call per process: only the first call of an
  xdist worker reached the guard, so a rerun showed nothing; resetting
  that cache before each test reproduced it. The guard now closes the
  socket before it raises, and `tests/test_loopback_marker.py` asserts
  `sock.fileno() == -1` after a refused `connect`, `connect_ex` and
  `socket.create_connection` (#528).

## From the 0.25.0 release (#556 to #563)

- **A fresh `contextvars.Context()` starts from the defaults.** A test that
  runs code "in a clean context" to check a non-default state must enter that
  state inside the context. #559's hook leg of a surface test ran on the
  library default, so it was vacuous: replacing the fallback line with `pass`
  still gave "5 passed".
- **A text-pattern mutant stops applying after the formatter reflows the
  code.** In #561 five mutant patterns no longer matched once ruff rewrapped a
  set literal, and "all killed" was overstated. The harness must fail when a
  pattern is not found.
- **A mutant survives when every internal caller pre-normalises the input.**
  `read_huggingface` is public and can get a padded URL, but every generator
  strips it first, so a "no strip" mutant lived (#561). Test the public
  function directly.
- **A negative substring check over a message that embeds a temporary path
  breaks on the path.** `assert "argument" not in file_err`
  (`tests/test_byte_cap_surfaces.py`) fails under any basetemp holding
  "argument", such as a worktree of that name (#560); `assert "--" not in
  text` also scanned an archive path (#559). Strip the path first, or assert
  on the exact field.
- **`configure_logging()` added to a constructor lets earlier steps' `INFO:`
  records reach `caplog`.** Four `test_persist_registry.py` tests failed
  (#560). Clear `caplog` before each `at_level` block, or assert only on
  records made inside it.
- **A docs-example test parses a flag inside a prose code span as a CLI
  example.** #556's "`--build-timeout has no effect`" failed the full suite;
  name only the flag inside the span.
- **A before/after sweep proves only the fields it recorded.** The LicenseID
  0.9.3 vs 0.9.4 probe read `r.texts`, an attribute the reading type lacks:
  `None` for all 339 files, "0 differ", while 6 files had changed (#563). Read
  typed attributes (no `getattr` default) and assert each recorded column has
  a value for some input in each run; count the provenance method the sweep
  is about (the 13 wheel SBOMs held no `licenseid_detection` at all).
- **A broad `except` around a third-party call hides a fake's missing
  method.** Three hand-written LicenseID fakes lacked `texts()`; the
  `AttributeError` went to a debug log and gave the expected "no reading"
  (#563). Spec fakes on the real class (`create_autospec(..., instance=True)`).
- **Do not edit the tree while a full or coverage run is going.** Docs-example
  tests read `docs/` at collection, so a docs edit gave xdist "Different tests
  were collected", and coverage mixed old data with edited source (#556,
  #557). Freeze the tree or run on a `git archive` copy.
- **Mark only the tests that touch files `platform`, not a whole slow
  module.** Marking `test_license_detection_corpus.py` added 41 tests of about
  1 s each to every Windows and macOS PR leg; #563 narrowed it to the Hub test.
