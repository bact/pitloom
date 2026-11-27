---
Created: 2026-09-19
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Building a project to discover its file list (`--allow-build`)

See also: [Command line](cli.md) for every other subcommand and flag --
this page covers `--allow-build`/`--no-build-isolation`/`--build-timeout`
only, split out because of its own size.

Available on `project`/`generate`/`embed-wheel` only (not `wheel`/`enrich`/
`env`/`model`, which never rescan a project directory), and not for a project
fetched from a Git URL: a downloaded repository is untrusted, so its build
backend is never run and the flag is reported as having no effect.

By default, Pitloom's file discovery is a **static read** of a project's
build-backend config (Hatchling, setuptools, Poetry, PDM, Flit) -- it
never executes the project's own build. For a backend with no static
introspection at all (currently: uv_build), or when a supported
backend's own static discovery fails on a given project, Pitloom falls
back to a Hatchling-based heuristic and prints a `WARNING:` -- the file
list may be inaccurate in that case.

`--allow-build` opts into a more accurate but heavier alternative:
Pitloom actually invokes the project's own [PEP
517](https://peps.python.org/pep-0517/) build backend (in a subprocess,
via [`build`](https://pypi.org/project/build/)) and reads the resulting
wheel's real file list. This is a **security-relevant** decision --
it executes third-party build-time code from the project being scanned
-- so:

- It's off by default and must be passed explicitly every time; like
  `--trust-model-files` and `--allow-signed-wheel`, it has **no**
  `[tool.pitloom]` config-file equivalent. A target project's own
  `pyproject.toml` must never be able to silently opt itself into code
  execution for whoever scans it.
- Only enable it for a project whose build script you trust.
- Requires the optional `pitloom[build]` extra (`pip install
  pitloom[build]`).
- By default, the build runs in an isolated temporary environment
  (installs the project's own `[build-system] requires`, may hit the
  network -- reuses pip's normal cache across runs). `--no-build-isolation`
  skips this and uses the current environment's already-installed
  backend instead (faster, no network); it has no effect without
  `--allow-build` (logs a `WARNING:` if passed alone).
- `--build-timeout DURATION` caps how long the build may run --
  see "Timing out a build" below.
- The build's own stdout/stderr are captured to a log file rather than
  leaking onto Pitloom's own stdout/stderr. A failed build's last output
  line is part of its `WARNING:` (`[build-failed]`, a credential in it
  masked); on failure or timeout, `loom --debug`
  also shows the end of the build output (up to 8 KiB) at `DEBUG:`. The
  build's stdin is closed (`/dev/null`-equivalent), so a backend that
  waits on stdin gets EOF instead of hanging.
- On any failure (network unavailable, backend not installed, build
  script error, timeout), Pitloom falls back to the same static file
  discovery used without the flag -- the build backend's own (setuptools
  for a project declaring none), the Hatchling heuristic only when that
  fails; where static discovery is unsupported (e.g. a `setup.py` passing
  `packages` itself, with no `[project]` table), the SBOM lists no files,
  with a `WARNING:`. `--allow-build`'s worst case is never worse than
  leaving it off.
- It changes the file list, so which AI models are found can differ from a
  run without it; see [Settings that change the
  SBOM](ai-model-scan-limits.md#settings-that-change-the-sbom).
- On `generate`, all three flags parse for every target (`generate`
  auto-detects env/wheel/model-file/Hugging-Face/project targets from
  one shared parser) but only take effect when the target resolves to a
  project *directory* -- for any other target, including an sdist
  archive (whose file list comes from the archive's own listing, not a
  build), they're a no-op and Pitloom prints a `WARNING:` saying so.
  The same applies to `embed-wheel` without `--project-dir` (for the
  library, no `project_dir`) -- the current directory is never used as
  the project -- or when `--sbom` supplies an already-generated SBOM to
  embed verbatim.

```bash
loom project . --allow-build -o sbom.json
loom project . --allow-build --no-build-isolation -o sbom.json
loom project . --allow-build --build-timeout 15m -o sbom.json
```

## When static file discovery falls short

Without `--allow-build`, a project's file list is read from its static
configuration. When that cannot give an exact list, Pitloom says so on stderr
in a line that ends with its `[code]`, and the SBOM is written with a
Hatchling-style heuristic list or, where the project has no `[project]`
table, without one. Each code, its causes and what to do about it are on
[File discovery](message-codes-file-discovery.md). One line of each, with a
value in place of each `<name>`:

| Code | A line of it |
| :--- | :--- |
| `file-discovery-unusable` | `WARNING: DIR=<dir>: file discovery failed; Hatchling heuristic used, file list may be inaccurate [file-discovery-unusable]` |
| `file-discovery-needs-build` | `WARNING: DIR=<dir>: file discovery not backend-aware for build-backend <backend>; Hatchling heuristic used, file list may be inaccurate [file-discovery-needs-build]` |
| `file-discovery-conflict` | `WARNING: DIR=<dir>: two files map to wheel path <entry>; kept <kept>, dropped <dropped> [file-discovery-conflict]` |

A `needs-build` line is the one `--allow-build` answers: a real build lists
the files exactly.

## What Pitloom says about a build

Each build is announced, and each outcome that is no wheel to read is said, on
stderr in a line that ends with its `[code]`. A line starts `WARNING: Build: `
or `INFO: Build: `; `Build: ` is a frame that names the step and no part of
the line, and it admits only the codes below (the `option-no-effect` line also
starts `Build: `, as a literal, and is not among them) ([Messages and
codes](messages.md#line-grammar)). Each code, its causes and what to do about
it are on [Builds and temporary directories](message-codes-build.md). One line
of each, with a value in place of each `<name>`:

| Code | A line of it |
| :--- | :--- |
| `build-code-unsafe` | `WARNING: Build: DIR=<dir>: --allow-build runs a PEP 517 build for up to <duration> (--build-timeout), which executes the project's build code (build-backend <backend>, no discovery module for it) in an isolated build environment [build-code-unsafe]` |
| `build-failed` | `WARNING: Build: DIR=<dir>: the build exited with code <exit-code>; last output: <output> [build-failed]` |
| `build-failed` | `WARNING: Build: DIR=<dir>: no Python interpreter to run PyPA build with; not built [build-failed]` |
| `build-failed` | `WARNING: Build: DIR=<dir>: the build wrote <number> wheels, not one [build-failed]` |
| `build-failed` | `WARNING: Build: DIR=<dir>: the built wheel holds no file outside .dist-info; read as a failed discovery [build-failed]` |
| `build-failed` | `WARNING: Build: DIR=<dir>: the build could not run or its wheel could not be read; <failure> [build-failed]` |
| `build-timeout` | `WARNING: Build: DIR=<dir>: the build timed out after <duration> (--build-timeout); its process tree was stopped [build-timeout]` |
| `build-processes-unsafe` | `INFO: Build: the build left processes running (process group <process-group>); killed [build-processes-unsafe]` |
| `interrupted` | `WARNING: Build: received SIGTERM during the build; exiting after cleanup [interrupted]` |
| `temp-dir-unwritable` | `WARNING: Build: DIR=<dir>: could not be fully removed; left in the system temp directory [temp-dir-unwritable]` |
| `library-missing` | `WARNING: Build: required library not installed: build; install pitloom[build] [library-missing]` |

The lines quote the command line. A library call names its own options
instead: `BuildOptions.allow runs a PEP 517 build for up to <duration>
(BuildOptions.timeout), ...` and `the build timed out after <duration>
(BuildOptions.timeout); ...`; a build option given without `allow` says
`Build: <subject>: BuildOptions.timeout has no effect without
BuildOptions.allow [option-no-effect]`.

- The `build-code-unsafe` line comes before the build runs: for a backend no
  file discoverer of Pitloom reads (as above), or for a supported one whose
  static discovery failed (`... build-backend <backend>, its static discovery
  failed) ...`), and says `in Pitloom's own environment (no build isolation)`
  in place of `in an isolated build environment` with `--no-build-isolation`.
- A build that fails prints one `[build-failed]` line, the cause: the exit
  code and the last line the build printed (a credential in it masked, the line
  cut at 200 characters, then `...`), or the other causes in the table. The
  file discovery line of the fallback follows it (see above); the exit code of `loom` is 0.
- `[library-missing]` keeps its code: PyPA `build` is the library, installed by
  `pip install pitloom[build]`.
- `INFO:` of `[build-processes-unsafe]` is the clean-up; its `WARNING:` twin
  says Pitloom could not confirm the processes stopped (see below).

## Timing out a build

`--build-timeout DURATION` bounds how long the real PEP 517 build (see
above) may run before Pitloom kills its whole process tree and falls
back to static discovery. No effect without `--allow-build`.

`DURATION` is a bare ASCII integer (seconds, e.g. `900`), or `h`/`m`/`s`
units written largest-first, each used at most once (`900s`, `15m`,
`1h30m`, `1h30m45s`) -- the same grammar as Go's `time.ParseDuration`/
Prometheus durations restricted to whole seconds. Rejected: decimals
(`1.5h`), `ms`/`d` units (`500ms`, `1d`), uppercase, and whitespace.
Range: 1 second to 7 days (604800); default 20 minutes (1200) when the
flag is omitted.

On expiry, Pitloom terminates the build's whole process tree (not just
the immediate child process) and logs `WARNING: Build: DIR=<dir>: the build
timed out after <duration> (--build-timeout); its process tree was
stopped [build-timeout]` -- or `...; could not confirm its process tree stopped
[build-timeout]` when
a process in the tree was still alive after the kill (on Windows: when
`taskkill` did not report success). Either way Pitloom then falls back
to static file discovery, as without `--allow-build` (see above); the
command still exits 0 and still writes an SBOM, just with a potentially
less accurate or empty file list. Terminating the tree can take up to
about 8 seconds past the deadline on Linux/macOS (a grace period after
SIGTERM, then SIGKILL), and up to about 90 seconds on Windows.

Ctrl-C, SIGTERM and SIGHUP sent to Pitloom during the build (e.g. a CI
job cancellation, an external `timeout(1)` around `loom`, a closed
terminal) also terminate the build's process tree and remove its
temporary directories first; a signal that arrives while a temporary
directory is being removed waits for that removal to finish. The same
holds after the build, for as long as its files are in use (hashing,
AI-model scanning, every wheel of an `embed-wheel` batch): the
extracted-wheel temporary directory (`pitloom-build-and-read-*` in the
system temp directory) is removed at once, without waiting for the
current step to finish. Then:

- **Ctrl-C (SIGINT)** stops Pitloom with `ERROR: loom <command>: interrupted
  [interrupted]` and exit status 130, as for any other command (see
  [Debugging](cli.md#debugging) for the traceback).
- **SIGTERM/SIGHUP** log `WARNING: Build: received SIGTERM during the build;
  exiting after cleanup [interrupted]` (or `... after the build; ...` once
  the build has finished and its files are being read) and re-raise the same
  signal, so the exit status still reads "killed by that signal" (143
  for SIGTERM in a shell). Running as PID 1 in a container (no
  `--init`), where the kernel ignores an unhandled SIGTERM, Pitloom
  exits with status 143 instead.

Either way no SBOM is written. Processes a *successful* build leaves
running in the background are killed before its temporary directory is
removed (Linux/macOS only), with `INFO: Build: the build left processes
running (process group <process-group>); killed [build-processes-unsafe]` -- or
`WARNING: Build: the build left processes running (process group
<process-group>); could not confirm they stopped [build-processes-unsafe]` when
some survived the kill (on Linux, e.g. one running as
another user; macOS reports such a survivor the same way as a group
with only exited processes left, so it goes unreported there).

**Known limitations:**

- The build runs in its own process session, so it is orphaned when
  Pitloom dies without running that cleanup: on SIGKILL (e.g. `timeout
  -s KILL`, or a harness that escalates to it), or when the library API
  is called from a non-main thread or from an application that
  installs its own SIGTERM/SIGHUP handler (Pitloom then leaves signal
  handling to that application). A build backend process that calls
  `setsid()` itself also escapes Pitloom's kill.
- Once Pitloom no longer needs the build's files (the SBOM document is
  being assembled and written), SIGTERM/SIGHUP get their default
  handling back: there is nothing left to clean up.
- Windows: SIGTERM cannot be delivered from outside at all, and a
  forced termination (`taskkill /F`, a job-object kill), closing the
  console window, logoff or shutdown cannot be intercepted. Ctrl-Break
  is handled like SIGTERM above (the build receives it too, as it
  shares Pitloom's console); after the build, a file still open at that
  moment cannot be deleted on Windows, so the build's temporary
  directories may be left behind (a `WARNING:` ending `[temp-dir-unwritable]`
  names each one, by its name in the system temp directory).
  Descendants of a build child that has already exited -- including
  background processes a successful build leaves running -- may not be
  reachable.

## From Python

Pass `build_options=BuildOptions(allow=True)` to
`generate()`/`generate_project_sbom()` to let Pitloom invoke a project's own
PEP 517 build backend to discover its real file list, when static discovery
has no module for the backend (e.g. `uv_build`) or a supported backend's own
static discovery fails. The security rationale above applies identically.
Unlike `use_lockfile=`, it has **no** `[tool.pitloom]` config-file equivalent
and must be passed explicitly every call: there is no
config layer for a scanned project to silently opt itself into.

```python
from pathlib import Path
from pitloom import BuildOptions, generate

generate(
    Path("/path/to/project"),
    output_path=Path("sbom.spdx3.json"),
    build_options=BuildOptions(allow=True, timeout=900),
)
```

`BuildOptions` mirrors the three CLI flags:

| Field | CLI flag | Default |
| --- | --- | --- |
| `allow` (`bool`) | `--allow-build` | `False` |
| `no_isolation` (`bool`) | `--no-build-isolation` | `False` |
| `timeout` (`int` seconds or `None`) | `--build-timeout` | `None` (1200 s) |

`timeout` is plain `int` seconds -- **not** a duration string; the CLI's
own `h`/`m`/`s` grammar is a CLI/Action-layer convenience only.
`BuildOptions(...)` validates its fields when constructed, for every
target: a non-`bool` `allow`/`no_isolation` (e.g. the string `"false"`)
or a non-`int` `timeout` raises `TypeError`; a `timeout` outside 1 to
604800 raises `ValueError`. A field set where it has no effect -- a
target other than a project directory, or `no_isolation`/`timeout`
without `allow` -- logs one `WARNING: Build: ...` line per field
(`[option-no-effect]`),
naming the field as the caller gave it (`BuildOptions.timeout has no
effect without BuildOptions.allow`); the command line names its flags
instead (`--build-timeout`, `--allow-build`). The code is the same on
both. Logged as early as
possible on every surface -- before any project-metadata or lock-file
`WARNING:` a project directory target might also trigger -- so it's
never buried later in a run's output.

## See also

- [Command line](cli.md) -- every other subcommand and flag.
- [Python API](python-api.md) -- the rest of the library API.
- [GitHub Action](github-action.md) -- the `allow-build`/
  `no-build-isolation`/`build-timeout` Action inputs.
