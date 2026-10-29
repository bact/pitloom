---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Git LFS pointers

See also: [known-bugs.md](../design/known-bugs.md) (the open item),
[roadmap.md](../design/roadmap.md) (0.22.0).

A Git checkout made with LFS off holds a short text pointer for each
LFS-tracked file. `pitloom.core.lfs_pointer` is the one detector:
`opens_lfs_pointer` (the 44-byte version-line test the model gate uses),
`parse_lfs_pointer` (the whole grammar), `read_lfs_pointer` (a file, at
most 1,024 bytes read, none when its size is 1,024 or more) and
`PrefixCapture` (for a hasher reading a file once; holds at most 1,024
bytes). A pointer's stated size is only recorded, never used to read.

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
