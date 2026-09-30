---
Created: 2026-09-19
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `--allow-build` follow-ups from the PR #226 reviews

Deviations the `--build-timeout` reviews and the first
`scripts/manual_cli_checks` runs found and left open: PR #226 fixed the
correctness defects among them, and these are what remains. Summarised
in [roadmap.md](roadmap.md) as one bullet linking here.

See also: [allow-build-termination.md](../implementation/allow-build-termination.md)
(accepted limits of the termination design, and why each stands),
[allow-build-timeout.md](../implementation/allow-build-timeout.md),
[manual-cli-checks.md](../implementation/manual-cli-checks.md).

## Build-flag warnings

- The library `generate()` logs it after the `--use-lockfile` warning;
  the CLI logs it before.
- In a batch, the once-per-batch warning names only the first wheel as
  its subject, because `EmbedFileCache.settle` keys on
  (options, reason).

## Build output and extraction

- The `--debug` build-output tail prints a blank line as an empty
  `DEBUG: Build: build output:` line, with a trailing space.
- `_clean_line` strips ESC but leaves an OSC sequence's body (e.g.
  `]8;;url`) in `WARNING:` text.
- Entries differing only in case (or Unicode normalisation) overwrite each
  other when extracted onto a case-insensitive filesystem, so one entry
  gets the wrong hash; see
  [archive-member-followups.md](archive-member-followups.md) section 1.

## Outcome of the fallback

- A timed-out build falls back to static discovery, and when that fails
  too the run still writes an SBOM with zero `software_File` entries and
  exits 0 (three `WARNING:` lines say so on stderr, but nothing in the
  exit status does). Seen on the `uv_build` fixture
  `django-model-import-0.9.0`, whose project name and module name differ,
  so the Hatchling heuristic finds nothing: 16 files with a successful
  build, 0 after a timeout. Not specific to the timeout -- any failed
  discovery ends the same way.

## Isolation of the build child

- A `PYTHONPATH` entry pointing into the project still shadows PyPA
  `build` (the `cwd=work_dir` fix covers only the current directory).
- `_require_build_package()` checks Pitloom's own `sys.path`, not the
  child's, so a missing PyPA `build` can surface as a bare exit code.
- `-I`/`-E`/`-s` are not passed on to the child.
- setuptools writes `build/` and `*.egg-info` into the scanned project
  (as the previous in-process build did).

## `EmbedFileCache` on worker threads

One discovery and one settle are locked, but a discovery a worker thread
ran registers its temp directory with that thread's own
`TerminationGuard`, whose ownership is thread-local. Only the block's
own exit then removes it -- so it leaks both on a signal mid-batch and
on an exit interrupted after that discovery was cached, where the exit
deliberately touches no state (a thread may hold the lock). A discovery
still running at that point does remove its own, finding the block gone
(or replaced) when it returns. Registering it with the
batch's guard needs `TerminationGuard._run_cleanups()` to survive a
`BaseException` from one cleanup first -- today it suppresses
`Exception` only, so a `KeyboardInterrupt` from one cleanup skips the
rest.

## One predicate, several spellings

- `cli/commands/generate.py` still uses `target_path.is_file()` in its
  settle chain, where the rest of this PR moved to `os.path.isfile` for
  the never-raises reason.
- `embed_wheel.py`'s cwd probe tests `os.path.isfile()` on the project
  config names while `read_project()` tests `Path.exists()` on the same
  names, so a *directory* named `pyproject.toml` makes them disagree.
  Degenerate: the run still ends in a clean `ERROR:`, just with no
  build-flag warning before it.
- `_build_and_read_wheel` leaves already-run one-shot cleanups registered
  on the batch's guard, so that list grows one entry per discovery. They
  are idempotent, so this only costs memory.

## Blind spots of `scripts/manual_cli_checks`

- S1 cannot see a rescan: the fixture wheel ships only `demo/`, so no
  file at the project root is ever scanned.
- `M/model/offline/*` never reaches the network, so its `--offline` cell
  proves nothing.
- S1-S8 and the fixture builds run without the network guard.
- An interrupted run leaves its `pitloom-mcc-*` scratch directory behind.
- Surviving pytest mutants: `TerminationGuard`'s cleanup order and its
  nested hold, the build wait's deadline slack, and
  `parse_build_timeout`'s empty-match guard.
