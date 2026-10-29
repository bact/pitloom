---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Evidence levels: measured, declared or not recorded

See also: [roadmap.md](roadmap.md) (the summary bullet),
[sbom-format-gaps.md](sbom-format-gaps.md) (FG-9 to FG-12),
[the taxonomy](generation-gaps-extraction-and-recording.md) this extends,
[known-bugs.md](known-bugs.md),
[git-lfs-pointers.md](../implementation/git-lfs-pointers.md) (the first case),
and [message-catalogue-and-skills.md](message-catalogue-and-skills.md) (the
codes used below).

Status: design, revised 2026-10-29 after an Opus review against the code.
Built so far: Git LFS pointers (#378), flags for both size ceilings (#381),
the dataset-size unit fix (#382); the `evidence_segment` helper, `minimal`
keeping an entry with `Evidence:`, and the merge drop of a superseded
`not_measured` entry with the comment-join fix it needs (#386). Everything
else below is unbuilt.

## Principle

**A size or time cap bounds what Pitloom reads. It never bounds what Pitloom
reports.** The caps exist for security and for hangs: do not read something too
big, or for too long. If the artefact's size, hash or other property is known
by a safe route, the SBOM states it. Every recorded fact has an *evidence
level*, and the SBOM says which.

## The levels

In order of preference. The first that is available is used.

| Level | Meaning | Recorded as |
| - | - | - |
| `measured_stat` | Taken from the file system without reading content | the value; `Evidence: measured_stat` |
| `measured_read` | Computed by reading the content within the caps | the value; no `Evidence:` segment (today's meaning) |
| `declared` | Stated by metadata and not checked: an archive header, an LFS pointer, a Hub API response, `Content-Length`, a lock file, `RECORD` | the value; `Evidence: declared`, naming the source |
| `lower_bound` | A read or walk stopped at its limit: "at least N" | provenance only, carrying the limit (`Budget:`), never the partial value |
| `not_measured` | Not safe to read, and nothing declared | no value; `Evidence: not_measured` and `Reason: <catalogue code>` |

`stat()` is safe for any regular file, so a size is available even when the
content is over the cap. A pointer's `stat()` size is the pointer's, about 130
bytes, not the content's: it is `measured_stat` of the pointer and must not be
passed off as the artefact's size.

**Why a fact can be `not_measured`.** The read cap is one reason. For a remote
artefact the bytes may never arrive:

| Reason | Example | Catalogue code (proposed) |
| - | - | - |
| Read cap | a model over `max-model-extract-bytes` | `over-cap` |
| Download cap | a clone stopped at the size limit | `over-cap` (the run aborts: stderr only) |
| Wait too long | a network timeout, a slow server | `timeout` |
| Not reachable | a refused or failed fetch | `network-failed` |
| Not resolved | an unpulled Git LFS file (only the pointer arrived) | `lfs-pointer` |
| Not readable | a permission error, a vanished file | `unreadable-file` |

The declared route stays open: a remote API or a pointer often states the size
and hash of something Pitloom did not download (the Hub API lists each LFS
file's `oid` and size; a pointer states both; a server may send
`Content-Length`). Record that as `declared` with its source.

## Rules

1. **Prefer measured to declared.** If both exist and differ materially, record
   the measured value and say the declared one differed. A ZIP that declares a
   small size and expands huge is the attack case, not noise.
2. **Several declared sources are taken in a fixed order**, and a disagreement
   is stated, not hidden.
3. **A declared value is validated before it is recorded:** a non-negative
   integer, at most 2^63-1 (the git-lfs bound), and within the JSON-safe
   2^53-1 the fragment reader already enforces. Out of range: not recorded,
   with the reason.
4. **A declared value may stop a read early and never permit one; the cap
   counts real bytes.** (A pointer stating 100 GB is hashed like any other; a
   ZIP member whose declared size is over the cap is skipped, which is the safe
   direction.)
5. **Time and network limits are caps too:** a download size cap, a connect or
   read timeout, a total wait. A fetch that times out is `not_measured` with
   the reason `timeout`, unless a declared value exists.
6. **A walk is bounded by entries only.** Summing the sizes of a directory with
   a million entries can hang on `stat()` alone. A time budget makes the output
   depend on the machine, and so does a partial sum (`os.walk` order depends on
   the file system): an exhausted budget gives a `lower_bound` that states the
   budget, never the sum so far.
7. **`not_measured` is a deviation, not absence.** Absent source data stays
   quiet (a field the source lacks). A fact left unread by policy is a
   `WARNING:` (as the cap warnings already are) and a provenance entry.
8. **The same code in both places.** The provenance `Reason:` is the catalogue
   code the warning carries, so the SBOM, stderr and the skills agree. Never raw
   server or exception text, which is attacker text.

## Provenance of absence

Provenance has meant "where this value came from". It also says where a value
could have come from and could not, and why. The outcomes of a source:

| Outcome | Recorded? | Example |
| - | - | - |
| `used` | yes, as today | the value read from `config.json` |
| `unavailable`: the source has nothing | no (absent data stays quiet) | a bare Safetensors file has no version |
| `refused`: policy stopped the read | yes | over the read, download or time cap |
| `failed`: the read or fetch broke | yes | a timeout, a refused connection, a vanished file |
| `declared_only`: only a statement reached us | yes, as the value | a pointer's oid and size |

Only the last three are written: they are deviations, and `unavailable` is not,
so the SBOM does not fill with "this source had nothing".

**Shape (from the review of the provenance code).**

- Provenance is a `dict[field -> "Key: v | Key: v"]` per element
  (`parse_provenance_value`, `core/provenance.py`); a key not in the table
  passes through, so `Evidence:` and `Reason:` need no schema change. Do not
  overload `Method:`: it says *how* a value was read, and the level is
  independent (the Hub's parameter count is `Method: tensor_element_sum` and
  declared).
- An entry with no `Evidence:` means what it means today, so nothing is written
  for the thousands of measured file hashes.
- `filter_high_signal` keeps an entry that has a `method`, or a source outside
  the transparent list. A negative entry from a transparent source (for example
  `Source: hugging face hub | Reason: network-failed`) is dropped in `minimal`,
  which is the default. One line in `_is_high_signal`: keep any entry that has
  `evidence` (built, #386).
- One helper (`core/evidence.py`, `evidence_segment(...)`) is the only writer:
  it checks the reason against the catalogue and sanitises every value
  (built, #386).
- One entry per element and field, as a segment of the field's own entry (no new
  Annotation, no new ids). Where there is no element (an unreadable project file
  is skipped whole), the entry rides on the main package with `Count:`, and its
  `contains` relationship may say `completeness=incomplete`. A per-file family
  is one entry with a count and the first sorted name, never one per file.
- A repeated key keeps only the last value, so the order of sources considered
  cannot be recorded in the current grammar. Dropped for now; a `Considered:`
  segment could carry it later.
- Never write evidence text into `ProjectMetadata.provenance
  ["locked_dependencies"]`: it feeds the document uuid. A guard test.

**Where the entry attaches:** a dataset over the cap, the dataset package (it is
built even when the hash is omitted); a wheel model over the cap, the stub's
`ai_AIPackage`; a Hub failure, the AI package; an unreadable project file, the
main package; a clone over the cap, nowhere (the run aborts, so only stderr
carries it).

## Where each level lands in SPDX

- **SPDX 3.0.1** (the installed binding): `dataset_datasetSize` on datasets
  only; no size property on files or models (FG-9).
- **SPDX 3.1-dev** (checked against the spec's develop branch): `byteSize`
  (non-negative integer, one value) on `SoftwareArtifact`, so on files, packages
  and datasets; `datasetSize` is marked deprecated in favour of it. Adopt with
  the 3.1 binding; until then a size goes in the `Hash` comment (as for Git LFS
  pointers) or `datasetSize`.
- **Declared hash:** stays in `verifiedUsing` with the `Hash` comment and
  `Evidence: declared`. `IntegrityMethod` is a mechanism that permits
  verification and does not claim Pitloom verified anything; an oid is checkable
  after a pull. FG-11 stays open.

## Today (audited 2026-10-29)

| Fact | Today | Gap |
| - | - | - |
| File hash, project files | `measured_read` | none |
| Git LFS pointer hash and size | `declared` (#378) | the provenance says `Method: lfs_pointer`, not the level |
| Dataset hash | `measured_read`; over `max-dataset-hash-bytes` (flag and keyword since #381): omitted with a warning | no negative entry |
| Dataset size | only what the library caller supplies (`DatasetMetadata.byte_size`, bytes); a Croissant item count is not recorded (#382) | `stat()` already runs for the cap check and its size is discarded |
| Hashed file sizes | measured (`FileDigests.size`) and discarded; `ProjectFile` has no size | kept for 3.1 `byteSize` |
| Model over `max-model-extract-bytes` (flag since #381) | wheel route: a stub with a warning; the declared ZIP size is in memory and unused. A local or project model has a `stat()` size | name the declared size |
| Directory size | the walk already `stat()`s every file with no budget, and throws the sum away | an entries budget, and the LFS caveat |
| Git source, clone over the cap | the run aborts (`git.too-large`); no SBOM | stderr only |
| Hub source, file size and hash | not read from the API | the API states them: `declared` |

**The unit clash is fixed** (#382). `dataset_datasetSize` holds bytes only:
`DatasetMetadata.byte_size` replaced `dataset_size`, and a Croissant item
count is no longer read (no SPDX 3.0.1 property; FG-12). A byte size from
`stat()` can now go in the same property without mixing units.

## Scope and order

0. ~~Fix the unit clash~~ (done, #382).
1. **One case end to end: a single-file dataset over the cap.** `DatasetDigest`
   gains `size` (from the `stat()` already done at the cap check) and `omitted`
   (a reason code); the size is recorded as `measured_stat`, and the omitted
   hash carries `Evidence: not_measured | Reason: over-cap` through the existing
   `hash_provenance` slot. Directories wait: pointer files in them stat at about
   130 bytes, so one sum would mix levels, and the walk budget is undecided.
2. **The value type and the helper** (`core/evidence.py`; the helper is built,
   #386, the value type is not), then models, the Hub and unreadable files;
   hashes move onto it.
3. **The catalogue codes** in the provenance, once `lfs-pointer` and `over-cap`
   exist.
4. **With the SPDX 3.1 binding:** `byteSize` for files and models.

## Tests

For every fact: `measured_stat`, `measured_read`, `declared`, `lower_bound`,
`not_measured`. Lies: a ZIP declaring small and expanding big; a ZIP declaring
huge with tiny content; a pointer stating 100 GB (hashed normally); a size above
2^53-1. A file that grows between `stat()` and the read (hash omitted, size from
`stat()`, no contradiction). `minimal` against `full` with a transparent source;
a fragment that supplies the missing hash or size (the negative entry goes) and
the comment merge followed by a drop (both covered by
`tests/assemble/test_fragments_evidence.py`). The document uuid does not change when an
entry is added. Byte-for-byte output across two runs and two listing orders.
Under the caps the output is identical to HEAD (a before and after sweep). A
reason outside the catalogue is rejected; injected `|`, `;` and a newline are
escaped.

## Risks, worst first

1. ~~The unit clash~~ (fixed, #382).
2. ~~A negative entry dropped in `minimal`~~ (fixed, #386).
3. ~~A merged SBOM that shows a hash and `not_measured` side by side: the merge
   must drop the entry when the merged element gains the property~~ (fixed,
   #386).
4. Evidence text reaching the document uuid.
5. Output that depends on the machine (a time budget, a partial sum).
6. A pointer's `stat()` size passed off as the content's.
7. A repeated key, or `provenance.update`, overwriting an entry.
8. ~~After a comment merge the second `Metadata provenance:` block is not found
   by the drop helpers (they strip the prefix only at the start of a line)~~
   (fixed, #386).
9. Drift in `docs/metadata-provenance.md` and the skills.
10. A file name forging an evidence segment (a `|` in it read as a segment
    separator, so the merge drop acted on a forged `Evidence: not_measured`)
    (fixed: sanitised, #386).

## The `AGENTS.md` rule

The rule below goes into `AGENTS.md` ("Design principles") with the first
implementing PR (sizes under a cap), not before: it binds every agent session,
and no code follows it yet.

```text
- **Caps bound reading, never reporting; every fact has an evidence level.**
  A size or time cap is for security and hangs only. Record the first
  available: **measured** (`stat()`, or a read within the caps);
  **declared** (archive header, LFS pointer, API) with its source, never
  passed off as measured; a **lower bound** (provenance only); else nothing,
  with provenance `not_measured` and why. A declared value never gates a cap
  or a read. Plan:
  [evidence-levels.md](working-docs/design/evidence-levels.md).
```

## Decisions

Decided 2026-10-29 unless marked. Each took the recommended answer.

1. **Words:** `Evidence:` and `Reason:` segments, not `Method:`.
2. **`lower_bound`:** in the SBOM as provenance only, carrying the budget.
3. **Walk budget:** entries only, one config key.
4. **byteSize:** adopt with the 3.1 binding; the value type carries the size
   now (`DatasetMetadata.byte_size` exists since #382).
5. **Declared hash:** stays in `verifiedUsing` with the comment and
   `Evidence: declared`.
6. **Segment, not a separate Annotation.**
7. **Merge:** generalise the drop helpers so a `not_measured` entry goes when
   the merged element gains the property; fix the comment-merge problem first
   (built, #386).
8. **Release placement of steps 0 and 1:** 0.22.0. Step 0 is done. [proposed]
