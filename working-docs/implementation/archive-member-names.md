---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Archive member names: implementation notes

See also: [wheel-embedding.md](wheel-embedding.md) (the embed flow that
reads the same names), [ai-model-scanning.md](ai-model-scanning.md) (PR D's
wheel model producer reuses the helper).

## Problem

`read_wheel` and the `.zip` sdist reader used the raw `ZipInfo.filename`
as `software_File.name`. CPython's `ZipInfo.__init__` replaces `os.sep`
with `/` only where `os.sep != "/"`, and `ZipFile` builds every member
through it. A wheel holding `pkg\mod.py` therefore gave `pkg/mod.py` on
Windows and `pkg\mod.py` on POSIX: the same archive, two SBOMs.
`./pkg/mod.py`, `pkg//mod.py` and `../x` leaked through verbatim, in tar
sdists too.

## Decision (DQ-2, 2026-09-30; widened to sdists in review)

One module, `pitloom.core.archive_member_names`, turns archive members into
distribution paths for every reader:

- `archive_members()` works on (raw name, payload) pairs. The tar sdist
  reader uses it directly.
- `zip_file_members()` wraps it for a ZIP. `read_wheel`, the `--allow-build`
  extraction (`_extract_wheel_to_included_files`), the `.zip` sdist reader
  and, next, PR D's wheel model producer all use it.

`software_File.name` is the same on every OS.

- **Raw input:** `ZipInfo.orig_filename`, which CPython keeps unconverted on
  every OS (a tar name is never converted). Reading `filename` would make
  both the names and the warnings depend on the OS.
- **Normalised:** `\` becomes `/` (via `to_posix_distribution_path`), and
  empty and `.` segments are dropped (repeated `./`, `a//b`, `a/./b`). This
  is a portability policy, not what every installer does: on POSIX, pip and
  `installer` would write a file literally named `pkg\mod.py`. DQ-2 chose
  the Windows reading so that one archive gives one SBOM. For tar, one
  leading `./` (`tar -C dir -czf x .`) is ordinary and is dropped without a
  warning (`dot_prefix_ok`); a wheel's ZIP has no such convention.
- **Unsafe, skipped:** any of these:
  - a leading `/` (also UNC `//host`);
  - a first remaining segment starting with a drive (`C:`), so `./C:/x` is
    caught, and so is `a:b.py`, which is drive-relative on Windows although
    legal on POSIX;
  - any `..` segment;
  - a NUL;
  - nothing left after normalising.
- **Directories:** a ZIP entry whose raw name ends in `/`, `\` or a `.`
  segment (`pkg/.`) is a directory. `ZipInfo.is_dir()` reads `filename`,
  so `pkg\` was a directory on Windows only. Directories are skipped; one
  that carries data warns, since its bytes are dropped.
- **Same name twice** (`a/b` and `./a/b`, or an exact duplicate arcname):
  only the last one is kept. Read with `\` as a separator, an installer
  extracting in archive order leaves that one behind. Keeping both gave
  two `software_File` elements with one name: `file_spdx_ids` and the
  registry kept only the last, and `--allow-build` extraction wrote both to
  one file, so the first entry reported the second one's hash. For an
  sdist this also picks the last of two identical root members
  (`PKG-INFO`), as unpacking leaves it; `_scan`'s first-wins rule now only
  breaks ties between two top-level directories.
- **File that is also a directory** (`pkg` alongside `pkg/mod.py`): the
  file is skipped. No installer can write both. Keeping it gave a file
  element and a directory element both named `pkg`, and made
  `--allow-build` extraction fail the whole discovery.
- **One `WARNING:` per affected member**, quoting the raw name, in the
  `KEY=VALUE` shape of the per-file `FORMAT=%s FILE=%s:` warnings:
  - `<prefix>ARCHIVE=<name> ENTRY=<raw!r>: non-conforming name -- recorded as <name!r>`
  - `... no safe install location -- skipped`
  - `... overwritten by later entry <raw!r> -- skipped`
  - `... also a directory of other entries -- skipped`
  - `... directory entry carries data -- skipped`

  `<prefix>` is `Build: ` on the `--allow-build` path and empty elsewhere.
  `ARCHIVE` is the archive's file name, quoted with `%r` like `ENTRY`, so a
  name with a space keeps the line `KEY=VALUE`-parseable. The
  `--allow-build` resolve-guard warning uses the same keys, and it also
  quotes the raw name. The sdist reader's root-only scan,
  which serves `--verbose` source reporting, passes no logger: the same
  run's full read already warned.

## Why skip unsafe names rather than keep them

- Kept, `../x` or `/etc/x` becomes `software_File.name`. `_document_files`
  then builds directory elements named `..` or `/` with `contains` edges,
  the registry harvests the name as a file key, and any consumer that joins
  the name onto a directory (PR D's `materialize`) inherits a zip-slip.
- Rewriting it (dropping `..` or the leading `/`) would present a
  legal-looking path the archive never installs to.
- pip and `installer` refuse such a wheel, so it has no install location to
  report.
- The `--allow-build` extraction already skipped these entries. Every reader
  now agrees, and the `WARNING:` keeps the omission visible.

The `resolve().is_relative_to()` check in `_extract_wheel_to_included_files`
stays as defence in depth. The helper makes it unreachable, so a test
patches the helper out to keep it covered.

## Consumers

Keyed by `distribution_path`, now consistent with no change of their own:
`_document_files` (names, directory chain, `contains`), `file_spdx_ids` for
phantom dependency and AI `contains`/`hasDataFile` links,
`_embed_build_sbom._merge_file_extras` (joins wheel names with POSIX source
paths), the Merkle-root sort, `find_phantom_dependencies` (`Path.parts` was
OS-dependent on a backslash name), registry lookups and harvest, and the
sdist root-member lookup (`PKG-INFO`, `pyproject.toml`, `setup.cfg` split
with `Path.parts`, OS-dependent before).

Not changed here: `_wheel_sbom_location` (dist-info lookup,
`find_embedded_sbom`, so verify-wheel/validate-wheel) and `_embed_wheel`
(RECORD rewrite, stale SBOM removal, archive copy). They work on the archive
itself, not on SBOM names, and still read `ZipInfo.filename`. They are
OS-dependent in the way this change fixed for SBOM names: a backslash
`.dist-info` prefix is found on Windows only, and the archive copy rewrites
`pkg\x` to `pkg/x` on Windows only, leaving RECORD with the old spelling.
Out of scope; see `roadmap.md`.

## Known limits

- `embed-wheel`/`wheel --embed` with `--allow-build` reads two archives
  (the user's wheel and a fresh build). One non-conforming name present in
  both therefore warns once per archive: once plain, once with `Build: `.
- `--allow-build` extraction on a case-insensitive filesystem, or on Windows
  with `a.py:stream`, device names (`CON`) or trailing dots, can still map
  two names to one file or none. The SBOM name is the same on every OS; only
  that path's extracted bytes can differ. This predates the change.

## Tests

- `tests/_raw_archive.py` writes raw names by setting `ZipInfo.filename`
  after construction (tar keeps names raw anyway). The archive therefore
  holds the same bytes whatever the runner's `os.sep`.
- `mimic_windows_infolist` gives the Windows view of the same ZIP. The SBOM
  (wheel) or file list (sdist) and the warnings must match the native run.
- `tests/test_archive_member_name_surfaces.py` covers the wheel surfaces
  (`loom wheel`, `loom wheel --embed`, `loom embed-wheel`,
  `generate_wheel_sbom()`, `embed_wheel_sbom()`) and the sdist surfaces
  (`loom project`, `loom generate`, `generate_project_sbom()`), each for
  zip and tar.
- Mutation-tested: each classification rule, `orig_filename`, directory
  detection and its data warning, keep-last deduplication, the file/directory
  rule, METADATA on the normalised name, the silent root-only sdist scan, the
  unsafe skip in the extraction and the resolve guard.
