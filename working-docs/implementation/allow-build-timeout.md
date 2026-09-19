---
Created: 2026-09-19
Last-Modified: 2026-09-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `--allow-build` timeout: implementation record

See also: [non-hatchling-file-discovery.md](../design/non-hatchling-file-discovery.md)
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
- **Warnings come from three methods, all on `BuildOptions`.**
  `warn_no_effect(subject, reason)` logs the line itself, for each
  given flag; `settle(subject)` runs at every surface that *does*
  reach file discovery, as early as that surface can tell (a project
  directory, confirmed by a cheap `is_file()`/`is_dir()` check, before
  any project-metadata or lock-file read) -- CLI command handlers via
  `build_options_from_args(args, subject)`, then again (idempotently,
  since a settled value has nothing left to warn about) inside
  `generate_project_sbom()`, `embed_wheel_sbom()`, and finally
  `get_wheel_files()` itself for a direct caller that skipped every
  earlier layer. `settle_not_applicable(subject, reason)` is `settle`'s
  mirror for a target a caller already knows will *never* reach file
  discovery (an sdist archive, a non-project target, an
  externally-supplied `--sbom`): it calls `warn_no_effect()` with a
  target-specific *reason* and resets to defaults in one call, so a
  caller that determines the target's fate cheaply (an `is_file()`
  check, a string classification) can warn immediately, before any
  metadata read of its own, rather than deferring to a later layer.
  Every run path reaches exactly one warning per given flag, so each
  ignored flag gets exactly one
  `WARNING: Build: <subject>: <flag> has no effect <reason>` line on
  every surface, and it's always the *first* thing that surface logs,
  never buried after a later metadata warning. One line per flag, not
  one combined line, so a grep for one flag finds it.
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
- `generate()` now calls `configure_logging()` first; before, its own
  "no effect" lines could reach stderr without the `WARNING:` prefix.
- An sdist archive target used to show its build-flag warning after a
  metadata warning from a CLI handler's own pre-read (`loom project
  <sdist>`'s `_resolve_project_generation_settings()`, `loom generate
  <sdist>`'s non-fast-path `_resolve_common_options()` peek) or from
  `generate_project_sbom()`'s own metadata resolution for a direct
  library caller. Fixed: `BuildOptions.settle_not_applicable(subject,
  reason)` warns (if any flag was given) and resets to defaults in one
  call, mirroring `settle()`'s contract but for a target a caller
  already knows won't reach file discovery. Both CLI handlers call it
  -- with the shared `pitloom.core.build_options.SDIST_TARGET_REASON`
  string -- right after the cheap `is_file()` check that tells them
  it's an sdist, before either resolves any metadata;
  `generate_project_sbom()` calls it too, so a direct library caller
  gets the same ordering with no CLI layer involved. Idempotent, so
  whichever layer settles first leaves nothing for a later layer to
  re-warn about.
- An env/wheel/model-file/Hugging-Face target under `loom generate`
  gets the same treatment: the handler classifies it with
  `target_resolves_to_project()` and calls `settle_not_applicable()`
  with the shared `NON_PROJECT_TARGET_REASON` (also used by
  `generate()`) before `_resolve_common_options()`'s peek.

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
combinations).

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

Each is handled at a commented line in
`src/pitloom/core/_models_wheel_build_subprocess.py` or
`_models_wheel_build_kill.py` (the comments are not numbered) -- read
the comment at the line, not just this list, before touching that code.

1. **Missing `build`.** `importlib.util.find_spec("build")` returning
   `None` -- or a namespace-package spec (`origin is None`), which is
   just a bare `build/` directory on `sys.path`, e.g. setuptools' output
   dir in the cwd under `python -m pitloom` -- raises `RuntimeError` up
   front, naming the `pitloom[build]` extra, rather than letting a
   cryptic `ModuleNotFoundError` surface from deep inside the
   subprocess's own stderr. (The child runs with `cwd=work_dir`, trap 3,
   so it would never see that directory.) `find_spec("build.__main__")`
   was not used: it imports the parent package into Pitloom's own
   process. Also guards against an empty/`None` `sys.executable`
   (embedded/frozen interpreters).
2. **Path length.** The work directory's layout keeps names short
   (`o/` for outdir, `t/` for the child's own temp, `build.log`) --
   observed in practice: a backend using `multiprocessing` creates an
   AF_UNIX socket path under temp
   (`.../T/plb-XXXXXXXX/t/pymp-XXXXXXXX/listener-XXXXXXXX`) and POSIX's
   108-byte-ish `sockaddr_un` limit (104 usable on macOS) is easy to
   blow past with a verbose prefix. Windows `MAX_PATH` is the same
   class of hazard.
3. **`cwd=work_dir`, never `project_dir` or the inherited cwd.** `-m`
   prepends the current directory to `sys.path`; a scanned project
   that happens to ship its own `build.py` or `build/__init__.py`
   (common enough as a repo-local build-helper module name) would
   shadow PyPA `build` itself if run from the project root -- exactly
   where `loom project .` is normally invoked from.
4. **Environment redirect.** `TMPDIR`/`TEMP`/`TMP` all point at
   `work_dir/"t"`, so `DefaultIsolatedEnv`'s `build-env-*` venv and
   pip's own temp files land inside the directory this code already
   owns and cleans up -- a build this code kills leaves nothing behind
   in the system temp directory. The work dir is a
   `TemporaryDirectory(ignore_cleanup_errors=True)` (on Windows a
   just-killed process may hold a handle briefly); if it still exists
   afterwards, a single `WARNING: Build: could not fully remove
   temporary directory <path>` names it instead of leaving it silently. `PYTHONUNBUFFERED=1` keeps the captured log
   from buffering indefinitely. `NO_COLOR=1` plus popping
   `FORCE_COLOR` suppresses the CLI's own ANSI-coloured error line
   (`build/__main__.py`) -- otherwise escape-code residue could end up
   inside the one-line `WARNING:` this code emits on failure.
5. **`stdin=subprocess.DEVNULL`.** Closes the second, narrower
   unbounded-hang case noted above.
6. **Output to a log file, never `PIPE`.** A pipe can fill and
   deadlock the parent; a surviving grandchild holding the write end
   open would make `communicate()` block even after the parent process
   is killed. This is also why `subprocess.run(timeout=)` is not used
   here at all -- on Windows it calls `communicate()` internally after
   killing the process, reintroducing the exact hang being avoided.
7. **Platform-specific process-group setup.** POSIX:
   `start_new_session=True` so the child's pgid equals its pid, letting
   `os.killpg()` reach the whole tree. Windows: no special
   `creationflags` -- `CREATE_NEW_PROCESS_GROUP` would disable Ctrl-C
   delivery to the child and isn't needed, since `taskkill /T` walks
   the process tree by parent PID instead. Written as two explicit
   `Popen(...)` calls under `if sys.platform == "win32":` rather than
   one call with a conditional kwargs dict, because mypy's `Popen`
   overloads reject an unpacked `**kwargs` dict, and
   `os.killpg`/`signal.SIGKILL` are POSIX-only in typeshed and need the
   same platform narrowing to type-check.
8. **Sliced wait loop, not one blocking `proc.wait(timeout=...)`.** On
   Windows, CPython 3.10's `WaitForSingleObject`-based wait is not
   interrupted by Ctrl-C -- a single long wait could hang up to the
   full timeout even after the user hits Ctrl-C. Polling in 0.25 s
   slices keeps Ctrl-C responsive on every platform, and is where a
   recorded SIGTERM/SIGHUP/SIGBREAK is acted on. The kill happens
   in a `except BaseException:` handler around the whole loop --
   unconditionally, not gated on "is the process still running" --
   because the *direct* child can exit right at the deadline while its
   own grandchildren are still alive; and because the new session means
   the terminal's own Ctrl-C signal no longer reaches the child at all,
   so the parent is the only thing that can kill it either way. After a
   *normal* exit, the group is sent SIGKILL too
   (`kill_leftover_descendants()`, POSIX only; `ESRCH` -- nothing left --
   is the normal case), then polled until gone: a backend's background
   child would otherwise outlive the build, still in the group, and
   keep writing into the work dir while it is removed. Killing one is a
   side effect worth an `INFO:` line (e.g. a compiler-cache server the
   backend started without `setsid()`); one that can't be confirmed gone
   gets a `WARNING:`. Own zombies are reaped first (PID 1, subreaper) so
   they don't count as leftovers. On Windows
   nothing can reach such a leftover (`taskkill /T` needs a live parent
   PID; a Job Object would, but is not used).
9. **`kill_process_tree()` (`_models_wheel_build_kill.py`) raises
   nothing of its own.** It runs while a
   `BuildTimeoutError` or `KeyboardInterrupt` is already propagating;
   a new exception there would mask the original one and leave an
   un-waited `Popen` behind, which surfaces as a `ResourceWarning` --
   and this repository's `filterwarnings = ["error"]` turns that into
   a hard test failure, not a log line. Every OS call inside it is
   wrapped in `try/except (OSError, subprocess.SubprocessError)`. A
   `BaseException` arriving mid-way -- a second Ctrl-C during the
   SIGTERM grace, or during `taskkill` -- is held; every later step
   (SIGKILL, `proc.kill()`, the reap, the group poll) still runs, each
   guarded the same way, and only then is the first one re-raised: the
   first version let it abort before SIGKILL, orphaning any
   SIGTERM-ignoring descendant. An interrupted reap resumes within its
   time bound: `with Popen` waits only 0.25 s on `KeyboardInterrupt`,
   and an unreaped `Popen` is a `ResourceWarning`. `proc.kill()` of the
   direct child covers a child not leading its group (no own session):
   `killpg()` misses it and `with Popen`'s unbounded wait hangs --
   mutation testing hung the whole suite that way. It returns whether the tree was
   confirmed gone (POSIX: the group probe raised; Windows: `taskkill`
   exited 0), carried as `BuildTimeoutError.tree_terminated`, so the
   timeout `WARNING:` says "build process tree terminated" only when
   that is known, and "could not confirm the build process tree
   terminated" otherwise.
   POSIX: SIGTERM, wait up to 3s, unconditional SIGKILL, reap the
   direct child (up to 2s), then poll `os.killpg(pgid, 0)` every 0.1s
   (up to 3s) until it raises -- `ProcessLookupError` normally, but
   macOS can report `EPERM` once only zombies remain. `EPERM` counts as
   gone on macOS only: on Linux it means a live member this process may
   not signal (e.g. a setuid `sudo` child), so the timeout `WARNING:`
   then says "could not confirm". macOS also reports `EPERM` when every
   live member belongs to another user, indistinguishable from the
   zombie case -- such a survivor goes unreported there (accepted). The poll keeps temp-directory cleanup
   from racing still-dying grandchildren.
   Order matters on Linux: a zombie stays in its process group until
   reaped, so the direct child is reaped before the first probe, and
   each probe is preceded by `waitpid(-pgid, WNOHANG)`. That second
   reap matters only when Pitloom is PID 1 in a container (no
   `--init`) or a child subreaper: killed descendants are then
   reparented to Pitloom rather than to an init that reaps them, and
   would otherwise keep the probe succeeding until it gives up
   ("could not confirm"). `waitpid(-pgid)` touches only that group,
   never a host application's other children. Verified only by a
   Linux-only test using `PR_SET_CHILD_SUBREAPER` (CI), not locally. Windows: `taskkill.exe /F /T /PID <pid>`
   via the full `%SystemRoot%\System32\taskkill.exe` path (satisfies
   bandit B607's "no bare command name" rule), then `proc.kill()` and
   a final `wait()`. If the very last wait still times out, it's
   logged at `DEBUG:` and left to the `with Popen(...)` context
   manager's own exit to wait -- acceptable as a last resort, not
   silently swallowed. `taskkill /T` finds descendants by parent PID,
   so once the direct child has exited, its orphaned descendants are
   probably unreachable; unverified on a real Windows run, so the code
   comment claims no guarantee.

   Worst-case delay past the deadline (a signal: plus one 0.25 s wait
   slice): POSIX 3 s SIGTERM grace + 2 s reap after SIGKILL + 3 s group
   poll = about 8 s, normally well under 1 s (the grace ends as soon as the direct
   child exits, the other two once the processes are gone). The first
   version used 5 + 5 + 5 s; cut so the whole kill fits inside
   `docker stop`'s default 10 s between SIGTERM and SIGKILL (and a
   GitHub Actions cancellation's gaps between SIGINT, SIGTERM and
   SIGKILL), guarded by a test. After SIGKILL the last two bounds only
   matter for a process stuck in the kernel. Windows: 60 s `taskkill`
   timeout + 30 s final wait = about 90 s, normally a second or two;
   not tuned, as no Windows signal path needs it to be shorter.
10. **Result classification after a normal return.** Non-zero exit
    becomes `BuildSubprocessError` carrying the log's last non-empty
    line. A zero exit is only accepted if `out.glob("*.whl")` finds
    **exactly** one wheel -- zero or more than one is also a
    `BuildSubprocessError`, since either means something about the
    build's own output contract wasn't what was expected.
11. **Log tail extraction stays bounded.** `_read_log_tail()` seeks
    from the end and reads at most the last 8 KiB, never the whole
    file -- the "resource efficiency" rule in CLAUDE.md applies to a
    build log exactly as much as to any other large artifact. Decoded
    as UTF-8 with `errors="replace"`. The `WARNING:` line gets only the
    single last non-empty line, control characters stripped, capped at
    roughly 200 characters, matching the CLI-output convention of one
    tagged line with no untagged continuation. On failure or timeout,
    every tail line is also logged at `DEBUG:` -- individually prefixed
    so a log line that happens to start with `::` can never be
    misread as a GitHub Actions workflow command by a runner that later
    echoes captured output.

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
