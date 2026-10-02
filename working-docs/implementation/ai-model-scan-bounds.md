---
Created: 2026-10-01
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scan bounds

See also: [ai-model-scanning.md](ai-model-scanning.md) (the scanner design
these bounds belong to),
[ai-model-scan-security-lessons.md](ai-model-scan-security-lessons.md) (the
review rounds, with measurements),
[model-metadata-readers.md](../design/model-metadata-readers.md) (the planned
header-only readers) and `docs/ai-model-scan-limits.md` (the user-facing
caps).

What bounds a model reader before and while it runs: the inner-member read
cap, the header, opcode and entry bounds, the ZIP central-directory check, the
audit that every cut says so, and what the bounds leave open.

## Inner members

Read bounded (`extract/ai_model/archive_member.py`).
A model archive (`.keras`, `.pt`, `.pt2`) is untrusted, and a few KiB of
deflate inflate to gigabytes, so every reader reads a metadata member
(`config.json`, `data.pkl`, `model.json`, the PT2 `extra/` files, an `.npy`
v3 header length) through `read_archive_member()`: `read(CAP + 1)`, reject
when longer. `CAP` is 8 MiB: these members are KiB to a few MiB even for a
model with thousands of layers, and nothing Pitloom reads needs more. A
`.pt` `data.pkl` is read into a `BytesIO` of at most `CAP` for fickling
(whose `Pickled.load` would `read()` a non-seekable stream whole, and
allocates what a `BINBYTES8` header claims). The error is an
`ArchiveMemberTooLarge`, not a `ValueError`, so each reader's broad
`except` lets it through; the scanner logs one `archive member X larger
than N bytes; metadata not read` and keeps the stub. It applies to project
scans too: same readers.

## Bounds before a parser runs

- **Parsers** (project scans too; all raise
  `ModelLimitExceeded`, which a reader's broad `except` lets through; the
  scanner logs one `FORMAT= FILE=: <reason>; metadata not read` and keeps the
  stub). Pickle (`_pickle_bounds.py`, an adapter over
  `formats/pickle_walk.py`): Pitloom's own walker goes through
  `pickletools.opcodes` (no per-opcode state), refuses more than 250k, and
  only the bytes of the first pickle reach fickling. It replaced
  `pickletools.genops`, which calls `int()` on the decimal text of `INT`,
  `LONG`, `GET` and `PUT` before yielding: the bound came too late (quadratic with
  `PYTHONINTMAXSTRDIGITS=0`: 3.4 s for one 1M-digit `LONG`, about 4 min
  extrapolated at the 8 MiB member cap; 0.034 s at 100k digits), and with the
  default limit a number over 4300 digits was reported as a malformed pickle, so
  the outcome depended on interpreter configuration. The walker finds a decimal
  argument with a bounded `readline(4303)` and never converts it, and refuses a
  number over 4300 digits (sign, `L` and whitespace not counted, as CPython's
  `int_max_str_digits` counts) as `ModelLimitExceeded`; a decimal argument of
  more than 4302 bytes with fewer digits is refused too. Measured: a 1M-digit
  `LONG` is refused in about 25 microseconds with the limit off; 8 MiB of
  4300-digit `INT`s (1949 opcodes) walks in 4.5 ms against 127 ms for `genops`.
  The first plan capped at 4302 bytes, believing everything shorter converts
  under the default limit. Verified false: a 4301-digit unsigned `INT` (4301
  bytes) and a 4301-digit `LONG` (4302 bytes) fit, yet the default limit rejects
  them, so the outcome would still have depended on the setting. The cap counts
  digits (decided 2026-10-02); the 4302-byte window only bounds the scan. A
  model pickle uses `BININT*`/`LONG1` (protocol 2 and later), and a protocol 0
  integer of a model has at most about 20 digits; the cost is that a protocol 0
  pickle with a number over 4300 digits, accepted before under
  `PYTHONINTMAXSTRDIGITS=0`, is now refused. A drift-guard test checks the
  walker against `genops` on protocols 0-5 and both fixture `data.pkl` files;
  `formats/` is stdlib only (see
  [model-metadata-readers.md](../design/model-metadata-readers.md)).
  fickling's stderr (it prints per failure, 62 MB
  in one measured case) is captured, per thread, by a process-wide `sys.stderr`
  proxy (`_stderr_capture.py`, installed under a lock; the capturing threads,
  not a counter, say whether it is in use, and an interrupt at any step of a
  block undoes only what that block did, by identity, like the log capture
  below; `contextlib.redirect_stderr` swaps the stream for every thread and,
  with two overlapping, could leave it swapped for good) into a bounded sink and
  summarised in one warning. GGUF (`_gguf_bounds.py`): a `struct` walk over the
  key/value section refuses tensors, pairs and array elements over one weighted
  budget of 1M, arrays nested deeper than the walker follows, or a count that
  cannot fit in the file, before `GGUFReader`; a merely truncated file, or a
  version `GGUFReader` itself rejects, is left to the reader, while a version it
  reads and the walker does not know (round-4 review, fail closed) is refused.
  Safetensors (`safetensors.py`): the 8-byte header length is read first and
  refused over 16 MiB (`MAX_SAFETENSORS_HEADER_BYTES`). Detection (magic only,
  which matters for an explicit path without the suffix) uses the format's own
  limit, `SAFETENSORS_FORMAT_MAX_HEADER_BYTES` = 100,000,000, kept beside it
  (it was `_SAFETENSORS_MAX_HEADER` in `reader.py`). The cap stays below the
  format limit so a header between the two is detected and refused with its
  size, not called "Unsupported model format". The library's limit is
  inclusive (0.8.0: a declared 100,000,000 is "invalid header length", past the
  size check; 100,000,001 is "header too large"), so detection changed from
  `< 100_000_000` to `<= 100_000_000`, a one-byte boundary change.
  NumPy (`numpy.py`): the `.npy` header length field is
  read first and refused over numpy's own 10000 (numpy reads the declared length
  before checking it: a v2 header declaring 4 GiB in a 48 MiB deflated member
  inflated it), and an `.npz` stops reading after 1001 members. Entry caps
  (`limits.cap_entries()`, in the scanner, so one place for every reader): the
  first 1000 of `inputs`, `outputs`, `hyperparameters`, `properties` and
  `raw_metadata`, the provenance of the dropped keys removed, one warning naming
  the fields cut. "First" is the order the reader hands over, so it must be the
  same on every run. Surveyed (round 5): GGUF fields, ONNX `metadata_props` and
  graph inputs, Keras/PT2 JSON, HDF5 attributes, `.npz` member names and
  fastText labels all come from the file in file order. The one exception was
  Safetensors: `safetensors` returns `__metadata__` from a Rust hash map, in an
  order that differs per process (`keys()`, the tensor names, is stable), so a
  file over the cap gave a different SBOM on every run. `read_safetensors()` now
  keeps the 1001 smallest keys, in key order, with `heapq.nsmallest` (one past
  the cap, so `cap_entries()` still cuts and warns, as for `.npz`). Under the
  cap nothing is reordered: every consumer sorts (the annotation is JCS,
  hyperparameters and provenance are sorted). Rejected: sorting every map in
  `cap_entries()` (a reader with a file order would lose it for nothing), and
  sorting a map at or under the cap. The cut applies only to what is kept as
  `properties`/`raw_metadata`: the well-known keys (`modelspec.title`, `name`,
  `format`, ...) are read from the whole map first, or a key sorting past the
  cut lost the model its name. `loom model FILE` and `loom enrich FILE` apply
  the same cap through the same `limits.cap_and_warn()` the scanner calls
  (they kept 1001 entries, silently, before).
- **ZIP central directory** (rounds 5b, 5c). Keras, PT2, PyTorch zip and `.npz`
  open the archive with `zipfile`, which builds a `ZipInfo` (~600 B) per
  entry before any reader looks at one: a `.keras` of 3 million empty entries,
  16 MiB in a wheel, peaked at 1.8 GB. Round 5b parsed the end record itself
  and trusted its counts; round 5c's review showed it disagreed with `zipfile`
  on which end record applies (a ZIP64 record found through the locator's
  offset behind extensible data, a signature inside the end record's own
  fields, Python 3.10's wider search window than 3.14's), and that `zipfile`
  ignores the counts and walks the directory by its byte size. Now
  `archive_member.check_zip_bounds()` asks `zipfile._EndRecData` (what `ZipFile`
  itself calls) for the directory's size and the end record's position,
  refuses a directory over 25,600,000 bytes, then walks it header by header
  as `_RealGetContents` does (start = end record position - directory size, so
  prepended data is handled; stop at the byte size) and refuses at the
  100,001st entry. A header that is not one, or is cut short, refuses too
  (`malformed ZIP central directory`): a disagreement with `zipfile` about
  where the directory is must never read as "within the cap". For ZIP64
  there are two conventions among releases of one Python version: with the
  CVE-2025-8291 fix (3.10.19, 3.11.14, 3.12.12, 3.13.12, 3.14.7) `_EndRecData`
  reports the ZIP64 record's position; without it (3.11.9, CI's Windows leg)
  it stays the plain end record's and `_RealGetContents` takes 76 bytes off
  (`sizeEndCentDir64 + sizeEndCentDir64Locator`). `_zip64_start_shift()` asks
  the running `zipfile` through a minimal ZIP64 archive built in memory, on
  each check (no cache, so it cannot go stale); an answer that is neither
  convention fails closed. One handle is opened, checked and handed to `ZipFile` /
  `numpy.load` (`open_model_zip`, `open_model_binary`), so the checked file is
  the read file. A missing or odd `_EndRecData` (a private API) fails closed:
  `ModelLimitExceeded`, a stub and one `WARNING:`; a test pins its shape and
  the arithmetic in the running interpreter's source. Rejected: our own end
  record parser (3.10 and 3.14 already differ), reading the counts.
  A wheel scan also asks `reader_requirements.require_library()` before it
  copies a model, so a missing reader library no longer costs a copy.
- **Nothing recorded is lost silently** (round-5 audit). Every cap, bound and
  gate has one `INFO:`/`WARNING:`: ceiling, budget, member, pickle, GGUF,
  Safetensors, `.npy` bounds, the entry cap, the wheel gate, the usage hint
  and the usage-scan caps. Two cuts had none. The unparsed HDF5 `model_config`
  cut to 500 characters now warns when it is longer (rare: only a config that
  failed to parse). The
  20-name `archive_contents` of a PyTorch classic or PT2 archive does not: a
  checkpoint has a file per tensor, so nearly every real model would warn,
  and the value ends `, ... (<N> total)` itself. Not warned, by design: the
  fickling stderr quote (a diagnostic, not recorded data), the first pickle
  only (the rest of a legacy file is not model metadata) and the
  artifact-metadata cap (opt-in, marked `truncated` in the output). The
  settings that change the output are listed in
  `docs/ai-model-scan-limits.md`.

## What the bounds do not cover

Not covered, by design, until the metadata-only readers
([model-metadata-readers.md](../design/model-metadata-readers.md)):

- **GGUF CPU.** `gguf.GGUFReader` loops in Python once per tensor, key/value
  pair and array element (scalar or string, at any nesting depth), keeping a
  numpy view for each: ~1.1 KiB and 6 us per string, ~0.5 KiB per scalar,
  ~3.5 KiB per tensor or pair. The walker charges all of them to one budget of
  1M (a tensor or pair weighs 4, an element 1) and refuses nesting deeper than
  it follows, so a hostile header is refused in well under a second; the
  largest accepted headers measured ~1.1 GB and 6 s (990k strings, 8 MB),
  ~0.9 GB and 8 s (250k tensors, 10 MB), ~0.6 GB (250k pairs), ~0.5 GB
  (990k scalars). Before the combined budget, 12 x 1M uint8 elements (12 MB)
  peaked at 5 GB, arrays nested 5 deep were not followed by the walker but
  were by the reader (24 MB, 3.3 GB), and 1M tensor infos (39 MB) took 3.6 GB.
  A real vocabulary plus merges is ~0.5M elements, so the budget cannot drop
  further without stubbing real models. GGUF is also gated in a wheel. Replacing
  `GGUFReader` with our own key/value reader, which makes the walker
  unnecessary, is part of the metadata-only readers
  ([model-metadata-readers.md](../design/model-metadata-readers.md)).
- **Pure-Python amplification.** fickling builds an AST per opcode (~200x the
  pickle's size): a pickle at the 250k-opcode cap measured ~100 MB and 0.4 s. The
  safetensors `__metadata__` and ONNX readers build their result before the
  entry cap cuts it, so the cap bounds the SBOM, not one reader's peak
  memory. `cap_entries()` rebuilds a capped map instead of deleting keys
  (a dict never shrinks its table): a wheel of 24 Safetensors files with a
  16 MiB `__metadata__` each peaked at 5.8 GB, then at 1.06 GB (951 / 1060 /
  1062 MB for 1 / 8 / 24 files, round-5 review), and now at 0.53 / 0.57 /
  0.58 GB: the Safetensors reader cuts the map to the entry cap itself (see
  "Entry caps"), so the full map is not copied into `properties`,
  `raw_metadata` and provenance. A wheel's peak is its largest model's, not
  the sum of its models'.
- **Safetensors header.** The 8-byte length is read before `safe_open` and
  refused over 16 MiB (the library allows 100 MB; a 34.9 MB header peaked at
  1.7 GB above baseline, a 15.7 MB one at 0.8 GB, the bound's worst case).
- **Native readers.** libhdf5, protobuf (ONNX) and fastText are gated in a
  wheel, not bounded; a project scan runs them on the user's own tree.
  Under `--trust-wheel-model` a hostile wheel can crash or hang them
  (measured: a 16 MiB ONNX of empty inputs peaked at 3 GB; of two 8 KiB
  HDF5 files mutated from a valid `.h5`, one segfaults and one never
  returns).
