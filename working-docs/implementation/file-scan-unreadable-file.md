---
Created: 2026-09-30
Last-Modified: 2026-10-03
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Project file scan: one unreadable file

See also: [roadmap.md](../design/roadmap.md),
[get-wheel-files-skip-merkle-root.md](get-wheel-files-skip-merkle-root.md)
(the open/close access probe),
[file-discovery-unlistable-dir.md](file-discovery-unlistable-dir.md)
(the directory counterpart),
[recurring-bug-patterns.md](recurring-bug-patterns.md).

**Status (2026-09-30):** implemented in PR
[#244](https://github.com/bact/pitloom/pull/244); found in the PR #239
review.

## Problem

`_scan_included_files()` (`core/_models_wheel.py`) wrapped the whole
per-file loop in `except Exception`, logged at DEBUG and returned
`None`. One `chmod 000` file, or a file under a directory without search
permission, emptied the SBOM's entire file set with nothing on stderr.

## Decisions

- **Per-file classification.** A discovered path that is missing or not
  a regular file is skipped silently (normal absence, as before). A file
  that exists but raises `OSError` on `stat()` or open/read gets one
  `WARNING: FILE=<path>: could not read for file scanning; <exception>`
  and is skipped alone. The wording does not say "skipped from the
  SBOM": on the embed surfaces the file stays (see below). The Merkle
  root covers the readable files only. `None` (then `(None, [])` to
  callers) now means "no readable regular file at all".
- **`FILE=` path is stable**: project-relative, or `distribution_path`
  for an `--allow-build` file in a temporary directory, via
  `project_relative_or_fallback()`.
- **One wording for every per-file read failure.**
  `path_probe.UNREADABLE_FILE_WARNING` (`FILE=%s: could not read %s;
  %s`) is shared by this scan and the AI model header read and usage
  scan (`extract/scanner.py`); each passes only what the read was for.
  (The declared license-files read in `extract/_license.py` used it too,
  until license files stopped being listed in an SBOM.)
- **Only `OSError` is caught.** Header parsing and content-type
  detection never raise on arbitrary bytes, so anything else is a bug:
  it propagates (discovery cleanup still runs) instead of becoming a
  silently empty file list.
- **`is_file()` replaced by `pitloom.core.path_probe.is_regular_file()`.**
  `Path.is_file()` raises `PermissionError` on 3.10-3.13 and returns
  `False` on 3.14, which would have made a file under a denied directory
  vanish silently on 3.14 only. The probe `os.stat()`s and classifies
  with the errno/winerror set `Path.exists()` uses (the PR #217
  `_is_missing_errno()`, promoted from `assemble/spdx3/fragments.py` to
  the new public `core/path_probe.py`; fragment merge and `loom fragment
  list` import it from there).
- **Embed surfaces**: `embed-wheel --project-dir` takes the file set from
  the wheel itself; the project scan only adds header/content-type data.
  An unreadable project file there warns once and loses only its own
  extras -- the file stays in the SBOM with the wheel's hash.

## Tests

- `tests/_unreadable.py`: shared deny modes -- `open`/`stat`
  (monkeypatched, every platform) and `chmod-file`/`chmod-dir` (real,
  gated on `POSIX_NON_ROOT`, a short-circuited module constant).
- `tests/core/models_wheel/test_models_wheel_unreadable.py`: the scan,
  silent absence, the temporary-directory path, all-unreadable cleanup,
  non-`OSError` propagation.
- `tests/test_unreadable_file_surfaces.py`: `loom project`/`generate`/
  `embed-wheel --project-dir`, `generate_project_sbom()`, `generate()`,
  `embed_wheel_sbom(project_dir=...)` and the Hatchling hook, each with
  every deny mode.
