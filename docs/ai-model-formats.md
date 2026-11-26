---
Created: 2026-08-14
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model formats

See also: [AI model scan limits](ai-model-scan-limits.md) for why a model
can be missing metadata, and [Metadata provenance](metadata-provenance.md)
for the annotations named below, and [SBOM from a Git URL](git-urls.md#model-files)
for a model file in a Git repository. The per-field reference is on
[AI model formats, fields read](ai-model-formats-fields.md), and models
read from the Hub on
[AI model formats, Hugging Face Hub](ai-model-formats-hugging-face.md).

Use this when you want to know which AI model file formats `loom model`
reads, what each format can hold, what Pitloom takes from it, and where
each value ends up in the SBOM.

## Quick guide

```bash
pip install "pitloom[ai]"
loom model path/to/model.safetensors -o model.spdx3.json
```

`pip install "pitloom[ai]"` installs every optional reader library below;
install a single extra (`pitloom[gguf]`, ...) if you need one format only.
Every reader is read-only: Pitloom never runs model code and never calls
`pickle.load()`. See [Command line](cli.md) for `loom model` and the other
targets that scan for models.

## How a file is recognised

A file is a model when its header confirms a format. The header check comes
first, so a file named on the command line (`loom model`, `loom generate`,
`generate()`), or by a Git URL, is read whatever its suffix when its header
has a magic (a `x.dat` with GGUF magic is GGUF); ONNX, Keras v3, PyTorch,
PT2 and NumPy `.npz` files have none Pitloom can tell from other files (a
protobuf, a ZIP, a pickle), so a copy of one named `x.dat` is not recognised: it keeps its
suffix. A project or wheel scan, and a folder given for its
one model file, only look at the suffixes below. A header that contradicts the suffix (text named `.gguf`)
is not a model, and a Git LFS pointer is never one (it is listed as a
file only); see
[What is a model](ai-model-scan-limits.md#what-is-a-model).

| Format | Suffixes scanned | Header check | Reads | Library (extra) |
| :----- | :--------------- | :----------- | :---- | :-------------- |
| CRFsuite | `.crfsuite`, `.model` | magic `lCRF` | header and label strings | none |
| fastText | `.ftz`, `.bin` | magic `BA 16 4F 2F` | whole model, in memory | `fasttext-community` (`fasttext`) |
| GGUF | `.gguf` | magic `GGUF` | key-value header and tensor infos, by Pitloom's own reader (memory-mapped; arrays as length and type) | `gguf` (`gguf`), for quantisation names and tensor sizes |
| HDF5, Keras v1-v2 | `.h5`, `.hdf5` | HDF5 magic, or any non-empty file (a userblock moves the signature) | root attributes | `h5py` (`hdf5`) |
| Keras v3 | `.keras` | ZIP | `metadata.json`, `config.json` (architecture, compile settings) and the member list | none |
| NumPy | `.npy`, `.npz` | `.npy`: magic `\x93NUMPY`; `.npz`: ZIP | array headers | `numpy` (`numpy`) |
| ONNX | `.onnx` | none: any non-empty file | whole protobuf, in memory; external data files not loaded | `onnx` (`onnx`) |
| PyTorch classic | `.pt`, `.pth` | ZIP, or pickle protocol 2-5 (a text `.pth` path file is not a model) | archive listing, top of `data.pkl` | `fickling` (`pytorch`), optional: without it, no type of model |
| PT2 (`torch.export`) | `.pt2` | ZIP | archive listing, small text and JSON members | none |
| Safetensors | `.safetensors` | 8-byte little-endian header size, then `{` | JSON header | `safetensors` (`safetensors`) |
| Hugging Face Hub | model ID or URL, not a file | -- | Hub API, model card, config files | `huggingface_hub` (`huggingface_hub`) |

An HDF5 file with a `keras_version` attribute is reported as format
`keras`, otherwise as `hdf5` (and then only its format is recorded).
`.bin` and `.model` are shared with other tools: such a file is a model only
when it carries a supported format's magic (usually fastText or CRFsuite), and no
warning is given otherwise.

## What each format holds

Moved to [AI model formats, fields read](ai-model-formats-fields.md#what-each-format-holds).

## Producer and parameter count

Two values the G7 SBOM-for-AI minimum elements ask for are read from
structured fields only. A value that sits in free text (a model card's
prose) is left to [the `sbom-enrich` Skill](agent-skills.md).

| Format | Producer (`originators`) | Supplier (`supplier`) | Parameter count (`parameter_count`) |
| :----- | :----------------------- | :-------------------- | :---------------------------------- |
| GGUF | `general.author`, then `general.organization`: one name each | -- | Sum over the shapes in `tensor_infos`; none when `split.count` is above 1 |
| ONNX | `model_author` metadata property: a comma-separated list | -- | Sum over `graph.initializer` and `graph.sparse_initializer`, subgraphs included |
| PT2 (`torch.export`) | `extra/author`: one name | -- | Sum over the sizes of every stored weight (parameters and buffers) in `data/weights/model_weights_config.json` |
| CRFsuite | -- | -- | The feature count of the `FEAT` chunk: each feature stores one weight |
| Safetensors | `modelspec.author` in `__metadata__` (ModelSpec): one name | -- | Sum over every tensor shape in the header (header only) |
| Hugging Face Hub | The repository owner (`author`): one name | The same name | `safetensors.total`, else `gguf.total`, as the Hub states it |

In the provenance the values are keyed by their field names, `originators`,
`supplier` and `parameter_count`.

Every other format gives neither: PyTorch classic (no shapes without
unpickling), Keras and HDF5 (the weights are not read), NumPy (a bare array
is not a model) and fastText (its matrix size follows the dictionary stream).

**Producer and supplier.** Each name becomes a generic SPDX `Agent` (name
only, no email) in the `ai_AIPackage`'s `originatedBy`, one Agent per
distinct producer name, shared when two models name the same one, and with a
dataset creator of that name (an SBOM creator of type `agent`, a main-package
author and a dependency's author are other elements and are not merged with
it). No model
file format sets `suppliedBy`: an author written in a file originated the
model, and the file does not say who ships it. A model read from the Hugging
Face Hub is the exception: the Hub repository is where the model is shipped
from, so its owner is also the `suppliedBy`, and the same one `Agent` is
referenced by both properties. `suppliedBy` holds one agent, so one owner. A
model never inherits the main package's `suppliedBy` (the SBOM's first
creator, which says nothing about the model). Whether a name is a person or
an organisation is not decided here; a [fragment](fragments.md) can add a
`Person` or `Organization` to `originatedBy` when the model card says which
(lists merge by union, so the generic `Agent` stays beside it). Things to
know:

- ONNX defines `model_author` as a comma-separated list, so the text is
  split on commas, and `Method: comma_list` is recorded when it has one. A
  name that itself holds a comma (`Doe, Jane`, `Foo, Inc.`) is split wrongly.
- The Hub's `author` is the account that owns the repository, recorded with
  `Method: repository_owner` for both `originators` and `supplier`. A
  re-upload, quantisation or fine-tune names the uploader, not the original
  maker; the base model a card names is recorded separately as
  `descendantOf`, which records lineage only.
- GGUF, PT2 and Safetensors names are not split: `general.author`,
  `extra/author` and `modelspec.author` hold one name. The raw keys also
  stay in `properties`.
- The llama.cpp converter often fills GGUF `general.organization` by
  guessing from the base model's `_name_or_path`, so a fine-tune's file can
  name the base model's organisation. Pitloom reads it as stated and cannot
  tell a stated organisation from a guessed one. The Hub route names the
  repository owner instead, so the same model can show two producers by
  route.
- A name over the length cap is cut; several over-long names in one model
  give one warning, not one per name (see
  [scan limits](ai-model-scan-limits-caps.md#size-and-count-caps)).

**Parameter count.** SPDX 3.0.1 has no property for a model's size, so the
count is an `ai_hyperparameter` entry, key `parameters`, value a decimal
integer as text (`"7241732096"`). The G7 SBOM for AI mapping to SPDX
(bact.github.io/bom) names this key for the parameter count. It is not a
hyperparameter, and the package `comment` says so, in this line, whenever
the entry is there:

```text
Parameter count: ai_hyperparameter "parameters" holds the number of elements in the model's stored tensors, as its parameter count, because SPDX 3.0.1 has no model-size property (it is not a hyperparameter).
```

A [fragment](fragments.md) merge keeps the line in step with the entry for
each package it merges into: afterwards the package has the line first in its
`comment` if it has a `parameters` entry that is a positive decimal integer
(ASCII digits, up to 10^15) and none otherwise, whatever a fragment's `comment`
says (a base `parameters` entry wins over a fragment's). A value such as `7B`
gets no line. A package that no fragment merges into keeps its `comment` as
written. A merge cannot tell a model's own `parameters` entry from a count, so
it labels that too.

- A count read from the file is the sum of the **element** counts of its
  tensors, not bytes: a `[32, 2]` tensor adds 64 whatever its type. It is
  recorded with `Method: tensor_element_sum`, as is the Hub's: its
  `safetensors.total` (or `gguf.total` when there is no `safetensors` field;
  `safetensors` wins when both exist) is the same sum, computed by the Hub.
  The provenance reads `Source: Hugging Face Hub | Field: model_info
  safetensors.total | Method: tensor_element_sum`.
- ONNX counts every tensor in `graph.initializer` and
  `graph.sparse_initializer` and in subgraphs, a tensor stored in an
  external data file by its declared dimensions (the file is not read).
  `Constant` nodes and `model.functions` are not counted.
- PT2 counts every weight its weights config lists, parameters and buffers
  alike, by the sizes the config states (no tensor is read). Names sharing
  one stored weight (tied weights: one blob, one view) count once; views
  of one blob count each; lifted
  constants, in their own config, are not counted. A symbolic size gives
  none, with the malformed-dimension `WARNING:` below.
- CRFsuite counts its features (`Method: one_weight_per_feature`): each
  stores one weight, and CRFsuite keeps only the features whose weight is
  not zero.
- A Safetensors file that is one shard of a model gives that file's count,
  and the format has no sign that it is a shard. A GGUF file with
  `split.count` above 1 gives none, since its sum would understate the model.
- A sum of 0, or a file with no tensor, gives no count (never `"0"`), with
  no message. A malformed dimension (negative, not an integer) or a count
  over 10**15 gives none and one `WARNING:` ending `parameter count not
  recorded`; see [scan limits](ai-model-scan-limits-caps.md#size-and-count-caps).
- A hyperparameter the model itself declares under the key `parameters` is
  replaced by the count, with a `WARNING:`.

### What the count counts

It is the number of elements of **all** stored tensors, not the "trainable
parameters" of a size such as `bom:ai-model-size`. Do not filter by type:
int8 weights are parameters.

- It includes buffers stored as tensors (attention masks, shape constants)
  and tied weights stored twice (a PT2 archive stores a tied weight once:
  it counts once). The ONNX test model `gpt2-tiny-decoder`
  counts 404256, which includes a 262144-element uint8 causal mask
  (`transformer.h.0.attn.bias`, `[1, 1, 512, 512]`) and a 32000-element
  transposed copy of `wte.weight`; about 110112 are weights of their own. A
  tiny Marian Safetensors model's 174535 includes the 58101-element
  `final_logits_bias` buffer, and `squeezenet1.1-7`'s 1235498 is 1235496
  weights plus a 2-element int64 reshape constant. The Hub API gave
  137022720 for `openai-community/gpt2` (2026-10-15), against about 124.4
  million weights: attention-mask buffers make up the rest.
- Packed or quantised weights count differently by format. GGUF shapes are
  logical (a Q4_0 tensor of shape `[64]` counts 64). GPTQ, AWQ and
  bitsandbytes Safetensors files store packed integer tensors: a GPTQ-style
  64 x 64 layer with `qweight` (I32 `[8, 64]`), `scales`, `qzeros` and
  `g_idx` counts 648 against 4096 real weights. Block-quantised ONNX
  (`MatMulNBits`) under-counts likewise.
- The Hub's `safetensors.total` and `gguf.total` have the same property. For
  a repository of several components, such as the diffusion pipeline
  `stabilityai/stable-diffusion-xl-base-1.0`, whose `safetensors.total` is
  the UNet only, the Hub's total may cover only part of the repository.

## Where each field goes

Moved to [AI model formats, fields read](ai-model-formats-fields.md#where-each-field-goes).

## Hugging Face Hub models

Moved to [AI model formats, Hugging Face Hub](ai-model-formats-hugging-face.md#hugging-face-hub-models).

## Not yet supported

JAX (Orbax), TensorFlow SavedModel, TensorFlow Lite, and scikit-learn
(pickle/joblib) are on the roadmap but not implemented yet.

## Adding a format

The tables are kept one row per model format and per field, one column per
output format, so that either grows by one line or one column.

- **A new SBOM output format** (CycloneDX, another SPDX version): add a
  column to [Where each field goes](ai-model-formats-fields.md#where-each-field-goes). The SPDX 3
  mapping lives in `pitloom.assemble.spdx3._ai_package` and
  `pitloom.assemble.spdx3.ai`; a new format gets its own assembler that
  reads the same `AiModelMetadata`.
- **A new model format**: fill every field the format can express the way the
  existing formats do (licence, producer, parameter count, version), and read
  only what the file itself stores: a value a binding returns as a default, or
  resets by version, is not the file's (fastText's `lr` is one). Then add a
  row to the tables in
  [How a file is recognised](#how-a-file-is-recognised) and
  [What each format holds](ai-model-formats-fields.md#what-each-format-holds), and its name to the
  "Filled by" cells it fills. In code: an `AiModelFormat` member (suffixes,
  magic) in `pitloom.core.ai_metadata`; a reader in
  `pitloom.extract.ai_model` (a library-free header reader goes in its
  `formats` subpackage), registered in `REGISTRY` in
  `pitloom.extract.ai_model.reader` (and in `_EXTENSION_ADMITS` there when
  the format has no magic); its library in
  `pitloom.extract.ai_model.reader_requirements` and a `pyproject.toml`
  extra; a decision on the wheel gate
  (`pitloom.extract.scanner_wheel.WHEEL_GATED_FORMATS`); and fixtures
  under `tests/fixtures/aimodels/`. A reader that knows the producer or the
  tensor shapes fills `originators` with `originator_names()`
  (`pitloom.core.model_originators`, which bounds the read; the reader
  records the `originators` provenance) and `parameter_count` with
  `derived_parameter_count()` (`pitloom.extract.ai_model.parameter_count`,
  which bounds the sum and records its provenance); it does not build an
  `Agent` or an entry itself.

## See also

- [AI model scan limits](ai-model-scan-limits.md) -- caps, gated formats
  in wheels, and what a format cannot record.
- [AI model formats, fields read](ai-model-formats-fields.md) -- what
  each format holds and where each field goes.
- [AI model formats, Hugging Face Hub](ai-model-formats-hugging-face.md)
  -- models read from the Hugging Face Hub.
- [Metadata provenance](metadata-provenance.md) -- the provenance and
  artifact-metadata annotations.
- [Command line](cli.md) -- the `loom model` command in context with
  Pitloom's other generation targets.
- [Python API](python-api.md) -- `generate_model_sbom()`, the equivalent
  entry point from Python code.
