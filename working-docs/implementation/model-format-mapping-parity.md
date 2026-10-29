---
Created: 2026-10-28
Last-Modified: 2026-10-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Model formats: mapping parity and what a file records

See also: [docs/ai-model-formats.md](../../docs/ai-model-formats.md) (the user
matrix: "What each format holds", "Where each field goes", "Adding a format"),
[model-metadata-extraction.md](model-metadata-extraction.md) (the readers),
[model-file field notes](sbom-generator-field-notes/model-file-metadata.md)
(the war stories: fastText `lr`, `maxn`, ONNX `model_author`).

Two rules for every model format, present and future. Read this before adding a
reader, a field to a reader, or a key to a mapping.

## 1. Parity: a new format gets the mappings its siblings have

Every field of `AiModelMetadata` that a format *can* express is filled the same
way for every format that can express it, through the shared helper:

| Field | The one path | Format-neutral rule |
| - | - | - |
| `license` | the reader sets the text; `add_model_license` classifies it (SPDX expression, else text) | An SPDX-only key (GGUF `general.license`) calls `warn_unless_expression`; a free-text key (ModelSpec `modelspec.license`, GGUF `general.license.name`) does not. A placeholder (`other`, `custom`, ...: `is_vague_license_value`) gives way to a name beside it |
| `originators` | `originator_names()` (`core/model_originators.py`) | One name per key unless the spec says a list (ONNX `model_author` is comma-separated) |
| `parameter_count` | `derived_parameter_count()` (`ai_model/parameter_count.py`) | Elements of stored tensors, from shapes; never dtype-filtered |
| `name`, `description`, `version` | the reader | A name that is an exporter default is no name |
| `architecture`, `type_of_model` | the reader | `type_of_model` is a fixed fact or the format's own field, `architecture` the producer's |
| `quantization`, `hyperparameters` | the reader | Scalars only; arrays by length |
| `inputs`, `outputs` | the reader | Only what the file states; a derived one says `Method: derived_from_format` |
| `properties`, `raw_metadata` | `source_metadata()` | Every format keeps its verbatim metadata under the same caps |

Rules:

- **Every cell of the matrix has an answer.** `--` means the format cannot hold
  it; `Yes`/`Part`/`Kept` is read; `No` means the format can hold it and Pitloom
  does not read it, which needs a row in "Current gaps" below with the reason
  (a bug-sized one also goes in `working-docs/design/known-bugs.md`). A new
  format adds a row and fills each column it can.
- **Absent stays absent**: no warning, no empty value, no default. A value of
  the wrong type is ignored with a debug line.
- **Precedence**: a file's own statement beats a model card or a detected
  licence file; an explicit SPDX key beats a name; a placeholder (`other`,
  `custom`, `proprietary`, `unknown`, `unlicensed`, and `NOASSERTION` for a
  file key) gives way to a name; `NONE` is a statement and stays. Where this is
  built: GGUF (`general.license` then `.name`), Safetensors (one key). Not yet
  the same everywhere: a Hub model card's `license_name` is not read, and a
  dataset card has its own placeholder rule (`other` only; name and link
  combined, `dataset/licence.py`), not `is_vague_license_value`.
- **Measure the key names before mapping a convention.** `modelspec.license` was
  mapped because 4 of the 9 real Safetensors headers read on 2026-10-28 carry it
  (stable-diffusion-xl-base-1.0, the SDXL refiner, sdxl-turbo and
  stable-cascade); gpt2, Qwen2.5-0.5B, whisper-tiny, sd-vae-ft-mse and
  lcm-lora-sdxl do not, and `license`, `license_name` and `license_link`
  appeared in none (stable-diffusion-3-medium returned HTTP 401). The headers
  were read once by HTTP range request and are not stored; repeat the
  measurement before relying on it. Record the sample in the ledger entry and
  say what was not seen.
- **A field that SPDX can hold but `AiModelMetadata` cannot is a Pitloom gap**,
  not a format gap: `general.license.link` could be an `ExternalRefType`
  `license`; it needs a field first.

### Current gaps (the `No` cells)

| Format | Field | Why not read |
| - | - | - |
| GGUF | inputs, outputs | the file has tensors, no signature |
| GGUF | licence link (`general.license.link`) | no licence-URL field in `AiModelMetadata` (SPDX 3.0.1 has `ExternalRefType` `license`) |
| Keras v3 | training (`compile_config`) | not read yet |
| NumPy | inputs | an array is data, not a model input |
| PyTorch classic | hyperparameters, inputs, training | a pickle of arbitrary objects; only the top class is read, without running it |
| Safetensors | inputs, a licence key other than `modelspec.license` | weights only; no other key seen |
| Hugging Face Hub | labels | not read |
| Hugging Face Hub (model card) | `license_name` beside `license: other` | not read; the card path falls back to licence-file detection |
| Hugging Face Hub (dataset card) | placeholder rule | its own (`other` only), not the shared `is_vague_license_value` |

## 2. What the file records: read the format, not the binding

A binding (a Python wrapper, a loader) returns values the *file* does not store:
defaults for missing fields, resets by version or model type, derived values.
Recording one as the model's own fact is wrong and, when another source states
the real value, produces a false conflict. The case: fastText's `getArgs()` gave
`lr` 0.05 and `minCountLabel` 0 for a model trained with 0.77 and 2, because the
loader builds a fresh `Args()` and reads only what `Args::save` wrote (#361).

Before mapping a field from a reader:

1. Read the format's specification or source for what the file stores, and at
   which version. Write it in the table below with the source.
2. For each attribute the binding exposes: is it stored, or a loader default, a
   version reset, a model-type reset? Record only what is stored.
3. Note the version(s) and what changed between them. Where the version changes
   the meaning of a field, read the version and gate on it, narrowly (fastText:
   `maxn` is reset only for a *supervised* model of file version 11; a gate on
   every file below 12 was wrong for cbow and skipgram).
4. Test one real file of each kind, and one with its header rewritten to the
   other version. A mock that lacks the model type hides the bug.
5. Proto3 and similar formats cannot tell an unset scalar from a zero or empty
   one: treat `0` and `""` as unknown, never as a value.
6. Record the format version in the SBOM where the reader knows it
   (`format_info.format_version` or a property), as a stored fact.

### The record, per format

Each cell cites the reader module or a measured file. "Not measured" means
nobody checked the file format for it; do not assume.

| Format | Versions the code knows | Stored in the file | Not stored (do not read), or stored and deliberately not read | Version-dependent |
| - | - | - | - | - |
| fastText | header int32 after magic `793712314` | `dim`, `ws`, `epoch`, `minCount`, `neg`, `wordNgrams`, `loss`, `model`, `bucket`, `minn`, `maxn`, `lrUpdateRate`, `t` (`Args::save`) | Not stored: `lr`, `minCountLabel` (loader defaults); labels of cbow/skipgram are the word vocabulary | version 11: loader resets `maxn` to 0, supervised only (`fasttext.py`) |
| GGUF | header version (kept as `GGUF.version`) | typed key-value pairs (`general.*`, `<arch>.*`), tensor infos | Stored, recorded by length only: arrays; `general.file_type` 1024 (`GUESSED`) is not a stated type | not the format version: a sharded model (`split.count` above 1) gets no summed parameter count (`gguf.py`) |
| ONNX | `ir_version`, opset imports | graph, initializers, `metadata_props`, `model_version`, `producer_*`, `domain` | an unset proto3 scalar reads as `0`/`""` | IR 3 lists weights in `graph.input`; from IR 4 a name in both is an input with a default; `model_version` may be bit-packed SemVer (`onnx.py`) |
| Safetensors | none in the format | JSON header: tensor dtype, shape, offsets; `__metadata__`: flat string-to-string, free-form | any author, licence or version key: the format has none; conventions only (ModelSpec `modelspec.*`, kohya `ss_*`) | not measured |
| NumPy | `.npy` format version in bytes 6-7 (1.0, 2.0, 3.0); `.npz` is a ZIP | dtype, shape, order | any model meaning | the header encoding follows the major version (`numpy.py`) |
| HDF5, Keras v1-v2 | `keras_version` root attribute (major = `v1`/`v2`) | root attributes `keras_version`, `backend`, JSON `model_config`, `training_config` | an HDF5 file without them is not a Keras model | recorded as `format_version` (`hdf5.py`) |
| Keras v3 | `metadata.json` `keras_version` | ZIP: `metadata.json`, `config.json`, `model.weights.h5` | Stored, not read: `compile_config` | the ZIP magic is shared, so detection needs the `.keras` extension and a ZIP header (`reader.py`) |
| PyTorch classic | not read | ZIP members and the top class of `data.pkl` (found without running it), or an old raw pickle (`format_detail: raw pickle`) | Stored, not read: the pickled objects | pickle protocol: not measured |
| PT2 / ExecuTorch | no format version read (`extra/model_version` is the model's) | ZIP, `extra/` files, `models/model.json` signature | Stored, not read: parameters, buffers, constants (not inputs) | not measured |
| CRFsuite | header version 100, type `FOMC` | header counts, labels | Stored, not read: feature weights, attribute strings | any other version or type is `UnsupportedVersion` (`formats/crfsuite.py`) |
| Hugging Face Hub | the repository revision (40-digit hash) | API fields, model card YAML | a card's free text as a fact | not a file format |

## 3. Lessons that made these rules

- fastText: `lr` and `minCountLabel` from a loader default (#361); then a `maxn`
  gate that was too wide (found by a reviewer who rewrote a header).
- ONNX: `model_author` is a comma-separated list; a name such as `Doe, Jane`
  breaks it. Build a fixture with the field set, for every field a mapping
  reads.
- Safetensors / GGUF licence: only one real key found in nine headers; llama.cpp
  writes a card's `license: other` with `license_name` as
  `general.license.name`, so a placeholder must give way to the name (found by
  a review of the mapping).
- A reader that calls `warn_unless_expression` for a free-text key is wrong; one
  that skips it still sees the assembler's general classification warning.
