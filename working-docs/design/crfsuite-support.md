---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CRFsuite model support

Status: designed, not built. Next AI-format work after #292 (ONNX names
and licences), ahead of the PyTorch metadata-only reader. Summarised in
[roadmap.md](roadmap.md) as one bullet linking here.

See also: [model-metadata-readers.md](model-metadata-readers.md) (the
stdlib-only `formats/` subpackage this reader is built in),
[model-metadata-extraction.md](model-metadata-extraction.md) (planned
formats table),
[model-file-metadata.md](../implementation/sbom-generator-field-notes/model-file-metadata.md)
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
| 16 | num_features | 0 (the real count is in the `FEAT` chunk) |
| 20 | num_labels | as in the table |
| 24 | num_attrs | as in the table |
| 28-44 | offsets of `FEAT`, labels, attributes, `LFRF`, `AFRF` | ascending, inside the file |

- `FEAT` chunk: `<4sII` = tag, size, feature count; then the weights.
- Labels and attributes are each a CQDB (constant quark database: string
  to id and back). CQDB header `<4sIIIII` = `CQDB`, size, flag, byte-order
  mark `0x62445371`, backward-array size, backward-array offset; then 256
  hash tables. The backward array holds one record offset per id; a
  record is `int32` id, `uint32` key size (NUL included), the key bytes.
  So label strings are read by id, in id order, without hashing.
- `LFRF`/`AFRF`: label and attribute feature references (tag, size, ...).
  Not needed.

## Decisions (2026-10-08)

1. **Detection: suffix filter, then magic.** Scan `.crfsuite` and
   `.model` as candidate suffixes; a file is CRFsuite only when it starts
   with `lCRF`. `.model` is shared (SentencePiece writes a protobuf
   `.model`), so it joins `.zip` and `.bin` in the scanner's
   `_ALLOWED_EXTS` rather than becoming a format extension; the
   `AiModelFormat` member is `CRFSUITE = ("crfsuite", (".crfsuite",),
   b"lCRF")`. A `.model` without the magic is not a model and must stay
   as quiet as a non-model `.bin` is today.
2. **Pure-Python header-and-label reader, no python-crfsuite.** Built as
   `pitloom.extract.ai_model.formats.crfsuite`: stdlib only, no Pitloom
   import (the isolation test applies), seekable binary file plus a
   `Limits` object in, a frozen `CrfsuiteHeader` dataclass out, errors from
   `formats._errors`. So it can leave with the rest of `formats/` as its
   own distribution later. A thin adapter in `extract/ai_model/crfsuite.py`
   maps it to `AiModelMetadata`, adds provenance and Pitloom's wording.
   It is the first reader written straight into `formats/` with no library
   reader before it, so there is no parity oracle; generated fixtures and
   the PyThaiNLP files serve instead (see Tests).
3. **What it reads.** The header; the `FEAT` chunk header (count only);
   the labels CQDB (every label string); the attributes CQDB header
   (count only). Never the weights, the attribute strings, `LFRF` or
   `AFRF`.
4. **Labels go to the source-metadata properties and the description.**
   Properties: `labels` (comma-joined), `num_labels`, `num_attributes`,
   `num_features`, `type` (`FOMC`). `raw_metadata` keeps the label list
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

- `size` must equal the file size; every offset must lie inside the file
  and leave room for the chunk header it points to; chunk tags must match
  (`FEAT`, `CQDB`, `CQDB`).
- `num_labels` must equal the labels CQDB's backward-array size, and both
  stay under the entry cap; each key size under a per-string cap and
  inside its chunk; ids `0..n-1` with no gap or duplicate.
- Byte-order mark other than `0x62445371`, or a type other than `FOMC`:
  `UnsupportedVersion` (stub plus one `WARNING:`), not a guess.
- Total bytes read bounded by the labels chunk, never by the attribute
  or feature counts.

## Tests

- **Generated fixtures**, small, made by a committed generator script with
  python-crfsuite (a test/fixture-only dependency, never a runtime one):
  - a complete one: several labels including non-ASCII ones, every
    section populated, `.crfsuite` suffix;
  - an imperfect one: `.model` suffix, one or two labels, minimal
    attributes, to exercise detection on the shared suffix and the edge
    counts.
  Hostile variants (truncated, wrong `size`, offset past the end, label
  count mismatch, bad byte-order mark, non-UTF-8 label) are mutated from
  these in the tests, not committed.
- A SentencePiece-shaped `.model` (protobuf bytes, no magic) is not a
  model and logs nothing at `WARNING:`.
- The PyThaiNLP files are measured evidence (counts above), not fixtures:
  most have no stated licence.
- Each fixture gets its `tests/fixtures/README.md` entry with source and
  licence.

## Open questions

- **Label encoding.** CRFsuite stores bytes; PyThaiNLP's are UTF-8. A
  non-UTF-8 label: refuse the file as malformed, or decode with
  `backslashreplace` and keep going?
- **Description cut.** How many labels before `...` (the entry cap, or a
  smaller display cap)? And a real description from a fragment or
  catalogue must win over the generated one: confirm the merge order
  treats a generated description as weak.
- **Generator determinism.** Does python-crfsuite training give
  byte-identical output across runs and platforms? If not, commit the
  binaries and keep the script as the record of how they were made.
- **Personal-data hints.** Label names such as `B-PERSON`, `B-PHONE`,
  `B-EMAIL` suggest a model trained on personal data. Leave any
  `ai_useSensitivePersonalInformation` inference to the `sbom-enrich`
  Skill (fuzzy), not core.
- **Big-endian files.** CRFsuite's writer is little-endian on every file
  seen; no big-endian sample exists to test against.
