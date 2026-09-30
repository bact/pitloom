---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Wheel member names: implementation notes

See also: [wheel-embedding.md](wheel-embedding.md) (the embed flow that
reads the same names), [ai-model-scanning.md](ai-model-scanning.md) (PR D's
wheel model producer reuses the helper).

## Problem

`read_wheel` used the raw `ZipInfo.filename` as `software_File.name`.
CPython's `ZipInfo.__init__` replaces `os.sep` with `/` only where
`os.sep != "/"`, and `ZipFile` builds every member through it. A wheel
holding `pkg\mod.py` therefore gave `pkg/mod.py` on Windows and
`pkg\mod.py` on POSIX: the same wheel, two SBOMs. `./pkg/mod.py` and
`pkg//mod.py` leaked through verbatim everywhere.

## Decision (DQ-2, 2026-09-30)

One helper, `pitloom.core.wheel_member_names.wheel_file_members()`, lists a
wheel's file members for every reader that turns them into distribution
paths: `read_wheel`, the `--allow-build` extraction
(`_extract_wheel_to_included_files`) and, next, PR D's wheel model
producer. `software_File.name` is the same on every OS.

- **Raw input:** `ZipInfo.orig_filename`, which CPython keeps unconverted on
  every OS. Reading `filename` would make both the names and the warnings
  depend on the OS.
- **Normalised:** `\` becomes `/` (via `to_posix_distribution_path`); empty
  and `.` segments are dropped (repeated `./`, `a//b`, `a/./b`). This is a
  portability policy, not what every installer does: on POSIX, pip and
  `installer` would write a file literally named `pkg\mod.py`. DQ-2 chose
  the Windows reading so one wheel gives one SBOM.
- **Unsafe, skipped:** a leading `/` (also UNC `//host`), a drive prefix
  (`C:`) on the first remaining segment (so `./C:/x` is caught too), any
  `..` segment, a NUL, or nothing left after normalising.
- **Directories:** judged by the raw name ending in `/`, `\` or a `.`
  segment (`pkg/.`); `ZipInfo.is_dir()` reads `filename`, so `pkg\` was a
  directory on Windows only. Skipped silently, as before.
- **Same install location twice** (`a/b` and `./a/b`, or an exact duplicate
  arcname): only the last one in the archive is kept, since an installer
  extracting in archive order leaves that one behind. Keeping both gave
  two `software_File` elements with one name; `file_spdx_ids` and the
  registry kept only the last, and `--allow-build` extraction wrote both
  to one file, so the first entry reported the second one's hash.
- **One `WARNING:` per affected member**, quoting the raw name. The message
  constants live beside the helper, extending the existing `wheel entry %r`
  wording:
  - `<prefix><wheel>: wheel entry <raw!r> is non-conforming -- recorded as <name!r>`
  - `... has no safe install location -- skipped`
  - `... is overwritten by later entry <raw!r> -- skipped`

  `<prefix>` is `Build: ` on the `--allow-build` path and empty in
  `read_wheel`; `<wheel>` is the wheel's file name in both.

## Why skip unsafe names rather than keep them

- Kept, `../x` or `/etc/x` becomes `software_File.name`. `_document_files`
  then builds directory elements named `..` or `/` with `contains` edges,
  the registry harvests the name as a file key, and any consumer that joins
  the name onto a directory (PR D's `materialize`) inherits a zip-slip.
- Rewriting it (dropping `..` or the leading `/`) would present a
  legal-looking path the wheel never installs to.
- pip and `installer` refuse such a wheel, so it has no install location to
  report.
- The `--allow-build` extraction already skipped these entries. Both readers
  now agree, and the `WARNING:` keeps the omission visible.

The `resolve().is_relative_to()` check in `_extract_wheel_to_included_files`
stays as defence in depth. The helper makes it unreachable, so a test
patches the helper out to keep it covered.

## Consumers

Keyed by `distribution_path`, now consistent with no change of their own:
`_document_files` (names, directory chain, `contains`), `file_spdx_ids` for
phantom dependency and AI `contains`/`hasDataFile` links,
`_embed_build_sbom._merge_file_extras` (joins wheel names with POSIX source
paths), the Merkle-root sort, `find_phantom_dependencies` (`Path.parts` was
OS-dependent on a backslash name), and registry lookups and harvest.

Not changed here: `_wheel_sbom_location` (dist-info lookup,
`find_embedded_sbom`, so verify-wheel/validate-wheel) and `_embed_wheel`
(RECORD rewrite, stale SBOM removal, archive copy). They work on the archive
itself, not on SBOM names, and still read `ZipInfo.filename`. That makes
them OS-dependent in the same way this change fixed for SBOM names: a
backslash `.dist-info` prefix is found on Windows only, and the archive copy
rewrites `pkg\x` to `pkg/x` on Windows only, leaving RECORD with the old
spelling. Out of scope; see `roadmap.md`.

## Known limits

- `embed-wheel`/`wheel --embed` with `--allow-build` reads two archives
  (the user's wheel and a fresh build), so one non-conforming name present in
  both warns once per archive: once plain, once with `Build: `.
- `--allow-build` extraction on a case-insensitive filesystem, or on Windows
  with `a.py:stream`, device names (`CON`) or trailing dots, can still map
  two names to one file or none. The SBOM name is the same on every OS; only
  that path's extracted bytes can differ. This predates the change.

## Tests

- Raw names are written with `ZipInfo.filename` set after construction
  (`tests/_raw_wheel.py`), so the archive holds the same bytes whatever the
  runner's `os.sep`.
- `mimic_windows_infolist` gives the Windows view of the same archive; the
  SBOM bytes and warnings must match the native run.
- `tests/test_wheel_member_name_surfaces.py` covers `loom wheel`,
  `loom wheel --embed`, `loom embed-wheel`, `generate_wheel_sbom()` and
  `embed_wheel_sbom()`.
- Mutation-tested: each classification rule, `orig_filename`, directory
  detection, keep-last deduplication, METADATA on the normalised name, the
  unsafe skip in both readers and the resolve guard.
