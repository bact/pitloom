---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Test fixtures

## Build-backend fixtures

### Hatchling

`sampleproject-hatchling/` is a minimal Python package used to test the
Pitloom Hatchling build hook (`pitloom.plugins.hatch`).  See
[sampleproject-hatchling/README.md](sampleproject-hatchling/README.md) for
build instructions.

### Setuptools

`sampleproject-setuptools/` is a minimal Python package that exercises
Pitloom's setuptools metadata extraction (`pitloom.extract.setuptools`).
It uses the common transitional layout: `pyproject.toml` for the
`[build-system]` table only, with all project metadata in `setup.cfg`
and a bare `setup.py` shim.

## AI model fixtures

The `fasttext/`, `gguf/`, `hdf5/`, `keras/`, `numpy/`, `onnx/`,
`pytorch/`, `pytorch_pt2/`, and `safetensors/` subdirectories
contain small AI model files used as integration test fixtures.
The files are committed to the repository because they are small enough
(all under 6 MB) and stable enough to serve as reliable test inputs.

Each fixture is used by a corresponding `scope="module"` pytest fixture in
[tests/test_ai_model_extractor.py](../test_ai_model_extractor.py) which calls
`pytest.importorskip` for the required library and skips if the fixture file
does not exist, so tests are automatically skipped when the optional
dependency is not installed or the file is absent.

> **Note:**
> The AI model files are excluded from the source distribution (sdist)
> to reduce download size. They are available in the GitHub repository.
> Clone the repo to run the full test suite.

## AI model summary

| Path | Format | Task | License |
| :--- | :--- | :--- | :--- |
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

## Hugging Face Hub mock data

`tests/test_extract_huggingface.py` exercises `pitloom.extract._huggingface`
entirely through mocks -- no network calls are made at test time.  The survey
covers **132 real model repositories** (plus 2 dataset-namespace repos referenced
as dataset entries) observed on Hugging Face Hub in May 2026.

### Data source

The 104 models were chosen to stress-test every branch of the extractor.
They span a wide range of tasks, access restrictions, and metadata patterns:

- **Mainstream LLMs**: Mistral, Qwen, DeepSeek, LLaMA, Gemma, Phi, GPT-Neo,
  StableLM, OPT, TinyLlama; instruction-tuned, reasoning, and MoE variants.
- **Regional and low-resource models**: Thai, Japanese, Korean, Indonesian, Malay,
  Arabic, Irish, Indic (22 languages), SEA multilingual, African multilingual.
- **Multimodal and vision-language**: VQA (ViLT, BLIP, DePlot), document
  understanding (Donut, LayoutLM, Tapas), image+text (LLaVA, Gemma-3, OCR),
  text-to-image (ERNIE), food image recognition (Boba), video+text (LLaVA-Video).
- **Vision**: depth estimation (DepthPro, Marigold), keypoint detection (ViTPose),
  image segmentation (RMBG, geospatial flood), CLIP variants, DINOv2 and
  fine-tunes, ResNet/Swin.
- **Audio and speech**: ASR (Whisper, wav2vec2, Conformer, MiMo-ASR),
  TTS (OmniVoice), speaker diarization (pyannote), audio-to-audio translation
  (SeamlessM4T).
- **Embeddings and retrieval**: sentence-BERT (Japanese, Thai), ModernBERT
  (Ruri, Granite), CLIP/visual retrieval (Jina), fill-mask BERT family
  (XLM-RoBERTa, DistilBERT, gaBERT).
- **Domain-specific**: legal (Korean, Thai, Vietnamese, Italian, Arabic),
  medical summarization, educational quality scoring, human value detection,
  geospatial flood detection, food classification, robotics (GR00T, OpenVLA, Pi0.5).
- **Translation and seq2seq**: NLLB (200 languages), Opus-MT, Hunyuan-MT,
  protonX-legal T5.
- **Special-format repos**: GGUF-only (no `config.json`; multiple model families),
  diffusers repos (Marigold, Fibo-Edit, ERNIE), lerobot, timm, pyannote.audio,
  sentence-transformers, TerraTorch.
- **Access-restricted repos**: gated config (gemma-2b, Llama variants, UNI2-h,
  Indic-Conformer, pyannote), fully gated card+config (aya-vision, InkubaLM),
  no model card with config accessible (NLLB, Serengeti-E250).

Two dataset-namespace entries (`ai-for-good-lab/ai4g-flood-dataset`,
`blanchon/ETCI-2021-Flood-Detection`) appear in the granite-geospatial model card
`datasets:` field -- these are HuggingFace `/datasets/` repos, not model repos,
and cannot be passed to `read_huggingface`.  They appear as `DatasetReference`
objects in the extracted metadata.

### Why mocks instead of live API calls

Using real network calls in tests creates four problems:

1. **Flaky CI**: HuggingFace Hub access can be rate-limited, authenticated, or
   temporarily unavailable.
2. **Credential requirements**: gated models (Llama, Gemma, pyannote, etc.) require
   an accepted agreement and a token -- impossible to replicate in public CI.
3. **API instability**: model card YAML, config files, and computed tags can change
   at any time; tests would drift silently.
4. **Latency**: fetching dozens of large `config.json` files from the Hub in every
   test run would be prohibitively slow.

Mocks solve all four: each test controls exactly what the Hub "returns", including
401 responses, missing files, scalar vs. list YAML values, and exotic tag combinations
that may be rare or impermanent in the wild.

### How the mock harness works

`_patch_hf_calls(...)` is a context manager defined in the test file.  It wraps
`unittest.mock.patch.multiple()` over four private functions:

| Patched function | Replaced with | What it simulates |
| :--- | :--- | :--- |
| `_safe_load_json` | `MagicMock(side_effect=...)` keyed on filename | Returns inline dict for `config.json`, `tokenizer_config.json`, `generation_config.json`; `None` for 401/missing |
| `_load_model_card` | `MagicMock(return_value=(text, data))` | Returns model card prose + YAML frontmatter as a `(str, dict)` tuple; `(None, {})` for inaccessible/absent cards |
| `_load_model_info` | `MagicMock(return_value={...})` | Returns Hub API metadata: `author`, `sha`, `created_at`, `last_modified`, and computed `tags` list |
| `_detect_license_from_hf_files` | `MagicMock(return_value=(None, None))` | Suppresses real network calls for license-file detection; overridden per-test when detection is under test |

Each test function constructs its own `config`, `tokenizer_config`,
`generation_config`, `card_data`, and `hub_info` dicts as inline Python
literals that mirror the real API responses captured from HuggingFace Hub.
Tests are therefore self-contained: they assert on `read_huggingface()`'s
output without touching a network, a filesystem outside the test process,
or any installed model weights.

The shared helper `_make_card_data(license, pipeline_tag, tags, language, ...)` 
assembles a card YAML frontmatter dict with only the keys that are non-None,
matching the real API behaviour where absent fields simply do not appear.

### What the survey found and how the extractor improved

Every model in the zoo was tested against the extractor as it stood at the
time of addition.  Test failures and unexpected `None` values revealed six
categories of bugs and gaps:

#### 1. Language field as scalar string (bug fix)

The YAML field `language: ja` (scalar) previously caused the extractor to
iterate over the string character-by-character, yielding `["j", "a"]` instead
of `["ja"]`.  Fixed by guarding with `isinstance(raw_language, str)`.

Affected models: `sonoisa/sentence-bert-base-ja-mean-tokens`,
`jonatasgrosman/wav2vec2-large-xlsr-53-japanese`, `impira/layoutlm-document-qa`,
`google/tapas-large-finetuned-wtq`, `abeja/gpt-neox-japanese-2.7b`.

#### 2. Expanded `_DOMAIN_TAGS` (15 new pipeline tags)

The frozenset `_DOMAIN_TAGS` controls which HF pipeline tags become
`ai_domain` values in the SPDX output (rather than raw `hf.tags`).  Survey
of the 132 models found 15 tags missing:

| New tag | Example model(s) |
| :--- | :--- |
| `image-text-to-text` | `aisingapore/Gemma-SEA-LION-v4-4B-VL` |
| `video-text-to-text` | `llava-hf/LLaVA-NeXT-Video-7B-hf` |
| `image-to-image` | `briaai/Fibo-Edit-RMBG`, `windowseat-ai/windowseat-reflection` |
| `image-feature-extraction` | `facebook/dinov2-small` |
| `depth-estimation` | `apple/DepthPro-hf`, `prs-eth/marigold-depth-v1-0` |
| `keypoint-detection` | `usyd-community/vitpose-plus-huge` |
| `zero-shot-image-classification` | `laion/CLIP-convnext_base_w`, `geolocal/StreetCLIP` |
| `document-question-answering` | `naver-clova-ix/donut-base-finetuned-docvqa` |
| `table-question-answering` | `google/tapas-large-finetuned-wtq` |
| `visual-document-retrieval` | `jinaai/jina-embeddings-v4` |
| `any-to-any` | `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16` |
| `text-to-speech` | `k2-fsa/OmniVoice`, `drbaph/OmniVoice-bf16`, `HKUSTAudio/Llasa-3B` |
| `speaker-diarization` | `pyannote/speaker-diarization-community-1` |
| `audio-to-audio` | `facebook/seamless-m4t-v2-large` (via card `tags` list) |
| `time-series-forecasting` | `Salesforce/moirai-2.0-R-small` |

#### 3. New extraction: `base_model`, `base_model_relation`, `arxiv`, `doi`

`_load_model_info` was extended to return the `tags` list from the Hub API.
The main extraction loop now parses prefix-encoded tags:

| Tag prefix | Stored as | Notes |
| :--- | :--- | :--- |
| `base_model:{id}` | `extra_data["hf.base_model"]` | First ID only; also resolved from card YAML `base_model:` field |
| `base_model:{rel}:{id}` | `extra_data["hf.base_model_relation"]` | `finetune`, `quantized`, `merge`, `adapter` |
| `arxiv:{id}` | `extra_lists["hf.arxiv"]` | List; multiple papers accumulate |
| `doi:{id}` | `extra_data["hf.doi"]` | Single value |

`base_model` in card YAML may be a scalar string or a list; the extractor takes
the first entry.  The *relation type* always comes from the computed
`base_model:{rel}:{id}` tag in `model_info().tags`, not from card YAML.

The survey also confirmed all four relation keywords in practice:
`finetune` (most common), `quantized` (GGUF/AWQ/FP8 repos), `merge` (Crow-9B,
Qwen3-REAP, GLM-4.5-Air-REAP), `adapter` (no new examples, already supported).

#### 4. Dataset fallback from `model_info` tags

When `card_data.get("datasets")` is empty -- either because the model has no
card, or because the card and config are both gated -- the extractor falls back
to `dataset:*` prefix tags from `model_info().tags`.  Card YAML always takes
priority when non-empty; the fallback fires only for no-card or fully-gated repos.

This fixed dataset capture for `lelapa/InkubaLM-0.4B`: the card and config
are both gated, but `model_info().tags` contains `"dataset:lelapa/Inkuba-Mono"`,
which is now captured as a `DatasetReference`.

#### 5. YAML 1.1 boolean hazard

The ISO 639-1 language code `"no"` (Norwegian Bokmål) is parsed by PyYAML's
YAML 1.1 parser as the boolean `False`.  `openai/whisper-large-v3` has 99
language codes in its card YAML, including `"no"`.  The extractor filters
with `if lang is not False and lang`, dropping the boolean while keeping all
real strings.

#### 6. License handling: passthrough, vague, and no-license patterns

`_VAGUE_LICENSE_VALUES` = `{"other", "custom", "proprietary", "unknown", "unlicensed"}`.
Anything outside this set is stored as-is in `meta.license`, including
non-SPDX HuggingFace custom identifiers such as `"gemma"`, `"llama3.2"`,
`"llama3"`, `"bigcode-openrail-m"`, `"openrail++"`, `"apple-amlr"`,
`"kanana-license"`, `"bigscience-bloom-rail-1.0"`, `"bsd-3-clause"`,
`"cc-by-nc-4.0"`, `"cc-by-4.0"`, `"cc-by-sa-4.0"`.

When the card YAML contains a vague value, the raw string is saved in
`extra_data["hf.license_raw"]` and `_detect_license_from_hf_files` is called
to look for a real SPDX ID in license files (`LICENSE`, `COPYING`, etc.).

When the license field is absent entirely, `meta.license` is `None` and
`hf.license_raw` is not set (distinct from the vague-value path).

These patterns are tested through the license pipeline added in PR #72, which
calls `build_license_elements()` whenever `ai_model.license` is non-None,
emitting `hasDeclaredLicense` and `hasConcludedLicense` relationships into the
SPDX output and adding `simpleLicensing` to `profileConformance`.

#### 7. BLOOM architecture: non-standard config key names (known gap)

BLOOM models (`bigscience/bloom`, `bigscience/bloomz-7b1`) use `n_layer` and
`n_head` instead of `num_hidden_layers` and `num_attention_heads` — these are
**not** in `_HYPER_KEYS` → layer count and head count are silently skipped.
Similarly, BLOOM uses ALiBi positional bias with no fixed `max_position_embeddings`
field; instead it has `seq_length` for the training context window.

`"seq_length"` was **added to `_HYPER_KEYS`** so BLOOM's (and similar models')
training context length is now captured.  `n_layer` and `n_head` remain
unaliased — adding generic BLOOM aliases is deferred until other models using
those key names are found.

#### 8. Additional library names

The survey expanded the set of known `library_name` values stored in
`extra_data["hf.library_name"]`:

| `library_name` | Example model | Notes |
| :--- | :--- | :--- |
| `vllm` | `mistralai/Voxtral-Mini-4B-Realtime-2602` | vLLM serving framework for multimodal models |
| `scaling` | `Aleph-Alpha/Pharia-1-LLM-7B-control` | Aleph-Alpha proprietary training framework; config 404 |

Previously seen: `sentence-transformers`, `diffusers`, `open_clip`, `timm`,
`pyannote.audio`, `lerobot`, `TerraTorch`, `nemo`, `peft`, `gguf`.

### Metadata availability patterns

**Standard access (card + config accessible)**
Full extraction: name, type_of_model, architecture, hyperparameters, license,
domains, languages, datasets, base_model, arxiv, doi.
Examples: `mistralai/Mistral-7B-v0.1`, `Qwen/Qwen3-235B-A22B`,
`bigcode/starcoder2-3b`, `openai/whisper-large-v3`, `deepseek-ai/DeepSeek-R1`,
`typhoon-ai/typhoon-7b`, `EleutherAI/gpt-neo-2.7B`,
`kakaobank/kanana-1.5-v-3b-instruct`, `LGAI-EXAONE/EXAONE-4.5-33B`,
`THUDM/GLM-4.5-Air-REAP`, `line-corporation/line-distilbert-base-japanese`,
`line-corporation/clip-japanese-base-v2`, `Salesforce/moirai-2.0-R-small`,
`HKUSTAudio/Llasa-3B`, `mistralai/Voxtral-Mini-4B-Realtime-2602`,
`TildeAI/TildeOpen-30b-64k`, `TildeAI/TildeOpen-30b`,
`openeurollm/datamix-9b-80-20`, `bigscience/bloom`, `bigscience/bloomz-7b1`,
`occiglot/occiglot-7b-eu5-instruct`, `utter-project/EuroLLM-1.7B`.

**Gated config, accessible card**
`config.json` returns 401; `type_of_model`, `architecture`, and `hyperparameters`
are absent, but `license`, `language`, and `usage.domains` still come from
the card YAML.  Examples: `google/gemma-2b`, `meta-llama/Llama-3.2-1B`,
`meta-llama/Llama-3.2-3B`, `meta-llama/Llama-3.2-3B-Instruct`,
`MahmoodLab/UNI2-h`, `ai4bharat/indic-conformer-600m-multilingual`,
`pyannote/speaker-diarization-community-1`, `briaai/RMBG-2.0`,
`LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR`, `Fujitsu/Fujitsu-LLM-KG-8x7B`,
`CohereLabs/aya-23-8B` (partially gated — card 401, config 401).

**GGUF-only repo (no `config.json`, not gated)**
`config.json` returns 404 (file absent, not a permissions error); all metadata
comes from the model card YAML.  Architecture and hyperparameters are absent.
Examples: `aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF`,
`nomic-ai/nomic-embed-text-v1.5-GGUF`, `iapp/chinda-qwen3-4b-gguf`,
`cstr/mimo-asr-GGUF`, `Doses-AI/boba-0.8b-food-GGUF`, `lmg-anon/vntl-llama3-8b-v2-gguf`.
Same pattern applies to diffusers repos (`prs-eth/marigold-depth-v1-0`,
`briaai/Fibo-Edit-RMBG`), PEFT adapter repos (`windowseat-ai/windowseat-reflection`),
custom-framework repos (`Aleph-Alpha/Pharia-1-LLM-7B-control`,
`Aleph-Alpha/Pharia-1-LLM-7B-control-aligned`), and other library-specific repos
(`lerobot/pi05_base`, `timm/convnext_large.dinov3_lvd1689m`,
`ibm-granite/granite-geospatial-uki-flooddetection`).

**No model card, config accessible**
`ModelCard.load()` raises an exception; `card_data = {}`.  Architecture and
hyperparameters come from `config.json`; `usage.domains`, `hf.language`, and
`license` are empty/None because these fields only exist in the card YAML.
**Known gap**: tags in `model_info().tags` (which do carry domain and language
info for some no-card models) are not mapped to those fields.
Examples: `UBC-NLP/serengeti-E250`, `facebook/nllb-200-distilled-600M`.

**Fully gated (card + config both return 401)**
`model_info()` exposes `card_data`, but the extractor reads `model_info` only
for `author`, `sha`, dates, and computed tag prefixes -- not for the
`card_data` object on the API response.  Result is nearly empty: only `name`,
`hf.model_id`, `hf.url`, and `hf.author` are populated.
**Known gap**: extending `_load_model_info` to read `model_info().card_data`
would improve coverage for gated repos.
Examples: `CohereLabs/aya-vision-8b`, `CohereLabs/aya-23-8B`,
`Unbabel/wmt22-cometkiwi-da`, `lelapa/InkubaLM-0.4B`
(InkubaLM's dataset is still captured via the `dataset:*` tag fallback).

**Vague license → file detection** (`"other"`, `"custom"`, …)
The raw card value is preserved in `extra_data["hf.license_raw"]`;
`_detect_license_from_hf_files` downloads license files and runs `licenseid`
detection.  In tests, file detection is mocked to `(None, None)` by default
and overridden per-test when the detection path is being exercised.
Examples: `openthaigpt/openthaigpt-r1-32b-instruct`, `moonshotai/Kimi-K2.6`,
`SeaLLMs/SeaLLMs-v3-7B-Chat`, `briaai/RMBG-1.4`, `facebook/opt-2.7b`,
`facebook/opt-iml-max-1.3b`, `timm/convnext_large.dinov3_lvd1689m`,
`mistralai/Mistral-Medium-3.5-128B`, `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16`,
`LGAI-EXAONE/EXAONE-4.5-33B`, `LGAI-EXAONE/EXAONE-4.5-33B-AWQ`,
`LGAI-EXAONE/EXAONE-4.5-33B-FP8`, `LGAI-EXAONE/EXAONE-4.5-33B-GGUF`,
`LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR`,
`Aleph-Alpha/Pharia-1-LLM-7B-control`, `Aleph-Alpha/Pharia-1-LLM-7B-control-aligned`.

**No license** (`license` field absent from card YAML)
`meta.license` is `None`; `hf.license_raw` is not set.
Examples: `deepseek-ai/DeepSeek-R1` (MIT via `license: mit`), contrast with:
`jinaai/jina-embeddings-v4`, `microsoft/rad-dino`, `nvidia/GR00T-N1.7-3B`,
`mesolitica/mallam-1.1B-4096`, `tencent/HY-MT1.5-1.8B`, `tencent/Hunyuan-MT-7B`,
`DCU-NLP/bert-base-irish-cased-v1`, `nlp-chula/aspect-finnlp-th`,
`microsoft/VibeVoice-ASR`, `talkie-lm/talkie-1930-13b-it`.

**Domain from `tags` instead of `pipeline_tag`**
When `pipeline_tag` is absent, the extractor scans the card `tags` list for
any value in `_DOMAIN_TAGS`.  Examples: `microsoft/swin-tiny-patch4-window7-224`
and `microsoft/resnet-18` (both have `"image-classification"` in `tags`);
`Helsinki-NLP/opus-mt-th-en` has `"translation"` in `tags`; `microsoft/phi-2`
has `"code"` in `tags` (→ `usage.domains`, not `extra_lists["hf.tags"]`).

**Dataset priority: card YAML beats `model_info` tags**
When both the card YAML `datasets:` field and `model_info().tags` carry dataset
information, card YAML always wins.  Only when `card_data.get("datasets")` is
empty does the extractor fall back to `dataset:*` prefix tags.
Two tests verify this: `test_dataset_card_yaml_takes_priority_over_info_tags`
and `test_dataset_info_tag_fallback_when_no_card_datasets`.

**`"multilingual"` language keyword**
The string `"multilingual"` is not an ISO 639-1 code but appears in real card
YAML.  The extractor's language filter only drops `False` (YAML 1.1 bool) and
empty strings, so `"multilingual"` is preserved in `extra_lists["hf.language"]`.
Examples: `jinaai/jina-embeddings-v4`, `tencent/Hy-MT1.5-1.8B-2bit-GGUF`,
`k2-fsa/OmniVoice` (646 languages listed as `["multilingual"]`).

**HF dataset-namespace repos as `DatasetReference`**
Entries in the card YAML `datasets:` list that point to
`https://huggingface.co/datasets/...` repos are wrapped as `DatasetReference`
objects with that URL as `download_url`.  `read_huggingface` itself cannot be
called on dataset repos (they have no `config.json` or model card in the model
sense).  Example: `ibm-granite/granite-geospatial-uki-flooddetection` references
`ai-for-good-lab/ai4g-flood-dataset` and `blanchon/ETCI-2021-Flood-Detection`.

**Encoder-decoder / non-transformer config keys**
The m2m_100 config (`facebook/nllb-200-distilled-600M`) uses `d_model` instead
of `hidden_size`, and `encoder_layers`/`decoder_layers` alongside
`num_hidden_layers`.  Only keys in `_HYPER_KEYS` are captured, so `d_model`,
`encoder_layers`, `encoder_attention_heads`, and their decoder counterparts are
silently skipped.  This is a general pattern for seq2seq and vision models whose
config schemas differ from standard decoder-only transformers.

**Tokenizer `model_max_length` sentinel**
Some tokenizers set `model_max_length` to `1_000_000_000_000_000_019_884_624_838_656`
(≈ 10³⁰) to indicate "unlimited".  The extractor compares against
`_TOKENIZER_MAX_LEN_UNLIMITED = 10**20` and skips values at or above that
threshold.  Examples: `UBC-NLP/serengeti-E250`, `tencent/HY-MT1.5-1.8B`,
`pythainlp/wangchanglm-7.5B-sft-enth`.  Real (small) values such as 512
(`Falconsai/medical_summarization`) and 128 000 (`openai/privacy-filter`)
are captured normally as `hf.tokenizer_max_length`.

### Model zoo (132 model repos)

#### Text generation and language models

| Model ID | Pattern | Notable |
| :--- | :--- | :--- |
| `mistralai/Mistral-7B-v0.1` | Baseline transformer | Standard LLM: GQA, apache-2.0, `text-generation` pipeline |
| `Qwen/Qwen3-235B-A22B` | MoE, `qwen` license passthrough, generation config | `qwen3_moe` arch; `Qwen3MoeForCausalLM`; thinking-mode temperature+top_p |
| `Qwen/Qwen3.5-27B` | Dense Qwen3.5, GQA (8 KV heads), apache-2.0 | `qwen3` arch; `Qwen3ForCausalLM`; 40 attention heads / 8 KV heads |
| `openthaigpt/openthaigpt-r1-32b-instruct` | Vague license + file detection | `license=other`; `license_name=qwen` secondary field; Thai |
| `hexgrad/Kokoro-82M` | No `model_type` / `architectures` | Custom config schema → `type_of_model=None`, `architecture=None` |
| `moonshotai/Kimi-K2.6` | Vague license + file detection | `license=other` → `hf.license_raw`; `_detect_license_from_hf_files` triggered |
| `google/gemma-2b` | Gated config, custom license | 401 on config.json; `gemma` license in card |
| `meta-llama/Llama-3.2-1B` | Gated config, custom license, 8 languages | `llama3.2` license; config inaccessible → no arch |
| `meta-llama/Llama-3.2-3B` | Gated base, no architecture | Config gated → `type_of_model=None`; llama3.2 license |
| `meta-llama/Llama-3.2-3B-Instruct` | Gated instruct, base_model finetune | Config gated; `base_model_relation=finetune` from 3B base |
| `NousResearch/Hermes-3-Llama-3.2-3B` | Not gated, llama3 license, finetune | `LlamaForCausalLM`; `llama3` license; finetune from Llama-3.2-3B |
| `deepseek-ai/DeepSeek-R1` | MIT license, no pipeline_tag, MoE | Empty `usage.domains`; standard SPDX MIT |
| `bigcode/starcoder2-3b` | `"code"` tag → domain, dataset ref | `code` → `usage.domains` not `extra_lists["hf.tags"]`; training dataset |
| `SeaLLMs/SeaLLMs-v3-7B-Chat` | Vague license, 12 SEA/Asian languages | `license=other`; no pipeline_tag; qwen2 base |
| `typhoon-ai/typhoon-7b` | Thai-only, GQA | `["th"]`; `num_key_value_heads=8`; apache-2.0 |
| `iapp/chinda-qwen3-4b` | Base_model finetune, DOI | Thai LLM; Qwen3-4B base; `doi:10.57967/hf/5709`; apache-2.0 |
| `iapp/chinda-qwen3-4b-gguf` | GGUF-only, base_model quantized, scalar base_model | `base_model` as scalar string in card YAML; no config.json |
| `talkie-lm/talkie-1930-13b-it` | No config.json, finetune, no domain | No pipeline_tag → empty `usage.domains` |
| `pythainlp/wangchanglm-7.5B-sft-enth` | Multi-dataset, tokenizer sentinel | 3 datasets; `model_max_length` sentinel filtered; cc-by-sa-4.0 |
| `mesolitica/mallam-1.1B-4096` | No license, Malay only | `license=None`; `language=["ms"]`; mistral base |
| `llm-jp/llm-jp-3-1.8b` | Large JP vocab LLaMA | 99 584-token vocab; apache-2.0; Japanese+English |
| `mistralai/Mistral-Medium-3.5-128B` | 22 languages, vague license, no pipeline_tag | `usage.domains==[]`; `license=other` |
| `poolside/Laguna-XS.2` | Custom `model_type` and architecture | `model_type=laguna`; `LagunaForCausalLM`; custom tags preserved |
| `abeja/gpt-neox-japanese-2.7b` | Language scalar, multi-dataset | `language: ja` scalar → `["ja"]`; cc100+wikipedia datasets |
| `ibm-granite/granite-4.1-8b` | GQA (8 KV heads), 12 languages, finetune | granite arch; finetune from granite-4.1-8b-base; apache-2.0 |
| `Crownelius/Crow-9B-HERETIC-4.6` | `base_model_relation=merge`, 26 languages | Qwen3.5; merged/distilled from Claude |
| `SamsungSAILMontreal/Qwen3-Coder-Next-REAP` | `base_model_relation=merge`, MoE | Qwen3-Next 80B→60B expert pruning; merge relation |
| `facebook/opt-2.7b` | Vague license (other), OPT arch | `opt` arch; Meta non-commercial → `hf.license_raw=other` |
| `facebook/opt-iml-max-1.3b` | Vague license, arxiv, instruction-tuned OPT | `arxiv:2212.12017`; instruction-tuned on ~2000 NLP tasks |
| `EleutherAI/gpt-neo-2.7B` | gpt_neo arch, standard SPDX license | `GPTNeoForCausalLM`; 32 layers; apache-2.0 |
| `stabilityai/stablelm-2-zephyr-1_6b` | stablelm_epoch arch, 12 languages | `StableLMEpochForCausalLM`; 100 352-token vocab; apache-2.0 |
| `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | Shallow LLaMA (22 layers) | Shallower than standard 7B (32 layers); apache-2.0 |
| `microsoft/phi-2` | phi arch, `"code"` tag → domain | `code` in `_DOMAIN_TAGS`; MIT; `code` not in `hf.tags` |
| `tokyotech-llm/Qwen3-Swallow-8B-SFT-v0.2` | Qwen3 finetune, Japanese+English | SFT from CPT stage; apache-2.0 |
| `aisingapore/Gemma-SEA-LION-v4-27B-IT` | `image-text-to-text` in tags → extra domain | Gemma3 27B; 11 SEA languages; `gemma` license |
| `FINAL-Bench/Darwin-28B-KR-Legal` | Korean legal LLM, finetune | `qwen3_5` arch; 64 layers; Korean+English |
| `Intelligent-Internet/II-Medical-8B` | Qwen3 finetune, empty card tags | Medical domain; `hidden_size=4096`; no pipeline_tag; apache-2.0 |
| `THUDM/GLM-4.5-Air-REAP` | MoE, `base_model_relation=merge`, apache-2.0 | `glm4_moe` arch; `Glm4MoeForCausalLM`; Samsung REAP merge from GLM-4.5-Air |
| `Fujitsu/Fujitsu-LLM-KG-8x7B` | Gated config, NeMo library | Config 401; `library_name=nemo` → `hf.library_name`; apache-2.0 |
| `mistralai/Voxtral-Mini-4B-Realtime-2602` | Multimodal audio+text (ASR), `vllm` library | `voxtral_realtime` arch; audio encoder + text decoder; `library_name=vllm` |
| `TildeAI/TildeOpen-30b-64k` | YaRN RoPE context extension, 7 datasets, cc-by-4.0 | 8 192 → 65 536 tokens via YaRN; `rope_scaling` not in `_HYPER_KEYS`; `tokenizer_max_length=65536` |
| `TildeAI/TildeOpen-30b` | Base 30B, unlimited tokenizer sentinel | Same 7 corpora; LlamaTokenizer sentinel filtered; no YaRN |
| `openeurollm/datamix-9b-80-20` | Gemma-3 tokenizer (262K vocab), no GQA, no pipeline_tag | `vocab_size=262400`; `num_kv_heads=num_attn_heads=32`; empty `usage.domains` |
| `bigscience/bloom` | BLOOM 176B, ALiBi, custom key names, custom license | `n_layer`/`n_head` not in `_HYPER_KEYS` → layers skipped; `bigscience-bloom-rail-1.0` passthrough |
| `bigscience/bloomz-7b1` | BLOOM 7B, `seq_length` captured, xP3 finetune | `seq_length=2048` (new `_HYPER_KEYS` entry); finetune from bloom-7b1; `bigscience/xP3` dataset |
| `CohereLabs/aya-23-8B` | Fully gated (card + config 401) | Same pattern as `CohereLabs/aya-vision-8b`; only `hf.author` from `model_info` |
| `occiglot/occiglot-7b-eu5-instruct` | Mistral, `sliding_window` captured, 5 EU langs | `sliding_window=4096` in `_HYPER_KEYS`; finetune from occiglot-7b-eu5 |
| `Aleph-Alpha/Pharia-1-LLM-7B-control` | Config 404, custom `scaling` lib, `license_name` | `library_name=scaling`; `license_name=open-aleph-license`; 7 EU langs |
| `Aleph-Alpha/Pharia-1-LLM-7B-control-aligned` | DPO-aligned variant of control, finetune | Same `scaling` framework; `base_model_relation=finetune` from control |
| `utter-project/EuroLLM-1.7B` | 34 languages, GQA (16h/8kv), no pipeline_tag | Smallest multilingual EU model; unlimited tokenizer sentinel filtered |
| `Unbabel/wmt22-cometkiwi-da` | Fully gated (card + config 401) | MT quality estimation; only `hf.author` captured |

#### Embeddings, retrieval, and text classification

| Model ID | Pattern | Notable |
| :--- | :--- | :--- |
| `sonoisa/sentence-bert-base-ja-mean-tokens` | Language scalar string fix | `language: ja` → `["ja"]`; sentence-similarity; cc-by-sa-4.0 |
| `cl-nagoya/ruri-v3-310m` | ModernBERT, base_model finetune, arxiv | `arxiv:2409.07737`; Japanese embedding; sentence-similarity |
| `nomic-ai/nomic-embed-text-v1.5-GGUF` | GGUF-only, base_model quantized | No config.json; `base_model_relation=quantized`; nomic-embed |
| `ibm-granite/granite-embedding-97m-multilingual-r2` | ModernBERT, sentence-transformers library | 200+ languages; `hf.library_name=sentence-transformers`; feature-extraction |
| `FacebookAI/xlm-roberta-base` | fill-mask, 100+ languages, MIT | xlm-roberta arch; 250 002-token multilingual vocab |
| `distilbert/distilbert-base-multilingual-cased` | fill-mask, 6 layers (distilled), `["multilingual"]` | DistilBERT halves BERT's `num_hidden_layers` to 6; 119 547-token vocab |
| `DCU-NLP/bert-base-irish-cased-v1` | fill-mask, Irish (`ga`), no license | gaBERT; 30 000-token vocab; `license=None` |
| `airesearch/WangchanX-Legal-ThaiCCL-Retriever` | Base_model finetune, MIT, dataset ref | Fine-tuned from BAAI/bge-m3; xlm-roberta arch; Thai legal |
| `jinaai/jina-embeddings-v4` | visual-document-retrieval domain, no license | 131 072 token context; `language=["multilingual"]` keyword preserved; `license=None` |
| `HuggingFaceFW/fineweb-edu-classifier` | text-classification, base_model finetune | Fine-tuned from Snowflake arctic-embed; educational quality 0–5 |
| `tum-nlp/Deberta_Human_Value_Detector` | text-classification, `openrail++` passthrough | `openrail++` ∉ `_VAGUE_LICENSE_VALUES`; 20 value categories |
| `nlp-chula/aspect-finnlp-th` | text-classification, Thai financial, no license | CamemBERT-based; fine-tuned from wangchanberta; `license=None` |
| `openai/privacy-filter` | token-classification, 128 K context | `hf.tokenizer_max_length=128000` captured; custom arch |
| `line-corporation/line-distilbert-base-japanese` | fill-mask, DistilBERT (6 layers) | Japanese BERT distilled to 6 layers; `DistilBertForMaskedLM`; apache-2.0 |
| `line-corporation/clip-japanese-base-v2` | feature-extraction, custom `clyp` model_type | Line Corp CLIP variant; `CLYPModel` arch; apache-2.0; Japanese |

#### Vision

| Model ID | Pattern | Notable |
| :--- | :--- | :--- |
| `apple/DepthPro-hf` | depth-estimation domain, custom license | `apple-amlr` ∉ `_VAGUE_LICENSE_VALUES` → stored as-is; DepthPro arch |
| `prs-eth/marigold-depth-v1-0` | depth-estimation, diffusers, no config | `library_name=diffusers`; no config.json → no arch |
| `usyd-community/vitpose-plus-huge` | keypoint-detection domain | ViTPose arch; human pose estimation |
| `laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg` | zero-shot-image-classification, no config | No config.json → no arch; `library_name=open_clip` |
| `geolocal/StreetCLIP` | zero-shot-image-classification, CLIP, cc-by-nc-4.0 | CLIP arch; geo-localisation tags in extra_lists |
| `microsoft/swin-tiny-patch4-window7-224` | No pipeline_tag, domain from card tags | `"image-classification"` in `tags` → domain; imagenet-1k dataset |
| `microsoft/resnet-18` | image-classification from card tags | `resnet` arch; apache-2.0; same tag-domain pattern as Swin |
| `facebook/dinov2-small` | image-feature-extraction domain | DINOv2 self-supervised ViT; apache-2.0 |
| `microsoft/rad-dino` | image-feature-extraction, no license | DINOv2 fine-tuned on radiology; `license=None` |
| `MahmoodLab/UNI2-h` | Gated config, `cc-by-nc-nd-4.0` | Pathology/histology ViT; restrictive NC+ND license; tags in extra_lists |
| `timm/convnext_large.dinov3_lvd1689m` | Vague license, timm library, no config | `license=other`; `library_name=timm`; no config.json |
| `briaai/RMBG-1.4` | Vague license, image-segmentation | `license=other` → `hf.license_raw`; custom tags |
| `briaai/RMBG-2.0` | Gated config, vague license | Config gated → no type_of_model; domain from card; `license=other` |
| `ibm-granite/granite-geospatial-uki-flooddetection` | image-segmentation, TerraTorch, HF dataset refs | No transformers config; two `/datasets/` repos as `DatasetReference` |
| `prithivMLmods/Flood-Image-Detection` | image-classification, siglip, arxiv, finetune | Fine-tuned from google/siglip2-base-patch16-512; `arxiv:2502.14786` |
| `LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR` | Gated config, non-standard pipeline tag | Config 401; `pathology-image-analysis` captured as domain (pipeline_tag, not tags); `license=other` |
| `windowseat-ai/windowseat-reflection` | No config, PEFT library, image-to-image | Config 404; `library_name=peft` → `hf.library_name`; apache-2.0 |

#### Multimodal and visual question answering

| Model ID | Pattern | Notable |
| :--- | :--- | :--- |
| `dandelin/vilt-b32-finetuned-vqa` | visual-question-answering, base_model finetune, arxiv | ViLT on VQAv2; `arxiv:2102.03334`; finetune from vilt-b32 |
| `google/deplot` | visual-question-answering + `image-text-to-text` in tags | pix2struct; both pipeline tag and card tag → two domains; `arxiv:2212.10505` |
| `Salesforce/blip-vqa-base` | visual-question-answering, `bsd-3-clause` passthrough | `bsd-3-clause` ∉ `_VAGUE_LICENSE_VALUES`; blip arch |
| `naver-clova-ix/donut-base-finetuned-docvqa` | document-question-answering, vision-encoder-decoder | `image-to-text` also captured via card tags; donut arch |
| `impira/layoutlm-document-qa` | document-question-answering, language scalar | `language: en` scalar → `["en"]`; layoutlm arch; MIT |
| `google/tapas-large-finetuned-wtq` | table-question-answering, language scalar, dataset ref | `language: en` scalar; dataset ref; tapas arch |
| `llava-hf/LLaVA-NeXT-Video-7B-hf` | video-text-to-text + image-text-to-text (two domains) | Both pipeline tag and card tag → two domain entries; llava2 license |
| `aisingapore/Gemma-SEA-LION-v4-4B-VL` | image-text-to-text, gemma license, SEA, finetune | Gemma3 multimodal; 9 SEA languages; finetune from google/gemma-3-4b-it |
| `openvla/openvla-7b` | robotics + image-text-to-text (two domains), MIT | VLA policy; pipeline tag and card tag → two domains |
| `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16` | any-to-any domain, vague license | Reasoning + audio+video+text; `license=other`; card dataset takes priority |
| `briaai/Fibo-Edit-RMBG` | image-to-image, arxiv, base_model finetune | `arxiv:2511.06876`; finetune from briaai/Fibo-Edit; diffusers |
| `baidu/ERNIE-Image-Turbo` | text-to-image, diffusers, Chinese+English | Distilled DiT; `library_name=diffusers`; apache-2.0 |
| `Doses-AI/boba-0.8b-food-GGUF` | image-text-to-text, GGUF, food domain | No config.json → `type_of_model=None`; finetune from Qwen3.5-0.8B |
| `bakrianoo/arabic-legal-documents-ocr-1.0` | image-text-to-text, gemma license, Arabic OCR | Gemma3; `license=gemma`; scanned Arabic legal documents |
| `kakaobank/kanana-1.5-v-3b-instruct` | image-text-to-text, `kanana-license` passthrough | `kanana-1.5-v` arch; `KananaVForConditionalGeneration`; Korean VLM |
| `LGAI-EXAONE/EXAONE-4.5-33B` | image-text-to-text, vague license, 6 languages | `exaone4_5` arch; Korean+multilingual; `license=other` → `hf.license_raw` |
| `LGAI-EXAONE/EXAONE-4.5-33B-AWQ` | AWQ quantized, config accessible (unlike GGUF) | Config present; `base_model_relation=quantized`; `license=other` |
| `LGAI-EXAONE/EXAONE-4.5-33B-FP8` | FP8 quantized, `torch_dtype=float8_e4m3fn` | `torch_dtype` in `_HYPER_KEYS` → captured in hyperparameters |
| `LGAI-EXAONE/EXAONE-4.5-33B-GGUF` | GGUF, no config.json, vague license | `type_of_model=None`; `base_model_relation=quantized`; `license=other` |

#### Audio and speech

| Model ID | Pattern | Notable |
| :--- | :--- | :--- |
| `openai/whisper-large-v3` | 99-language ASR, YAML 1.1 boolean hazard | ISO code `"no"` parsed as `False` → filtered; apache-2.0 |
| `facebook/seamless-m4t-v2-large` | ASR pipeline + `audio-to-audio` + `text-to-speech` from tags | Three domains captured; cc-by-nc-4.0 |
| `ibm-granite/granite-speech-4.1-2b` | ASR, base_model finetune, 6 languages | Conformer + Q-Former + granite LM; finetune from granite-4.0-1b-base |
| `ai4bharat/indic-conformer-600m-multilingual` | Gated ASR, 22 Indian language codes | MIT; config gated; 22 ISO language codes extracted from card |
| `cstr/mimo-asr-GGUF` | GGUF ASR, base_model quantized | Qwen2-based; quantized from XiaomiMiMo/MiMo-V2.5-ASR; zh+en |
| `microsoft/VibeVoice-ASR` | ASR with diarization, arxiv, no license | 51+ languages; `arxiv:2601.18184`; vibevoice arch; `license=None` |
| `neurlang/ipa-whisper-medium` | ASR → IPA phonetics, base_model finetune | Fine-tuned from whisper-medium; outputs IPA transcriptions; 74 languages |
| `indonesian-nlp/wav2vec2-indonesian-javanese-sundanese` | ASR, 3 languages (id+jv+su), finetune | Fine-tuned from facebook/wav2vec2-large-xlsr-53 |
| `jonatasgrosman/wav2vec2-large-xlsr-53-japanese` | Language scalar, DOI | `language: ja` scalar; `doi:10.57967/hf/3568`; ASR domain |
| `k2-fsa/OmniVoice` | text-to-speech domain, arxiv, base_model finetune | 646 languages as `["multilingual"]`; `arxiv:2604.00688`; Qwen3-0.6B base |
| `drbaph/OmniVoice-bf16` | text-to-speech domain, finetune | BF16 conversion of k2-fsa/OmniVoice; same TTS domain |
| `pyannote/speaker-diarization-community-1` | speaker-diarization domain, gated, pyannote.audio | cc-by-4.0 (permissive, despite gating); no config.json; `library_name=pyannote.audio` |
| `HKUSTAudio/Llasa-3B` | text-to-speech, LLaMA arch, large vocab | `LlamaForCausalLM` repurposed for TTS; `vocab_size=193800` (speech tokens); cc-by-nc-4.0 |

#### Translation, seq2seq, and domain-specific

| Model ID | Pattern | Notable |
| :--- | :--- | :--- |
| `facebook/nllb-200-distilled-600M` | No model card, config accessible; 200 languages | m2m_100 arch; 256 K vocab; `d_model`/`encoder_layers` outside `_HYPER_KEYS` |
| `Helsinki-NLP/opus-mt-th-en` | Translation domain from card tag (no pipeline_tag) | `"translation"` in card `tags` → domain; marian arch; Thai→English |
| `tencent/HY-MT1.5-1.8B` | Translation from tag, no license, tokenizer sentinel | `"translation"` in tags; `model_max_length` sentinel filtered; `license=None` |
| `tencent/Hy-MT1.5-1.8B-2bit-GGUF` | GGUF quantized, `"multilingual"` language keyword | No config.json; `language=["multilingual"]`; `base_model_relation=quantized` |
| `tencent/Hunyuan-MT-7B` | Translation from tag, no license | Same hunyuan arch as HY-MT1.5; `license=None` |
| `protonx-models/protonx-legal-tc` | text2text-generation, NC license → other, Vietnamese | T5; proprietary non-commercial → `license=other` → `hf.license_raw` |
| `ReDiX/Legal-Embedding-ita-0.6B` | sentence-similarity, Italian legal, cc-by-nc-4.0 | Qwen3 base; Italian legal corpus |
| `lmg-anon/vntl-llama3-8b-v2-gguf` | GGUF, base_model quantized, llama3 license | Quantized from rinna/llama-3-youko-8b; translation domain |
| `sugoitoolkit/Sugoi-14B-Ultra-GGUF` | GGUF, base_model as list | `base_model: ["sugoitoolkit/Sugoi-14B-Ultra-HF"]` → first entry extracted |
| `Falconsai/medical_summarization` | T5 summarization, tokenizer max length | `model_type=t5`; `hf.tokenizer_max_length=512` captured |
| `UBC-NLP/serengeti-E250` | No model card, 250 K-vocab Electra, tokenizer sentinel | Domains/languages only in `model_info.tags` → not captured; sentinel filtered |
| `CohereLabs/aya-vision-8b` | Fully gated, license not captured | Card + config 401; `cc-by-nc-4.0` only in `model_info` object |
| `lelapa/InkubaLM-0.4B` | Fully gated, dataset captured via tag fallback | Card + config 401; `dataset:lelapa/Inkuba-Mono` captured from `model_info` tags |
| `nvidia/GR00T-N1.7-3B` | Robotics domain, no license | Humanoid robot foundation model; `pipeline_tag=robotics`; `license=None` |
| `lerobot/pi05_base` | Robotics, lerobot library, custom license, no config | `license=gemma`; `library_name=lerobot`; no config.json; Pi0.5 policy |
| `Salesforce/moirai-2.0-R-small` | `time-series-forecasting` domain, custom config keys | New `_DOMAIN_TAGS` entry; config keys (`d_model`, `patch_sizes`) not in `_HYPER_KEYS` → empty hyperparameters; cc-by-nc-4.0 |

## SBOM fragment fixtures

`fragments/` contains minimal hand-crafted SPDX 3 JSON-LD fragment files used
to test the `merge_fragments` merge pipeline and verify that AI- and
dataset-profile fields are not dropped during the stitch step.

| Path | Content | Purpose |
| :--- | :--- | :--- |
| `fragments/ai-model-fragment.spdx3.json` | One `ai_AIPackage` with hyperparameters, metrics, domain, energy consumption | Tests that all AI-profile fields survive `merge_fragments` |
| `fragments/dataset-fragment.spdx3.json` | One `dataset_DatasetPackage` with type, size, availability | Tests that dataset-profile fields survive `merge_fragments` |
| `fragments/training-run-fragment.spdx3.json` | `ai_AIPackage` + 2 `dataset_DatasetPackage` + `trainedOn`/`testedOn` relationships | Tests that provenance relationships from a simulated `loom.shoot()` output survive |

All fragment fixtures are licensed CC0-1.0.
Tests that exercise these fixtures live in `tests/test_fragments.py`.

## File details

### fasttext/lid.176.ftz

| Property | Value |
| :--- | :--- |
| Format | fastText quantised (`ftz`) |
| Architecture | Supervised text classifier - 176-class language identification |
| Task | Language identification (176 languages) |
| Input | Text (UTF-8 string) |
| Output | Class probabilities `[176]` (one score per ISO language code) |
| Embedding dim | 16 |
| Labels | 176 ISO language codes (e.g. `__label__en`, `__label__de`, …) |
| Training | epoch=5, lr=0.05, wordNgrams=1, loss=hs |
| n-gram range | minn=2, maxn=4 |
| Size | 938 013 bytes (0.89 MB) |
| SHA-256 | `8f3472cfe8738a7b6099e8e999c3cbfae0dcd15696aac7d7738a8039db603e83` |
| License | CC-BY-SA-3.0 |
| Source | <https://fasttext.cc/docs/en/language-identification.html> (`lid.176.ftz`) |
| Required library | `fasttext` (`pip install pitloom[fasttext]`) |

Notable metadata extracted by the fastText extractor:

- `type_of_model` = `"supervised"` (from `args.model`)
- `hyperparameters`: `dim=16`, `lr=0.05`, `epoch=5`, `wordNgrams=1`,
  `minCount=1000`, `minn=2`, `maxn=4`, `neg=5`, `bucket=2000000`, `ws=5`
- `properties["lossName"]` = `"hs"` (hierarchical softmax)
- `properties["labels"]` contains 176 comma-separated language codes
- `name`, `description`, `version` are all `None`

### fasttext/sentimentdemo.bin

| Property | Value |
| :--- | :--- |
| Format | fastText binary (quantised, version 12) |
| Architecture | Supervised text classifier - 4-class Thai sentiment |
| Task | Sentiment classification: `pos`, `neg`, `neu`, `q` (question) |
| Input | Text (UTF-8 string, Thai language) |
| Output | Class probabilities `[4]` (`pos`, `neg`, `neu`, `q`) |
| Embedding dim | 21 |
| Labels | `__label__pos`, `__label__neg`, `__label__neu`, `__label__q` |
| Training | epoch=100, lr=0.05, wordNgrams=4, loss=softmax |
| n-gram range | minn=3, maxn=6 |
| Size | 96 339 bytes (0.09 MB) |
| SHA-256 | `a88bf0de7dff74d740cd45048521d319ff7c2560085f2604af265561e72ec4bc` |
| License | CC0-1.0 |
| Source | <https://github.com/bact/sentimentdemo> (`model.bin`) |
| Required library | `fasttext` (`pip install pitloom[fasttext]`) |

Notable metadata extracted by the fastText extractor:

- `type_of_model` = `"supervised"` (from `args.model`)
- `hyperparameters`: `dim=21`, `lr=0.05`, `epoch=100`, `wordNgrams=4`,
  `minCount=1`, `minn=3`, `maxn=6`, `neg=5`, `bucket=33502`, `ws=5`
- `properties["lossName"]` = `"softmax"`
- `properties["labels"]` = `"__label__pos,__label__neg,__label__neu,__label__q"`
- `name`, `description`, `version` are all `None` - fastText binary files
  do not embed a model name or description

---

### gguf/ggml-vocab-bert-bge.gguf

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

---

### gguf/ggml-vocab-phi-3.gguf

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
- `properties["tokenizer.ggml.model"]` = `"llama"` - uses LLaMA BPE
  tokenizer, unlike `ggml-vocab-bert-bge.gguf` which uses BERT
  WordPiece

---

### gguf/mmproj-tinygemma3.gguf

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

This is a multimodal projector file (not a standalone language model),
making it a useful fixture for verifying that the extractor handles
non-LLM GGUF architectures correctly.

---

### gguf/stories260K.gguf

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

The model is intentionally tiny (added to the tinyllamas collection
specifically for use in unit tests and similar lightweight scenarios).

---

### hdf5/example-model.h5

| Property | Value |
| :--- | :--- |
| Format | HDF5 - legacy Keras v2 format (`.h5`) |
| Magic bytes | `\x89HDF\r\n\x1a\n` (HDF5 signature) |
| Architecture | `Sequential` (`nn.Linear(10, 1)` equivalent - Dense(1, sigmoid)) |
| Task | Binary classification (10 features -> 1 output) |
| Input | float32 `[None, 10]` |
| Output | float32 `[None, 1]` (sigmoid probability) |
| Version | 3.13.2 (Keras version) |
| Model name | `Binary_Classifier_v1` |
| Size | 23 352 bytes (0.02 MB) |
| SHA-256 | `587004a95c71efffd650977f9530deab113e5017a04a8af91403011a4302be59` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | `h5py` (`pip install pitloom[hdf5]`) |

Notable metadata extracted by the HDF5 extractor:

- `version` = `"3.13.2"` (from `keras_version` attribute)
- `type_of_model` = `"Sequential"` (from `model_config.class_name`)
- `name` = `"Binary_Classifier_v1"` (from `model_config.config.name`)
- `inputs[0]["shape"]` = `[None, 10]`
- `hyperparameters`: `trainable=True`
- `properties["backend"]` contains the Keras backend name

---

### keras/example-model.keras

| Property | Value |
| :--- | :--- |
| Format | Keras v3 native format (`.keras`) - ZIP archive |
| Architecture | `Sequential` (`nn.Linear(10, 1)` equivalent - Dense(1, sigmoid)) |
| Task | Binary classification (10 features -> 1 output) |
| Input | float32 `[None, 10]` |
| Output | float32 `[None, 1]` (sigmoid probability) |
| Version | 3.13.2 (Keras version) |
| Model name | `Binary_Classifier_v1` |
| Size | 19 215 bytes (0.02 MB) |
| SHA-256 | `d0941f8de74c5afdfdcb93e395bb1e3538b6029eac4001a31dd283d95e979fde` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | None (uses stdlib `zipfile` + `json`) |

Notable metadata extracted by the Keras extractor:

- `version` = `"3.13.2"` (from `metadata.json`)
- `type_of_model` = `"Sequential"` (from `config.json`)
- `name` = `"Binary_Classifier_v1"` (from `config.json`)
- `inputs[0]["shape"]` = `[None, 10]`
- `hyperparameters`: `trainable=True`
- `properties["date_saved"]` contains the save timestamp

---

### numpy/example-model-bundle.npz

| Property | Value |
| :--- | :--- |
| Format | NumPy NPZ archive (`.npz`) |
| Arrays | 1: `weights` - shape `(2, 2)`, dtype `float32` |
| Data | `weights`: `[[1.0, 2.0], [3.0, 4.0]]` |
| Size | 284 bytes |
| SHA-256 | `dc19291ff85cbe795eba48c2c84bd31cf32263b3219bc53a97128467070ae3b5` |
| License | CC0-1.0 |
| Source | Generated for testing purpose |
| Required library | `numpy` (`pip install pitloom[numpy]`) |

Notable metadata extracted by the NumPy extractor:

- `inputs` lists 1 array: `{"name": "weights", "shape": [2, 2], "dtype": "float32"}`
- `properties` does not contain `npy_format_version` - NPZ archives do not
  expose a per-file NPY version at the archive level
- `name`, `description`, `version` are all `None`

---

### numpy/example-model-v1.npy

| Property | Value |
| :--- | :--- |
| Format | NumPy v1.0 (`.npy`) |
| NPY version | 1.0 - 2-byte LE uint16 header length, latin1 header encoding |
| Shape | `(2, 2)` |
| dtype | `float32` |
| Data | `[[1.0, 2.0], [3.0, 4.0]]` |
| Size | 144 bytes |
| SHA-256 | `e8072b61f5d81a3cc4dc59b9d5e14187b20b5d8a3ddd8e6d0bc5128bda5f27aa` |
| License | CC0-1.0 |
| Required library | `numpy` (`pip install pitloom[numpy]`) |

Notable metadata extracted by the NumPy extractor:

- `properties["npy_format_version"]` = `"1.0"`
- `properties["header_encoding"]` = `"latin1"`
- `inputs[0]` = `{"shape": [2, 2], "dtype": "float32"}`
- `name`, `description`, `version` are all `None`

---

### numpy/example-model-v2.npy

| Property | Value |
| :--- | :--- |
| Format | NumPy v2.0 (`.npy`) |
| NPY version | 2.0 - 4-byte LE uint32 header length, latin1 header encoding |
| Shape | `(2, 2)` |
| dtype | `float32` |
| Data | `[[1.0, 2.0], [3.0, 4.0]]` |
| Size | 144 bytes |
| SHA-256 | `f133b24fb6c1a4cd7dff975636fdc2d93616bb40afa0e2e6ce59e4bbf34e18e1` |
| License | CC0-1.0 |
| Source | Generated for testing purpose |
| Required library | `numpy` (`pip install pitloom[numpy]`) |

Notable metadata extracted by the NumPy extractor:

- `properties["npy_format_version"]` = `"2.0"`
- `properties["header_encoding"]` = `"latin1"`
- `inputs[0]` = `{"shape": [2, 2], "dtype": "float32"}`
- `name`, `description`, `version` are all `None`

---

### numpy/example-model-v3.npy

| Property | Value |
| :--- | :--- |
| Format | NumPy v3.0 (`.npy`) |
| NPY version | 3.0 - 4-byte LE uint32 header length, UTF-8 header encoding |
| Shape | `(2,)` |
| dtype | `[('π_weights', '<f4', (2,))]` (structured dtype with Unicode field name) |
| Data | `[([1., 2.],), ([3., 4.],)]` |
| Size | 144 bytes |
| SHA-256 | `8cd3ec2addd4446899352d1408a4849762e4d453d584c56e375216fce3344dd8` |
| License | CC0-1.0 |
| Source | Generated for testing purpose |
| Required library | `numpy` (`pip install pitloom[numpy]`) |

Notable metadata extracted by the NumPy extractor:

- `properties["npy_format_version"]` = `"3.0"`
- `properties["header_encoding"]` = `"utf-8"` - required for the Unicode field
  name `π_weights` (Greek letter π); version 1.x/2.x latin1 encoding would
  reject this header
- `inputs[0]["dtype"]` contains `"π_weights"` - confirms UTF-8 round-trip
- `name`, `description`, `version` are all `None`

---

### onnx/encoder-model-q4f16.onnx

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

### onnx/gpt2-tiny-decoder.onnx

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

### onnx/light-inception-v2.onnx

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

### onnx/resnet-tiny-beans.onnx

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

### onnx/squeezenet1.1-7.onnx

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

---

### pytorch/example-model.pt

| Property | Value |
| :--- | :--- |
| Format | PyTorch classic (`.pt`) - full model (`torch.save(model, ...)`) |
| Architecture | `nn.Linear(10, 1)` (linear regression) |
| Task | Linear regression (10 features -> 1 output) |
| Input | `x`: float32 `[batch, 10]` |
| Output | float32 `[batch, 1]` |
| Size | 2 637 bytes |
| SHA-256 | `38c9cf8d5d491fd9a85e8e311e172406f6edda0d961fa9aa6ec04f249a002186` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | `torch` (`pip install pitloom[pytorch]`) |

Notable metadata extracted by the PyTorch extractor:

- `format` = `AiModelFormat.PYTORCH` (detected via ZIP magic bytes)
- `type_of_model` = `None` - class name extraction requires the optional
  `fickling` library
- `name`, `description`, `version` are all `None` - PyTorch classic format
  embeds no model metadata

---

### pytorch/example-model.pth

| Property | Value |
| :--- | :--- |
| Format | PyTorch classic (`.pth`) - weights-only (`torch.save(model.state_dict(), ...)`) |
| Architecture | `nn.Linear(10, 1)` (linear regression) |
| Task | Linear regression (10 features -> 1 output) - weights-only save (no class info) |
| Input | `x`: float32 `[batch, 10]` |
| Output | float32 `[batch, 1]` |
| Size | 2 005 bytes |
| SHA-256 | `748f37e6fc24a5ec7b77aa5186cb7cff662e5635317f65a4f2b800a6bd7f14d2` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | `torch` (`pip install pitloom[pytorch]`) |

Notable metadata extracted by the PyTorch extractor:

- `format` = `AiModelFormat.PYTORCH` (detected via ZIP magic bytes)
- `type_of_model` = `None` - state-dict saves contain only tensors, no class name
- `name`, `description`, `version` are all `None`

---

### pytorch_pt2/example-model.pt2

| Property | Value |
| :--- | :--- |
| Format | PyTorch PT2 Archive (ExecuTorch on-device format) - ZIP archive |
| Architecture | `nn.Linear(10, 1)` (linear regression) |
| Task | Linear regression (10 features -> 1 output) |
| Description | A serialized PT2 model for metadata extraction test. |
| Version | 1.0.0 |
| Input | `x`: float32 `[batch, 10]` |
| Output | `linear`: float32 `[batch, 1]` |
| Author | Pitloom |
| Tags | regression |
| Size | 8 800 bytes |
| SHA-256 | `7f057931a7094fd88dcc1a9331a73b5a2fe0769e285ea8b63e1d31a8372319f5` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | None (uses stdlib `zipfile` + `json`) |

Notable metadata extracted by the PT2 extractor:

- `version` = `"1.0.0"` (from `extra/model_version`; takes precedence over `archive_version`)
- `description` = `"A serialized PT2 model for metadata extraction test."`
  (from `extra/description`)
- `license` = `"CC0-1.0"` (from `extra/license`)
- `properties["author"]` = `"Pitloom"` (from `extra/author`)
- `properties["tags"]` = `"regression"` (from `extra/tags`)
- `inputs` = `[{"name": "x"}]`, `outputs` = `[{"name": "linear"}]` (from `models/model.json`)
- `type_of_model` = `None` - PT2 extractor does not inspect pickle data
- `name` = `None` - no `extra/name` or `METADATA.json` with name in this fixture

---

### safetensors/marian-tiny-random.safetensors

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
- `inputs` lists 86 tensors covering `model.encoder.*`, `model.decoder.*`,
  and `model.shared.weight` - confirming the seq2seq encoder-decoder structure

---

### safetensors/phi-tiny-random.safetensors

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
- `inputs` lists 33 tensors: `model.embed_tokens.weight`, `model.layers.*`,
  `model.final_layernorm.*`, `lm_head.*`

---

### safetensors/speech2text-tiny-random.safetensors

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
- `inputs` lists 93 tensors with `model.encoder.*` (including conv sub-sampler)
  and `model.decoder.*` - distinguishes the convolutional ASR encoder from the
  attention-only Whisper encoder in `whisper-tiny-random.safetensors`

---

### safetensors/vits-tiny-random.safetensors

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
- `inputs` lists 438 tensors - the most in the fixture set - covering
  sub-modules `decoder.*`, `text_encoder.*`, `flow.*`, and
  `posterior_encoder.*`

---

### safetensors/whisper-tiny-random.safetensors

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
- `inputs` lists 50 tensors with both `model.encoder.*` and
  `model.decoder.*` keys - confirms encoder-decoder architecture

---
