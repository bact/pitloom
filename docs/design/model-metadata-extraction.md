---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model metadata extraction

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

| Format | Extension(s) | Module | Optional dependency |
| :----- | :----------- | :----- | :------------------ |
| fastText | `.ftz`, `.bin` | `_fasttext.py` | `pip install fasttext` |
| GGUF | `.gguf` | `_gguf.py` | `pip install gguf` |
| HDF5 / Keras v1–v2 | `.h5`, `.hdf5` | `_hdf5.py` | `pip install h5py` |
| Keras v3 | `.keras` | `_keras.py` | (stdlib only) |
| NumPy | `.npy`, `.npz` | `_numpy.py` | `pip install numpy` |
| ONNX | `.onnx` | `_onnx.py` | `pip install onnx` |
| PyTorch classic | `.pt`, `.pth` | `_pytorch.py` | `pip install fickling` (safe pickle inspection) |
| PyTorch PT2 / ExecuTorch | `.pt2` | `_pytorch_pt2.py` | (stdlib only) |
| Safetensors | `.safetensors` | `_safetensors.py` | `pip install safetensors` |

## Planned format support

The formats below are on the roadmap.
Priority ordering reflects breadth of use and feasibility of safe extraction
without executing model code.

| Format | Priority | Extraction approach | Notes |
| :----- | :------- | :------------------ | :---- |
| JAX (Orbax) | Higher | `orbax-checkpoint` for pytree structure inspection without full restoration | Stores checkpoints as directories of arrays; metadata in YAML config files alongside checkpoint data |
| TensorFlow SavedModel | Planned | Parse `saved_model.pb` via Protocol Buffers; inspect `MetaGraphDef` for signature defs | `tensorflow` package or `tensorflow.core.protobuf.saved_model_pb2` for protobuf-only parsing |
| TensorFlow Lite | Planned | Parse FlatBuffer binary without loading the TF runtime | `flatbuffers` Python package; no GPU/runtime required |
| Scikit-learn | Planned, complex | Pickle/joblib serialisation — no single standard format; `fickling` for safe AST inspection to extract estimator class and `get_params()` values | Common extensions: `.pkl`, `.joblib`. Fickling is already an optional dependency. The challenge is that the serialized type varies widely (`Pipeline`, `GridSearchCV`, etc.) |
| MLflow model flavors | Planned | `MLmodel` YAML file in the artifact directory records `flavors`, `run_id`, and artifact paths | Partially addressed via `pitloom.bom.from_mlflow_run()` (SPDX fragment path); direct model flavor parsing is a separate step |

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

AIMMX is relevant to Pitloom's planned SBOM enrichment capability —
filling metadata gaps in model formats that carry little embedded information
by looking at the surrounding repository context.
See `docs/design/sbom-enrichment.md` for the enrichment design.

## Framework-native metadata extraction

| Model Format | Status | Recommended Extraction Method | Key Python Libraries |
| :---- | :---- | :---- | :---- |
| **fastText** | ✅ Implemented | `model.f.getArgs()` via C++ binding; `model.get_labels()` for supervised class list | fasttext |
| **GGUF** | ✅ Implemented | `GGUFReader` to extract typed key-value pairs from the binary header | gguf (official gguf-py) |
| **HDF5 / Keras v1–v2** | ✅ Implemented | `h5py.File.attrs` for root attributes; JSON-encoded `model_config` and `training_config` | h5py |
| **Keras v3** | ✅ Implemented | Inspect `config.json` inside the `.keras` ZIP archive; no model execution required | (stdlib only) |
| **NumPy** | ✅ Implemented | Memory-map header to read shape and dtype without loading tensor data | numpy |
| **ONNX** | ✅ Implemented | `onnx.load()` to access graph properties and `metadata_props` dictionary | onnx |
| **PyTorch classic** | ✅ Implemented | ZIP archive structure inspection; `fickling` for safe pickle AST inspection (never calls `pickle.load`) | fickling (optional) |
| **PyTorch PT2 / ExecuTorch** | ✅ Implemented | ZIP archive structure; `extra/` metadata files; `models/model.json` graph inputs/outputs | (stdlib only) |
| **Safetensors** | ✅ Implemented | `safe_open()` reads the JSON header without loading multi-gigabyte weight tensors | safetensors |
| **JAX (Orbax)** | 🔄 Planned (Higher) | `orbax-checkpoint` for pytree structure inspection without full restoration | jax, orbax-checkpoint |
| **TensorFlow SavedModel** | 🔄 Planned | `saved_model.pb` protobuf; `tflite-support` for TFLite metadata | tensorflow, tflite-support |
| **TensorFlow Lite** | 🔄 Planned | FlatBuffer format; parse without loading the TF runtime | flatbuffers |
| **Scikit-learn** | 🔄 Planned (Complex) | Pickle/joblib; `fickling` AST inspection for class name and `get_params()` values — no single standard format | scikit-learn, fickling |

## AI dataset metadata extraction

If the dataset used for AI training, fine-tuning, or testing is
available on platforms like Hugging Face, Kaggle, or OpenML,
the dataset may have metadata in machine-readable Croissant format.
<https://github.com/mlcommons/croissant>

For dataset-to-model linking within the SBOM, SPDX 3 provides dedicated
relationship types between `ai_AIPackage` and `dataset_DatasetPackage`:
`trainedOn`, `testedOn`, `finetunedOn`, `validatedOn`, and `pretrainedOn`.
Documenting the datasets associated with a model is a current gap in Pitloom's
SBOM output — only the AI model itself is recorded, not its training or
evaluation datasets.
See `docs/design/sbom-enrichment.md` for the dataset linking design plan.
