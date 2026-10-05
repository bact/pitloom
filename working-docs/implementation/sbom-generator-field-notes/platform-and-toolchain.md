---
Created: 2026-10-02
Last-Modified: 2026-10-05
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

- **`Path.exists()` changed its promise in Python 3.14.** Under a
  `chmod 000` directory it raises `PermissionError` on 3.10-3.13 and
  returns `False` on 3.14, so a denied file would vanish from the SBOM
  file scan there with no warning (#217, #226, #244; detail in the lessons
  doc, 3.4).
  Do: use `os.path.isfile` where "never raises" is meant; where a denied
  path must be reported, `stat()` it and classify the errno yourself.
- **A Windows "not found" carries two codes.** A real Windows
  `FileNotFoundError` has `errno=ENOENT` and `winerror` 2 or 3; CPython
  ignores `errno in _IGNORED_ERRNOS or winerror in _IGNORED_WINERRORS`
  (3.11-3.13; spelt `_IGNORED_ERROS` in 3.10).
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
  `skipif(os.geteuid() != 0, ...)` raises `AttributeError` while Windows
  collects the module, so the skip never applies (#226).
  Do: keep POSIX-only names out of decorator, default and `parametrize`
  arguments.
- **Shell scripts meet three different shells.** Native Windows Python
  ends lines with CR, which Git Bash's `$(...)` keeps; Git Bash has no
  `/dev/stderr`; macOS bash 3.2 has no `readarray` and is quadratic on
  `${x//pat/}` (#224).
  Do: strip CR from every captured value and test on all three.

- **`Path.resolve()` on a symlink loop differs by version.** On 3.10.18,
  3.11.12 and 3.12.9 it raises `RuntimeError: Symlink loop` in both strict
  and non-strict mode; on 3.13 and 3.14 non-strict returns a path silently
  and `strict=True` raises `OSError` (errno 62, ELOOP). A bare
  `except (ValueError, OSError)` misses it on 3.10 to 3.12 (PR not
  identified).
  Do: catch `RuntimeError` alongside `OSError` around `resolve()` until
  3.12 is dropped.
- **`Path("sub/../x").resolve()` collapses `..` when `sub` is absent.**
  With `x.gguf` present and `sub` missing, `resolve()` names an existing
  file, but `open("sub/../x.gguf")` raises `FileNotFoundError`, so a
  command that checks the resolved path and opens the typed one fails
  (3.10 to 3.14; PR not identified).
  Do: check and open the same spelling of a path.
- **A NUL in a path is `ValueError`, not `OSError`.** For `"a\0b.txt"`,
  `os.stat` and `open` raise `ValueError` (3.10: `embedded null byte`;
  3.13, 3.14: `stat: embedded null character in path`), while
  `Path.exists()`, `Path.is_file()` and `os.path.isfile()` return False.
  A `setup.cfg` `file:` directive is user text, so the probe that tells
  "missing" (silent, as setuptools skips it) from "unreadable" (one
  `WARNING:`) catches `ValueError` as missing beside `OSError`
  (`_read_listed_file()`, #276).
  Do: catch `ValueError` next to `OSError` around any stat or open of a
  path taken from file content.
- **`os.path.normcase` does nothing on macOS.** `normcase("/Tmp/ABC")`
  returns `/Tmp/ABC` on 3.10 and 3.14 even on a case-insensitive volume,
  so a "same path" helper built on `normcase(realpath(...))` misses case
  variants; in the registry v3 review it would have let an in-tree
  registry keep rewriting itself. Complements the `(st_dev, st_ino)` item
  above (#257).
  Do: compare file identity with `os.path.samefile`, not `normcase`.
- **An unclosed `HTTPError` warns on 3.14 only.** Collecting one emits
  `ResourceWarning` (3.11 to 3.13: none; 3.14.3: one), which under
  `filterwarnings=error` fails whichever test is running at garbage
  collection. `files.pythonhosted.org` answers a bare probe with 404, so
  real runs hit it (#238 tests, #242 source).
  Do: `close()` every `HTTPError` you catch, helpers in tests included.
- **`rmtree(ignore_errors=True)` still raises `RecursionError` on 3.10
  and 3.11.** A 1,200-deep tree defeats it and
  `TemporaryDirectory.cleanup()` at the default limit of 1000; 3.12 to
  3.14 remove it cleanly. The build backend decides the depth, so a
  successful build looked like a failure and left two temp dirs behind
  (#226).
  Do: wrap every temp-tree removal in `except Exception`, then warn if
  anything is left.
- **Temp files are created owner-only.** `NamedTemporaryFile` is `0o600`
  and `mkdtemp` `0o700`, so rewriting a wheel via a temp file and
  `os.replace` loses the original mode unless you restore it; on NTFS
  only the read-only bit survives (#220).
  Do: capture `st_mode` before the rewrite and restore it; test with a
  read-only file on Windows.

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
- **pip's `--no-build-isolation` applies to the whole command.** A
  self-referential install (Pitloom's wheel is built with Pitloom's own
  hook, which must not be fetched stale from PyPI) needs it, but in the
  same `pip install` as `--group` packages it turns isolation off for all
  of them, a risk for any that builds from source (`atheris` has no wheel
  below Python 3.12). `pip` has no per-package switch (#222).
  Do: give the local install its own `pip install` call.
- **Tool output echoed to a CI log can run workflow commands.** A line
  starting `::` is executed by the runner. Fence the echo with
  `::stop-commands::<random token>`; since the runner does not order
  stdout against stderr, the fence, the echo and later annotations must
  share one stream (`exec 1>&2`). Annotation text needs `%25`, `%0A`,
  `%0D` escaping, and `while read` drops a last line without `\n` unless
  it also tests `[ -n "${line}" ]` (#224).
  Do: treat every tool's output as untrusted input to the log.
- **CI runner hazards.** GitHub Actions expands `${{ }}` even in a `run:`
  shell comment, so one explanatory comment broke 10 workflows (`An
  expression was expected`); `mpalmer/action-validator` splits `patterns`
  per line, so a comma-joined value validated zero files; and
  `actions/upload-artifact`'s `if-no-files-found` fires only when no line
  of a multi-line `path` matches, so a missing SBOM beside a present wheel
  passed (#222).
  Do: write "a GitHub expression splice" in comments, never the syntax;
  check each expected artefact in its own step.
- **A validator's exit code may not mean what it says.** `python -m
  spdx3_validate` (0.0.7) exits 0 on invalid input because its `__main__`
  drops `main()`'s return value; it also downloads its JSON Schema and
  SHACL model from spdx.org on every run, so a test calling it is a
  network test even though the in-process socket block never sees it
  (#238).
  Do: call the console entry's `main()` and use its code; mark subprocess
  network use explicitly.

- **A backend below the feature floor drops hook data silently.**
  Hatchling before 1.29.0 ignores a hook's `build_data["sbom_files"]`: the
  wheel builds with no SBOM and no warning. Under PEP 440,
  `1.29.0.dev1 < 1.29.0` and `1.29.0rc1 < 1.29.0`, so compare
  `Version.release`, or a pre-release that has the feature is refused
  (#223, floor leg in CI).
  Do: fail loudly when the backend is too old; compare release segments
  for feature gates.
- **Backends hand you OS-native paths.** Hatchling's
  `recurse_included_files()` joins with `os.path.join`, giving `\` on
  Windows, and `get_distribution_path()` does a plain string replace.
  Pitloom runs every backend's `distribution_path` through
  `to_posix_distribution_path()`
  ([hatchling-build-hook.md](../hatchling-build-hook.md)).
  Do: POSIX-normalise every path a backend gives you before it reaches
  `software_File.name`.
- **A fresh venv on Python 3.12 or later has no setuptools.** Any
  `--no-build-isolation` install that falls back to an sdist then has no
  build backend (setuptools importable on 3.11.12, not on 3.12.9 or
  3.14.3). In CI this was `fasttext==0.9.3` on 3.14, which also needs
  `pybind11` it never declares (#222).
  Do: pre-install the backends sdist builds need, or keep isolation on.
- **A project built with its own hook needs a bootstrap step.**
  `build-system.requires = ["hatchling>=1.29.0", "pitloom"]` pulled
  PyPI's stale hook into isolation, and it crashed on the new Hatchling.
  CI installs with `HATCH_BUILD_NO_HOOKS=1 pip install
  --no-build-isolation` on that one step only (#222).
  Do: switch the self-hook off on the bootstrap install only.
- **When you swap in a fork, key tool config on the import name.**
  `fasttext` 0.9.3 ships no Windows wheel and fails from source, so
  Pitloom moved to `fasttext-community>=0.11.8`, which keeps
  `import fasttext`; the mypy and pyrefly overrides needed no change
  (#220, #222).
  Do: key type-checker overrides on the module name, not the
  distribution name.
- **One build budget covers the whole process tree.** A real `uv_build`
  chain (`loom`, `python -m build`, `pip`, `uv-build`) taking 20.2 s
  returned in 6.17 s with a 6 s limit and 7.21 s with 7 s (default
  1200 s). A descendant calling `setsid()` escapes `killpg`, unreported.
  On Windows CPython ignores `start_new_session` and `taskkill /T` walks
  by parent PID, so orphans are unreachable; on macOS `killpg` reports
  `EPERM` once only zombies remain (#226,
  [allow-build-termination.md](../allow-build-termination.md)).
  Do: one deadline, kill by process group, document the escape routes.
- **Give a sandboxed build its own temp root and encoding.** The child
  gets `TMPDIR`, `TEMP` and `TMP` inside the work dir, so a killed build
  leaves the system temp dir empty, and `PYTHONIOENCODING=utf-8`
  because Windows would use cp1252. After a run killed mid `pip install`
  the next run gave a bit-for-bit identical SBOM (#226).
  Do: redirect the child's temp variables and fix its encoding.
- **Probe the interpreter before replacing it.** PEP 668's marker is
  `EXTERNALLY-MANAGED` in `sysconfig.get_path("stdlib")`, and
  `PIP_BREAK_SYSTEM_PACKAGES` overrides it. Check that both `purelib` and
  `scripts` are writable. `setup-python` changes `PATH` for every later
  step, so the action keeps the workflow's own Python when it is usable
  (#224).
  Do: use the existing interpreter when the probe passes.
- **Linter versions differ between local and CI.** pylint 4.1 stopped
  honouring a comment-line `# pylint: disable=` before `except`: 4.0.8
  rated a file 10.00 and 4.1.1 reported `W0718`. CI had 4.1.1 while the
  local `.venv` had 4.0.8, so local runs passed; 43 comments changed to
  `disable-next` (#235).
  Do: use `disable-next`, and run the linter version CI installs.
- **A search path with both `.` and `src` gives a module two identities.**
  pyrefly resolved `src/pitloom/...` as `src.pitloom.id_registry._registry`
  and as `pitloom.id_registry._registry`, so a `TYPE_CHECKING` reference
  failed with "`Self@src.pitloom...` is not assignable to
  `pitloom...`" while mypy and pyright were clean (#234).
  Do: put the package root before the repository root, or list one only.
- **`uv run --with X` mutates the project; `uvx --from X` does not.**
  Inside a project, `uv run --with packaging` created `.venv/` and
  `uv.lock` and built the project (uv 0.10.4); `uvx --from packaging`
  left only `pyproject.toml` and `src`. A read-only "check with the
  tool's own Python" recipe in a skill must not alter the checkout (#235).
  Do: run helper tools with `uvx` or `pipx run`, never `uv run --with`.

## 3. Test harness

More in [testing-traps.md](testing-traps.md).

- **A capture helper can erase the bug under test.**
  `subprocess.run(text=True)` turns CRLF into LF, so every "stray CR is
  stripped" assertion passed with the stripping code deleted. Found by
  18 one-line mutations of the action scripts, not by review (#224).
  Do: decode bytes yourself; mutation-test shell and CI changes.
- **Monkeypatching a stdlib module patches every thread.** Patching
  `module.time.sleep` also recorded a stray thread's sleeps (red under
  xdist only); import the name (`from time import sleep`) and patch that
  (#259).
  Do: patch the importing module's own name, or inject the callable.
- **A logging handler outlives the test's stderr.** See the lessons doc,
  3.4 (#263).
  Do: restore logger handlers, `warnings` filters and signal handlers
  after every test.
- **Mutation testing can lie twice.** An equivalent mutant cannot be
  killed, and an assertion on a lazily installed side effect observes
  nothing (#226).
  Do: reinstate the exact pre-fix code, character for character.
