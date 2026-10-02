---
Created: 2026-09-30
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Archive member names: follow-ups from the PR #251 reviews

PR #251 made `software_File.name` the same on every OS for wheel and sdist
members. The review rounds found three gaps it deliberately left open,
because each changes behaviour beyond naming and needs its own design.
Summarised in [roadmap.md](roadmap.md) as one bullet linking here.

See also: [archive-member-names.md](../implementation/archive-member-names.md)
(what PR #251 built and why),
[allow-build-followups.md](allow-build-followups.md) (other `--allow-build`
gaps).

## 1. `--allow-build` extraction depends on the filesystem

`_extract_wheel_to_included_files` writes each kept member to
`extract_dir / distribution_path` and then hashes and scans that on-disk
file. The file's name is therefore interpreted by the host filesystem,
which differs by OS.

- **Case/Unicode folding** (macOS APFS by default, Windows NTFS): `PKG/a`
  and `pkg/a`, or NFC and NFD spellings of `é`, land on one file. Both
  `IncludedFile`s hash the later bytes, and the directories merge on disk.
  Linux keeps them apart, so the Source SBOM differs by OS. This supersedes
  the "unverified" case-collision bullet in `allow-build-followups.md`.
- **Windows path rules:**
  - A path longer than 260 characters (deep member under `%TEMP%`, without
    long-path support) fails with `OSError`. The broad except turns that
    into "discovery failed", so the whole Source SBOM falls back to static
    discovery on Windows only.
  - `a.py:stream` writes an NTFS alternate data stream.
  - Reserved names (`CON`, `nul.py`) hit a device; the resolve guard
    usually skips them.
  - A trailing dot or space (`x.py.`) aliases `x.py`.

**Direction:** extract each member to a path that does not depend on its
name, e.g. `extract_dir / f"{index:06d}"`, and carry `distribution_path`
separately, as `IncludedFile` already does. This removes every case above at
once.

**Constraints to design for before changing it:**

- `_build_project_file_entry` passes `source.name` (the on-disk basename)
  to content-type detection (`detect_content(raw_bytes, filename, ...)`).
  Either keep the leaf name (`extract_dir / f"{index:06d}" / leaf`, which
  still exposes the leaf to Windows rules) or pass the basename of
  `distribution_path` instead. The second needs a check that every other
  backend gives the same answer.
- `physical_path` for these files is already an absolute temp path that
  consumers replace with `distribution_path` via
  `project_relative_or_fallback`. Confirm that nothing else reads the
  directory layout (the AI model scan joins `project_dir / physical_path`,
  and here that is absolute).
- `source.read_bytes()` reads each file whole. Streaming the hash would
  fit the resource-efficiency rule, but it is separate work.
- Tests: a case-only pair on a case-insensitive runner (macOS CI), and a
  member path over 260 characters on the Windows leg.

## 2. The embed copies a non-conforming member under `info.filename`

`_wheel_sbom_location` and `_embed_wheel` select from `wheel_members()`
(`orig_filename`) since #266, and the embed refuses a non-conforming name in
the wheel's own `.dist-info`. Still open: `_rewrite_wheel_archive` copies every
other member with `new_zf.open(info, "w")`, which encodes `info.filename`. On
Windows, embedding rewrites `pkg\x` as `pkg/x` while RECORD keeps the old
spelling; on POSIX the name survives byte for byte, so the embedded wheel's
bytes depend on the OS.

**Direction:** copy under `orig_filename`. Open question: should embedding
ever repair a non-conforming name? It is a byte-preserving copy, and repair
would also mean rewriting RECORD.

Also open: `embed-wheel --project-dir` merges header data from the project
scan onto the wheel's own `ProjectFile`s (`_merge_file_extras`). The
provenance string for that data (`Source: <path> | Field: ...`) names the
wheel file's `physical_path`, the raw archive name, but the data came from the
project file (`src/pkg/x.py` in a src layout). Carrying the project file's path
for provenance only would fix it, without losing the raw-name registry key.

## 3. Tar links in sdists

`_tar_entries` keeps `TarInfo.isfile()` members only. Hard links
(`LNKTYPE`) and symlinks to files are dropped from the file list with no
`WARNING:`, although unpacking the sdist creates them. This conflicts with
the module's "read as for the unpacked project directory" contract.

**Open questions:**

- List a hard link as a file with its target's bytes (as unpacking gives)?
- List a symlink as a file (following it inside the archive only, never
  outside), or skip it with a `WARNING:`?
- How should a link whose target is unsafe or missing be handled? It needs
  the same `archive_members` classification as an ordinary member.

This predates PR #251. PR #251 only touched the surrounding function.
