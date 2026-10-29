---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Git LFS pointers

See also: [known-bugs.md](../design/known-bugs.md#found-2026-10-29) (open
follow-ups), [roadmap.md](../design/roadmap.md) (0.22.0),
[sbom-format-gaps.md](../design/sbom-format-gaps.md) (FG-9 to FG-11),
[ai-model-scan-security-lessons-transparency-and-correctness.md](ai-model-scan-security-lessons-transparency-and-correctness.md)
(3.10, the model-only first step).

A Git checkout made with LFS off holds a short text pointer for each
LFS-tracked file. Built in the 0.22.0 cycle (PR number: see CHANGELOG).

## What was built

`pitloom.core.lfs_pointer` is the one detector: `opens_lfs_pointer` (the
44-byte version-line test of the model gate), `parse_lfs_pointer` (the whole
grammar), `read_lfs_pointer` (a file; at most 1,024 bytes read, none when its
size is 1,024 or more), `PrefixCapture` (for a hasher reading once; holds at
most 1,024 bytes), `UnreadPointers` (one run's pointers, one summary warning).

- **Checkout** (CLI project, library, Git URL, Hub Git area): a pointer file
  is listed with its `oid` as SHA-256, no SHA-512, Hash comment `Git LFS
  pointer oid; content not read; size N bytes`, file provenance `Method:
  lfs_pointer`. Nothing is read or fetched; no content type, licence, header
  tags or copyright come from the pointer text. The stated size is recorded
  only in that comment (FG-9 to FG-11).
- **Archive-keeps-bytes vs checkout-takes-oid.** A wheel, an sdist, an
  `--allow-build` file, the Hatchling hook and `embed-wheel` ship the pointer
  text, so their hashes must match `RECORD`: they keep the bytes' hashes and
  only warn (`Git LFS pointer shipped ... the build did not pull LFS
  content`). A checkout has no such constraint, and the `oid` is the better
  identity: it survives `git lfs pull`.
- **One warning per kind per SBOM**, from `assemble/spdx3/_document_lfs.py`
  (called by `document.build()`, so CLI, library, hook, Action and
  `embed-wheel` agree): `FILE=<first, sorted>: Git LFS pointer, content not
  read (N files); run 'git lfs pull' for the content`. `--debug` adds a line
  per file. Loom runs warn once at run exit.
- **Model-named pointers** (`.gguf`, `.onnx`, `.bin`, `.model`, `.zip`, ...)
  are files only, no AI package, and no per-file warning when the whole file
  is a valid pointer. A file that only opens like one (malformed rest, or
  1,024 bytes or more) keeps the per-file `header is a Git LFS pointer`
  warning and is hashed normally. A named `loom model|enrich|generate` of a
  pointer errors with the `oid`, size and `git lfs pull`
  (`assemble/_model_generator.py`).
- **Loom.** `loom.dataset(path=)` and `use_model(path=)` on a pointer record
  the `oid` (`_loom_dataset.py`, `_loom_dataset_keys.py`, `_loom_model.py`,
  `core/dataset_hash.py`); a directory's Merkle leaf is the `oid`. The
  dataset-hash ceiling counts real on-disk bytes, never a stated size.
- **ID registry.** A checkout pointer is keyed by its `oid`
  (`id_registry.sha256_file` is the stated digest); an archive or hook SBOM
  states the digest of the pointer text. The file lookup accepts either, the
  stated one first (`ProjectFile.registry_hashes`), so a registry made by
  `id generate` on the checkout is hit by every route. `id import` and
  `id generate` record SHA-256 only.

## Decisions

- The warning's advice follows the source: a temporary Git-URL clone has
  nothing to pull into, so `GitCheckout.reading()` marks the run
  (`lfs_pointer.reading_remote_clone`) and the advice is `clone with git lfs,
  then run on the directory`.
- A licence source that is a pointer is no licence text on the directory
  route either (`read_license_file`, as the sdist route): `None`, with a
  `DEBUG` line only, even when the file is not among the listed files.
- The hook keeps the pointer text as the Merkle leaf (`bytes_as_is`: it
  matches the wheel's `RECORD`); `loom project` takes the `oid`. So the two
  document ids differ for a project with pointers; file ids do not.
- No fetching: it would contact a second server the Git URL guard does not
  cover. A future `--allow-lfs-fetch` could reuse the clone cap.
- A stated size is never used to read or allocate. The pointer file is read
  in full only below 1,024 bytes.
- The grammar is read strictly (below): a false negative lists the file as an
  ordinary file; a false positive would put a wrong identity on content.

## Not done, limits

- A checkout pointer has no SHA-512; a BSI TR-03183 hash check may want one:
  `git lfs pull` and regenerate.
- After a pull the SHA-256 and the Merkle root are unchanged, but a dataset
  may then exceed the ceiling and get no hash.
- The hook's and `loom project`'s package Merkle root (so document id)
  differ for a project with pointers.
- The ceilings and the clone cap have no flag yet; see known-bugs.

## Lessons and traps

- Every suffix class failed differently (see 3.10 in the lessons doc): test
  one pointer per class.
- A tool stricter than git-lfs needs a probe against the real tool: the matrix
  below found that git-lfs's decoder accepts forms it never writes.
- A fixture must be a pointer by the spec, not by its first line.
- A doc claim about the warning text is checked against `warn_pointers_not_read`.

## Tests and fixtures

`tests/core/test_lfs_pointer.py` (grammar matrix, git-lfs probe),
`test_lfs_pointer_warning.py`, `test_dataset_hash_lfs.py`,
`test_loom_lfs_pointer.py`, `tests/assemble/test_document_lfs_report.py`,
`test_document_files_lfs.py`, `test_model_lfs_pointer_named.py`,
`test_model_generator_lfs_pointer.py`,
`tests/id_registry/test_registry_lfs_pointer.py`,
`tests/core/models_wheel/test_models_wheel_lfs_pointer.py`,
`tests/extract/project/test_hatch_hook_lfs_pointer.py`; per surface (CLI,
library, hook, Action): `tests/test_lfs_pointer_surfaces.py` and
`test_lfs_pointer_warning_surfaces.py`; builder `tests/_lfs.py`; fixtures
`tests/fixtures/lfs-pointers/`.

## Grammar

`version <url>` (`https://git-lfs.github.com/spec/v1`, or the earlier
`https://hawser.github.com/spec/v1` and `http://git-media.io/v/2`, whole),
then any `ext-<digit>-<name> sha256:<64 hex>` lines, `oid sha256:<64
lowercase hex>`, `size <digits>` (no sign, `_` or leading zero, at most
2^63-1). Every line ends as the first does (LF or CRLF); the last line's
ending is optional. Shorter than 1,024 bytes; nothing else. An empty file
is not a pointer.

## Pointer grammar probe (git-lfs 3.4.1)

`git lfs pointer --check --stdin` on each row of the matrix in
`tests/core/test_lfs_pointer.py` (which re-runs it when git-lfs is
installed). Exit 0 accepts, 1 rejects; `--strict` exits 2 for a
non-canonical pointer.

| Form | Pitloom | git-lfs | `--strict` |
| --- | --- | --- | --- |
| canonical (LF, final LF); ext line; size 2^63-1; 1,023 bytes | accept | accept | accept |
| hawser or git-media URL; CRLF; no final line end; two ext lines; size 0 | accept | accept | 2 |
| 1,024 bytes (valid otherwise) | reject | accept | accept |
| empty file | reject | accept | accept |
| blank line; trailing blank line; trailing space at the end | reject | accept | 2 |
| ext line after `oid`; `size +5`; `size 05`; mixed LF/CRLF | reject | accept | 2 |
| 63 or 65 hex; upper-case hex; `sha1:`; `size` before `oid`; no `size` | reject | reject | reject |
| extra key; `size 1_0`; Arabic-Indic digit; `size -5`; size 2^63 | reject | reject | reject |
| BOM; `/spec/v1x`; `https://git-media.io/v/2`; CR-only; binary after the version line | reject | reject | reject |

So Pitloom accepts nothing git-lfs refuses, and refuses what git-lfs would
not write (the stricter rows are listed in the test as `_STRICTER`). The
1,024-byte cut-off is ours: git-lfs reads its first 1,024 bytes and parses
those. Its decoder skips blank lines, trims white space at both ends and
strips a CR before each LF, which explains the other stricter rows.
