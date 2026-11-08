---
Created: 2026-10-03
Last-Modified: 2026-11-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs, by priority and category

See also: [roadmap.md](roadmap.md),
[id-registry-v3.md](../implementation/id-registry-v3.md),
[id-registry-followups.md](id-registry-followups.md),
[canonical-output-followups.md](canonical-output-followups.md) (open
canonicalisation questions behind several bugs here). The entries are in the
parts under [known-bugs/](known-bugs/), listed below.

Bugs found up to #286, each reproduced on `main` unless marked
otherwise. Features and design work stay in the roadmap. A fixed item
stays ticked, with its PR, until its release ships, then moves to
[roadmap-completed.md](../implementation/roadmap-completed.md).
Size: S under half a day, M about a day.

## Planned releases (decided 2026-10-30)

- 0.22.1 (released 2026-11-03, #413-#433): small remaining bug fixes. (The
  path-in-message fix, #410, landed before the 0.22.0 tag.) Also re-run the
  0.22.0 release checks that were left to CI (decided 2026-10-30): the full
  manual CLI checks, the CHANGELOG-against-merged-PRs cross-check, the
  coverage-snapshot diffs and the `scripts/` lint; fix what they find. Re-run
  2026-11-02: see
  [Release checks re-run](known-bugs/process-tooling-and-release-checks.md#release-checks-re-run-2026-11-02).
- 0.23.0 (released 2026-11-05, #434-#446): the LicenseID 0.7.0 adoption
  (#437 to #440, the final gate #443), the catalogue plan refresh (#442) and
  catalogue PRs 2b, 1b and 1c.
- 0.23.1 (released 2026-11-07, #450-#455): LicenseID 0.7.2's short-text notice
  at `DEBUG`; its licence titles and aliases read as ids (#455).
- 0.23.3 (released 2026-11-07, #457-#459): a declared licence name quiet with
  no LicenseID database (#458); LicenseID 0.7.3's Apache name readings (#459).
- 0.24.0: the uniform `loom <command>:` frame, catalogue PRs 3 to 18
  (licence included), the licence provenance mapping
  ([licence-resolution-provenance.md](licence-resolution-provenance.md)) and
  `--report`/SARIF. See
  [message-catalogue-migration-plan.md](message-catalogue-migration-plan.md).

## Open entries by part and priority

Counts of open entries (a ticked entry is counted under Fixed). Each part
lists its open entries first, ranked as described under
[Severity scale](#severity-scale), then its fixed entries.

| Part | P0 | P1 | P2 | P3 | Found | Leads | Open | Fixed |
| - | -: | -: | -: | -: | -: | -: | -: | -: |
| [AI model readers and metadata](known-bugs/ai-models-readers-and-metadata.md) | - | - | - | 33 | 5 | - | 38 | 10 |
| [Licences and LicenseID](known-bugs/licences-and-licenseid.md) | - | - | 2 | 3 | 9 | - | 14 | 14 |
| [ID registry and identity](known-bugs/id-registry-and-identity.md) | - | 3 | - | - | 10 | 1 | 14 | 11 |
| [Messages, catalogue and provenance](known-bugs/messages-and-provenance.md) | - | - | - | 2 | 18 | - | 20 | 15 |
| [Remote sources, Git LFS and datasets](known-bugs/remote-sources-lfs-and-datasets.md) | - | - | - | - | 12 | - | 12 | 7 |
| [Extraction, fragments and merge](known-bugs/extraction-and-fragments.md) | 1 | - | 3 | 8 | 9 | - | 21 | 11 |
| [CLI, Action, hook and wheel](known-bugs/surfaces-hook-and-wheel.md) | - | - | - | 7 | 2 | 2 | 11 | 5 |
| [Process, tooling and release checks](known-bugs/process-tooling-and-release-checks.md) | - | - | - | 2 | 10 | - | 12 | 9 |
| **Total** | **1** | **3** | **5** | **55** | **75** | **3** | **142** | **82** |

Open = the `- [ ]` entries plus the Leads, which are plain bullets with no box;
Fixed = the `- [x]` entries. The P and Found columns count `- [ ]` entries only.

## Parts

- [AI model readers and
  metadata](known-bugs/ai-models-readers-and-metadata.md): AI model files
  (GGUF, ONNX, PyTorch PT2, Keras and HDF5, Safetensors, fastText, CRFsuite,
  NumPy): what each reader records, what the SBOM shows of it, and how
  metadata is escaped, capped and spelt across formats.
- [Licences and LicenseID](known-bugs/licences-and-licenseid.md): Licence
  detection, declared and concluded licences, the LicenseID resolver and
  database, licence elements and their provenance.
- [ID registry and identity](known-bugs/id-registry-and-identity.md): Stable
  ids: ID registry keys, harvest and lookup, document and entity identity,
  `Agent` elements.
- [Messages, catalogue and provenance](known-bugs/messages-and-provenance.md):
  Message wording and codes, the message catalogue migration, and provenance
  strings and annotations.
- [Remote sources, Git LFS and
  datasets](known-bugs/remote-sources-lfs-and-datasets.md): Git and Hugging
  Face sources, Git LFS pointers, dataset size and hashing, and the size
  ceilings and clone cap.
- [Extraction, fragments and merge](known-bugs/extraction-and-fragments.md):
  Reading project, environment, lock-file and installed-package metadata;
  dependency versions and direct references; fragments and `loom merge`; the
  model-usage scan.
- [CLI, Action, hook and wheel](known-bugs/surfaces-hook-and-wheel.md): The
  surfaces (CLI, GitHub Action, library, Hatchling hook) and wheel handling:
  options, output paths, signals and platform differences.
- [Process, tooling and release
  checks](known-bugs/process-tooling-and-release-checks.md): CI, test layout,
  linters, release reproducibility and the release-check records.

## Severity scale

The earlier single file never defined a severity scale. This one is built from
the tags the entries already carry, and no entry was re-ranked when the file
was split (2026-11-02). Inside a part, an entry sorts by its priority tier,
then by its size tag, then by its place in the earlier file.

Priority tier, highest first (the section an entry sat in):

| Tier | Meaning |
| - | - |
| P0 | In 0.21.0 |
| P1 | Registry v3 in 0.21.0 (some built, some not) |
| P2 | 0.21.0 and later |
| P3 | After 0.20.0 |
| Found | Recorded in a review round with no P level yet; to be triaged into P0 to P3 |
| Leads | Seen in past sessions, not reproduced on current `main` |

Size tag inside the entry, the only finer signal the entries carry. It
states effort, not harm, and it orders entries only within a tier:

| Tag | Order | Meaning |
| - | -: | - |
| M | 1 | About a day |
| S-M | 2 | Between the two |
| S | 3 | Under half a day |
| doc | 4 | A documentation or layout fix |
| low, cosmetic, idea | 5 | Minor, or not yet a decided fix |
| none | 6 | The entry states no tag |

## Adding an entry

1. Pick the part by what the bug touches (see [Parts](#parts)). A bug
   between two parts goes where its fix would land; mention the other part
   in the entry.
2. Add it under that part's **Open** section, in the tier it belongs to. A bug
   with no priority yet goes under *Found in review rounds, not yet
   prioritised*, and its last line, in italics, gives the date and the review
   (`*Found 2026-11-02, PyPI 0.22.0 verification.*`).
3. Write it as `- [ ] **Title (size).** Text.` with the size tag S, S-M or M
   (or `doc`); keep it reproduced on `main`, or put it under *Leads to
   verify*. Keep entries in tag order inside the tier.
4. When it is fixed, tick it (`[x]`), name the PR, and move it to the same
   tier under **Fixed** in the same part. Do not delete it. It moves to
   [roadmap-completed.md](../implementation/roadmap-completed.md) when its
   release ships.
5. Update the counts in the table above, and the part's own scope line if
   the part now covers something new. Keep each part under about 350 lines;
   split a part by topic before it grows past that.

## Notes from the earlier layout

The entries of 2026-10-30 came with this scope note, kept as written ("above"
meant the earlier sections of the old single file):

> From the 0.22.0 rounds (#404 to #408). Open; items the rounds already
> recorded above are not repeated (the `loom env` and private-index lookups, a
> direct reference's version and PURL, the silent skip, and the Hugging Face
> key rules).
