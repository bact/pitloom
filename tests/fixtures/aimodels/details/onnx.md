---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# ONNX fixtures

File details for `onnx/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## onnx/encoder-model-q4f16.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 8, opsets: ai.onnx 14, com.microsoft 1) |
| Architecture | Whisper tiny - speech encoder |
| Task | Automatic speech recognition (encoder half only) |
| Quantisation | Q4F16 (4-bit weights, float16 activations) |
| Input | `input_features`: float32 `[batch_size, 80, 3000]` (mel spectrogram) |
| Output | `last_hidden_state`: float32 `[batch_size, 1500, 384]` |
| Size | 6 296 073 bytes (6.00 MB) |
| SHA-256 | `236f9f7d8bf038df0b4cc92daa33eb7ef71770d664ceac10b78c545665e82373` |
| License | Apache-2.0 (Whisper) |
| Source | <https://huggingface.co/onnx-community/whisper-tiny-ONNX> |
| Required library | `onnx` (`pip install pitloom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"main_graph"` (from `graph.name`)
- `type_of_model` = `"neural network"` (empty domain falls back to default)
- `properties["opset.ai.onnx"]` = `"14"`
- `properties["opset.com.microsoft"]` = `"1"` (Microsoft contrib ops for
  quantised kernels)

---

## onnx/gpt2-tiny-decoder.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 8, opset 13) |
| Architecture | GPT-2 causal language model decoder |
| Task | Text generation with KV-cache outputs |
| Inputs | `input_ids`: INT64; `attention_mask`: INT64 |
| Outputs | `logits` + 10 KV-cache tensors (`present.{0-4}.{key,value}`) |
| Size | 1 031 944 bytes (0.98 MB) |
| SHA-256 | `c0e66aade2899caa6498a4de411e48c3e5caa92e8a3286a4ad9aa0b9e986c52c` |
| License | MIT (fxmarty/gpt2-tiny-onnx) |
| Source | <https://huggingface.co/fxmarty/gpt2-tiny-onnx> |
| Required library | `onnx` (`pip install pitloom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"torch_jit"` (PyTorch JIT export)
- `properties["opset.ai.onnx"]` = `"13"`
- `outputs` includes `logits` and 10 KV-cache tensors
  (`present.0.key` … `present.4.value`) - unique decoder structure
  not present in the encoder-only ONNX fixtures

---

## onnx/light-inception-v2.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 3, opset 9) |
| Architecture | InceptionV2 - lightweight CNN for ImageNet classification |
| Task | Image classification (1 000 ImageNet classes) |
| Input | `data_0`: float32 `[1, 3, 224, 224]` (NCHW) |
| Output | `prob_1`: float32 `[1, 1000]` |
| Graph inputs | 487 total (1 data input + 486 weight initializers) |
| Size | 159 024 bytes (0.16 MB) |
| SHA-256 | `224d77d55b26559a959db627c3f417a623fbf3b3000d25f0939327aa935d933f` |
| License | Apache-2.0 |
| Source | <https://github.com/onnx/onnx> |
| | (`onnx/backend/test/data/light/light_inception_v2.onnx`) |
| Required library | `onnx` (`pip install pitloom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"inception_v2"` (from `graph.name`)
- `type_of_model` = `"neural network"` (empty domain falls back to default)
- `properties["opset.ai.onnx"]` = `"9"` - oldest opset in the fixture set
- 487 graph inputs: the first is `data_0` [1, 3, 224, 224]; the remaining
  486 are weight initializers listed in `graph.input` following the pre-ONNX
  opset-9 convention where initializers were included in the input list

---

## onnx/resnet-tiny-beans.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 7, opset 11) |
| Architecture | ResNet (2-stage, basic blocks) fine-tuned for bean disease |
| Task | Image classification - 3 classes: angular\_leaf\_spot, bean\_rust, healthy |
| Input | `pixel_values`: float32 `[batch, channels, 224, 224]` |
| Output | `logits`: float32 `[batch, 3]` |
| Size | 761 053 bytes (0.73 MB) |
| SHA-256 | `cf2b1901da25924f8b68a4c9cec74b5a673f12d2b9dead57c2488d400dd2a2b5` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/fxmarty/resnet-tiny-beans> |
| Required library | `onnx` (`pip install pitloom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"torch_jit"` (PyTorch JIT export sets the graph name to `torch_jit`)
- `type_of_model` = `"neural network"` (empty domain falls back to default)
- `properties["opset.ai.onnx"]` = `"11"`

---

## onnx/squeezenet1.1-7.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 3, opset 7) |
| Architecture | SqueezeNet 1.1 - lightweight CNN for ImageNet classification |
| Task | Image classification (1 000 ImageNet classes) |
| Parameters | ~1.2 M |
| Input | `data`: float32 `[1, 3, 224, 224]` (NCHW, normalised RGB) |
| Output | `squeezenet0_flatten0_reshape0`: float32 `[1, 1000]` |
| Size | 4 956 208 bytes (4.73 MB) |
| SHA-256 | `1eeff551a67ae8d565ca33b572fc4b66e3ef357b0eb2863bb9ff47a918cc4088` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/onnxmodelzoo/squeezenet1.1-7> |
| Required library | `onnx` (`pip install pitloom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"main"` (from `graph.name`)
- `type_of_model` = `"neural network"` (domain is empty, falls back to default)
- `properties["opset.ai.onnx"]` = `"7"`
