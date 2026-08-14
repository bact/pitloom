---
Created: 2026-03-05
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model metadata extraction: implemented formats

See [design/model-metadata-extraction.md](../design/model-metadata-extraction.md)
for planned-but-unbuilt format support and the AI dataset metadata
extraction gap. The user-facing format list lives at
[docs/ai-model-formats.md](../../docs/ai-model-formats.md).

An AI BOM generator can utilize existing model exchange standards, such as
ONNX and Safetensors, as a machine-readable source of truth
for model architecture, hyperparameters, and other model-specific metadata.

Pitloom can detect the format of a model file, extract its metadata,
and record those metadata in the AI BOM.

## Implemented format extractors

All extractors live in `pitloom.extract` and expose a
`read_<format>(model_path: Path) -> AiModelMetadata` interface.
Format detection is handled by
`pitloom.extract.ai_model.detect_ai_model_format()` and `read_ai_model()`.

| Format | Extension(s) | Module | Optional dependency | Extraction method |
| :----- | :----------- | :----- | :------------------ | :----------------- |
| fastText | `.ftz`, `.bin` | `_fasttext.py` | `pip install fasttext` | `model.f.getArgs()` via C++ binding; `model.get_labels()` for supervised class list |
| GGUF | `.gguf` | `_gguf.py` | `pip install gguf` | `GGUFReader` to extract typed key-value pairs from the binary header |
| HDF5 / Keras v1-v2 | `.h5`, `.hdf5` | `_hdf5.py` | `pip install h5py` | `h5py.File.attrs` for root attributes; JSON-encoded `model_config` and `training_config` |
| Keras v3 | `.keras` | `_keras.py` | (stdlib only) | Inspect `config.json` inside the `.keras` ZIP archive; no model execution required |
| NumPy | `.npy`, `.npz` | `_numpy.py` | `pip install numpy` | Memory-map header to read shape and dtype without loading tensor data |
| ONNX | `.onnx` | `_onnx.py` | `pip install onnx` | `onnx.load()` to access graph properties and `metadata_props` dictionary |
| PyTorch classic | `.pt`, `.pth` | `_pytorch.py` | `pip install fickling` (safe pickle inspection) | ZIP archive structure inspection; `fickling` for safe pickle AST inspection (never calls `pickle.load`) |
| PyTorch PT2 / ExecuTorch | `.pt2` | `_pytorch_pt2.py` | (stdlib only) | ZIP archive structure; `extra/` metadata files; `models/model.json` graph inputs/outputs |
| Safetensors | `.safetensors` | `_safetensors.py` | `pip install safetensors` | `safe_open()` reads the JSON header without loading multi-gigabyte weight tensors |

## Format reference tools and prior art

### Netron

Netron is a visualizer and metadata extractor supporting nearly all common
formats (ONNX, PyTorch, TensorFlow, GGUF, Core ML, RKNN, and many more).
<https://github.com/lutzroeder/netron>

Netron is written in JavaScript and is not directly importable from Python.
However, it is a valuable reference for:

- Understanding the internal layout of numerous formats, including edge
  cases and version differences.
- Handling format variants that lack official Python libraries
  (e.g., Core ML, RKNN, TFLite FlatBuffer parsing details).

When adding support for a new format, Netron's parser for that format is
a useful reading companion alongside the format specification.

### AIMMX

[AIMMX](https://github.com/IBM/AIMMX) (Automated AI Model Metadata eXtractor)
is a research library that mines AI-specific metadata from software
repositories. Rather than parsing model files directly, AIMMX infers
characteristics from README files, training scripts, and requirements.

AIMMX is relevant to Pitloom's enrichment capability -- filling metadata
gaps in model formats that carry little embedded information by looking
at the surrounding repository context. See
[sbom-enrichment.md](../design/sbom-enrichment.md) for the enrichment
design.
