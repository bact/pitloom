---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Evidence levels: how Pitloom records a fact it measured, was told, or could not get

See also: [roadmap.md](roadmap.md) (the summary bullet),
[sbom-format-gaps.md](sbom-format-gaps.md) (FG-9 to FG-11),
[known-bugs.md](known-bugs.md),
[git-lfs-pointers.md](../implementation/git-lfs-pointers.md) (the first case),
and `message-catalogue-and-skills.md` in this folder once it is merged (the
codes used below).

Status: draft 2026-10-29; the decisions at the end are open.

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
| `measured` (stat) | Taken from the file system without reading content | the value; provenance `measured_stat` |
| `measured` (read) | Computed by reading the content within the caps | the value; provenance `measured_read` |
| `declared` | Stated by metadata and not checked: an archive header, an LFS pointer, a Hub API response, `Content-Length`, a lock file, `RECORD` | the value; provenance `declared`, naming the source |
| `lower_bound` | A read stopped at the cap: "at least N" | provenance only; the exact-integer property stays unset |
| `not_measured` | Not safe to read, and nothing declared | no value; provenance `not_measured` with the reason (the catalogue code, e.g. `over-cap`) |

Reading is not the only way to measure: `stat()` is safe for any regular file,
so a size is available even when the content is over the cap.

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
4. **A declared value is never compared with a cap and never decides what is
   read.** (A pointer stating 100 GB is hashed like any other; the cap counts
   real bytes.)
5. **A walk is bounded too.** Summing the sizes of a directory with a million
   entries can hang on `stat()` alone; give it an entry or time budget, and let
   an exhausted budget produce a `lower_bound`.
6. **`not_measured` is a deviation, not absence.** Absent source data stays
   quiet (a field the source lacks). A fact left unread by policy is a
   `WARNING:` (as the cap warnings already are) and a provenance entry.
7. **The same code in both places.** The provenance names the catalogue code the
   warning carries, so the SBOM, stderr and the skills' explanation agree.

## Where each level lands in SPDX

- **Datasets:** `dataset_datasetSize` exists in SPDX 3.0.1.
- **Files and models:** SPDX 3.0.1 has no size property (FG-9). SPDX 3.1-dev has
  a `byteSize` property on `SoftwareArtifact` and its subclasses (maintainer,
  2026-10-29; to verify against the spec text when the binding moves). Until
  then the size goes in a `Hash` comment (as for Git LFS pointers) and in the
  ledger. Hashes follow the same levels: a declared hash is stated as declared
  (FG-10).
- **Provenance:** the existing `Source: ... | Field: ... | Method: ...`
  annotations and comments carry the level.

## Today (audited 2026-10-29)

| Fact | Today | Gap |
| - | - | - |
| File hash, project files | `measured_read` | none |
| Git LFS pointer hash and size | `declared` (oid, stated size), content not read | the provenance says `lfs_pointer`, not the level |
| Dataset hash | `measured_read`; over the cap: omitted with a warning | none |
| Dataset size | not reported unless the user supplies it, although `stat()` is already called for the cap check | report `measured_stat`, also when the hash is omitted |
| Model over the cap | a stub with a warning; no size | the declared ZIP size is in memory and could be named |
| Directory size | not reported | a bounded walk |

## Scope and order

1. **Sizes under a cap (proposed 0.22.0).** Dataset size from `stat()` or a
   bounded walk, reported when the hash is omitted; the declared size in the
   over-cap warning and stub; the FG-9 note updated.
2. **The provenance vocabulary and the value type.** A small value type holding
   the value, its basis and its source, built by extractors and written by the
   SBOM emitter into the provenance already attached. Hashes move onto it.
3. **The catalogue codes in the provenance**, once the `lfs-pointer` and
   `over-cap` families exist.
4. **When the binding moves to SPDX 3.1:** `byteSize` for files and models.

## Tests

For every fact: a measured, a declared, a lower-bound and an absent case; two
lies (declared small and actual huge; declared huge and actual small); a
declared value out of range; a walk that runs out of budget; the declared
source order. A before and after guard shows nothing changes for an artefact
under the caps.

## Open decisions

1. The shape of the value type and the exact provenance words.
2. Whether `lower_bound` appears in the SBOM or only on stderr.
3. The budget for a directory walk (entries, time, or both).
4. Release placement of step 1.
5. Whether a declared hash may sit in `verifiedUsing` at all (FG-10).
