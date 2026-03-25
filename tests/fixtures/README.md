---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Test fixtures

This directory contains small AI model files used as integration test fixtures.
The files are committed to the repository because they are small enough
(all under 5 MB) and stable enough to serve as reliable test inputs.

Each fixture is used by a corresponding `scope="module"` pytest fixture in
[tests/test_ai_model_extractor.py](../test_ai_model_extractor.py) which calls
`pytest.importorskip` for the required library, so tests are automatically
skipped when the optional dependency is not installed.

## Summary

| Filename | Format | Task | License |
| :--- | :--- | :--- | :--- |
| `encoder_model_q4f16.onnx` | ONNX | Speech recognition — Whisper encoder | Apache-2.0 |
| `gpt2-tiny-decoder.onnx` | ONNX | Text generation — GPT-2 decoder with KV-cache | MIT |
| `light-inception-v2.onnx` | ONNX | Image classification (ImageNet 1 000) | Apache-2.0 |
| `resnet-tiny-beans.onnx` | ONNX | Image classification — bean disease (3 classes) | Apache-2.0 |
| `squeezenet1.1-7.onnx` | ONNX | Image classification (ImageNet 1 000) | Apache-2.0 |
| `marian-tiny-random.safetensors` | Safetensors | Machine translation — MarianMT (random weights) | MIT |
| `phi-tiny-random.safetensors` | Safetensors | Text generation — Phi (random weights) | Apache-2.0 |
| `speech2text-tiny-random.safetensors` | Safetensors | Speech recognition — Speech2Text (random weights) | Apache-2.0 |
| `vits-tiny-random.safetensors` | Safetensors | Text-to-speech — VITS (random weights) | Apache-2.0 |
| `whisper-tiny-random.safetensors` | Safetensors | Speech recognition — Whisper (random weights) | Apache-2.0 |
| `ggml-vocab-bert-bge.gguf` | GGUF | Tokenizer vocabulary — BERT BGE (vocab only) | MIT |
| `ggml-vocab-phi-3.gguf` | GGUF | Tokenizer vocabulary — Phi-3 (vocab only) | MIT |
| `mmproj-tinygemma3.gguf` | GGUF | Multimodal — CLIP vision projector | Apache-2.0 |
| `stories260K.gguf` | GGUF | Text generation — LLaMA 260 K (TinyStories) | MIT |

## Files

### encoder_model_q4f16.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 8, opsets: ai.onnx 14, com.microsoft 1) |
| Architecture | Whisper tiny — speech encoder |
| Task | Automatic speech recognition (encoder half only) |
| Quantisation | Q4F16 (4-bit weights, float16 activations) |
| Input | `input_features`: float32 `[batch_size, 80, 3000]` (mel spectrogram) |
| Output | `last_hidden_state`: float32 `[batch_size, 1500, 384]` |
| Size | 6 296 073 bytes (6.00 MB) |
| SHA-256 | `236f9f7d8bf038df0b4cc92daa33eb7ef71770d664ceac10b78c545665e82373` |
| License | Apache-2.0 (Whisper) |
| Source | <https://huggingface.co/onnx-community/whisper-tiny-ONNX> |
| Required library | `onnx` (`pip install loom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"main_graph"` (from `graph.name`)
- `type_of_model` = `"neural network"` (empty domain falls back to default)
- `properties["opset.ai.onnx"]` = `"14"`
- `properties["opset.com.microsoft"]` = `"1"` (Microsoft contrib ops for
  quantised kernels)

---

### gpt2-tiny-decoder.onnx

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
| Required library | `onnx` (`pip install loom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"torch_jit"` (PyTorch JIT export)
- `properties["opset.ai.onnx"]` = `"13"`
- `outputs` includes `logits` and 10 KV-cache tensors
  (`present.0.key` … `present.4.value`) — unique decoder structure
  not present in the encoder-only ONNX fixtures

---

### light-inception-v2.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 3, opset 9) |
| Architecture | InceptionV2 — lightweight CNN for ImageNet classification |
| Task | Image classification (1 000 ImageNet classes) |
| Input | `data_0`: float32 `[1, 3, 224, 224]` (NCHW) |
| Output | `prob_1`: float32 `[1, 1000]` |
| Graph inputs | 487 total (1 data input + 486 weight initializers) |
| Size | 159 024 bytes (0.16 MB) |
| SHA-256 | `224d77d55b26559a959db627c3f417a623fbf3b3000d25f0939327aa935d933f` |
| License | Apache-2.0 |
| Source | <https://github.com/onnx/onnx> |
| | (`onnx/backend/test/data/light/light_inception_v2.onnx`) |
| Required library | `onnx` (`pip install loom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"inception_v2"` (from `graph.name`)
- `type_of_model` = `"neural network"` (empty domain falls back to default)
- `properties["opset.ai.onnx"]` = `"9"` — oldest opset in the fixture set
- 487 graph inputs: the first is `data_0` [1, 3, 224, 224]; the remaining
  486 are weight initializers listed in `graph.input` following the pre-ONNX
  opset-9 convention where initializers were included in the input list

---

### resnet-tiny-beans.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 7, opset 11) |
| Architecture | ResNet (2-stage, basic blocks) fine-tuned for bean disease |
| Task | Image classification — 3 classes: angular\_leaf\_spot, bean\_rust, healthy |
| Input | `pixel_values`: float32 `[batch, channels, 224, 224]` |
| Output | `logits`: float32 `[batch, 3]` |
| Size | 761 053 bytes (0.73 MB) |
| SHA-256 | `cf2b1901da25924f8b68a4c9cec74b5a673f12d2b9dead57c2488d400dd2a2b5` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/fxmarty/resnet-tiny-beans> |
| Required library | `onnx` (`pip install loom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"torch_jit"` (PyTorch JIT export sets the graph name to `torch_jit`)
- `type_of_model` = `"neural network"` (empty domain falls back to default)
- `properties["opset.ai.onnx"]` = `"11"`

---

### squeezenet1.1-7.onnx

| Property | Value |
| :--- | :--- |
| Format | ONNX (IR version 3, opset 7) |
| Architecture | SqueezeNet 1.1 — lightweight CNN for ImageNet classification |
| Task | Image classification (1 000 ImageNet classes) |
| Parameters | ~1.2 M |
| Input | `data`: float32 `[1, 3, 224, 224]` (NCHW, normalised RGB) |
| Output | `squeezenet0_flatten0_reshape0`: float32 `[1, 1000]` |
| Size | 4 956 208 bytes (4.73 MB) |
| SHA-256 | `1eeff551a67ae8d565ca33b572fc4b66e3ef357b0eb2863bb9ff47a918cc4088` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/onnxmodelzoo/squeezenet1.1-7> |
| Required library | `onnx` (`pip install loom[onnx]`) |

Notable metadata extracted by the ONNX extractor:

- `name` = `"main"` (from `graph.name`)
- `type_of_model` = `"neural network"` (domain is empty, falls back to default)
- `properties["opset.ai.onnx"]` = `"7"`

---

### marian-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | MarianMT encoder-decoder (2 encoder + 2 decoder layers, randomly initialised) |
| Task | Neural machine translation (not usable for real inference — random weights) |
| Tensors | 86 (shared embedding, encoder layers, decoder layers, projection bias) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 707 324 bytes (0.67 MB) |
| SHA-256 | `806e6a41de92e593c6a0275c67771f8faf0e95c92fe002faf7371fcef56142ea` |
| License | MIT |
| Source | <https://huggingface.co/optimum-internal-testing/tiny-random-marian> |
| Required library | `safetensors` (`pip install loom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- `inputs` lists 86 tensors covering `model.encoder.*`, `model.decoder.*`,
  and `model.shared.weight` — confirming the seq2seq encoder-decoder structure

---

### phi-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | Phi (2-layer causal LM, randomly initialised weights) |
| Task | Text generation (not usable for real inference — random weights) |
| Tensors | 33 (embeddings, 2 × self-attention blocks, LM head) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 323 520 bytes (0.31 MB) |
| SHA-256 | `6fbbc177683bcd0c8d694d552461d9dba3cd6e7f5a883cb8c6c6cce36ce6882e` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/echarlaix/tiny-random-PhiForCausalLM> |
| Required library | `safetensors` (`pip install loom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- `inputs` lists 33 tensors: `model.embed_tokens.weight`, `model.layers.*`,
  `model.final_layernorm.*`, `lm_head.*`

---

### speech2text-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | Speech2Text encoder-decoder (2 encoder + 2 decoder layers, randomly initialised) |
| Task | Automatic speech recognition (not usable for real inference — random weights) |
| Tensors | 93 (encoder with convolutional sub-sampler, decoder, embeddings) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 705 880 bytes (0.67 MB) |
| SHA-256 | `7261459bb4f43dfb595e3e576cef19b8ea2a095e29ed8837236014cd56865016` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/optimum-internal-testing/tiny-random-Speech2TextModel> |
| Required library | `safetensors` (`pip install loom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- `inputs` lists 93 tensors with `model.encoder.*` (including conv sub-sampler)
  and `model.decoder.*` — distinguishes the convolutional ASR encoder from the
  attention-only Whisper encoder in `whisper-tiny-random.safetensors`

---

### vits-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | VITS — randomly initialised text-to-speech model |
| Task | Text-to-speech synthesis (not usable — random weights) |
| Tensors | 438 (decoder, text encoder, flow network, posterior encoder) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 344 288 bytes (0.33 MB) |
| SHA-256 | `36d41f2b533a3c5d763f7e7e7ba483dbdba875a2c326d8e8d7abc7f5531e3ca7` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/echarlaix/tiny-random-vits> |
| Required library | `safetensors` (`pip install loom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- `inputs` lists 438 tensors — the most in the fixture set — covering
  sub-modules `decoder.*`, `text_encoder.*`, `flow.*`, and
  `posterior_encoder.*`

---

### whisper-tiny-random.safetensors

| Property | Value |
| :--- | :--- |
| Format | Safetensors |
| Architecture | Whisper encoder-decoder — randomly initialised |
| Task | Automatic speech recognition (not usable — random weights) |
| Tensors | 50 (encoder and decoder layers) |
| `__metadata__` | `{"format": "pt"}` |
| Size | 871 760 bytes (0.83 MB) |
| SHA-256 | `f2befb0a67d1d7ce3a6ac707fa894eef12e1b23ce22a0c8fe36cc75ef4c09576` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/optimum-internal-testing/tiny-random-whisper> |
| Required library | `safetensors` (`pip install loom[safetensors]`) |

Notable metadata extracted by the Safetensors extractor:

- `name`, `description`, `version`, `type_of_model` are all `None`
- `properties["format"]` = `"pt"`
- `inputs` lists 50 tensors with both `model.encoder.*` and
  `model.decoder.*` keys — confirms encoder-decoder architecture

---

### ggml-vocab-bert-bge.gguf

| Property | Value |
| :--- | :--- |
| Format | GGUF version 3 |
| Architecture | BERT (BGE tokenizer vocabulary only — no model weights) |
| Task | Tokenizer test fixture for llama.cpp |
| Tensors | 0 (vocabulary-only; no weight tensors) |
| Context length | 512 tokens |
| Embedding length | 384 |
| Size | 627 549 bytes (0.60 MB) |
| SHA-256 | `fbcbe22278fb302694d5f4a41bfe48c5f90e8e3554eab1c0435387dff654a854` |
| License | MIT |
| Source | <https://github.com/ggerganov/llama.cpp> (`models/ggml-vocab-bert-bge.gguf`) |
| Required library | `gguf` (`pip install loom[gguf]`) |

Notable metadata extracted by the GGUF extractor:

- `name` = `"bert-bge"` (from `general.name`)
- `type_of_model` = `"bert"` (from `general.architecture`)
- `hyperparameters`: `block_count=12`, `context_length=512`,
  `embedding_length=384`, `feed_forward_length=1536`,
  `attention.head_count=12`
- `properties["GGUF.tensor_count"]` = `"0"` — distinguishing feature:
  vocabulary-only GGUF files carry no weight tensors
- `properties["tokenizer.ggml.model"]` = `"bert"`,
  `properties["tokenizer.ggml.pre"]` = `"bert-bge"`

---

### ggml-vocab-phi-3.gguf

| Property | Value |
| :--- | :--- |
| Format | GGUF version 3 |
| Architecture | Phi-3 (vocabulary only — no model weights) |
| Task | Tokenizer test fixture for llama.cpp |
| Tensors | 0 (vocabulary-only; no weight tensors) |
| Context length | 4 096 tokens |
| Embedding length | 3 072 |
| Size | 726 019 bytes (0.69 MB) |
| SHA-256 | `967d7190d11c4842eab697079d98d56c2116e10eb617be355a2733bfc132e326` |
| License | MIT |
| Source | <https://github.com/ggerganov/llama.cpp> (`models/ggml-vocab-phi-3.gguf`) |
| Required library | `gguf` (`pip install loom[gguf]`) |

Notable metadata extracted by the GGUF extractor:

- `name` = `"Phi3"` (from `general.name`)
- `type_of_model` = `"phi3"` (from `general.architecture`)
- `hyperparameters`: `context_length=4096`, `embedding_length=3072`,
  `block_count=32`, `attention.head_count=32`,
  `rope.dimension_count=96`, `rope.freq_base=10000.0`
- `properties["GGUF.tensor_count"]` = `"0"` (vocab-only)
- `properties["tokenizer.ggml.model"]` = `"llama"` — uses LLaMA BPE
  tokenizer, unlike `ggml-vocab-bert-bge.gguf` which uses BERT
  WordPiece

---

### mmproj-tinygemma3.gguf

| Property | Value |
| :--- | :--- |
| Format | GGUF version 3 |
| Architecture | CLIP vision projector for tinygemma3 (multimodal) |
| Task | Multimodal image–text alignment (vision encoder → language model) |
| Tensors | 71 |
| Image size | 32 × 32 px, patch size 2 × 2 |
| Projection dim | 128 |
| Size | 1 039 072 bytes (0.99 MB) |
| SHA-256 | `93c2ba8c34574dd8f2dfda64931fc20943de2f941bfe03e6e9eca68951b80604` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/ggml-org/tinygemma3-GGUF> |
| Required library | `gguf` (`pip install loom[gguf]`) |

Notable metadata extracted by the GGUF extractor:

- `name` = `None` (no `general.name` in this mmproj file)
- `type_of_model` = `"clip"` (from `general.architecture`)
- `hyperparameters`: `embedding_length=128`, `feed_forward_length=512`,
  `block_count=4`, `attention.head_count=4`
- `properties["general.type"]` = `"clip-vision"`,
  `properties["clip.projector_type"]` = `"gemma3"`,
  `properties["clip.vision.image_size"]` = `"32"`,
  `properties["GGUF.tensor_count"]` = `"71"`

This is a multimodal projector file (not a standalone language model),
making it a useful fixture for verifying that the extractor handles
non-LLM GGUF architectures correctly.

---

### stories260K.gguf

| Property | Value |
| :--- | :--- |
| Format | GGUF version 3 |
| Architecture | LLaMA (260 K parameters, 5 layers, 64-dim embeddings, 8 attention heads) |
| Task | Text generation — trained on the TinyStories dataset |
| Tensors | 48 |
| Context length | 2 048 tokens |
| Size | 1 185 376 bytes (1.13 MB) |
| SHA-256 | `270cba1bd5109f42d03350f60406024560464db173c0e387d91f0426d3bd256d` |
| License | MIT |
| Original author | Andrej Karpathy ([llama2.c](https://github.com/karpathy/llama2.c) / [karpathy/tinyllamas](https://huggingface.co/karpathy/tinyllamas)) |
| GGUF source | <https://huggingface.co/ggml-org/models> (`tinyllamas/stories260K.gguf`) |
| Required library | `gguf` (`pip install loom[gguf]`) |

Notable metadata extracted by the GGUF extractor:

- `name` = `"llama"` (from `general.name`)
- `type_of_model` = `"llama"` (from `general.architecture`)
- `hyperparameters`: `context_length=2048`, `embedding_length=64`,
  `block_count=5`, `attention.head_count=8`, `attention.head_count_kv=4`,
  `feed_forward_length=172`, `rope.dimension_count=8`
- `properties["GGUF.version"]` = `"3"`, `properties["GGUF.tensor_count"]` = `"48"`

The model is intentionally tiny (added to the tinyllamas collection
specifically for use in unit tests and similar lightweight scenarios).

---
