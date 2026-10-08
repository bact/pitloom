---
Created: 2026-08-14
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model formats

Use this when you want to know exactly which AI/ML model file formats
`loom model` reads, which optional dependency each one needs, and what
Pitloom actually pulls out of the file.

## Quick guide

```bash
pip install "pitloom[ai]"
loom model path/to/model.safetensors -o model.spdx3.json
```

`loom model` auto-detects the format from the file itself, not just the
extension: a file is a model when its header confirms a format (its magic
bytes, a ZIP header for `.keras`, `.pt2` and `.npz`, or a ZIP header or a
protocol 2 to 5 pickle for `.pt` and `.pth`). ONNX has no signature at
offset 0, and an HDF5 one may sit after a userblock, so their suffixes admit
any non-empty file. A header that contradicts the suffix (text named `.gguf`)
is not a model, and a Git LFS pointer is not one under any suffix; see
[What is a model](ai-model-scan-limits.md#what-is-a-model).

## Supported formats

| Format | Extension(s) | Install extra |
| :----- | :----------- | :------------- |
| CRFsuite | `.crfsuite`, `.model` (only with the `lCRF` magic) | (none -- stdlib only) |
| fastText | `.ftz`, `.bin` | `pip install fasttext-community` |
| GGUF | `.gguf` | `pip install gguf` |
| HDF5 / Keras v1-v2 | `.h5`, `.hdf5` | `pip install h5py` |
| Keras v3 | `.keras` | (none -- stdlib only) |
| NumPy | `.npy`, `.npz` | `pip install numpy` |
| ONNX | `.onnx` | `pip install onnx` |
| PyTorch classic | `.pt`, `.pth` (a ZIP or a pickle; a plain-text `.pth` path-config file is not a model) | `pip install fickling` (safe pickle inspection) |
| PyTorch PT2 / ExecuTorch | `.pt2` | (none -- stdlib only) |
| Safetensors | `.safetensors` | `pip install safetensors` |

`pip install "pitloom[ai]"` pulls in every optional dependency above at
once; install a single extractor's package directly if you only need one
format.

Every extraction is read-only and inspects the file's own structure
(binary header, ZIP archive contents, or safe AST inspection of a pickle)
-- Pitloom never executes model code or calls `pickle.load()`.

A GGUF array (a tokenizer vocabulary, scores, per-layer values) is recorded
as its element count only, property `<key>.length` (for example
`tokenizer.ggml.tokens.length`); in the verbatim artifact-metadata annotation
the key holds `{"length": N, "type": "<element type>"}` (`type` is left out
for an element code the format does not define).

A CRFsuite model is read by Pitloom itself (header and label strings only;
never the feature weights or the attribute strings, which come from the
training text). Its SBOM entry has type of model `conditional random
field` and a description Pitloom generates from the labels. When the
verbatim artifact-metadata annotation is preserved
(`preserve-source-metadata`), it also holds all the labels, in the order
training first saw them, and the label, attribute and feature counts.

Size and header limits, the wheel-scan gate and the fields a format cannot
carry are in [AI model scan limits](ai-model-scan-limits.md).

## Hugging Face Hub models

Pass a Hugging Face Hub URL or a bare model ID instead of a local file --
no download required for the SBOM itself (needs
`pip install pitloom[huggingface_hub]`):

```bash
loom model https://huggingface.co/mistralai/Mistral-7B-v0.1
loom model Qwen/Qwen3-235B-A22B
```

This reads the model card, `config.json`, `tokenizer_config.json`, and
`generation_config.json` from the Hub API and produces an enriched
`ai_AIPackage`.

## Not yet supported

JAX (Orbax), TensorFlow SavedModel, TensorFlow Lite, and scikit-learn
(pickle/joblib) are on the roadmap but not implemented yet.

## See also

- [AI model scan limits](ai-model-scan-limits.md) -- why a model can be
  missing metadata: caps, gated formats, fields not recorded.
- [Command line](cli.md) -- the `loom model` command in context with
  Pitloom's other generation targets.
- [Python API](python-api.md) -- `generate_model_sbom()`, the equivalent
  entry point from Python code.
