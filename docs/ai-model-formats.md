---
Created: 2026-08-14
Last-Modified: 2026-08-14
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
extension.

## Supported formats

| Format | Extension(s) | Install extra |
| :----- | :----------- | :------------- |
| fastText | `.ftz`, `.bin` | `pip install fasttext` |
| GGUF | `.gguf` | `pip install gguf` |
| HDF5 / Keras v1-v2 | `.h5`, `.hdf5` | `pip install h5py` |
| Keras v3 | `.keras` | (none -- stdlib only) |
| NumPy | `.npy`, `.npz` | `pip install numpy` |
| ONNX | `.onnx` | `pip install onnx` |
| PyTorch classic | `.pt`, `.pth` | `pip install fickling` (safe pickle inspection) |
| PyTorch PT2 / ExecuTorch | `.pt2` | (none -- stdlib only) |
| Safetensors | `.safetensors` | `pip install safetensors` |

`pip install "pitloom[ai]"` pulls in every optional dependency above at
once; install a single extractor's package directly if you only need one
format.

Every extraction is read-only and inspects the file's own structure
(binary header, ZIP archive contents, or safe AST inspection of a pickle)
-- Pitloom never executes model code or calls `pickle.load()`.

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

- [Command line](cli.md) -- the `loom model` command in context with
  Pitloom's other generation targets.
- [Python API](python-api.md) -- `generate_model_sbom()`, the equivalent
  entry point from Python code.
