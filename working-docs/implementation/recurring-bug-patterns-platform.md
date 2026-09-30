---
Created: 2026-09-20
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: platform, concurrency, test harness, CI

See also: [recurring-bug-patterns.md](recurring-bug-patterns.md) (the
data-and-semantics half of the same list),
[CLAUDE.md](../../CLAUDE.md) ("Recurring bug patterns" -- the short
summary of both files).

Failure modes that come from the environment rather than from the data:
a Python version changing a stdlib promise, a platform lacking a
function, threads and signals crossing a context manager, a test that
passes for the wrong reason, a CI leg that fails where no other does.
Split out of [recurring-bug-patterns.md](recurring-bug-patterns.md) on
2026-09-20 when that file passed the size limit; nothing was reworded in
the move.

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
- **`Path.exists()`/`.is_file()` do NOT swallow every `OSError` -- only a
  specific errno set.** CPython's `pathlib._ignore_error()` returns
  `False` for genuinely any other failure, e.g. `PermissionError`
  (`EACCES`), which propagates straight out of a bare `.exists()` call
  instead of the caller getting a clean "not found"/"can't tell" signal.
  `merge_fragments()` (PR #217, `assemble/spdx3/fragments.py`) crashed
  the whole build with an unhandled `PermissionError` on a
  permission-denied fragment path before this was caught. Fix: classify
  the failure explicitly (now `pitloom.core.path_probe.is_missing_errno()`)
  instead of trusting a bare `.exists()`/`.is_file()` call to degrade
  gracefully on its own.
- **The POSIX/Windows split in that same classification must `OR` both
  checks unconditionally, never short-circuit on "winerror is set".** A
  real Windows `FileNotFoundError` carries *both* `errno=ENOENT` *and* a
  `winerror` (typically 2/3, `ERROR_FILE_NOT_FOUND`/`ERROR_PATH_NOT_FOUND`)
  -- neither of which is in the *extra* winerror set (21/123/1921) that
  exists specifically to catch cases `errno` alone doesn't cover.
  CPython's actual `_ignore_error()` is
  `errno in _IGNORED_ERRNOS or winerror in _IGNORED_WINERRORS` (checks
  both, every time). PR #217's own first fix for the item above got this
  wrong -- `if winerror is not None: return winerror in
  _STAT_MISSING_WINERRORS` -- which silently misclassified the single
  most common not-found case on Windows as "not missing," and wasn't
  caught until the *next* review round (a live interpreter check against
  `inspect.getsource(pathlib)` is what settled it, not reasoning from the
  docstring). Lesson underneath the bug: a fix from an earlier review
  round is not exempt from the next round's scrutiny -- verify it with
  the same rigor as new code, especially any platform-conditional logic
  that can't be exercised on the CI runner actually reviewing it.
- **`json.loads(bytes)` and `json.loads(str)` disagree on a leading
  UTF-8 BOM -- bytes auto-detects and strips it, `str` (after an explicit
  `.decode("utf-8")`) raises `JSONDecodeError: Unexpected UTF-8 BOM`.**
  The real SPDX3 merge path (`spdx3.JSONLDDeserializer().read()` on a
  binary file handle) is BOM-tolerant; any sibling code that does
  `path.read_bytes().decode("utf-8")` then `json.loads(str)` is not, and
  silently rejects a BOM-prefixed fragment a real build would merge
  fine. This exact bug shipped twice, independently, in one PR (#217):
  once in `cli/commands/fragment.py`'s `_fragment_read_status()`, and
  again in a *different* file added in the same PR,
  `extract/_json_io.py`'s `load_json_bytes()` -- fixed once, then found
  again by the next review round in the sibling file nobody thought to
  re-check. Prefer `json.loads(raw_bytes)` directly over decode-then-parse
  for any JSON read meant to match a binary-file-handle parse elsewhere.
- **`dict.get(key, default)` only guards the key's *absence*, not the
  key being present with the wrong type.** `data.get("@graph", [])`
  looks like it always yields something `len()`-able, but if `@graph`
  is present with a non-list value (e.g. a hand-edited or malformed
  fragment file with `{"@graph": 5}`), the default never applies and
  `len(5)` raises an uncaught `TypeError` (PR #217,
  `_fragment_read_status()` in `cli/commands/fragment.py`) -- crashing
  an entire multi-item CLI listing command instead of degrading just the
  one malformed record. Add an explicit `isinstance` check on the
  *value*, not just a default for the *key*, whenever "valid JSON, wrong
  shape" is a real possibility (any external/user-editable file, as
  opposed to output this codebase generated itself).
- **A monkeypatched stdlib method's fake must match the real method's
  actual signature, or mypy --strict silently accepts a runtime-only
  contract violation.** `pathlib.Path.stat()` is
  `stat(self, *, follow_symlinks: bool = True)` -- keyword-only, no
  positional `*args`. A test fake written as
  `def fake_stat(self, *args: object, **kwargs: object)` runs fine under
  pytest (nothing calls it with conflicting args in practice) but fails
  `mypy --strict` the moment the real call site passes
  `follow_symlinks=...` as a keyword, since `**kwargs: object` can't
  satisfy a `bool` parameter (PR #217,
  `test_fragments_merge_required.py`). Write the fake against the real
  method's actual signature (check it, don't guess), not a generic
  passthrough shim.
- **A version floor asserted in many places drifts -- and nothing checks
  it.** `scripts/check_version_consistency.py` covers Pitloom's *own*
  version string only, not dependency floors. The Hatchling floor lives in
  `pyproject.toml` (`[build-system] requires` *and* `dependencies`),
  README/docs/example snippets, the `hatch-integration.yml` matrix's
  floor axis, `_MIN_HATCHLING_SBOM_VERSION` in `plugins/hatch.py`, test
  literals, and an action-input example (PR #223). Two traps: (1) raising
  the floor to "the latest known-good" silently defeats a version-agnostic
  compat fix (#222 exists so older Hatchling keeps working) -- keep the
  floor at the *empirically verified* technical minimum (build + embed in a
  scratch venv pinned to it), and raise it only when a feature needs more;
  (2) prose and code sample disagreeing in the same paragraph ("Hatchling
  **1.29.0+** required" above `requires = ["hatchling>=1.32.3"]`). When
  changing one, `grep -rn` every spelling and classify each hit: *enforced
  requirement* and *illustrative example* move together; *historical
  narrative* (what the floor was when a past break happened) stays
  factual. Also keep the CI matrix's floor axis equal to the pyproject
  floor.
- **A manual repro that fails is first suspect for a wrong replication,
  not a real bug.** Two false alarms in one session (PR #223): an
  editable install run without the install sequence the CI composite
  action actually performs (Hatchling pin, `editables`, `setuptools`),
  and `normalize_requirement("Foo>=1")` called with a raw `str` where the
  real call site passes a `packaging.requirements.Requirement`. Read the
  actual call site/invocation and replicate its exact shape before
  concluding an old dependency version is incompatible.
- **To find what an undocumented upstream release changed, diff the two
  released wheels, not the changelog.** Hatchling 1.32.3's generic-arity
  change was in no changelog: `pip download pkg==A pkg==B --no-deps`,
  unzip both, `diff` the module (here `builders/plugin/interface.py`) and
  `git log -S` the upstream repo for the introducing commit (PR #222).
- **`gh pr checks` lists job names, not workflow names, and `paths-ignore`
  skips workflows on docs-only commits.** A "missing" check usually
  means a differently-named job of a workflow that did run (`Python 3.10
  on ubuntu-latest` is `build.yml`; pylint is a step inside `Ruff (Lint &
  Format)`, not its own check). Confirm with `gh run list --workflow=...`
  before concluding a check didn't run.
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
- **Workflow-command injection through echoed tool output.** A composite
  step that tees a tool's output to the log lets a line starting `::` run
  as a workflow command. `::stop-commands::<random token>` fences the echo,
  but the runner does not order stdout against stderr, so put the fence,
  the echo and the later annotations on one stream (`exec 1>&2`); a real
  run showed the token masked as `***` in the log, which is cosmetic
  (PR #224).
- **Annotation text needs `%` escaping** (`%25`, `%0A`, `%0D` are decoded
  by the runner), and a final line without a trailing newline is dropped
  by `while read` unless the loop also tests `[ -n "${line}" ]` (PR #224).
- **Python 3.14 changed what `Path.exists()`/`.is_file()` promise: they
  now swallow `PermissionError` and return `False`, where 3.10-3.13
  propagate it.** The rule recorded above (only a specific errno set is
  swallowed, anything else propagates) is therefore version-dependent
  from 3.14 on, and a test asserting `pytest.raises(PermissionError)`
  from `Path.is_file()` passes on every other matrix leg and fails only
  on 3.14 (`DID NOT RAISE`). Two consequences, both hit in PR #226:
  - In production, use `os.path.isfile`/`os.path.isdir` when the intent
    is "never raises" -- they have behaved that way on every supported
    version, so no version gate is needed and no leg can disagree.
    `is_sdist_archive()` and `target_settle_plan()` were moved to them
    for exactly this reason.
  - When a denied path must be *reported*, not treated as absent, use
    `pitloom.core.path_probe.is_regular_file()`: it raises the
    `PermissionError` on every version. On 3.14 a bare `is_file()` made
    a file under a denied directory vanish from the SBOM file scan with
    no warning ([file-scan-unreadable-file.md](file-scan-unreadable-file.md)).
  - The directory form of the same hazard: `os.walk()` without
    `onerror`, `glob` and `Path.glob()` skip an unlistable directory
    silently on every version. Backend libraries walk this way and take
    no callback, so discovery records the attempted listings with an
    audit hook instead
    ([file-discovery-unlistable-dir.md](file-discovery-unlistable-dir.md)).
  - In tests, gate the raising assertion with
    `if sys.version_info < (3, 14):` and keep a version-independent
    probe (`target.read_bytes()` inside `pytest.raises(PermissionError)`)
    so the test still proves the directory really is unreadable. Without
    that probe the 3.14 branch asserts nothing and passes vacuously --
    the setup could silently stop denying permission and no leg would
    notice.
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
- **A context manager whose `__exit__` can be interrupted must reset its
  shared state in `__enter__`, not in `__exit__`.** `EmbedFileCache`
  (PR #226) cleared its per-batch state on the way out; a
  `KeyboardInterrupt` part-way through that exit left a half-cleared
  batch that the next block then inherited. The working shape, and each
  rule behind it:
  - **Reset on entry.** `__enter__` starts from a known state rather
    than trusting the previous exit to have finished. An interrupted
    exit is then allowed to leave its batch behind on purpose.
  - **Do not take the lock in `__enter__`.** A worker thread from the
    previous block may hold it for the length of a whole build, and the
    next batch must not wait for that. This was tried and deadlocked its
    own regression test.
  - **Install a fresh container, never `.clear()` it.** A writer still
    running from the previous block holds a reference to the old dict;
    with `clear()` it writes into the *next* block's state, with a fresh
    dict it writes into the one it took, which nobody reads again.
    Correspondingly, a method that both tests membership and writes must
    capture the container once (`settled = self._settled`) under the
    lock and use that same object for both, or it can straddle two
    blocks.
  - **Detect "my block ended" by identity, not presence.** A worker
    returning from a long call must compare `self._guard is block` (the
    object it started under), not `self._guard is not None` -- by then a
    *new* block may have installed its own guard, and a presence check
    would happily cache a result into it that nothing will clean up.
  - **Anything the interrupt path still needs must be read from the
    attribute, not from a local captured earlier**, so an interrupt
    before that point leaves it where the outer handler can find it.
- **An "interrupted cleanup, retry it without the lock" recovery path is
  an anti-pattern.** PR #226's first fix did exactly that, and the next
  review round's top finding was that fix: the unlocked retry ran the
  discovery's cleanup while a worker thread was still inside
  `resolve()`, deleting the extraction directory under a live caller.
  State protected by a lock stays the property of whoever holds the
  lock, including on the failure path; an interrupt handler may release
  its own resources (here, the `TerminationGuard`) and nothing else.
  More generally: when a review round's finding is the previous round's
  own fix, the fix was reasoned about rather than reproduced -- write a
  live, timeout-bounded repro for any concurrency claim before believing
  either the bug or its fix.
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
  hides how often the network fails. Ordinary CI skips; the release
  workflow is a strict gate: its `network-quality-gate` job sets
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
