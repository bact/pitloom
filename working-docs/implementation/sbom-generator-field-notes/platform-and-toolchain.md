---
Created: 2026-10-02
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: platform, toolchain and test harness

See also: [README.md](README.md) (index of these notes),
[recurring-bug-patterns-platform.md](../recurring-bug-patterns-platform.md)
(full detail of most items below),
[windows-macos-ci.md](../windows-macos-ci.md),
[ci-install-composite-action.md](../ci-install-composite-action.md),
[hatchling-build-hook.md](../hatchling-build-hook.md),
[github-action.md](../github-action.md).

## 1. Operating system and Python version

- **`Path.exists()` changed its promise in Python 3.14.** For a file
  under a `chmod 000` directory, `Path.exists()` raises `PermissionError`
  on 3.10-3.13 and returns `False` on 3.14 (checked 2026-10-02 on 3.13.12
  and 3.14); `is_file()` likewise. On 3.14 such a file vanished from the
  SBOM file scan with no warning; on 3.10-3.13 a bare `.exists()` crashed
  a whole build on one denied fragment (#217, #226, #244).
  Do: use `os.path.isfile` where "never raises" is meant; where a denied
  path must be reported, `stat()` it and classify the errno yourself.
- **A Windows "not found" carries two codes.** A real Windows
  `FileNotFoundError` has `errno=ENOENT` and `winerror` 2 or 3; CPython
  ignores `errno in _IGNORED_ERRNOS or winerror in _IGNORED_WINERRORS`.
  Pitloom's first fix returned early on "winerror is set" and so
  classified the commonest Windows not-found as "not missing"; it was
  caught by the next review round, not by CI (#217).
  Do: OR both checks unconditionally.
- **`/tmp/x` is not absolute on Windows.** `PureWindowsPath.is_absolute()`
  needs a drive letter, so a hand-typed POSIX literal in a test stopped
  exercising the "absolute path" branch on 7 call sites in 3 test files,
  found on the first `windows-latest` run (#220).
  Do: build test paths from `tempfile.gettempdir()` at run time.
- **NTFS keeps one read-only bit, not nine.** `os.chmod(p, 0o644)` reads
  back as `0o666` on Windows, so no `stat()` check can tell "restored"
  from "never touched". A first attempt with `mode & stat.S_IWRITE` was
  true either way (#220).
  Do: on Windows, spy on the `os.chmod` call
  (`Mock(wraps=os.chmod)`); keep the bit-for-bit check on POSIX.
- **One directory, two spellings.** On macOS `Path.resolve()` keeps the
  caller's case while `os.getcwd()` after `chdir()` gives the on-disk
  case; `loom project stproj` for on-disk `StProj` gave paths that
  `relative_to()` rejected, and a warning was silently lost. Pitloom
  falls back to an ancestor match on `(st_dev, st_ino)`, and treats
  `st_ino == 0` (FAT, exFAT, some network shares) as no identity, or
  every file on the volume would match (#257).
  Do: distrust any path produced by `chdir()` plus `getcwd()`.
- **Libraries skip unlistable directories in silence.** `os.walk()`
  without `onerror`, `glob` and `Path.glob()` drop a `chmod 000`
  directory's subtree on every Python version, and the backends' own
  discovery (Hatchling, flit-core, pdm-backend, poetry-core, setuptools)
  passes no callback. Pitloom records each `os.scandir`/`os.listdir`
  request with a PEP 578 audit hook during discovery, re-lists them
  afterwards, and logs one `WARNING: DIR=<path>: could not list ...` per
  failure. Patching `os.scandir` was rejected: process-global, racy, and
  blind to pathlib on 3.10 (#257).
  Do: observe the calls a library makes when you cannot pass it a
  callback.
- **A `skipif` argument runs at import, on every platform.**
  `@pytest.mark.skipif(os.geteuid() != 0, ...)` raises `AttributeError` on
  Windows while collecting, so the whole module errors and the skip never
  applies: one red leg naming a test that was never meant to run there.
  Use one short-circuited constant,
  `sys.platform != "win32" and os.geteuid() != 0` (#226).
  Do: keep POSIX-only names out of decorator, default and `parametrize`
  arguments.
- **Shell scripts meet three different shells.** Native Windows Python
  ends lines with CR, which Git Bash's `$(...)` keeps; Git Bash has no
  `/dev/stderr`; macOS bash 3.2 has no `readarray` and is quadratic on
  `${x//pat/}` (#224).
  Do: strip CR from every captured value and test on all three.

## 2. Build tools and CI

- **A build backend can break its plugin API in a patch release.**
  Hatchling 1.32.3 (2026-09-17) changed `BuildHookInterface` from one type
  parameter to two, in no changelog; subscribing it with one raised
  `TypeError: Too few arguments` at import, on every build. 1.32.4
  (2026-09-20) reverted it as a bug. Pitloom reads
  `len(BuildHookInterface.__parameters__)` at run time, fails loudly on an
  unknown count, and keeps one shape for type checkers under
  `TYPE_CHECKING`; no upper pin (#222, #229).
  Do: detect the runtime shape, not the version; find an undocumented
  change by diffing the two released wheels, not the changelog.
- **Keep a dependency floor at its verified minimum.** The Hatchling floor
  appears in `pyproject.toml` twice, docs, examples, the CI matrix, a
  constant and test literals; nothing checks they agree, and prose said
  "1.29.0+" above a `>=1.32.x` example. Raising the floor to "latest
  known-good" would defeat the compatibility fix. It stays at 1.29.0,
  proven by a build and embed in a venv pinned to it (#223).
  Do: grep every spelling when the floor moves; leave historical
  narrative as it was.
- **pip's `--no-build-isolation` applies to the whole command.** A
  self-referential install (Pitloom's wheel is built with Pitloom's own
  hook, which must not be fetched stale from PyPI) needs it, but in the
  same `pip install` as `--group` packages it turns isolation off for all
  of them, a risk for any that builds from source (`atheris` has no wheel
  below Python 3.12). `pip` has no per-package switch (#222).
  Do: give the local install its own `pip install` call.
- **GitHub Actions expands `${{ }}` inside shell comments.** Text after a
  `#` in a `run: |` block is substituted before the shell sees it; one
  explanatory comment with an empty `${{ }}` made a composite action fail
  to load (`An expression was expected`, reported at the block's line)
  and broke 10 workflows at once (#222).
  Do: write "a GitHub expression splice" in comments, never the syntax.
- **Tool output echoed to a CI log can run workflow commands.** A line
  starting `::` is executed by the runner. Fence the echo with
  `::stop-commands::<random token>`; since the runner does not order
  stdout against stderr, the fence, the echo and later annotations must
  share one stream (`exec 1>&2`). Annotation text needs `%25`, `%0A`,
  `%0D` escaping, and `while read` drops a last line without `\n` unless
  it also tests `[ -n "${line}" ]` (#224).
  Do: treat every tool's output as untrusted input to the log.
- **CI inputs fail silently in small ways.** `mpalmer/action-validator`
  splits `patterns` per line, so a comma-joined value validated zero files
  without an error; `actions/upload-artifact`'s `if-no-files-found`
  fires only when no line of a multi-line `path` matches, so a missing
  SBOM beside a present wheel passed (#222).
  Do: check each expected artefact in its own step.
- **A validator's exit code may not mean what it says.** `python -m
  spdx3_validate` (0.0.7) exits 0 on invalid input because its `__main__`
  drops `main()`'s return value; it also downloads its JSON Schema and
  SHACL model from spdx.org on every run, so a test calling it is a
  network test even though the in-process socket block never sees it
  (#238).
  Do: call the console entry's `main()` and use its code; mark subprocess
  network use explicitly.
- **A green linter may lint a fraction of the tree.** With
  `tests/__init__.py`, pylint expands `tests/` only into subfolders that
  have their own `__init__.py`, so every file under `tests/*/` was
  skipped, about 450 findings unseen. CI now runs
  `pylint ... tests/ tests/*/` (#268).
  Do: plant a known finding in the deepest folder to prove a linter's
  scope.

## 3. Test harness

- **A capture helper can erase the bug under test.**
  `subprocess.run(text=True)` turns CRLF into LF, so every "stray CR is
  stripped" assertion passed with the stripping code deleted. Found by
  18 one-line mutations of the action scripts, not by review (#224).
  Do: decode bytes yourself; mutation-test shell and CI changes.
- **Monkeypatching a stdlib module patches every thread.**
  `monkeypatch.setattr(module.time, "sleep", ...)` also recorded sleeps
  from a thread an earlier test left running: green alone, red on two CI
  legs under xdist (`[0.001, 0.002, ...] == [10, 30]`). The module now
  does `from time import sleep` and the test patches that name (#259).
  Do: patch the importing module's own name, or inject the callable.
- **A logging handler outlives the test's stderr.** A handler bound to
  `sys.stderr` under `capsys` points at pytest's capture file, closed at
  teardown; the next test on that worker printed `--- Logging error ---`
  and failed an "empty stderr" assertion, 1 run in 10 (#263).
  Do: restore logger handlers, `warnings` filters and signal handlers
  after every test.
- **Mutation testing can lie twice.** An equivalent mutant (moving a
  `clear()` inside the `try` it preceded) cannot be killed and proves
  nothing; an assertion on a side effect installed lazily (signal
  handlers at first use) observes nothing either way (#226).
  Do: reinstate the exact pre-fix code, character for character.
- **A fake must match the real signature.** `Path.stat()` is
  `stat(self, *, follow_symlinks=True)`; a fake taking
  `*args, **kwargs: object` ran under pytest but failed `mypy --strict`
  once a call passed `follow_symlinks=` (#217).
  Do: copy the real signature into the fake.
