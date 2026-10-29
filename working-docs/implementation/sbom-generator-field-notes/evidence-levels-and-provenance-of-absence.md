---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: evidence levels and the provenance of absence

See also: [README.md](README.md) (index of these notes),
[evidence-levels.md](../../design/evidence-levels.md) (the design, its rules
and decisions), [git-lfs-pointers.md](../git-lfs-pointers.md) (the first
declared-only case),
[provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md)
(the same provenance strings as an attack surface),
[spdx-modelling.md](spdx-modelling.md).

What an SBOM should say about a fact the generator chose not to read, or
could not read. Work of 2026-10-28/29: PRs #378, #381, #382, #383 (the
design), #386 and #387; the `Fact` value type is in review (#391).

## 1. Caps bound reading, never reporting

- **A safety cap had been silently deciding what the SBOM says.** Pitloom
  caps the bytes it reads from a model (`max-model-extract-bytes`) and
  hashes of a dataset (`max-dataset-hash-bytes`); both got a CLI flag in
  #381 (the dataset one a `loom.run` keyword too). Over the cap the hash was
  simply missing, so "no hash" meant both "unknown" and "skipped on
  purpose".
  The rule adopted into `AGENTS.md` with #387: a size or time cap is for
  security and hangs only; if a property is known by a safe route, the
  SBOM states it, with its evidence level.
  Do: separate the read budget from the report; a cap removes a read, not
  a fact.
- **Five evidence levels, first available wins.** `measured_stat` (file
  system, no content read), `measured_read` (read within the caps; no
  segment, so the thousands of measured file hashes write nothing new),
  `declared` (archive header, LFS pointer, API, `Content-Length`, lock file,
  `RECORD`; never passed off as measured), `lower_bound` (a walk stopped at
  its budget: provenance only, never the partial sum, which depends on
  `os.walk` order) and `not_measured` with a `Reason:` that is a catalogue
  code (`over-cap`, `timeout`, `network-failed`, `lfs-pointer`,
  `unreadable-file`). Written as `Evidence:`/`Reason:` segments of the
  existing provenance string, not a new `Method:` value: the method says how
  a value was read, the level how sure it is, and the two vary
  independently (the Hub's parameter count is `Method: tensor_element_sum`
  and declared) ([evidence-levels.md](../../design/evidence-levels.md),
  decision 1).
- **A declared value may stop a read, never permit one.** A pointer stating
  100 GB is hashed like any file; a ZIP member declaring a size over the cap
  is skipped. A declared number is validated (non-negative, at most 2^63-1,
  and within the 2^53-1 the JSON reader allows) before it is recorded.
- **Network and time limits are caps too.** A download cap, a connect or
  read timeout and a total wait all leave a fact `not_measured` unless a
  declared value exists (the Hub API lists each LFS file's `oid` and size
  without a download). A clone over the size cap aborts the run, so its
  only record is stderr.

## 2. Provenance of absence

- **Provenance gained a second meaning: where a value could have come from,
  and why it did not.** A source's outcome is `used`, `unavailable` (the
  source has nothing), `refused` (policy stopped the read), `failed` (the
  read broke) or `declared_only`. Only the last three are written:
  `unavailable` is absent data and stays quiet, as the project's "absent is
  not an error" principle demands, so the SBOM does not fill with "this
  source had nothing". The same split was added to the extraction taxonomy
  as a row of its own (a2859bcd, #383).
  Do: record a deviation (refused, failed), not an absence.
- **A negative entry needs its own survival rules.** `minimal`, the default
  detail level, dropped any entry from a "transparent" source with no
  method, so `Source: hugging face hub | Reason: network-failed` vanished;
  now any entry with `Evidence:` is kept (#386). A fragment merge that
  supplies the missing hash must drop the `not_measured` entry, or the SBOM
  shows a hash and "not measured" side by side (#386). The drop helpers
  first missed a second `Metadata provenance:` block joined into a comment
  with `"; "` (found in review, fixed in #386).

## 3. One size property, two units

- **A record count sat in a bytes property.** A Croissant `cr:totalItems`
  became `dataset_size` and then `dataset_datasetSize`, which SPDX defines
  in bytes; a docstring and a skill reference even called it a "record
  count".
  `totalItems` is not a Croissant term at all (6136fafd). Found by the Opus
  review of the provenance code against the design (56df35fc), fixed in
  #382 before any byte size could be written beside it: the count is no
  longer read, `DatasetMetadata.byte_size` replaced `dataset_size`, and the
  missing count property became format gap FG-12.
  Do: before adding a second writer to a property, inventory what the
  first writer puts there and in which unit.
- **SPDX 3.0.1 has a size for datasets only; 3.1-dev has one for every
  artefact.** 3.0.1: `dataset_datasetSize` on `dataset_DatasetPackage`, no
  size on files or models (FG-9). The 3.1 development branch has `byteSize`
  (one non-negative integer) on `SoftwareArtifact` and marks `datasetSize`
  deprecated. Until the 3.1 binding a size goes in the `Hash` comment (LFS
  pointers) or `datasetSize`; the evidence level itself has no SPDX
  property in either version (FG-13).
- **The first end-to-end case: a single-file dataset over the cap (#387).**
  The size comes from the `stat()` already made at the cap check
  (`measured_stat`); the omitted hash says `Evidence: not_measured |
  Reason: over-cap`. A file under 1,024 bytes over the cap gets no size and
  a `not_measured` size entry, because it may be a Git LFS pointer, whose
  own size is not the content's (a review finding, b0c89dd2). Directories
  wait: their pointer files stat at about 130 bytes, so one sum would mix
  levels.

## 4. What the review changed in the design

- **A wheel model over the cap already has a measured hash.** The design's
  "today" table lists "name the declared ZIP size" as a gap for a wheel
  model stub over `max-model-extract-bytes`. The wheel reader hashes every
  member in 8 KiB chunks with no extract cap
  (`extract/wheel.py::_hash_wheel_entry`), so the model's file entry is
  `measured_read`, and its byte count is measured in the same pass
  (`FileDigests.size`, discarded until 3.1 `byteSize`). A declared size
  adds nothing either: `zipfile` checks the CRC and stops a member whose
  header lies about its size (`identity-and-archives.md`, #263). The
  correction came from a review pass (session record); the design table
  still shows the gap.
  Do: before adding a "declared" route, check whether a measured route
  already reaches the same fact.
