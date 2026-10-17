---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Safetensors fixtures

File details for `safetensors/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## safetensors/marian-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | MarianMT encoder-decoder (2 encoder + 2 decoder layers, randomly initialised) |
| Task | Neural machine translation (not usable for real inference - random weights) |
| Tensors | 86 (shared embedding, encoder layers, decoder layers, projection bias) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 707 324 bytes (0.67 MB) |
| SHA-256 | `806e6a41de92e593c6a0275c67771f8faf0e95c92fe002faf7371fcef56142ea` |
| License | MIT |
| Source | <https://huggingface.co/optimum-internal-testing/tiny-random-marian> |
| Required library | `safetensors` (`pip install pitloom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- 86 tensors, none recorded as `inputs` (weights are not model inputs); their shapes give the parameter count

---

## safetensors/phi-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | Phi (2-layer causal LM, randomly initialised weights) |
| Task | Text generation (not usable for real inference - random weights) |
| Tensors | 33 (embeddings, 2 × self-attention blocks, LM head) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 323 520 bytes (0.31 MB) |
| SHA-256 | `6fbbc177683bcd0c8d694d552461d9dba3cd6e7f5a883cb8c6c6cce36ce6882e` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/echarlaix/tiny-random-PhiForCausalLM> |
| Required library | `safetensors` (`pip install pitloom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- 33 tensors, none recorded as `inputs` (weights are not model inputs); their shapes give the parameter count

---

## safetensors/speech2text-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | Speech2Text encoder-decoder (2 encoder + 2 decoder layers, randomly initialised) |
| Task | Automatic speech recognition (not usable for real inference - random weights) |
| Tensors | 93 (encoder with convolutional sub-sampler, decoder, embeddings) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 705 880 bytes (0.67 MB) |
| SHA-256 | `7261459bb4f43dfb595e3e576cef19b8ea2a095e29ed8837236014cd56865016` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/optimum-internal-testing/tiny-random-Speech2TextModel> |
| Required library | `safetensors` (`pip install pitloom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- 93 tensors, none recorded as `inputs` (weights are not model inputs); their shapes give the parameter count

---

## safetensors/vits-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | VITS - randomly initialised text-to-speech model |
| Task | Text-to-speech synthesis (not usable - random weights) |
| Tensors | 438 (decoder, text encoder, flow network, posterior encoder) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 344 288 bytes (0.33 MB) |
| SHA-256 | `36d41f2b533a3c5d763f7e7e7ba483dbdba875a2c326d8e8d7abc7f5531e3ca7` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/echarlaix/tiny-random-vits> |
| Required library | `safetensors` (`pip install pitloom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- 438 tensors, none recorded as `inputs` (weights are not model inputs); their shapes give the parameter count

---

## safetensors/whisper-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | Whisper encoder-decoder - randomly initialised |
| Task | Automatic speech recognition (not usable - random weights) |
| Tensors | 50 (encoder and decoder layers) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 871 760 bytes (0.83 MB) |
| SHA-256 | `f2befb0a67d1d7ce3a6ac707fa894eef12e1b23ce22a0c8fe36cc75ef4c09576` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/optimum-internal-testing/tiny-random-whisper> |
| Required library | `safetensors` (`pip install pitloom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- 50 tensors, none recorded as `inputs` (weights are not model inputs); their shapes give the parameter count
