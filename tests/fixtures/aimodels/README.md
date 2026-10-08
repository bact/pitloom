---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model fixtures

The `crfsuite/`, `fasttext/`, `gguf/`, `hdf5/`, `keras/`, `numpy/`, `onnx/`,
`pytorch/`, `pytorch_pt2/`, and `safetensors/` subdirectories
contain small AI model files used as integration test fixtures.
The files are committed to the repository because they are small enough
(all under 6 MB) and stable enough to serve as reliable test inputs.

Each fixture is used by a corresponding `scope="module"` pytest fixture in
[tests/extract/ai_model/test_ai_model.py](../../extract/ai_model/test_ai_model.py) which calls
`pytest.importorskip` for the required library and skips if the fixture file
does not exist, so tests are automatically skipped when the optional
dependency is not installed or the file is absent.

> **Note:**
> The AI model files are excluded from the source distribution (sdist)
> to reduce download size. They are available in the GitHub repository.
> Clone the repo to run the full test suite.

## Hostile fixtures (`hostile/`)

Not models to read: two 8 448-byte HDF5 files, each a one-to-27-byte mutation
of a valid Keras `.h5`, on which `h5py`/libhdf5 crashes or never returns.
They are regression inputs for the wheel scan's format gate: a wheel scan
without `--trust-wheel-model` must list such a model without metadata and
never open it. **Never pass them to a reader in-process** -- use a
subprocess with a timeout. Excluded from the sdist.

| Path | What libhdf5 does | SHA-256 |
| :--- | :--- | :--- |
| `hostile/hdf5-segfault.h5` | `SIGSEGV` inside `h5py.File(...)` | `20a74cfea05f0bac4b982198fcf5296262db5b1ba9050ce870357c09d6de0cc4` |
| `hostile/hdf5-hang.h5` | never returns (busy loop) | `aae5c4109f023e619206e0b821243b4173e4974457a38076d982793a7323158d` |

## AI model summary

| Path | Format | Task | License |
| :--- | :--- | :--- | :--- |
| `crfsuite/complete.crfsuite` | CRFsuite | Generated sequence labeller: 5 labels (Thai, space, punctuation), 14 attributes | CC0-1.0 |
| `crfsuite/minimal.model` | CRFsuite (`.model` suffix) | Generated sequence labeller: 2 labels, 2 attributes | CC0-1.0 |
| `fasttext/lid.176.ftz` | fastText | Language identification | CC-BY-SA-3.0 |
| `fasttext/sentimentdemo.bin` | fastText | Text sentiment classification | CC0-1.0 |
| `gguf/ggml-vocab-bert-bge.gguf` | GGUF | Tokenizer vocabulary - BERT BGE (vocab only) | MIT |
| `gguf/ggml-vocab-phi-3.gguf` | GGUF | Tokenizer vocabulary - Phi-3 (vocab only) | MIT |
| `gguf/mmproj-tinygemma3.gguf` | GGUF | Multimodal - CLIP vision projector | Apache-2.0 |
| `gguf/stories260K.gguf` | GGUF | Text generation - LLaMA 260 K (TinyStories) | MIT |
| `hdf5/example-model.h5` | HDF5 (Keras legacy) | Binary classification (10 features -> 1 output) | CC0-1.0 |
| `keras/example-model.keras` | Keras v3 | Binary classification (10 features -> 1 output) | CC0-1.0 |
| `numpy/example-model-v1.npy` | NumPy v1.0 | Array `[[1, 2], [3, 4]]` float32 | CC0-1.0 |
| `numpy/example-model-v2.npy` | NumPy v2.0 | Array `[[1, 2], [3, 4]]` float32 | CC0-1.0 |
| `numpy/example-model-v3.npy` | NumPy v3.0 | Structured array | CC0-1.0 |
| `numpy/example-model-bundle.npz` | NumPy NPZ | Archive with `weights` array (2 × 2 float32) | CC0-1.0 |
| `onnx/encoder-model-q4f16.onnx` | ONNX | Speech recognition - Whisper encoder | Apache-2.0 |
| `onnx/gpt2-tiny-decoder.onnx` | ONNX | Text generation - GPT-2 decoder with KV-cache | MIT |
| `onnx/light-inception-v2.onnx` | ONNX | Image classification (ImageNet 1 000) | Apache-2.0 |
| `onnx/resnet-tiny-beans.onnx` | ONNX | Image classification - bean disease (3 classes) | Apache-2.0 |
| `onnx/squeezenet1.1-7.onnx` | ONNX | Image classification (ImageNet 1 000) | Apache-2.0 |
| `pytorch/example-model.pt` | PyTorch classic | Linear regression (10 features -> 1 output) - full model save | CC0-1.0 |
| `pytorch/example-model.pth` | PyTorch classic | Linear regression (10 features -> 1 output) - weights-only save | CC0-1.0 |
| `pytorch_pt2/example-model.pt2` | PyTorch PT2 Archive | Linear regression (10 features -> 1 output) | CC0-1.0 |
| `safetensors/marian-tiny-random.safetensors` | Safetensors | Machine translation - MarianMT (random weights) | MIT |
| `safetensors/phi-tiny-random.safetensors` | Safetensors | Text generation - Phi (random weights) | Apache-2.0 |
| `safetensors/speech2text-tiny-random.safetensors` | Safetensors | Speech recognition - Speech2Text (random weights) | Apache-2.0 |
| `safetensors/vits-tiny-random.safetensors` | Safetensors | Text-to-speech - VITS (random weights) | Apache-2.0 |
| `safetensors/whisper-tiny-random.safetensors` | Safetensors | Speech recognition - Whisper (random weights) | Apache-2.0 |

## File details

One file per format, with source, licence and notable extracted metadata:

- [CRFsuite](details/crfsuite.md) (`crfsuite/`)
- [fastText](details/fasttext.md) (`fasttext/`)
- [GGUF](details/gguf.md) (`gguf/`)
- [HDF5 (legacy Keras)](details/hdf5.md) (`hdf5/`)
- [Keras v3](details/keras.md) (`keras/`)
- [NumPy](details/numpy.md) (`numpy/`)
- [ONNX](details/onnx.md) (`onnx/`)
- [PyTorch classic](details/pytorch.md) (`pytorch/`)
- [PyTorch PT2](details/pytorch-pt2.md) (`pytorch_pt2/`)
- [Safetensors](details/safetensors.md) (`safetensors/`)
