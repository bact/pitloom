---
Created: 2026-09-19
Last-Modified: 2026-09-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Building a project to discover its file list (`--allow-build`)

See also: [Command line](cli.md) for every other subcommand and flag --
this page covers `--allow-build`/`--no-build-isolation`/`--build-timeout`
only, split out because of its own size.

Available on `project`/`generate`/`embed-wheel` only (not `wheel`/`enrich`/
`env`/`model`, which never rescan a project directory).

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

- It's off by default and must be passed explicitly every time; there is
  **no** `[tool.pitloom]` config-file equivalent, unlike every other flag
  in this guide. A target project's own `pyproject.toml` must never be
  able to silently opt itself into code execution for whoever scans it.
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
  leaking onto Pitloom's own stdout/stderr; on failure or timeout, the
  log's last line is shown at `DEBUG:` (`loom --debug ...`). The
  build's stdin is closed (`/dev/null`-equivalent), so a backend that
  waits on stdin gets EOF instead of hanging.
- On any failure (network unavailable, backend not installed, build
  script error, timeout), Pitloom falls back to the same
  Hatchling-heuristic path used without the flag -- `--allow-build`'s
  worst case is never worse than leaving it off.
- On `generate`, all three flags parse for every target (`generate`
  auto-detects env/wheel/model-file/Hugging-Face/project targets from
  one shared parser) but only take effect when the target resolves to a
  project *directory* -- for any other target, including an sdist
  archive (whose file list comes from the archive's own listing, not a
  build), they're a no-op and Pitloom prints a `WARNING:` saying so.
  The same applies to `embed-wheel` when it can't resolve a project
  directory to rescan (no `--project-dir`, and the current directory
  is not a project; for the library, no `project_dir`) or when `--sbom` supplies an
  already-generated SBOM to embed verbatim.

```bash
loom project . --allow-build -o sbom.json
loom project . --allow-build --no-build-isolation -o sbom.json
loom project . --allow-build --build-timeout 15m -o sbom.json
```

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
the immediate child process) and logs:

```text
WARNING: Build: build-and-read for <dir> timed out after <N>s (--build-timeout) -- build process tree terminated
```

-- or `... -- could not confirm the build process tree terminated` when
a process in the tree was still alive after the kill (on Windows: when
`taskkill` did not report success). Either way it is followed by the
usual Hatchling-heuristic fallback warning; the command still exits 0
and still writes an SBOM, just with a potentially less accurate file
list. Terminating the tree can take up to about 8 seconds past the
deadline on Linux/macOS (a grace period after SIGTERM, then SIGKILL),
and up to about 90 seconds on Windows.

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

- **Ctrl-C (SIGINT)** stops Pitloom as usual, with a Python
  `KeyboardInterrupt` traceback (exit status 130 in a shell).
- **SIGTERM/SIGHUP** log `WARNING: Build: received SIGTERM during the
  build -- exiting after cleanup` (or `... after the build -- ...` once
  the build has finished and its files are being read) and re-raise the same
  signal, so the exit status still reads "killed by that signal" (143
  for SIGTERM in a shell). Running as PID 1 in a container (no
  `--init`), where the kernel ignores an unhandled SIGTERM, Pitloom
  exits with status 143 instead.

Either way no SBOM is written. Processes a *successful* build leaves
running in the background are killed before its temporary directory is
removed (Linux/macOS only), with `INFO: Build: killed processes the
build left running (process group <N>)` -- or a `WARNING: Build: could
not confirm the processes the build left running (process group <N>)
terminated` when some survived the kill (on Linux, e.g. one running as
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
  moment cannot be deleted on Windows, so the extracted-wheel directory
  may be left behind (a `WARNING:` names it). Descendants of a build
  child that has already exited -- including background processes a
  successful build leaves running -- may not be reachable.

Library API callers pass `BuildOptions(timeout=...)` as plain `int`
seconds (no duration-string parsing there) -- see
[`docs/python-api.md`](python-api.md).

## See also

- [Command line](cli.md) -- every other subcommand and flag.
- [Python API](python-api.md) -- `BuildOptions`, the library-API
  equivalent of these flags.
- [GitHub Action](github-action.md) -- the `allow-build`/
  `no-build-isolation`/`build-timeout` Action inputs.
