---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# GGUF fixtures

File details for `gguf/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## gguf/ggml-vocab-bert-bge.gguf

| Property | Value |
| :--- | :--- |
| Format | GGUF version 3 |
| Architecture | BERT (BGE tokenizer vocabulary only - no model weights) |
| Task | Tokenizer test fixture for llama.cpp |
| Input | N/A (vocabulary-only file - no model weights for inference) |
| Output | N/A |
| Tensors | 0 (vocabulary-only; no weight tensors) |
| Context length | 512 tokens |
| Embedding length | 384 |
| Size | 627 549 bytes (0.60 MB) |
| SHA-256 | `fbcbe22278fb302694d5f4a41bfe48c5f90e8e3554eab1c0435387dff654a854` |
| License | MIT |
| Source | <https://github.com/ggerganov/llama.cpp> (`models/ggml-vocab-bert-bge.gguf`) |
| Required library | `gguf` (`pip install pitloom[gguf]`) |

Notable metadata extracted by the GGUF extractor:

- `name` = `"bert-bge"` (from `general.name`)
- `type_of_model` = `"bert"` (from `general.architecture`)
- `hyperparameters`: `block_count=12`, `context_length=512`,
  `embedding_length=384`, `feed_forward_length=1536`,
  `attention.head_count=12`
- `properties["GGUF.tensor_count"]` = `"0"` - distinguishing feature:
  vocabulary-only GGUF files carry no weight tensors
- `properties["tokenizer.ggml.model"]` = `"bert"`,
  `properties["tokenizer.ggml.pre"]` = `"bert-bge"`
- Array fields as lengths: `properties["tokenizer.ggml.tokens.length"]` and
  `["tokenizer.ggml.token_type.length"]` = `"30522"`

---

## gguf/ggml-vocab-phi-3.gguf

| Property | Value |
| :--- | :--- |
| Format | GGUF version 3 |
| Architecture | Phi-3 (vocabulary only - no model weights) |
| Task | Tokenizer test fixture for llama.cpp |
| Input | N/A (vocabulary-only file - no model weights for inference) |
| Output | N/A |
| Tensors | 0 (vocabulary-only; no weight tensors) |
| Context length | 4 096 tokens |
| Embedding length | 3 072 |
| Size | 726 019 bytes (0.69 MB) |
| SHA-256 | `967d7190d11c4842eab697079d98d56c2116e10eb617be355a2733bfc132e326` |
| License | MIT |
| Source | <https://github.com/ggerganov/llama.cpp> (`models/ggml-vocab-phi-3.gguf`) |
| Required library | `gguf` (`pip install pitloom[gguf]`) |

Notable metadata extracted by the GGUF extractor:

- `name` = `"Phi3"` (from `general.name`)
- `type_of_model` = `"phi3"` (from `general.architecture`)
- `hyperparameters`: `context_length=4096`, `embedding_length=3072`,
  `block_count=32`, `attention.head_count=32`,
  `rope.dimension_count=96`, `rope.freq_base=10000.0`
- `properties["GGUF.tensor_count"]` = `"0"` (vocab-only)
- Array fields as lengths: `properties["tokenizer.ggml.tokens.length"]`,
  `["tokenizer.ggml.scores.length"]` and `["tokenizer.ggml.token_type.length"]`
  = `"32064"`
- `properties["tokenizer.ggml.model"]` = `"llama"` - uses LLaMA BPE
  tokenizer, unlike `ggml-vocab-bert-bge.gguf` which uses BERT
  WordPiece

---

## gguf/mmproj-tinygemma3.gguf

| Property | Value |
| :--- | :--- |
| Format | GGUF version 3 |
| Architecture | CLIP vision projector for tinygemma3 (multimodal) |
| Task | Multimodal image–text alignment (vision encoder -> language model) |
| Input | Image patches: float32 `[n_patches, clip_embed_dim]` (32 × 32 px) |
| Output | Projected embeddings: float32 `[n_patches, 128]` |
| Tensors | 71 |
| Image size | 32 × 32 px, patch size 2 × 2 |
| Projection dim | 128 |
| Size | 1 039 072 bytes (0.99 MB) |
| SHA-256 | `93c2ba8c34574dd8f2dfda64931fc20943de2f941bfe03e6e9eca68951b80604` |
| License | Apache-2.0 |
| Source | <https://huggingface.co/ggml-org/tinygemma3-GGUF> |
| Required library | `gguf` (`pip install pitloom[gguf]`) |

Notable metadata extracted by the GGUF extractor:

- `name` = `None` (no `general.name` in this mmproj file)
- `type_of_model` = `"clip"` (from `general.architecture`)
- `hyperparameters`: `embedding_length=128`, `feed_forward_length=512`,
  `block_count=4`, `attention.head_count=4`
- `properties["general.type"]` = `"clip-vision"`,
  `properties["clip.projector_type"]` = `"gemma3"`,
  `properties["clip.vision.image_size"]` = `"32"`,
  `properties["GGUF.tensor_count"]` = `"71"`
- Array fields as lengths: `properties["general.tags.length"]` = `"2"`,
  `["clip.vision.image_mean.length"]` and `["clip.vision.image_std.length"]`
  = `"3"`

This is a multimodal projector file (not a standalone language model),
making it a useful fixture for verifying that the extractor handles
non-LLM GGUF architectures correctly.

---

## gguf/stories260K.gguf

| Property | Value |
| :--- | :--- |
| Format | GGUF version 3 |
| Architecture | LLaMA (260 K parameters, 5 layers, 64-dim embeddings, 8 attention heads) |
| Task | Text generation - trained on the TinyStories dataset |
| Input | Token IDs: int32 sequence, up to 2 048 tokens |
| Output | Next-token logits: float32 `[vocab_size]` |
| Tensors | 48 |
| Context length | 2 048 tokens |
| Size | 1 185 376 bytes (1.13 MB) |
| SHA-256 | `270cba1bd5109f42d03350f60406024560464db173c0e387d91f0426d3bd256d` |
| License | MIT |
| Original author | Andrej Karpathy ([llama2.c](https://github.com/karpathy/llama2.c) / [karpathy/tinyllamas](https://huggingface.co/karpathy/tinyllamas)) |
| GGUF source | <https://huggingface.co/ggml-org/models> (`tinyllamas/stories260K.gguf`) |
| Required library | `gguf` (`pip install pitloom[gguf]`) |

Notable metadata extracted by the GGUF extractor:

- `name` = `"llama"` (from `general.name`)
- `type_of_model` = `"llama"` (from `general.architecture`)
- `hyperparameters`: `context_length=2048`, `embedding_length=64`,
  `block_count=5`, `attention.head_count=8`, `attention.head_count_kv=4`,
  `feed_forward_length=172`, `rope.dimension_count=8`
- `properties["GGUF.version"]` = `"3"`, `properties["GGUF.tensor_count"]` = `"48"`
- Array fields as lengths: `properties["tokenizer.ggml.tokens.length"]`,
  `["tokenizer.ggml.scores.length"]` and `["tokenizer.ggml.token_type.length"]`
  = `"512"`

The model is intentionally tiny (added to the tinyllamas collection
specifically for use in unit tests and similar lightweight scenarios).
