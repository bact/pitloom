---
Created: 2026-09-20
Last-Modified: 2026-11-24
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: platform, concurrency, CI

See also: [recurring-bug-patterns.md](recurring-bug-patterns.md) (the
data-and-semantics half of the same list),
[recurring-bug-patterns-test-harness.md](recurring-bug-patterns-test-harness.md)
(test-harness traps, split out of this file on 2026-11-24),
[recurring-bug-patterns-platform-windows.md](recurring-bug-patterns-platform-windows.md)
(Windows-only CI findings),
[CLAUDE.md](../../CLAUDE.md) ("Recurring bug patterns" -- the short
summary of these files).

Failure modes that come from the environment rather than from the data:
a Python version changing a stdlib promise, a platform lacking a
function, threads and signals crossing a context manager, a CI leg that
fails where no other does. Split out of
[recurring-bug-patterns.md](recurring-bug-patterns.md) on 2026-09-20 when
that file passed the size limit; nothing was reworded in the move.

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
  on ubuntu-latest` is `build.yml`; flake8 is a step inside `Ruff (Lint &
  Format)`, not its own check). Confirm with `gh run list --workflow=...`
  before concluding a check didn't run.
- **A green linter run can be linting a fraction of the tree.**
  `tests/__init__.py` makes `tests/` a package, and pylint expands a
  package only into subfolders that have `__init__.py` -- so `pylint
  tests/` (with or without `--recursive=y`) skipped every test file under
  `tests/*/`, ~450 findings unseen. Linting a subfolder directly named its
  modules by basename, so relative imports misreported (E0402) until
  `source-roots` gained `"."` (a directory argument only: a single file
  argument still gets a bare name); astroid still cannot resolve a relative
  import of a *subdirectory* from a namespace folder (`from .hf_patches.x`),
  so those became absolute `tests.` imports. CI now runs `pylint ...
  tests/ tests/*/`. Check a linter's scope by planting a known finding in
  the deepest folder, not by reading its score.
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
- **One directory, two spellings: a textual "is it under the project"
  check misses on a case-insensitive file system.** On macOS
  `Path.resolve()` keeps the caller's letter case, but `os.getcwd()`
  after `chdir()` returns the on-disk case, so `loom project stproj`
  for on-disk `StProj` gives paths that `relative_to(project_dir)`
  rejects. It hit twice, found in the PR #257 review: the unlistable-
  directory warning was silently dropped for setuptools (fixed by a
  `(st_dev, st_ino)` ancestor match after the textual one), and
  setuptools discovery itself returns absolute `physical_path`s (open in
  [roadmap.md](../design/roadmap.md)). Any path produced from a
  `chdir()` + `getcwd()` is suspect. When matching by identity, treat
  `st_ino == 0` as no identity: Python calls `st_ino` unique only when
  non-zero, and FAT/exFAT and some network shares report 0 for every
  file, which makes everything on the volume match. Test the case form
  where the file system is case-insensitive (skip otherwise), and the
  identity form portably through a symlinked alias.
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
- **`os.killpg` on the group of a process that has exited but is not reaped is
  `ESRCH` on Linux and `EPERM` on macOS.** A kill that races the exit
  (output cap, deadline) failed with `PermissionError` on macOS / 3.13 only
  (#317). Catch both; test with a patched `killpg` raising each.
- **Start the helper threads inside the `try` whose `except BaseException`
  kills the child.** `_capture` started a timer and a reader thread before
  it; a Ctrl-C in `Thread.start()` left git running (flaked on Ubuntu / 3.10,
  #467). Regression test: a Thread subclass whose `start()` raises
  `KeyboardInterrupt`, patched into the module under test; assert the child
  is gone.
- **`os.kill(pid, 0)` succeeds on a zombie**: use one shared "is it gone"
  helper (`tests/_pid.py`: `/proc` state `Z` is gone; `tasklist` on Windows).
  A plausible explanation of a flake is not a diagnosis until a test fails
  without the fix.
- **A skipped CI run must not remove the only full run of a leg**: with a
  platform subset on PRs, skip shrinks the Windows and macOS matrix, never
  empties it. A workflow that reads a PR label needs the `labeled` trigger in
  every workflow gating on it, and a per-run concurrency group for unrelated
  labels (#467).
- **A POSIX-only fixture name or URL fails on one Windows leg.** `a@b:c` is not a
  file name there, and `file://D:\x` is not a URL (#317): skip with the reason,
  keep the behaviour covered on POSIX.
