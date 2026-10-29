---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Evidence levels: measured, declared or not recorded

See also: [roadmap.md](roadmap.md) (the summary bullet),
[sbom-format-gaps.md](sbom-format-gaps.md) (FG-9 to FG-11),
[the taxonomy](generation-gaps-extraction-and-recording.md) this extends,
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

**Why a fact can be `not_measured`.** The cap on reading is one reason. For a
remote artefact the bytes may never arrive, and then nothing can be measured at
all:

| Reason | Example | Catalogue code (proposed) |
| - | - | - |
| Read cap | a model over `max-model-extract-bytes` | `over-cap` |
| Download cap | a clone stopped at the size limit (`git.too-large`); a file too big to fetch | `over-cap` or `download-cap` |
| Wait too long | a network timeout, a slow server | `timeout` |
| Not reachable | a refused or failed fetch, an unreachable host | `network-failed` |
| Not resolved | an unpulled Git LFS file (only the pointer arrived) | `lfs-pointer` |
| Not readable | a permission error, a vanished file | `unreadable-file` |

In every case the declared route is still open: a remote API or a pointer often
states the size and hash of something Pitloom did not download (the Hub API
lists each LFS file's `oid` and size; a pointer states both; a server may send
`Content-Length`). Record that as `declared` with its source, and the reason the
bytes are absent as the provenance of the missing `measured` value.

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
5. **Time and network limits are caps too.** A download size cap, a connect or
   read timeout and a total wait are security limits like the read cap: they
   bound what Pitloom waits for and never what it reports. A fetch that times
   out is `not_measured` with the reason `timeout`, unless a declared value
   exists. **A walk is bounded too.** Summing the sizes of a directory with a
   million entries can hang on `stat()` alone; give it an entry or time budget,
   and let an exhausted budget produce a `lower_bound`.
6. **`not_measured` is a deviation, not absence.** Absent source data stays
   quiet (a field the source lacks). A fact left unread by policy is a
   `WARNING:` (as the cap warnings already are) and a provenance entry.
7. **The same code in both places.** The provenance names the catalogue code the
   warning carries, so the SBOM, stderr and the skills' explanation agree.

## Provenance of absence

Provenance has meant "where this value came from". It now also says where a
value *could* have come from and could not, and why. The taxonomy grows from one
winning source per field to an account of the sources considered:

| Outcome of a source | Recorded? | Example |
| - | - | - |
| `used` | yes, as today | the value read from `config.json` |
| `unavailable`: the source has nothing | no (absent data stays quiet) | a bare Safetensors file has no version |
| `refused`: policy stopped the read | yes | over the read, download or time cap |
| `failed`: the read or fetch broke | yes | a timeout, a refused connection, a vanished file |
| `declared_only`: only a statement of it reached us | yes, as the value, with its source | a pointer's oid and size |

Only the `refused`, `failed` and `declared_only` outcomes are written down: they
are deviations, while `unavailable` is not, so the SBOM does not fill with "this
source had nothing". The entry carries a closed `Reason:` code (the catalogue
code), never raw server or exception text, which is attacker text. Rules:

1. **One entry per field and reason**, not per file: "model_author: 3 files
   `not_measured` (over-cap)" beats three lines.
2. **A negative entry survives the minimal detail level** where the fact it
   replaces would have: a reader of a minimal SBOM must still see that a hash is
   missing on purpose.
3. **It is machine-readable:** the same `Source:`, `Field:`, `Method:` segments,
   with `Method: not_measured` and `Reason: <code>`; the sanitiser for untrusted
   text applies to every segment.
4. **The order of sources is part of the record** when more than one was
   considered, so a reader can see the cascade, not only its winner.

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
| Git source, clone stopped at the size cap | the run is refused (`git.too-large`) | none per file; the reason is the run's |
| Git source, LFS file not pulled | `declared` (pointer), content not read | the level is not named in the provenance |
| Hub source, file size and hash | not read from the API | the API states them: `declared` |

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
4. Release placement of step 1, and whether the remote `declared` sources (Hub
   API sizes, `Content-Length`) are in the first step or the second.
5. Whether a declared hash may sit in `verifiedUsing` at all (FG-10).
6. Whether a negative entry is a separate annotation or a segment of the
   field's existing provenance string, and how it behaves in `minimal` detail.
