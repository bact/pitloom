---
Created: 2026-09-19
Last-Modified: 2026-11-06
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `--allow-build` timeout: implementation record

See also: [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md)
(the build-and-read mechanism this bounds, and the roadmap item this
closes), [allow-build-termination.md](allow-build-termination.md)
(SIGTERM/SIGHUP/SIGBREAK handling around the build and its result),
[allow-build-validation.md](allow-build-validation.md)
(real-world `--allow-build` validation this change doesn't invalidate --
same success/fallback outcomes, now with a bound on how long either can
take).

Roadmap: 1.0 table row 5, previously tracked under "Medium-term" in
[roadmap.md](../design/roadmap.md).

## The bug this closes

`--allow-build`'s real PEP 517 build (`build_and_read_wheel()` in
`src/pitloom/core/_models_wheel_build_and_read.py`) ran **in-process**
via PyPA `build`'s `ProjectBuilder`/`DefaultIsolatedEnv` API, which has
no timeout anywhere in its call chain
(`pyproject_hooks.default_subprocess_runner` is a bare `check_call`;
`env.install()` is `build._ctx.run_subprocess`, also untimed). A hung
build -- a slow or broken network fetch for `build-system.requires`, a
build backend blocking on stdin, a misbehaving build script -- blocked
the whole `loom project`/`generate`/`embed-wheel` invocation
indefinitely, with no escape but Ctrl-C. A user who opted into
`--allow-build` opted into running third-party build-time code, not
into an unbounded hang.

## Decisions

- New `--build-timeout DURATION` flag/`BuildOptions` field/Action input. CLI and
  Action accept a duration string (bare integer = seconds, or
  `h`/`m`/`s` units); the library API stays plain `int` seconds --
  Python callers already have `90 * 60`, a string parser would be
  friction, not help. See "Duration grammar" below.
- Default when omitted: 1200 s (20 minutes). The flag may set any valid
  value above or below the default -- there's no "recommended minimum"
  enforced beyond the general 1 s floor.
- Valid range: 1..604800 (7 days). No "0 = unlimited" -- an unbounded
  hang is the exact bug being fixed; a caller who wants a very long
  bound passes a very large number instead.
- On timeout: kill the whole build process tree, log a `WARNING:`, and
  fall back to static discovery -- the existing "build-and-read
  returned `None`" path, already wired to the Hatchling-heuristic
  fallback. No change needed in the fallback logic itself; a timeout is
  just one more way `build_and_read_wheel()` can come back empty.
- No `[tool.pitloom]` config-file key, matching `--allow-build` itself
  -- only meaningful alongside `--allow-build`, and a scanned project's
  own `pyproject.toml` must never be able to steer its own scanner's
  security-relevant behaviour. CLI flag, `BuildOptions.timeout` (library
  API and `ConfigOverrides`), and GitHub Action input only.
- Two more intentional behaviour changes, bundled into this change
  because they use the same subprocess plumbing: the build's own
  stdout/stderr no longer leak onto Pitloom's stdout/stderr (previously
  inherited via `check_call`); they're captured to a log file instead,
  shown at `DEBUG:` on failure. The build's stdin is closed
  (equivalent of `/dev/null`), so a backend that waits on stdin gets
  EOF immediately instead of hanging -- this was actually a *second*,
  narrower instance of the same "unbounded hang" bug, worth closing in
  the same change rather than filing separately.
- SIGTERM/SIGHUP (and Windows Ctrl-Break, SIGBREAK) to Pitloom kill
  the build tree and remove the temp dirs before Pitloom exits by the
  same signal -- during the build and for as long as its extracted files
  are in use. See [allow-build-termination.md](allow-build-termination.md).

## Shared build-options mechanism (`BuildOptions`)

The first cut threaded `allow_build`/`no_build_isolation`/`build_timeout`
as three kwargs through every layer (`generate()` ->
`generate_project_sbom()` -> `get_wheel_files()`, `ConfigOverrides` ->
`_build_sbom_from_project_and_wheel()` -> `get_wheel_files()`). That
left three problems:

- The "flag given without `--allow-build`" warning lived only in the
  CLI (`warn_if_build_flags_without_allow_build()`), so a library
  caller passing `build_timeout=900` alone to a project directory got
  no warning at all -- a silent no-op.
- For a target that never reaches file discovery (sdist, wheel, model,
  `embed-wheel --sbom`, ...), the CLI's stray warning *and* the
  library's "no effect for this target" warning both fired: two lines
  for one flag.
- Timeout validation was repeated at four public entry points, and the
  "any flag given" check was hand-copied at four warning sites.

Fix: one frozen dataclass,
`pitloom.core.build_options.BuildOptions(allow, no_isolation, timeout)`,
is the only form every surface takes (`build_options=` on `generate()`,
`generate_project_sbom()`, `get_wheel_files()`; a
`ConfigOverrides.build_options` field; the CLI builds it once with
`build_options_from_args()`). Changing the public signature was allowed
(private alpha, no backward-compat need).

- **Validation happens once, in `__post_init__`**, so an invalid value
  can't reach any surface, whatever the target. It also requires
  `allow`/`no_isolation` to be real `bool`s: with the old kwargs,
  `allow_build="false"` was truthy and started a real build.
- **Warnings come from three settle methods on `BuildOptions`.**
  `settle(subject)` runs at every surface that *does* reach file
  discovery, as early as that surface can tell (before any
  project-metadata or lock-file read) -- CLI command handlers first,
  then again (idempotently, since a settled value has nothing left to
  warn about) inside `generate_project_sbom()`, `embed_wheel_sbom()`,
  and finally `get_wheel_files()` itself for a direct caller that
  skipped every earlier layer. `settle_not_applicable(subject, reason)`
  is its mirror for a target a caller already knows will *never* reach
  file discovery (an sdist archive, a non-project target, an
  externally-supplied `--sbom`): it warns with a target-specific
  *reason* and resets to defaults in one call. `settle_target(path)`
  picks between the two for a project-or-sdist path: an sdist archive
  (`pitloom.core.project.is_sdist_archive()`, an extension match on an
  existing file) gets the sdist reason, a directory gets `settle`, and
  anything else -- a missing path, or a file that is no archive --
  settles nothing, so the read fails with an ERROR alone. Shared by
  `loom project`, `loom generate` and
  `generate_project_sbom()`. Every run path reaches exactly one warning
  per given flag, so each ignored flag gets exactly one `WARNING: Build:
  <subject>: <flag> has no effect <reason>` line on every surface, and
  it's always the *first* thing that surface logs. One line per flag,
  not one combined line, so a grep for one flag finds it.
- `get_wheel_files()` is the right place for the stray check: the
  Hatchling hook and `_model_generator.py` call it with the default
  (no flags given), so they stay silent.

Side effects, accepted:

- An `embed-wheel` batch warns once, not once per wheel, whatever the
  project source (`--project-dir`, cwd, `--sbom`, or none):
  `EmbedFileCache.settle()` settles once per `with` block for each
  distinct (options, reason) pair and reuses that result for every later
  wheel -- so a library batch sharing a public `EmbedFileCache` gets the
  same. Keyed, not a single memo: a later call's own options (e.g.
  `allow=True` after a `--sbom` call) must never be replaced by the
  first call's settled result. `resolve()` raises `ValueError` when a
  later call asks for another project directory, file-scan settings or
  build options than its cached file list was resolved with, rather than
  silently returning a list that doesn't match. The CLI handler also settles up
  front, for warning order: `--sbom` and `--project-dir` before its own
  config read, an implicit cwd right after it (that read is what tells
  whether cwd is a project).
- A target path that doesn't exist settles nothing (`generate_project_sbom()`
  settles an existing file or directory only; `embed-wheel` settles an
  explicit `--project-dir` only when it is a directory), so `loom
  project`, `loom generate`, `loom embed-wheel --project-dir` and the
  library all fail it with the one `ERROR:` / `FileNotFoundError`, and
  no build-flag warning about a target that was never there.
- `generate()` now calls `configure_logging()` first; before, its own
  "no effect" lines could reach stderr without the `WARNING:` prefix.
- An sdist archive target used to show its build-flag warning after a
  metadata warning from a CLI handler's own pre-read (`loom project
  <sdist>`'s `_resolve_project_generation_settings()`, `loom generate
  <sdist>`'s non-fast-path config-only peek, since removed) or from
  `generate_project_sbom()`'s own metadata resolution for a direct
  library caller. Fixed: `BuildOptions.settle_not_applicable(subject,
  reason)` warns (if any flag was given) and resets to defaults in one
  call, mirroring `settle()`'s contract but for a target a caller
  already knows won't reach file discovery. Both CLI handlers call it
  -- with the shared `pitloom.core.build_options.SDIST_TARGET_REASON`
  string -- right after the cheap `is_sdist_archive()` check that tells
  them it's an sdist, before either resolves any metadata;
  `generate_project_sbom()` calls it too, so a direct library caller
  gets the same ordering with no CLI layer involved. Idempotent, so
  whichever layer settles first leaves nothing for a later layer to
  re-warn about.
- An env/wheel/model-file/Hugging-Face target under `loom generate`
  gets the same treatment: the handler classifies it with
  `target_resolves_to_project()` and calls `settle_not_applicable()`
  with the shared `NON_PROJECT_TARGET_REASON` (also used by
  `generate()`) before any metadata is read.

Test matrix: `tests/test_build_flag_warnings.py` crosses surface (CLI
`project`/`generate`/`embed-wheel` via real argv; library `generate()`/
`generate_project_sbom()`/`embed_wheel_sbom()`/`get_wheel_files()`) x
target kind (project dir, the CLI's default `.`, sdist, wheel, env,
model file, Hugging Face, and the `embed-wheel` project sources
`--project-dir`/cwd/`--sbom`/none, each with one wheel and with two
wheels in one batch -- CLI, or a library `EmbedFileCache`) x all 8
flag combinations. Each case asserts both the exact per-flag warning
count and reason and the build settings that reach file discovery (once
per run, default timeout 1200 s). Every surface x target cell runs
unless `_NOT_APPLICABLE` names it with a reason, and
`test_matrix_accounts_for_every_cell` fails on a cell that is neither,
so a new surface or target kind can't go untested by omission. The
Action's inputs have their own row: `test_build_input_matrix` in
`tests/scripts/action/test_generate_step.py` (mode x 8 input
combinations). `tests/cli/test_cli_build_timeout_process.py` runs
`loom project --allow-build --build-timeout` as a real process (tagged
stderr, exit code, nothing left in the temp dir).

Against the pre-`BuildOptions` code, 36 of the then 138 cases failed on
count alone (0 lines for library stray flags, 2 lines on the CLI for
non-project targets). The multi-wheel `--sbom`/no-project/cwd cells,
added later, caught a batch warning once per wheel -- first on the CLI
(13 cases), then, once the library batch cells replaced a wrong "CLI-only"
exclusion, for `EmbedFileCache` library batches (17 cases).

## Why subprocess, not a thread

A thread cannot be killed from outside in CPython -- there is no safe
way to abort a hung `ProjectBuilder.build()` call running on one.
PyPA `build`'s own `runner=` hook (the one customization point
`ProjectBuilder` exposes) only wraps the PEP 517 hook invocations
themselves; it does not cover `DefaultIsolatedEnv.install()`, which
shells out to pip via `build._ctx.run_subprocess` on its own,
untouched by any caller-supplied runner. There is no way to inject a
timeout into the existing in-process call graph without patching
`build`'s own internals. Moving the whole build (isolation setup
included) into one external process tree is the only mechanism that
can be reliably killed as a unit, on any platform, from outside.

## Why `python -m build`, and how it differs from before

`python -m build` is PyPA `build`'s own public CLI, run via
`[sys.executable, "-m", "build", ...]` so it always resolves against
the same interpreter Pitloom itself runs under. Verified against
`build` 1.6.1, behaviour is *close to* -- not identical to -- the old
in-process call:

- `--wheel` builds straight from source, the same as before (no sdist
  built first).
- The isolated path installs `build-system.requires` plus
  `get_requires_for_build("wheel")`, matching the old
  `_run_pep517_build_wheel` -- but the CLI additionally passes pip
  `--ignore-installed` and `config_settings={}`, neither of which the
  old code passed explicitly.
- `--outdir` is auto-created if missing (the old code assumed the
  caller had already made it).
- The installer defaults to pip either way.
- Exit code 1 means a build error; exit code 2 means a CLI argument
  error -- distinguishable, useful for the `BuildSubprocessError`
  message.
- `--no-isolation` **must** be paired with `--skip-dependency-check`,
  or the CLI refuses outright on missing dependencies -- a check the
  old bare `ProjectBuilder(project_dir).build()` call never performed
  at all. Both flags predate the `build>=1.2.2` floor already in place,
  so no dependency bump was needed.

## The 11 traps

Each is handled at a commented line in `_models_wheel_build_subprocess.py`
or `_models_wheel_build_kill.py`; read that comment before touching the
code.

1. **Missing `build`.** `find_spec("build")` is `None`, or a namespace
   spec (a bare `build/` dir on `sys.path`): `RuntimeError` naming
   `pitloom[build]` up front. Not `find_spec("build.__main__")`, which
   imports the package. An empty `sys.executable` is refused too.
2. **Path length.** Short work-dir names (`o/`, `t/`, `build.log`): a
   `multiprocessing` AF_UNIX socket under temp must fit 104 bytes on
   macOS; Windows `MAX_PATH` likewise.
3. **`cwd=work_dir`.** `-m` puts the cwd on `sys.path`; a project's own
   `build.py` would shadow PyPA `build` when run from its root.
4. **Environment.** `TMPDIR`/`TEMP`/`TMP` -> `work_dir/t`, so the isolated
   env and pip temp files die with the work dir (`ignore_cleanup_errors`,
   a leftover gets a `WARNING:`); `PYTHONUNBUFFERED`; `NO_COLOR` and no
   `FORCE_COLOR`, so no ANSI residue reaches the `WARNING:`.
5. **`stdin=DEVNULL`.** A backend reading stdin gets EOF, not a hang.
6. **Log file, never `PIPE`.** A full pipe deadlocks, and a grandchild
   holding it blocks `communicate()` after the kill -- which is also why
   `subprocess.run(timeout=)` (it calls `communicate()` on Windows) is out.
7. **Process group.** POSIX `start_new_session=True`, so `killpg()`
   reaches the tree; Windows no `creationflags` (`CREATE_NEW_PROCESS_GROUP`
   would disable Ctrl-C) and `taskkill /T`. Two explicit `Popen` calls:
   mypy rejects a `**kwargs` dict and needs the platform narrowing.
8. **Sliced wait (0.25 s).** Windows 3.10 doesn't interrupt a long wait
   on Ctrl-C, and each slice acts on a recorded signal. The kill runs in
   `except BaseException`, unconditionally: the child can exit at the
   deadline with grandchildren alive. After a normal exit
   `kill_leftover_descendants()` kills what the build left in its group
   (`INFO:`; `WARNING:` if not confirmed gone), reaping Pitloom's own
   zombies first. Windows can't reach such leftovers (no Job Object).
9. **`kill_process_tree()` never raises.** It runs while a timeout or
   interrupt propagates; a second Ctrl-C mid-way is held until every
   step (SIGKILL, `proc.kill()`, reap, group poll) has run, else an
   SIGTERM-ignoring descendant is orphaned and the unreaped `Popen` is a
   `ResourceWarning`. `proc.kill()` covers a child not leading its group.
   It returns whether the tree was confirmed gone, which picks the
   timeout `WARNING:`'s "terminated" vs "could not confirm". POSIX:
   SIGTERM, 3 s grace, SIGKILL, 2 s reap, poll `killpg(pgid, 0)` up to
   3 s -- about 8 s worst case, inside `docker stop`'s 10 s (the first
   version's 5 + 5 + 5 s did not fit). `EPERM` means "gone" on macOS only
   (zombies left; it can't be told from survivors owned by another
   user), a live unsignalable member on Linux. Each probe is preceded by
   `waitpid(-pgid, WNOHANG)`: as PID 1 or a subreaper, killed descendants
   are Pitloom's zombies and would keep the probe succeeding (tested on
   Linux CI only). Windows: full-path `taskkill.exe /F /T` (bandit
   B607), `proc.kill()`, wait -- 60 + 30 s worst case, untuned.
10. **Result.** Non-zero exit -> `BuildSubprocessError` with the log's
    last line; exit 0 needs exactly one `*.whl`.
11. **Bounded log tail.** Last 8 KiB only, UTF-8 `errors="replace"`; the
    `WARNING:` gets one cleaned line (~200 chars); the `DEBUG:` tail lines
    are prefixed, so a `::` line never reaches a runner as a workflow
    command.

## Rejected paths

- **Thread + `Thread.join(timeout=)`.** Can detect a timeout but cannot
  actually stop the thread -- the hung build keeps running regardless,
  defeating the point.
- **A custom `runner=` passed to `ProjectBuilder`.** Doesn't cover
  `DefaultIsolatedEnv.install()`'s own subprocess calls (see "Why
  subprocess, not a thread" above) -- only half the problem.
- **`subprocess.run(cmd, timeout=...)`.** Convenient, but its
  post-kill `communicate()` call on Windows re-opens the pipe-deadlock
  hazard "The 11 traps" step 6 exists to avoid; also gives up the
  slice-and-poll wait loop step 8 needs for Ctrl-C responsiveness.
- **A `psutil` dependency for tree-walking/killing.** `os.killpg()`
  (POSIX) and `taskkill /T` (Windows) each already do this natively
  without adding a new third-party dependency for one call site.
- **`CREATE_NEW_PROCESS_GROUP` on Windows.** Would disable Ctrl-C
  delivery to the child process for no benefit, since `taskkill /T`
  doesn't need a separate process group to find the tree.
- **Signal-handling alternatives** (a handler raising wherever the
  signal lands, one installed unconditionally, `SystemExit` as the
  primary exit, ...) are in
  [allow-build-termination.md](allow-build-termination.md#rejected-paths).
- **A `[tool.pitloom]` config key for the timeout.** Rejected for the
  same reason `--allow-build` itself has none -- see "Decisions" above.
- **`0` meaning "unlimited".** Rejected -- see "Decisions" above.
- **An integer-only flag (seconds only, no unit suffixes).** Considered
  for simplicity, but a plain "how long, in seconds, should I wait" is
  an awkward thing for a human (or an agent talking to one) to reason
  about past a couple of minutes; `1h30m` reads far better than `5400`
  in a warning message or a recipe a user copy-pastes.
- **The full Go `time.ParseDuration` grammar**, including `ms`/`us`/`ns`
  and fractional values (`1.5h`). Rejected: sub-second precision is
  meaningless for a build that takes seconds to minutes at best, and a
  bare `m` next to an allowed `ms` is a one-character typo trap
  (`90m` vs `90ms` differ by three orders of magnitude) not worth
  the surface area for a value this coarse-grained.
- **A `str` duration in the library API.** A Python caller already has
  the natural, unambiguous `90 * 60` at hand; parsing a string there
  would add failure modes (the same rejected-grammar edge cases) with
  no expressiveness gained over a plain `int`.

## Duration grammar compatibility

`parse_build_timeout()`'s grammar (bare integer = seconds, or `h`/`m`/`s`
units largest-first, each at most once, no decimals/whitespace) is a
strict subset of the below -- every string Pitloom accepts means the
same thing in each of these tools; nothing Pitloom accepts is
interpreted differently elsewhere.

| Form | Go `time.ParseDuration` / Prometheus | GNU `timeout` | pip (`--timeout`) | Pitloom |
| :--- | :--- | :--- | :--- | :--- |
| Bare integer (`900`) | Not accepted (needs a unit) | Seconds | Seconds | Seconds |
| `900s` | Seconds | Seconds (`s` suffix) | Not accepted | Seconds |
| `15m` | Minutes | Minutes (`m` suffix) | Not accepted | Minutes |
| `1h30m` | 1h30m | Not accepted (single unit only) | Not accepted | 1h30m |
| `1.5h` | Accepted (fractional) | Not accepted | Not accepted | **Rejected** |
| `500ms` | Accepted | Not accepted | Not accepted | **Rejected** |
| `1d` | Not accepted (no day unit) | Accepted (`d` suffix) | Not accepted | **Rejected** |

Pitloom deliberately sits at the intersection: it never accepts a form
that Go/Prometheus would read as something numerically different, and
it never invents a unit (`d`) that Go/Prometheus don't have.

## Limitations

- **Signals Pitloom cannot handle** (SIGKILL, a host application's own
  handler, Windows forced termination, ...): see
  [allow-build-termination.md](allow-build-termination.md#limitations).
- **Windows descendants of an exited child.** `taskkill /T` walks by
  parent PID; see traps 8 and 9.
- **Encoding.** Python descendants get `PYTHONIOENCODING=utf-8`, so
  the log is written in the encoding `_read_log_tail()` decodes (on a
  Windows cp1252 locale a redirected stdout would otherwise not be
  UTF-8). A non-Python tool's output is still in its own encoding;
  undecodable bytes become U+FFFD. Pitloom's own `WARNING:` wording is
  ASCII; a project path or a build-log line in it may not be, and
  `sys.stderr`'s `backslashreplace` error handler keeps that from
  raising on a cp1252 console.
- **`setsid()` escape.** A build backend that calls `setsid()` on
  itself detaches from the process group `os.killpg()` targets, and
  survives the kill. No known real-world backend does this; documented
  as a residual risk, not exploitable by an *accidental* hang (only a
  backend deliberately trying to survive termination).
