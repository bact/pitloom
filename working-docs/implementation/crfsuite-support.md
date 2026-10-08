---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CRFsuite model support

Status: built in PR #294; the decisions below are what was built.
Summarised in [roadmap.md](../design/roadmap.md) as one bullet linking here.
Step-by-step plan: [crfsuite-implementation-plan.md](crfsuite-implementation-plan.md).

See also: [crfsuite-implementation-plan.md](crfsuite-implementation-plan.md),
[model-metadata-readers.md](../design/model-metadata-readers.md) (the
stdlib-only `formats/` subpackage this reader is built in),
[model-metadata-extraction.md](../design/model-metadata-extraction.md) (planned
formats table),
[model-file-metadata.md](sbom-generator-field-notes/model-file-metadata.md)
(what model files carry, measured).

## Why

PyThaiNLP bundles five CRFsuite models and Pitloom detects none of them:

| File | Labels | Attributes | Features | Loaded by |
|---|---|---|---|---|
| `thainer_crf_1_5_1.model` | 26 (`B-PERSON`, `I-DATE`, ...) | 15,741 | 25,067 | `tag/thainer.py` |
| `sentenceseg_crfcut.model` | 2 (`I`, `E`) | 36,428 | 61,280 | `tokenize/crfcut.py` |
| `crfchunk_orchidpp.model` | 9 (`B-NP`, `I-VP`, ...) | 9,045 | 18,717 | `chunk/crfchunk.py` |
| `han_solo.crfsuite` | 2 (`1`, `0`) | 2,715 | 4,957 | `tokenize/han_solo.py` |
| `blackboard-cls_v1.0.crfsuite` | 3 (`B_CLS`, ...) | 25 | 43 | none (orphan since PyThaiNLP #1024) |

All five are loaded with `pycrfsuite.Tagger` from
[python-crfsuite](https://github.com/scrapinghub/python-crfsuite), the
binding to [CRFsuite](https://www.chokkan.org/software/crfsuite/). Counts
were read with a pure-Python header reader, no CRFsuite library.

## On-disk format (verified on the five files)

Little-endian throughout. A 48-byte header, `struct` `<4sI4sIIIIIIIII`:

| Offset | Field | Observed |
|---|---|---|
| 0 | magic | `lCRF` |
| 4 | size | equals the file size |
| 8 | type | `FOMC` (first-order Markov CRF, the only type CRFsuite writes) |
| 12 | version | 100 |
| 16 | num_features | always 0: the writer never sets it; the count is `FEAT.num` |
| 20 | num_labels | as in the table |
| 24 | num_attrs | as in the table |
| 28-44 | offsets of `FEAT`, labels, attributes, `LFRF`, `AFRF` | ascending, inside the file |

Chunks and CQDB records: next section.

### Byte layout in detail

All integers are little-endian `uint32`, written byte by byte
(`crf1d_model.c` `write_uint32`, not host order).

Header, 48 bytes, struct `<4sI4sIIIIIIIII`: `magic` `lCRF`, `size`,
`type` `FOMC`, `version` 100, `num_features`, `num_labels`, `num_attrs`,
`off_features`, `off_labels`, `off_attrs`, `off_labelrefs`,
`off_attrrefs`. Chunks follow in exactly that order: `FEAT`, labels
`CQDB`, attributes `CQDB`, `LFRF`, `AFRF`; on every file seen, each chunk
ends where the next starts and `AFRF` ends at `size`.

- `FEAT`: `<4sII` tag, size, num; then `num` records of 20 bytes, so
  `size == 12 + 20 * num`.
- `CQDB`: 24-byte header `<4sIIIII` = tag, `size` (whole chunk, header
  included), `flag`, `byteorder` (`0x62445371`), `bwd_size`, `bwd_offset`;
  then 256 table refs `{offset, num}` (2048 bytes; `num` is two buckets per
  record, and CRFsuite sizes its backward array as `sum(num / 2)`, so a lying
  ref makes it read past its buffers: the reader checks them); records start
  at `OFFSET_DATA = 2072`, so a CQDB is never smaller, even when empty. A record is `<iI` id, `ksize` (string length **plus
  the NUL**), then the key bytes and the NUL. Then the hash tables, then the
  backward array: `bwd_size` uint32 record offsets indexed by id. **All
  CQDB offsets are relative to the CQDB chunk start**, not the file.
- `LFRF`/`AFRF`: `<4sII` tag, size, num; then offsets and per-item lists.
  `AFRF.num == num_attrs`; `LFRF.num` is `num_labels + 2`, as the writer
  opens it (`crf1dmw_open_labelrefs(writer, L+2)`, `crf1d_encode.c`):
  bound it (its offset array fits before `AFRF`), do not compare it with
  `num_labels`.

### Traps

What the layout above makes easy to get wrong. The
[implementation plan](crfsuite-implementation-plan.md) cites these by
number.

1. **`header.num_features` is always 0.** The writer never sets it. The
   real count is `FEAT.num`.
2. **CRFsuite validates almost nothing.** Its loader checks only that the
   file is over 48 bytes; python-crfsuite adds a magic check. It ignores
   `size`, `type`, `version` and trailing bytes, and **segfaults** on a bad
   label offset, a wrong byte-order mark or an inflated `num_labels`
   (measured). "As lenient as CRFsuite" is not a goal; every bound below is
   ours.
3. **Record offsets are chunk-relative; `ksize` counts the NUL.** Off by
   the chunk offset or by one byte reads garbage that still looks like a
   string.
4. **Label order is meaningful.** Ids are assigned in first-seen training
   order; the backward array is indexed by id. Keep that order; never sort
   labels (determinism comes from the file, not from sorting).
5. **Labels are bytes.** CRFsuite does no encoding; python-crfsuite writes
   UTF-8 but accepts `bytes` labels, and then cannot load the model it
   wrote (`UnicodeDecodeError`). Decode with
   `errors="backslashreplace"`: never crash, never guess an encoding.
6. **An embedded NUL truncates** in CRFsuite (C strings). Take the bytes
   before the first NUL, as CRFsuite does.
7. **Zero labels and zero attributes are valid on disk** (an empty training
   set saves). `bwd_offset` is 0 when a CQDB has no records.
8. **`flag` is always 0.** `CQDB_ONEWAY` (`0x1`) would drop the backward
   array, making labels unreadable by id; the CRF writer never sets it.
9. **Never read attribute strings.** Thousands per model, training-text
   features (privacy). Read only the attributes CQDB header (24 bytes).
10. **`.model` is a shared suffix** (SentencePiece, gensim and others). A
    `.model` without `lCRF` must stay silent, exactly as a non-model `.bin`
    is today; a `.crfsuite` without `lCRF` warns (a contradicted suffix,
    like `.gguf`). Do not put `.crfsuite` in `_EXTENSION_ADMITS`. **Except
    a Git LFS pointer:** a pointer named `.model` (an unfetched
    `tokenizer.model`, `spiece.model`, common in Hugging Face repos) gets the
    existing `header is a Git LFS pointer; not listed as an AI model`
    warning, as a pointer named `.bin` does today. Decided 2026-10-08:
    accept that (consistent with `.bin`); the 0.21.0 roadmap item "Git LFS
    pointers outside AI models" (one summary warning) will quiet both.
    Test it explicitly so the behaviour is chosen, not accidental.
11. **A labels list inside `raw_metadata` is one entry** to
    `cap_entries()`; the generic cap never shortens it. The reader caps the
    label count itself.
12. **Fixture bytes are not proven identical across platforms** (float
    weights; identical across runs and processes on one macOS arm64
    machine only). Commit the binaries; tests never regenerate them.

## Decisions (2026-10-08)

1. **Detection: suffix filter, then magic.** Scan `.crfsuite` and
   `.model` as candidate suffixes; a file is CRFsuite only when it starts
   with `lCRF`. `.model` is shared (SentencePiece writes a protobuf
   `.model`), so it becomes a shared suffix next to `.bin`
   (`SHARED_MODEL_SUFFIXES`, feeding both the scanner and `loom generate`;
   plan step 5) rather than a format extension; the
   `AiModelFormat` member is `CRFSUITE = ("crfsuite", (".crfsuite",),
   b"lCRF")`. A `.model` without the magic is not a model and must stay
   as quiet as a non-model `.bin` is today (nothing at `INFO` or above);
   a Git LFS pointer named `.model` warns, as one named `.bin` does.
2. **Pure-Python header-and-label reader, no python-crfsuite.** Built as
   `pitloom.extract.ai_model.formats.crfsuite`: stdlib only, no Pitloom
   import (the isolation test applies), seekable binary file plus a
   `Limits` object in, a `CrfsuiteModel` named tuple out, errors from
   `formats._errors`. So it can leave with the rest of `formats/` as its
   own distribution later. A thin adapter in `extract/ai_model/crfsuite.py`
   maps it to `AiModelMetadata`, adds provenance and Pitloom's wording.
   It is the first reader written straight into `formats/` with no library
   reader before it, so there is no parity oracle; generated fixtures and
   the PyThaiNLP files serve instead (see Tests).
3. **What it reads.** The header; the `FEAT` chunk header (count only);
   the labels CQDB (every label string); the attributes CQDB header
   (count only); the `LFRF` and `AFRF` chunk headers (tag and count, as
   consistency checks). Never the weights, the attribute strings or the
   `LFRF`/`AFRF` reference lists.
4. **Labels go to the source-metadata properties and the description;
   `outputs` is one `label_sequence` entry, no strings,
   `shape: ["sequence_length"]`** (revised 2026-10-08: it was
   `[n_labels]`, copied from fastText's `label_probabilities`, which read
   as a fixed-length output; a tagger emits one label per input item, so
   the length is symbolic, spelt as an ONNX `dim_param` is, and the label
   count stays in `num_labels`).
   Properties: `labels` (a JSON array: a label may contain `, `),
   `num_labels`, `num_attributes`, `num_features`, `model_type` (`FOMC`).
   fastText switches to the same JSON array first (decided 2026-10-08).
   `raw_metadata` keeps the label list
   and counts with native types. Description, generated: e.g.
   `CRFsuite model with 26 labels: B-URL, I-URL, O, ...`, its provenance
   marked as generated, not read (`Method: ...`). Long label lists are cut
   in the description, never in `raw_metadata`.
5. **Attributes: count only.** Attribute strings are training-text
   features (`word:...`, `pos:...`): thousands per model, and they can
   leak training data. A future SPDX field for model statistics may take
   the counts; until then they stay in properties.
6. **Model type: `"conditional random field"`.** Format version: `100`.
   Framework: `crfsuite`. No name, version, licence or author is in the
   file: the name falls back to the file stem
   (`AiModelMetadata.resolve_name()`, #292); the rest comes from a
   fragment, the registry or the package's own catalogue.

## Bounds and hostile input

Same discipline as the other `formats/` readers:

- `size` must not exceed the file size (bytes past it are ignored, as
  CRFsuite does); every offset must lie inside `size`
  and leave room for the chunk header it points to; chunk tags must match
  (`FEAT`, `CQDB`, `CQDB`).
- `num_labels` must equal the labels CQDB's backward-array size; each
  key inside its chunk; ids `0..n-1` in order. Over the label count cap
  or the labels-chunk byte cap (no separate per-string cap in the
  reader), the labels chunk stays unread past its header and the model
  is kept with its counts, no label and one `WARNING:`, as for a label
  over 4 KiB (revised 2026-10-08: was a `LimitExceeded` stub that lost
  the counts already read).
- Byte-order mark other than `0x62445371` or a non-zero flag in the labels
  CQDB, a type other than `FOMC` or a version other than 100:
  `UnsupportedVersion` (stub plus one `WARNING:`), not a guess. An
  attributes CQDB whose byte order differs is `Malformed`.
- Total bytes read bounded by the labels chunk, never by the attribute
  or feature counts.

## Tests

- **Generated fixtures**, small, made by a committed generator script with
  python-crfsuite, installed in a throwaway venv (never a runtime or
  dependency-group member):
  - a complete one: several labels including non-ASCII ones, every
    section populated, `.crfsuite` suffix;
  - an imperfect one: `.model` suffix, one or two labels, minimal
    attributes, to exercise detection on the shared suffix and the edge
    counts.
  Hostile variants (truncated, wrong `size`, offset past the end, label
  count mismatch, bad byte-order mark, non-UTF-8 label) are mutated from
  these in the tests, not committed.
- A SentencePiece-shaped `.model` (protobuf bytes, no magic) is not a
  model and logs nothing at `INFO` or above.
- The PyThaiNLP files are measured evidence (counts above), not fixtures:
  most have no stated licence.
- Each fixture gets its `tests/fixtures/README.md` entry with source and
  licence.

## Open questions

Resolved by reading CRFsuite's source and running python-crfsuite 0.9.12
(details in [Traps](#traps) and
[Byte layout in detail](#byte-layout-in-detail) above):

- **Label encoding.** CRFsuite stores bytes; python-crfsuite cannot load a
  non-UTF-8 label it wrote. Decode with `backslashreplace`, never refuse.
- **Generator determinism.** Byte-identical across runs and processes on
  one machine; across platforms unverified. Commit the binaries.
- **Big-endian files.** None: CRFsuite writes little-endian byte by byte,
  whatever the host.
- **Description cut.** 20 labels, then `... (N more)`.

Still open:

- A real description from a fragment or catalogue must win over the
  generated one: confirm the merge order treats it as weak.
- **Personal-data hints.** Label names such as `B-PERSON`, `B-PHONE`,
  `B-EMAIL` suggest a model trained on personal data. Leave any
  `ai_useSensitivePersonalInformation` inference to the `sbom-enrich`
  Skill (fuzzy), not core.
- SPDX 3.1 `additionalInformation`
  ([spdx-3-model#1267](https://github.com/spdx/spdx-3-model/pull/1267),
  open): a native dictionary for labels and counts, replacing the JSON in
  `ai_informationAboutApplication`, once released.
