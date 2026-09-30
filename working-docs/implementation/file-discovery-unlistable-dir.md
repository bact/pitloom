---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# File discovery: one unlistable directory

See also: [file-scan-unreadable-file.md](file-scan-unreadable-file.md)
(the per-file counterpart, PR #244),
[roadmap.md](../design/roadmap.md),
[recurring-bug-patterns.md](recurring-bug-patterns.md).

**Status (2026-09-30):** implemented in PR
[#257](https://github.com/bact/pitloom/pull/257) (pre-0.20.0 sweep item P16); found
in the PR #244 review.

## Problem

A directory that cannot be listed (`chmod 000`, another user's `0700`
directory) dropped its whole subtree from the discovered file set with
nothing on stderr. Every backend delegates its walk to its own library,
and none of them passes an `onerror` or reports the failure:

| Discovery path | Walk |
| --- | --- |
| Hatchling (also the fallback for `uv_build` and unknown backends) | `hatchling.builders.utils.safe_walk()` → `os.walk()` |
| flit-core | `Module.iter_files()`, `walk_data_dir()` → `os.walk()` |
| pdm-backend | `os.walk()`, `glob.iglob()`, `Path.glob()` |
| poetry-core | `Path.glob("**/*")` |
| setuptools | `find_packages()` → `os.walk()`; `package_data` → `glob` |

`glob` and `Path.glob()` swallow `OSError` themselves, so even a
wrapper around `os.walk` would not cover them.

## Decisions

- **Watch the listing calls, not the walk.** A PEP 578 audit hook
  (`core/_models_wheel_unlistable.py`) records each path that
  `os.scandir()`/`os.listdir()` are asked to list while
  `get_wheel_files()` runs discovery. `os.walk`, `glob` and `pathlib` go
  through those two calls on Python 3.10-3.14 (pathlib 3.10 binds
  `os.scandir` at import, but the audit event is raised in C, so the
  binding does not matter). Afterwards each recorded directory under the
  project is opened again with `os.scandir()`, and one
  `WARNING: DIR=<project-relative path>: could not list for file
  discovery; <exception>` is logged for each one that fails. Missing or
  not-a-directory failures (`path_probe.is_missing_errno()`) stay quiet:
  globbing probes such paths routinely.
- **Rejected: our own post-walk of the project tree.** Simpler, with no
  global hook, but it warns about directories the backend excludes
  anyway (e.g. a Docker volume directory owned by another user) and
  walks `.venv`/`.git` a second time. With the hook, only directories
  the backend really tried to list are named (see the known gaps for
  backends that list before excluding). Also rejected: warning
  only when the parent directory holds a discovered file. That misses a
  whole unlistable top-level package.
- **Rejected: patching `os.scandir`/`os.listdir`.** Process-global,
  racy under the discovery lock's concurrent readers, and it misses
  pathlib on 3.10.
- **Scope by context variable.** The hook is installed once per process
  and cannot be removed. It records only inside the
  `warn_unlistable_dirs()` block of the current context (thread), so a
  concurrent reader's discovery or unrelated code never adds paths. Its
  body catches every `Exception`, because an exception raised in an
  audit hook fails the audited call.
- **Relative names resolve at call time**: setuptools and pdm-backend
  `chdir()` into the project (under the discovery write lock), so
  `abspath()` runs inside the hook, not after.
- **"Under the project" is textual first, then by directory identity.**
  setuptools lists relative to its `chdir()`, and `os.getcwd()` gives the
  on-disk letter case on macOS and Windows, so `loom project stproj` for
  on-disk `StProj` recorded paths that `relative_to(project_dir)`
  rejected, and the warning was lost (found in the #257 review). When the
  text does not match, the recorded path's ancestors are compared with
  `project_dir` by `(st_dev, st_ino)`, with the result cached per call. An
  `st_ino` of 0 counts as no identity: Python documents it as unique only
  when non-zero, and FAT/exFAT and some network shares report 0 for every
  directory, which would match anything on the volume. The textual
  match comes first, so a directory reached through a symlink inside the
  project keeps its in-project name.
- **One place, every surface.** The block wraps the
  `_discover_included_files()` call in `get_wheel_files()`, the one
  function every surface uses: `project`, `generate`,
  `embed-wheel --project-dir`, `enrich --project-dir`, the library API
  and the Hatchling hook. A registered backend whose discovery fails,
  followed by the Hatchling fallback, still gives one warning per
  directory (the recorded set is shared, so each path appears once).
- **Wording** `path_probe.UNLISTABLE_DIR_WARNING`
  (`DIR=%s: could not list %s; %s`) matches `UNREADABLE_FILE_WARNING`'s
  shape. Like that warning, it does not say "skipped from the SBOM":
  on the embed surfaces the wheel's own file set is kept, and the
  directory may be one the backend excludes anyway (see below). It
  states only that the listing failed.
- **Nothing is logged when the block raises**: a raising discovery is a
  bug, and it already propagates.

## Known gaps

- **An excluded directory can still be named.** Hatchling prunes
  excluded directories before listing them, so they stay quiet.
  poetry-core, pdm-backend and setuptools' `package_data` glob `**/*`
  first and filter afterwards, so they list an excluded directory too:
  a poetry project with `exclude = ["pkg/secret"]` and `pkg/secret`
  unlistable warns about it, although the file set is unchanged. The
  same applies to a registered backend's failed attempt before the
  Hatchling fallback. Accepted: the warning says only that the listing
  failed, which is true. Filtering it through each backend's own
  exclude rules would take per-backend code for a rare case.
- **`--allow-build`** runs the real build in a child process, where the
  hook cannot see anything. There, an unlistable directory is still
  dropped as the backend itself drops it.

## Tests

- `tests/core/models_wheel/test_models_wheel_unlistable.py`: a real
  `chmod 000` over hatchling, setuptools, flit, pdm, poetry and the
  `uv_build` fallback (gated on `POSIX_NON_ROOT`, a short-circuited
  module constant); setuptools with `project_dir` in another letter case
  (skipped on a case-sensitive file system); plus portable tests of the
  helper with `os.scandir` denied by monkeypatch: project-relative naming
  (`.` for the root), cwd-relative names, a path through a symlinked
  alias of the project, an unstat-able or zero-inode `project_dir`, and
  the quiet cases (missing, outside
  the project, another thread, before the block, a raising block, odd
  audit arguments).
- `tests/test_unreadable_file_surfaces.py`: every surface, plus the
  `enrich` identity.
- Mutation-checked: removing the wiring, the missing-errno filter,
  `abspath()`, the hook's `except`, the project filter, or warning on a
  raising block each fails a test.
