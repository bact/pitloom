---
Created: 2026-10-23
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# TensorFlow Lite and SavedModel support (design note, not built)

See also: [model-metadata-extraction.md](model-metadata-extraction.md) (the
planned-format table this splits out of),
[jax-orbax-support.md](jax-orbax-support.md) (the other planned framework
format; Flax msgpack is there),
[model-metadata-readers.md](model-metadata-readers.md) (the stdlib-only
bounded-reader plan a new reader should follow),
[implementation/model-metadata-extraction.md](../implementation/model-metadata-extraction.md)
(the shipped readers), [roadmap.md](roadmap.md#backlog-designed-not-scheduled).

Status: nothing is built. What follows is what was checked on 2026-10-23
and what is still open. A claim not marked "verified" comes from the format's
public documentation and must be checked against real files before a reader
relies on it.

## Today (verified against the tree)

- `AiModelFormat` (`src/pitloom/core/ai_metadata.py`) has no TensorFlow Lite,
  SavedModel or Flax member, and no reader in `src/pitloom/extract/ai_model/`
  handles them.
- `.tflite` is not a model-candidate suffix (`model_file_suffixes()`, used by
  `is_model_candidate_name()` in `extract/scanner.py`), so `loom project` and
  the wheel scan skip such a file before reading it: it appears as a plain
  `software_File`, with no `ai_AIPackage`.
- `loom model x.tflite` reaches `read_ai_model()` and fails with
  `Unsupported model format for file: ...` (`extract/ai_model/reader.py`).
- A Keras `tf_model.h5` (the TensorFlow weights file that Hugging Face
  repositories such as `google-bert/bert-base-uncased` ship) is HDF5, which
  the HDF5 reader already handles. A SavedModel directory is not.

Demand signal: of about 390 Hub Spaces searched on 2026-10-23, about 35 held
an ONNX, TFLite or fastText model file
([hugging-face-spaces-support.md](hugging-face-spaces-support.md)).

## TensorFlow Lite (`.tflite`)

### Verified on real files (2026-10-23)

Read with the `tflite` 2.18.0 bindings (Apache-2.0; they need `flatbuffers`
and `numpy`) on two Hub files: `tflite-hub/conformer-lang-id`
`vad_short_model.tflite` (481,664 bytes) and `nyadla-sys/whisper-tiny.en.tflite`
`dtln_quantized.tflite` (372,664 bytes). Neither file is vendored; their
licences were not checked.

- A FlatBuffer: bytes 0-3 are the root table offset, bytes 4-7 the file
  identifier `TFL3`. The identifier is **not at offset 0**, so the existing
  `AiModelFormat.magic` check (a prefix at byte 0) cannot detect it; detection
  needs an offset-aware branch or a format-specific sniffer.
- `Model.version` (the schema version) was `3` in both.
- `Model.description`: `None` in one file, `"MLIR Converted."` in the other.
  That string is the converter's own note, not a description of the model
  (see open question 2).
- `Model.metadata`: a list of (name, buffer index) pairs. One file had a
  single `min_runtime_version` entry; the other had none.
- `Model.signatureDefs`: 0 in one file, 1 in the other.
- Subgraph input tensors carry a name, a shape and a type enum
  (`input0`, `[1, 528]`, `FLOAT32`; `serving_default_input_5:0`, `[1, 1, 257]`).

### Not verified

- **TFLite Model Metadata** (the `TFLITE_METADATA` metadata entry, a second
  FlatBuffer from `tflite-support` with name, description, version, author and
  licence): neither file had one. It is the only place a `.tflite` file is
  documented to state a name, author or licence; check its layout and how
  often it occurs on real files before mapping it.
- A parameter count from the constant tensors' buffers (sum of element counts
  of tensors whose buffer holds data). Not tried; quantised tensors and
  shared buffers need a rule before a count is written
  ([g7-model-producer-parameter-count.md](../implementation/g7-model-producer-parameter-count.md)
  is the rule for the other formats).
- Behaviour on large files (LLM-sized `.tflite` from `litert-community`) and
  on files with external buffers.

### Comparable readers

- Safetensors and GGUF read a header only; NumPy memory-maps the header. A
  FlatBuffer has no header block: tables are reached through offsets, so a
  bounded reader seeks (or memory-maps) and checks every offset and vector
  length against the file size and a cap, as the CRFsuite reader
  (`extract/ai_model/formats/crfsuite.py`) does with its own offsets.
- ONNX, Keras, HDF5 and PT2 write their input and output signature as JSON
  in `ai_informationAboutApplication`; TFLite signature defs and subgraph
  inputs and outputs fit the same field (with the same weakness: a
  signature is not a modality, FG-3 in
  [sbom-format-gaps.md](sbom-format-gaps.md)).
- [model-metadata-readers.md](model-metadata-readers.md) prefers stdlib-only
  readers in `extract/ai_model/formats/` over a library read. The `tflite`
  package is an alternative with two dependencies; which one to use is open
  question 1.

## TensorFlow SavedModel (directory)

Not verified here (TensorFlow was not installed). From the TensorFlow
documentation: a directory holding `saved_model.pb` (a `SavedModel` protocol
buffer with one or more `MetaGraphDef`s and their signature defs),
`variables/` (`variables.index` plus data shards) and optional `assets/` and
`fingerprint.pb`.

- Like an Orbax checkpoint, it is a directory, so it shares the two gaps
  [jax-orbax-support.md](jax-orbax-support.md) records: `detect_ai_model_format()`
  has no directory branch, and the project scan filters single files by
  suffix (`saved_model.pb` would need a name rule, not a suffix rule). One
  directory-target design should serve both.
- Parsing `saved_model.pb` needs a protobuf reader; Pitloom has none outside
  the `onnx` package. A stdlib protobuf wire-format walker bounded like the
  pickle walker is possible but not designed.

## Open questions

1. Reader: stdlib-only bounded FlatBuffer walker in `formats/` (no new
   dependency, matches the readers plan) or the `tflite` bindings as an
   optional extra (less code, two dependencies, and `numpy` on import).
2. Is a converter string such as `"MLIR Converted."` a description? It reads
   like a placeholder about the tool, not the model; by the "a placeholder is
   not a claim" rule it should not become `description`, but a rule needs a
   list of known converter strings or a different field.
3. `Model.version` is the schema version, not the model's: it must not fill
   `software_packageVersion`. Where does `min_runtime_version` go (no SPDX
   3.0.1 property; a format-gap ledger entry if it is recorded)?
4. Fixtures: a synthetic `.tflite` needs either the TensorFlow converter or a
   FlatBuffer built by hand from the schema; the second keeps the fixture
   generator free of TensorFlow. Not tried.
5. SavedModel: is there demand beyond TFLite and Keras files? Decide after
   the directory-target design for Orbax.
