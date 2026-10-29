---
Created: 2026-10-03
Last-Modified: 2026-10-29
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
- **A hand-made fake of a library object hides what the library does.**
  The licence reader drift test fed every surface a `_FakeMetadata` dict;
  the real `importlib.metadata` object dedents values, so the installed
  surface lost a licence's indent while the test passed (#286).
  Do: build the real object (`importlib.metadata.PathDistribution` over a
  `.dist-info` written in `tmp_path`) and patch only the lookup.
- **A narrowed `except` is untested until the dependency really fails.**
  #289 caught only `DatabaseNotReadyError` from `licenseid` 0.4.2; CI was
  green, but only mocks raised it. The new tests copy the real database
  into `tmp_path` and damage it after the matcher is built (delete,
  truncate, zero the 4 KiB header, drop one table): one `WARNING:`, no
  licence, a working lookup once the file is restored, and a deleted file
  never re-created. On `licenseid` 0.4.1 all four fail, so they also
  enforce the version floor. A table of hostile inputs on a healthy
  database (FTS operators, NUL, a lone surrogate, SQL injection, 100,000
  characters) must neither warn nor rebuild the matcher; it found the
  `LIKE` limit above (messages-and-surfaces.md).
  Do: damage a real copy of the dependency's files mid-run; pair that
  with hostile input on a healthy copy, which must stay silent.
- **Track an upstream bug with a strict `xfail`, and check its reason.**
  `xfail(strict=True)` turns the upstream fix into a red XPASS, the cue
  to drop the marker and raise the floor. A strict `xfail` passes on any
  failure, so run it once with `--runxfail`: one case first passed
  outright, because text appended after a JSON document made it no
  longer JSON, and the trigger needs the whole text to be JSON (#289).
  Do: give each upstream-bug case its own `xfail(strict=True)` and read
  its `--runxfail` failure once.
- **A hand-built fixture shares its author's assumptions.** The ONNX
  `type_of_model` rule passed every unit fixture and failed on the first
  real tf2onnx file (#294). Run the generator on a real project that
  uses the formats (here PyThaiNLP `main`: 3 ONNX plus 5 CRFsuite models,
  no `WARNING:`, schema and SHACL valid) before merging a reader change.
  Do: keep one real-data acceptance run per format family, offline-skipped.
- **A skipped upload shows a stale number.** Codecov reported 89% for a
  module that was at 100%: failing CI runs skip the upload step, so the
  last passing run's figure stayed. Forcing the upload with `always()`
  would replace it with a partial figure from failed tests, so the step
  was left alone (#294).
  Do: before trusting a coverage drop, check the run actually uploaded.
- **Adding a keyword to a test helper can trip the argument limit.**
  `_save(..., node_domain=)` made 7 arguments against pylint's 6
  (`too-many-arguments`), found only by CI's pylint (#294).
  Do: run pylint on the tests directory you touched, not just ruff.
- **A "stays the same" test passes if the input never arrived.** "An
  extra-only dependency the lock also resolves stays optional" passes too
  when the lock pin never reaches the document. The test runs it locked and
  unlocked, and the real-fixture case first asserts `time-machine==2.16.0`
  is in `locked_dependencies` (#300).
  Do: assert the precondition took effect, and run the opposite case.
- **Coverage is per interpreter, and a green local 100% can still upload a
  miss.** The branch `except (SyntaxError, ValueError)` around `ast.parse` is
  reached by a NUL byte on 3.10/3.11 only (3.12+ rejects it in the tokenizer
  first); the local 3.10 run covered it and the PR's Codecov report did not
  (#300). `api.codecov.io/api/v2/github/<org>/repos/<repo>/file_report/<path>
  ?sha=<sha>` gives the missed line numbers without a login.
  Do: cover every `except` type with an input that fails the same way on each
  supported version.
- **Compare a type checker's count against HEAD with the same interpreter.**
  `pyrefly` on a `git archive` copy with a different Python found 71 errors
  against 41 locally; `--python-interpreter <venv python>` gave 41 on both.
  Do: pin the interpreter before calling an error count "new".
- **A thread timeout cannot interrupt a regex.** `re` holds the GIL, so a
  test that bounds a quadratic splitter with a thread still hangs; the bound
  is a child process killed at the limit (`tests/_bounded.py`
  `run_bounded_in_child`). A 300,000-attribute expression also segfaults 3.10
  (exit 139), which only a child process survives.
- **A fail-on-base proof must run the copy's own code.** A subprocess test
  that launched `loom` passed on the base copy because the installed
  Pitloom, not the copy, ran; pinning `PYTHONPATH` to the copy's `src` made it
  fail as it should.

- **`write_text("x\n")` is CRLF on Windows.** A fixture written that way and
  checked against `hashlib.sha256(b"x\n")` passed on Linux and macOS and failed
  on `windows-latest` / Python 3.11 only (PR #305, four cases of one test;
  the lookup missed and the element got a minted id). Do: `write_bytes` for any
  digest of known bytes; list "literal bytes hashed against a text-mode write"
  in every Windows dry-run checklist.
- **A subset run shows coverage that the full run does not.** Lines of an
  untouched file read as uncovered in a partial `pytest` run and were 100% in
  the full one; a guard that was really unreachable (pruned by the walk and
  rejected by a PATH check first) was found only after ruling that out. Do:
  take the coverage figure from the full suite, then decide dead or missing.

- **Coverage that only another OS reaches.** The repository uploads coverage
  from one CI leg (Linux, Python 3.14). A case-fold branch that fires only
  where the file system folds case (macOS, Windows) was 100% on every
  developer machine and missing on the coverage service (one line, one
  partial branch in a 269-line module, 97.72%). A hard link in another case
  makes the same code path reachable on a case-sensitive file system; a
  case-sensitive APFS image (`hdiutil create -fs "Case-sensitive APFS"`)
  reproduces the Linux view on a Mac, and a whole-suite run on it found no
  other gap. Do: name the CI leg that reaches each OS- or
  interpreter-dependent branch, and test that branch there.
- **A Markdown line that starts with `<p>` hides the rest of the page.** A
  wrapped code span put `<p>` at the start of a line; the renderer treated it
  as an HTML block and dropped everything after it (2 of 7 headings
  rendered). The only symptom was three "missing anchor" notes from the site
  build. Do: compare source and rendered heading counts for every page.
- **`ZipFile.writestr(name, data)` writes the current time into the
  archive.** A test that built a PT2 archive that way, then compared two SBOM
  builds byte for byte, passed locally on every run and failed once on CI
  (Python 3.10): the archive hash feeds the wheel hash, the Merkle root and the
  document UUID, and the member time differed when the second ticked over
  between the builds (#306). `ZipInfo(name)` carries the fixed time
  1980-01-01. Rerunning proves nothing about a clock race; making the clock
  move on every call (`time.time` patched to a counter) failed the old shape
  3 times in 3.
  Do: perturb the source of non-determinism in the test, and grep fixture
  builders for `writestr(<str>`.
- **A second guard in a derived rule needs a case that differs only in it.**
  The count note is added when an entry has key `parameters` and a count-like
  value. Deleting the key test left 45 of 45 tests green until a case with
  another digit-valued key (`llama.context_length: "2048"`) was added; a
  mutation run found it (#306).
  Do: for `A and B`, one test where only `A` fails and one where only `B`
  fails.
- **A live host that is slow turns a fallback into a failure.** Pitloom probes
  a Git URL for a redirect and, if the probe fails, asks git directly; git
  follows no redirect, so a slow Savannah or labs.etsi.org gave
  `returned error: 301` or `302` (three red runs of one PR, 2026-10-28), and a
  TLS drop gave `gnutls_handshake() failed`. The live test now skips only when
  the probe failed *and* the error is a bare redirect, and the network classifier
  knows git's GnuTLS wording.
  Do: classify a failure by the cause the code logged (the probe failed), not by
  the final message alone; add each new wording to the classifier with a test
  row.
- **Two kinds of test shared one marker.** `network` covered 68 tests that use
  only a server the test starts and about 53 that reach real hosts, so
  excluding the flaky ones from default CI would have dropped the reliable ones.
  A `loopback` marker (guarded: in-process `connect` and `connect_ex` refuse any
  other address) separates them; `network` runs in the release gate, a weekly
  workflow and by hand. A review found the guard's limits: DNS lookups, UDP and
  subprocesses pass it, and one `loopback` test still asked DNS for
  `evil.example`.
  Do: when a marker's meaning splits, split it, and name in the docs what the
  guard does not cover.
- **A validator's output order can depend on the hash seed.** `spdx3-validate`
  findings, and the values inside a SHACL `not in list [...]` message, changed
  between runs with `PYTHONHASHSEED`; six seeds gave six outputs. Sorting the
  findings by (source, kind, message) and the list values (through
  `ast.literal_eval`, since a value can hold a quote or a bracket) gave one.
  Do: run a command under several seeds and hash its output before calling it
  deterministic.

- **A strict network mode turns another party's outage into your failure.** With
  `PITLOOM_REQUIRE_NETWORK=1`, seven live forge tests failed in the 0.21.1
  publish gate: `Could not resolve host: code.overheid.nl`, and `Failed to
  connect to git.sr.ht port 443 after 135048 ms`. "Re-run failed jobs" passed.
  Do: keep the strict set small and reliable, put the rest in a scheduled job,
  and never "Re-run all jobs" after `publish` (a new wheel timestamp).
- **A thread-local flag is cleared before the call and read right after it.** The
  discovery-failure flag is set on the caller's thread by whichever discoverer
  logs a failure; the dispatcher clears it first, so a report left by an earlier
  call cannot reword the next. Test the stale case, not only the set case.

- **A path spelled `./x` is normalised by `Path`, so a mutant on the
  de-duplication key survives.** The pointer summary de-duplicated on
  `normcase(realpath(path))`; a test using `./x` never differed from `x`. The
  test spelled `data/../data/x`, and a unit test patched `normcase` with a
  case-folding stub, so nothing depends on the file system.
- **A drift guard against the real tool needs a verdict per row, and the
  intended differences named.** The grammar matrix runs every row through `git
  lfs pointer --check --stdin` (skipped without git-lfs). Ten rows git-lfs
  3.4.1 accepts are refused on purpose (`1024-bytes`, `empty`, `blank-line`,
  `trailing-blank`, `trailing-space`, `ext-after-oid`, `size-plus`,
  `size-leading-0`, `mixed-eol`, `mixed-final-eol`); the list is asserted
  exactly, so a change in either direction fails.
- **A fixture checked out with CRLF changes its digest.** Real pointer fixtures
  carry `-text` in `.gitattributes`, and tests that need other line endings
  build them with `lfs_pointer_bytes(eol=...)`.
- **A skip for an absent fixture is also silent in a development checkout.**
  Tests that read the pointer fixtures use `pointer_fixture()`, which skips when
  `tests/fixtures/lfs-pointers/` is missing, so the sdist test run does not
  error. The same skip hides a checkout that lost the directory. Open: a test
  that asserts the directory exists when a `.git` directory does.
- **A "bounded read" claim needs a spy on `open`.** The detector tests wrap the
  file object and assert no read asks for more than 1024 bytes, and that a
  sparse 64 MiB file is read for zero bytes.

- **A module-level `pytest.skip` in a shared helper skips every importer.**
  `tests/_lfs.py` built its pointer table at import by calling a function that
  skips when the fixture directory is absent. In an sdist copy of `tests/` that
  skipped 17 modules (307 tests) instead of the 4 that needed the files. Found
  by copying `tests/` without the directory and running it; build such data
  lazily.
- **Simulate the artefact you ship.** The sdist exclude was correct, and its
  consequence for the tests was only visible by running a copy of `tests/`
  without the excluded directory.
- **A test written for a fix can pass without it.** The licence-reader test
  passed with the new check replaced by `return None`, because the project it
  built never put the pointer text where it asserted. Revert the fix, run the
  test, and look at the failure.
