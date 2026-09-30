---
Created: 2026-09-14
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `get_wheel_files()` skip-Merkle-root option

See also: [roadmap.md](../design/roadmap.md) (feature-oriented plan).

**Status (2026-09-14):** shipped on `main` via PR
[#213](https://github.com/bact/pitloom/pull/213) (merge commit `69f43c8`).

## What was built

`get_wheel_files()` (`src/pitloom/core/_models_wheel.py`) gained a
keyword-only `skip_merkle_root: bool = False` parameter. When `True`:

- No per-file SHA-256 hash is computed; every returned `ProjectFile` has
  `digest_sha256=None`.
- The returned Merkle root is always `None`.
- File discovery, sorting (by `distribution_path`, for determinism), and
  the `scan_file_headers`/`detect_content_type` scanners are unaffected.

`embed.py`'s `_build_sbom_from_project_and_wheel` -- the one caller that
never used `get_wheel_files()`'s own digests or root in the first place
(see below) -- now passes `skip_merkle_root=True`.

## Why

`_build_sbom_from_project_and_wheel` already discarded
`get_wheel_files()`'s `merkle_root` return value, recomputing one from
the wheel's own post-merge file hashes instead
(`_compute_wheel_merkle_root`, sourced from `wheel_metadata.files`, not
the source-tree rescan). Its `_merge_file_extras` step also only ever
adopts `project_files`' content-type/file-header extras onto the wheel's
files -- never `project_files`' own digest. So when both
`scan_file_headers` and `detect_content_type` are off, the source-tree
rescan was reading every project file's full bytes into memory and
SHA-256-hashing them purely to build a Merkle root and per-file digests
that this caller throws away -- real, avoidable I/O for large projects.

## Decisions made

- **`ProjectFile.digest_sha256` became `str | None`** (was `str`,
  required at construction), matching the sibling
  `PhantomDependency.digest_sha256` field already in the same file
  (`src/pitloom/core/project.py`). An empty-string sentinel was
  rejected: it would be the exact "`None` vs. empty is a distinct
  signal" conflation `CLAUDE.md`'s recurring-bug-patterns section warns
  against, applied to a hash rather than a container.
- **Every other consumer of `ProjectFile.digest_sha256` was traced**
  before widening the type, to confirm none can actually receive `None`
  at runtime: `_document_files.py`'s file-emission loop and
  `embed.py`'s `_compute_wheel_merkle_root` only ever process
  `metadata.files`/`merged_files`, which are sourced either from
  `get_wheel_files()`'s default (`skip_merkle_root=False`) or from the
  wheel's own real hashes -- never from the skip-hashing rescan. Both
  sites use `typing.cast(str, ...)` with a comment recording this
  invariant, rather than a defensive `if digest is None:` branch, which
  would silently misbehave (or drop a file) for a case that cannot
  happen. `cast()` without a runtime guard already matches how this
  codebase treats other statically-unreachable cases elsewhere (e.g.
  `provenance.py`, `_fragments_unify.py`) -- not a rule this repo's
  `CLAUDE.md` states explicitly, but the established local convention.
- **A cheap access probe (`with source.open("rb"): pass`) replaces the
  full read on the skip path**, rather than skipping file access
  entirely. Without it, a file that passes `source.is_file()` but fails
  to open (permission error, a TOCTOU deletion race) would no longer
  raise, so it would silently appear in the output with
  `digest_sha256=None` instead of degrading the whole call to
  `(None, [])` the way every other unexpected failure in
  `get_wheel_files()` does (see
  `test_get_wheel_files_returns_none_on_unexpected_discovery_failure`).
  The probe preserves that fail-loud contract while still avoiding the
  full-file read for the common (large-file) case.
  **Revised 2026-09-30:** a read failure no longer degrades the whole
  call; the probe now surfaces it as one `WARNING:` and that file is
  skipped alone -- see
  [file-scan-unreadable-file.md](file-scan-unreadable-file.md).

## Paths considered and rejected

- **Keying the post-loop emptiness check off the per-file hash list**
  (`file_entries`, as in the pre-existing code) instead of
  `project_files`. Since `file_entries` is now only populated when
  `not skip_merkle_root`, this would make `get_wheel_files(...,
  skip_merkle_root=True)` return `(None, [])` unconditionally --
  discarding every discovered file on every call, the opposite of the
  intended optimization. Caught during plan review, before
  implementation; fixed by checking `project_files` instead (the two
  lists are populated 1:1 in the same loop body regardless of the
  flag).
- **Skipping the digest for every caller of `get_wheel_files()`.**
  Rejected: `_document_files.py` and other callers (`plugins/hatch.py`,
  `assemble/_generators.py`, `assemble/_model_generator.py`) rely on a
  real per-file digest for `verifiedUsing` and phantom-dependency
  detection. `skip_merkle_root` defaults to `False` and only
  `embed.py`'s one caller opts in.

## Follow-up: `FileScanConfig` bundling (2026-09-14, same PR)

A code-review pass flagged that `_build_project_file_entry()` (the
extraction above) re-split the 4-field
`parse_header`/`detect_content`/`content_type_overrides`/
`content_type_method` bundle that `_resolve_file_header_extras()`
already took together, forwarding all 4 unbundled through both
functions plus `get_wheel_files()` itself -- three call sites each
threading the same 4 params by hand, each needing its own
`too-many-arguments` suppression.

Fixed by adding `FileScanConfig` (a `NamedTuple`) to
`src/pitloom/core/_models_wheel_types.py`, alongside its existing
`IncludedFile`/`FileHeaderExtras` sibling types -- matching this
module's own established convention of bundling per-file
discovery/scan data into a named type rather than passing it as loose
parameters. `get_wheel_files()` builds one `FileScanConfig` instance
and passes it down to `_build_project_file_entry()`, which forwards it
untouched to `_resolve_file_header_extras()`. This dropped
`_build_project_file_entry()`'s param count from 9 to 6 (no suppression
needed any more) and removed the triplicated forwarding.

## Where

- `src/pitloom/core/_models_wheel.py`: `get_wheel_files()`,
  `_build_project_file_entry()` (the per-file body was extracted into
  its own function to keep cognitive complexity under the project's
  flake8 ceiling once the skip-path branching was added; its scan
  params were then bundled into `FileScanConfig`, see above),
  `_resolve_file_header_extras()`.
- `src/pitloom/core/_models_wheel_types.py`: `FileScanConfig`.
- `src/pitloom/core/project.py`: `ProjectFile.digest_sha256`.
- `src/pitloom/embed.py`: `_build_sbom_from_project_and_wheel()`,
  `_compute_wheel_merkle_root()`.
- `src/pitloom/assemble/spdx3/_document_files.py`: the `cast()` site.
- Tests:
  `tests/core/models_wheel/test_models_wheel_skip_merkle_root.py`.
