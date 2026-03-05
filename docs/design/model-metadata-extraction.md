---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model metadata extraction

An AI BOM generator can utilize existing model exchange standards, such as
ONNX and Safetensors, as a machine-readable source of truth
for model architecture, hyperparameters, and other model-specific metadata.

Loom can try to detect the format of the model, then extract metadata of the
model, and record those metadata in the AI BOM.

## Automated metadata extraction for AI BOM generation

Effective AI BOM implementation relies on the ability to programmatically
extract model metadata without manual effort.

### Unified extraction tools

These tools provide a single entry point for extracting metadata across
multiple formats:

- Netron: A visualizer and metadata extractor that supports nearly all
  common formats (ONNX, PyTorch, TensorFlow, GGUF, Core ML, RKNN, etc.).
  It can programmatically display node attributes, input/output shapes,
  and model properties. <https://github.com/lutzroeder/netron>
- AIMMX (AI Model Metadata Extractor):
  A research library specifically designed to mine AI-specific metadata
  (paper references, dataset links, framework types)
  from software repositories. <https://github.com/IBM/AIMMX>.

### Framework-native metadata extraction

| Model Format | Recommended Extraction Method | Key Python Libraries |
| :---- | :---- | :---- |
| **PyTorch** | Use `torch.export` to get an `ExportedProgram` graph or inspect `model.state_dict()`. | torch, safetensors |
| **TensorFlow** | Use `model.summary()` or `tflite-support` for `SavedModel` and `TFLite` metadata. | tensorflow, tflite-support |
| **ONNX** | Load with `onnx.load()` to access the graph; hyperparameters are in `model.metadata_props`. | onnx, onnxruntime |
| **GGUF** | Use `GGUFReader` to extract key-value pairs (hyperparameters, architecture). | gguf (official gguf-py) |
| **JAX** | Use `Orbax` for checkpoint management or `torchax` for Pytree extraction. | jax, orbax-checkpoint, torchax |
| **Scikit-learn** | Use `estimator.get_params()` to retrieve estimator hyperparameters. | scikit-learn |
| **Keras v3** | Inspect the `config.json` inside the `.keras` zip archive or use `get_config()`. | keras, h5py |

## AI dataset metadata extraction

If the dataset used for AI training, fine-tuning, or testing is
available on platforms like Hugging Face, chances are that the dataset may
have metadata available in machine-readable Croissant format.
<https://github.com/mlcommons/croissant>
