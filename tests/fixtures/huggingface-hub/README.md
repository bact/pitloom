---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Hugging Face Hub mock data

`tests/test_extract_huggingface.py` exercises `pitloom.extract._huggingface`
entirely through mocks -- no network calls are made at test time.  The survey
covers **165 real model repositories** observed on Hugging Face Hub in May 2026.

## Data source

The 165 models were chosen to stress-test every branch of the extractor.
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

## Why mocks instead of live API calls

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

## How the mock harness works

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

## What the survey found and how the extractor improved

Every model in the zoo was tested against the extractor as it stood at the
time of addition.  Test failures and unexpected `None` values revealed bugs,
gaps, and a wide range of unusual patterns in real HF repos.

### 1. Language field as scalar string (bug fix)

The YAML field `language: ja` (scalar) previously caused the extractor to
iterate over the string character-by-character, yielding `["j", "a"]` instead
of `["ja"]`.  Fixed by guarding with `isinstance(raw_language, str)`.

Affected models: `sonoisa/sentence-bert-base-ja-mean-tokens`,
`jonatasgrosman/wav2vec2-large-xlsr-53-japanese`, `impira/layoutlm-document-qa`,
`google/tapas-large-finetuned-wtq`, `abeja/gpt-neox-japanese-2.7b`.

### 2. Expanded `_DOMAIN_TAGS` (19 new pipeline tags)

The frozenset `_DOMAIN_TAGS` controls which HF pipeline tags become
`ai_domain` values in the SPDX output (rather than raw `hf.tags`).  Survey
of the 165 models found 19 tags missing:

| New tag | Example model(s) |
| :--- | :--- |
| `image-text-to-text` | `aisingapore/Gemma-SEA-LION-v4-4B-VL` |
| `video-text-to-text` | `llava-hf/LLaVA-NeXT-Video-7B-hf` |
| `image-to-image` | `briaai/Fibo-Edit-RMBG`, `windowseat-ai/windowseat-reflection` |
| `image-feature-extraction` | `facebook/dinov2-small` |
| `depth-estimation` | `apple/DepthPro-hf`, `prs-eth/marigold-depth-v1-0` |
| `keypoint-detection` | `usyd-community/vitpose-plus-huge`, `ETH-CVG/lightglue_superpoint`, `qualcomm/HRNetPose` |
| `zero-shot-image-classification` | `laion/CLIP-convnext_base_w`, `geolocal/StreetCLIP` |
| `document-question-answering` | `naver-clova-ix/donut-base-finetuned-docvqa` |
| `table-question-answering` | `google/tapas-large-finetuned-wtq` |
| `visual-document-retrieval` | `jinaai/jina-embeddings-v4` |
| `any-to-any` | `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16`, `inclusionAI/LLaDA2.0-Uni`, `ByteDance-Seed/BAGEL-7B-MoT` |
| `text-to-speech` | `k2-fsa/OmniVoice`, `drbaph/OmniVoice-bf16`, `HKUSTAudio/Llasa-3B` |
| `speaker-diarization` | `pyannote/speaker-diarization-community-1` |
| `audio-to-audio` | `facebook/seamless-m4t-v2-large` (via card `tags` list) |
| `time-series-forecasting` | `Salesforce/moirai-2.0-R-small` |
| `text-to-3d` | `stabilityai/stable-zero123`, `openai/shap-e`, `FreedomIntelligence/BlenderLLM` |
| `image-to-3d` | `apple/Sharp` |
| `voice-activity-detection` | `FireRedTeam/FireRedVAD` |
| `text-ranking` | `Alibaba-NLP/gte-multilingual-reranker-base` |

### 3. `pipeline_tag` always captured; `tags` items filtered by `_DOMAIN_TAGS`

These two card YAML fields feed `usage.domains` via **different rules**:

- **`pipeline_tag`** (scalar) → always appended to `usage.domains`, regardless
  of whether the value appears in `_DOMAIN_TAGS`.  A non-standard or novel tag
  such as `"pathology-image-analysis"` (`LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR`)
  is still captured as a domain when it is the model's `pipeline_tag`.
- **`tags`** (list) → each item is checked against `_DOMAIN_TAGS`; only matching
  values are added to `usage.domains`.  Non-matching items go to
  `extra_lists["hf.tags"]`.  This prevents generic metadata strings
  (`"safetensors"`, `"transformers"`, geography tags, etc.) from polluting domains.

This means a model can have **multiple domains** when both sources fire:

| Model | `pipeline_tag` domain | Domain from `tags` |
| :--- | :--- | :--- |
| `llava-hf/LLaVA-NeXT-Video-7B-hf` | `video-text-to-text` | `image-text-to-text` |
| `facebook/seamless-m4t-v2-large` | `automatic-speech-recognition` | `audio-to-audio`, `text-to-speech` |
| `openvla/openvla-7b` | `robotics` | `image-text-to-text` |
| `google/deplot` | `visual-question-answering` | `image-text-to-text` |
| `aisingapore/Gemma-SEA-LION-v4-27B-IT` | `image-text-to-text` | `image-text-to-text` (dedup'd) |

The deduplication guard (`if tag_str not in usage_domains`) prevents double-counting
when `pipeline_tag` and a `tags` entry carry the same value.

### 4. New extraction: `base_model`, `base_model_relation`, `arxiv`, `doi`

`_load_model_info` was extended to return the `tags` list from the Hub API.
The main extraction loop now parses prefix-encoded tags:

| Tag prefix | Stored as | Notes |
| :--- | :--- | :--- |
| `base_model:{id}` | `extra_data["hf.base_model"]` | First ID only; also resolved from card YAML `base_model:` field |
| `base_model:{rel}:{id}` | `extra_data["hf.base_model_relation"]` | `finetune`, `quantized`, `merge`, `adapter` |
| `arxiv:{id}` | `extra_lists["hf.arxiv"]` | List; multiple papers accumulate |
| `doi:{id}` | `extra_data["hf.doi"]` | Single value |

**`base_model` in card YAML: scalar or list.**
The field may appear as a bare string (`base_model: owner/name`) or as a YAML
list (`base_model: ["owner/name"]`).  The extractor always takes the first
entry.  Example: `iapp/chinda-qwen3-4b-gguf` uses scalar form;
`sugoitoolkit/Sugoi-14B-Ultra-GGUF` uses list form.

**Relation type comes from Hub API tags, not card YAML.**
The card YAML `base_model:` field only provides the ID.  The relation keyword
(`finetune` / `quantized` / `merge` / `adapter`) always comes from the computed
`base_model:{rel}:{id}` tag in `model_info().tags`.

**Both `base_model:{id}` and `base_model:{rel}:{id}` may appear simultaneously.**
Some repos emit the plain-ID tag alongside the relational tag, e.g.:
`base_model:Qwen/Qwen3-VL-8B-Instruct` and
`base_model:finetune:Qwen/Qwen3-VL-8B-Instruct` (`TencentARC/TimeLens-8B`).
The extractor only extracts the relation from the relational form; the plain
tag is ignored (the ID is resolved from the card YAML instead).

**All four relation keywords confirmed in the wild:**
`finetune` (most common), `quantized` (GGUF/AWQ/FP8/MLX/ONNX/OpenVINO repos,
and unexpectedly for layer-distilled models — see §11), `merge` (Crow-9B,
Qwen3-REAP, GLM-4.5-Air-REAP), `adapter` (no new examples, already supported).

### 5. Dataset fallback from `model_info` tags

When `card_data.get("datasets")` is empty -- either because the model has no
card, or because the card and config are both gated -- the extractor falls back
to `dataset:*` prefix tags from `model_info().tags`.  Card YAML always takes
priority when non-empty; the fallback fires only for no-card or fully-gated repos.

This fixed dataset capture for `lelapa/InkubaLM-0.4B`: the card and config
are both gated, but `model_info().tags` contains `"dataset:lelapa/Inkuba-Mono"`,
which is now captured as a `DatasetReference`.

### 6. YAML 1.1 boolean hazard

The ISO 639-1 language code `"no"` (Norwegian Bokmål) is parsed by PyYAML's
YAML 1.1 parser as the boolean `False`.  `openai/whisper-large-v3` has 99
language codes in its card YAML, including `"no"`.  The extractor filters
with `if lang is not False and lang`, dropping the boolean while keeping all
real strings.

### 7. Non-ISO values in the `language` field

The `hf.language` extractor passes non-standard values through unchanged
(only `False` and empty strings are filtered).  Real repos use:

| Non-ISO value | Meaning | Example model(s) |
| :--- | :--- | :--- |
| `"multilingual"` | Covers many languages (not a specific code) | `jinaai/jina-embeddings-v4`, `k2-fsa/OmniVoice`, `tencent/Hy-MT1.5-1.8B-2bit-GGUF` |
| `"code"` | Programming-language content | `huggingface/CodeBERTa-small-v1` |
| `False` (bool) | ISO code `"no"` parsed by YAML 1.1 | `openai/whisper-large-v3` — filtered out |

### 8. License handling: passthrough, vague, and no-license patterns

`_VAGUE_LICENSE_VALUES` = `{"other", "custom", "proprietary", "unknown", "unlicensed"}`.
Anything outside this set is stored as-is in `meta.license`.  This includes
non-SPDX HuggingFace custom identifiers:

| Custom identifier | Example model(s) |
| :--- | :--- |
| `gemma` | `google/gemma-2b`, `aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF`, `lerobot/pi05_base`, `bakrianoo/arabic-legal-documents-ocr-1.0` |
| `llama3.2` | `meta-llama/Llama-3.2-1B`, `meta-llama/Llama-3.2-3B`, `meta-llama/Llama-3.2-3B-Instruct` |
| `llama3` | `NousResearch/Hermes-3-Llama-3.2-3B` |
| `apple-amlr` | `apple/DepthPro-hf`, `apple/OpenELM-270M`, `apple/Sharp` |
| `kanana-license` | `kakaobank/kanana-1.5-v-3b-instruct` |
| `bigscience-bloom-rail-1.0` | `bigscience/bloom`, `bigscience/bloomz-7b1` |
| `bigcode-openrail-m` | `bigcode/starcoder2-3b` |
| `openrail++` | `tum-nlp/Deberta_Human_Value_Detector` |
| `bsd-3-clause` | `Salesforce/blip-vqa-base` |
| `cc-by-nc-4.0` | `geolocal/StreetCLIP`, `MahmoodLab/UNI2-h`, `facebook/seamless-m4t-v2-large`, `HKUSTAudio/Llasa-3B` |
| `cc-by-4.0` | `pyannote/speaker-diarization-community-1`, `TildeAI/TildeOpen-30b-64k`, `TildeAI/TildeOpen-30b` |
| `cc-by-sa-4.0` | `sonoisa/sentence-bert-base-ja-mean-tokens`, `pythainlp/wangchanglm-7.5B-sft-enth` |
| `cc-by-nc-nd-4.0` | `MahmoodLab/UNI2-h` |
| `qwen` | `openthaigpt/openthaigpt-r1-32b-instruct` (via `license_name`) |
| `llava2` | `llava-hf/LLaVA-NeXT-Video-7B-hf` |

**The `license_name` secondary field** appears when the primary `license` field
is vague or unrecognised.  It is stored in `extra_data["hf.license_name"]`:

| `license_name` value | Example model | Notes |
| :--- | :--- | :--- |
| `qwen` | `openthaigpt/openthaigpt-r1-32b-instruct` | Clarifies which custom license |
| `sai-nc-community` | `stabilityai/stable-zero123` | Stability AI non-commercial |
| `tencent-hunyuan-community` | `tencent/HY-Motion-1.0` | Tencent Hunyuan community |
| `open-aleph-license` | `Aleph-Alpha/Pharia-1-LLM-7B-control` | Aleph Alpha open licence |
| `bsd-3-clause` | `TencentARC/TimeLens-8B` | SPDX ID used as `license_name` when HF has no SPDX slot |

When the card YAML contains a vague `license` value, the raw string is saved in
`extra_data["hf.license_raw"]` and `_detect_license_from_hf_files` is called
to look for a real SPDX ID in license files (`LICENSE`, `COPYING`, etc.).

When the `license` field is absent entirely, `meta.license` is `None` and
`hf.license_raw` is not set (distinct from the vague-value path).

### 9. BLOOM architecture: non-standard config key names (known gap)

BLOOM models (`bigscience/bloom`, `bigscience/bloomz-7b1`) use `n_layer` and
`n_head` instead of `num_hidden_layers` and `num_attention_heads` — these are
**not** in `_HYPER_KEYS` → layer count and head count are silently skipped.
Similarly, BLOOM uses ALiBi positional bias with no fixed `max_position_embeddings`
field; instead it has `seq_length` for the training context window.

`"seq_length"` was **added to `_HYPER_KEYS`** so BLOOM's (and similar models')
training context length is now captured.  `n_layer` and `n_head` remain
unaliased — adding generic BLOOM aliases is deferred until other models using
those key names are found.

ALiBi also appears in `Gen-Verse/MMaDA-8B-Base` (`model_type=llada`): no
`max_position_embeddings`, uses `alibi: true` instead.

### 10. Additional library names

The survey expanded the set of known `library_name` values stored in
`extra_data["hf.library_name"]`:

| `library_name` | Example model | Notes |
| :--- | :--- | :--- |
| `vllm` | `mistralai/Voxtral-Mini-4B-Realtime-2602` | vLLM serving framework for multimodal models |
| `scaling` | `Aleph-Alpha/Pharia-1-LLM-7B-control` | Aleph-Alpha proprietary training framework; config 404 |
| `stanza` | `stanfordnlp/stanza-fi`, `stanfordnlp/stanza-de` | Stanford Stanza NLP; no config.json; no pipeline_tag |
| `openvino` | `OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov` | OpenVINO quantized model; config accessible (unlike GGUF) |
| `mlx` | `mlx-community/gemma-4-e2b-it-4bit` | Apple MLX quantized model; config accessible |
| `transformers.js` | `onnx-community/gemma-4-E2B-it-ONNX` | Transformers.js ONNX export; config accessible |
| `aion` | `polymathic-ai/aion-base` | Custom scientific foundation model framework; no model_type |
| `ml-sharp` | `apple/Sharp` | Apple Sharp 3D generation library; no config.json |
| `bagel-mot` | `ByteDance-Seed/BAGEL-7B-MoT` | ByteDance BAGEL Mixture-of-Tokens framework |
| `HY-Motion-1.0` | `tencent/HY-Motion-1.0` | Tencent Hunyuan Motion series; non-standard `library_name` value |
| `pytorch` | `qualcomm/HRNetPose` | Qualcomm native PyTorch format; no config.json |
| `sap-rpt-1-oss` | `SAP/sap-rpt-1-oss` | Self-referential: `library_name` equals the model slug; gated config |

Previously seen: `sentence-transformers`, `diffusers`, `open_clip`, `timm`,
`pyannote.audio`, `lerobot`, `TerraTorch`, `nemo`, `peft`, `gguf`.

### 11. Nested config → empty hyperparameters (known gap)

Some models split their configuration across nested sub-dicts (e.g. `llm_config`,
`vit_config`, `vae_config`, `text_config`, `vision_config`).  The extractor's
`_HYPER_KEYS` lookup is shallow — it reads only the top-level keys of
`config.json`.  When all numeric parameters are inside a nested sub-config,
the top-level search finds nothing and `hyperparameters` is returned as `{}`.

This is intentional: adding recursive key scanning would risk false matches
across heterogeneous model families.  The gap is documented and deferred until
a need to extract nested keys from a common family arises.

Affected models:

| Model | Nested key(s) | Top-level gap |
| :--- | :--- | :--- |
| `ByteDance-Seed/BAGEL-7B-MoT` | `llm_config`, `vit_config`, `vae_config` | All LM numeric keys nested |
| `sensenova/SenseNova-U1-8B-MoT` | `llm_config` | All LM numeric keys nested |
| `TencentARC/TimeLens-8B` | `text_config`, `vision_config` | All LM numeric keys nested; top level uses `dtype` not `torch_dtype` |
| `ETH-CVG/lightglue_superpoint` | `keypoint_detector_config` | Non-standard top-level keys (`descriptor_dim`, etc.) also not in `_HYPER_KEYS` |
| `polymathic-ai/aion-base` | — (no `model_type`; fully custom) | No standard keys at any level |

**`dtype` vs `torch_dtype`** (related gap): Some newer VLMs use `dtype` at the
config top level instead of `torch_dtype`.  `dtype` is not in `_HYPER_KEYS`
and is therefore silently skipped.  Example: `TencentARC/TimeLens-8B` has
`dtype: bfloat16` at the top level; the equivalent `torch_dtype: bfloat16`
would have been captured.

### 12. `architectures` field absent from config.json (known gap)

Most model configs include an `architectures` list (e.g. `["BertForMaskedLM"]`).
Some older or minimally maintained repos omit this field entirely — the key is
simply absent rather than an empty list.  The extractor handles this safely:
`meta.architecture` is `None`, while `meta.type_of_model` is still populated
from the always-present `model_type` key.

Example: `dbmdz/bert-base-turkish-cased` — config.json has `model_type: bert`
but no `architectures` field → `type_of_model="bert"`, `architecture=None`.

### 13. `model_type` vs `architectures[0]`: base type vs custom wrapper

The `model_type` field identifies the base architecture family (used for
framework routing), while `architectures[0]` names the specific Python class
(which may be a custom wrapper around the base).  These can diverge:

- `XiaomiMiMo/MiMo-Audio-7B-Instruct`: `model_type="qwen2"` (base decoder)
  but `architectures=["MiMoAudioModel"]` (Xiaomi's audio-augmented wrapper).
  The extractor captures both: `type_of_model="qwen2"`,
  `architecture="MiMoAudioModel"`.
- `mistralai/Voxtral-Mini-4B-Realtime-2602`: `model_type="voxtral_realtime"`;
  `architectures=["VoxtralRealtimeForConditionalGeneration"]` — both custom,
  both captured.

### 14. `model_type="new"` as a literal placeholder string

The Alibaba GTE reranker family uses the string `"new"` as `model_type` — not
a descriptive name but a literal placeholder retained during Transformers
upstream work.  The `architectures` class is correspondingly named
`NewForSequenceClassification`.  The extractor captures both values verbatim:
`type_of_model="new"`, `architecture="NewForSequenceClassification"`.

Example: `Alibaba-NLP/gte-multilingual-reranker-base`.

### 15. `quantized` base_model relation applied to layer-reduced models

The Hub API tag `base_model:quantized:` is not limited to numeric precision
quantization (INT4/INT8/FP8/AWQ).  It is also applied when a model is
compressed by **layer reduction** (distillation to fewer layers):

- `cross-encoder/ms-marco-MiniLM-L6-v2`: distilled from the 12-layer L12
  model to 6 layers.  Hub tags it `base_model:quantized:cross-encoder/ms-marco-MiniLM-L12-v2`.
  The extractor faithfully stores `hf.base_model_relation="quantized"` even
  though no numeric quantization occurred.

The semantic gap between "model compression" (which `quantized` was intended
for in practice) and "numeric precision reduction" (the literal meaning) is a
Hub tagging convention, not an extractor bug.

### 16. Generation config: `generation.` prefixed hyperparameters

`generation_config.json` is read alongside `config.json`.  Keys in
`_GEN_HYPER_KEYS` = (`temperature`, `top_p`, `top_k`, `repetition_penalty`,
`max_new_tokens`) are extracted and stored in `hyperparameters` with a
`generation.` prefix: e.g. `"generation.temperature"`, `"generation.top_p"`.

Example: `Qwen/Qwen3-235B-A22B` has a thinking-mode generation config that
sets `temperature` and `top_p`; these appear as `generation.temperature` and
`generation.top_p` in the extracted hyperparameters.

### 17. Non-transformer (vision/seq2seq) configs: domain-specific keys (known gap)

Models that are not standard decoder-only transformers use config schemas with
no overlap with `_HYPER_KEYS`:

| Model family | Config keys present | Keys missing from `_HYPER_KEYS` |
| :--- | :--- | :--- |
| RT-DETR (`PekingU/*`) | `d_model`, `decoder_attention_heads`, `num_queries` | All except `torch_dtype` |
| NLLB (`facebook/nllb-*`) | `d_model`, `encoder_layers`, `decoder_layers` | `d_model`, `encoder_layers`, `decoder_layers` |
| Moirai (`Salesforce/moirai-*`) | `d_model`, `patch_sizes`, `context_length` | All — custom time-series schema |
| LightGlue (`ETH-CVG/lightglue_*`) | `descriptor_dim`, `filter_threshold` | All — feature matching schema |

For these models only `torch_dtype` (if present) is captured from `config.json`;
all other hyperparameters are `{}`.  This is a known gap deferred until
specific non-LM key extraction becomes a project need.

### 18. `pipeline_tag` mismatch between card YAML and Hub API

The card YAML `pipeline_tag:` (set by the author) and the Hub API's
`transformersInfo.pipeline_tag` (inferred by the framework) can disagree:

- `TencentARC/TimeLens-8B`: card says `video-text-to-text`; Hub auto-detection
  returns `image-text-to-text` (the Qwen3VL default).
- `cross-encoder/ms-marco-MiniLM-L6-v2`: card says `text-ranking`; Hub
  transformers auto-detection returns `text-classification`.
- `dbmdz/bert-base-turkish-cased`: no `pipeline_tag` in card; Hub would infer
  `fill-mask` from the BERT config, but the card author did not set one.

The extractor always uses the **card YAML** value (author's intent), never the
Hub API auto-detection.  If the card has no `pipeline_tag`, `usage.domains`
starts empty (then the `tags` list may still contribute domains).

## Metadata availability patterns

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
`occiglot/occiglot-7b-eu5-instruct`, `utter-project/EuroLLM-1.7B`,
`FreedomIntelligence/BlenderLLM`, `apple/OpenELM-270M`, `MiniMaxAI/MiniMax-M2.7`,
`inclusionAI/LLaDA2.0-Uni`, `Gen-Verse/MMaDA-8B-Base`,
`XiaomiMiMo/MiMo-Audio-7B-Instruct`, `sail/Sailor2-20B`,
`Alibaba-NLP/gte-modernbert-base`, `Bencode92/tradepulse-finbert-sentiment`,
`Alibaba-NLP/gte-multilingual-reranker-base`,
`OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov`,
`mlx-community/gemma-4-e2b-it-4bit`, `onnx-community/gemma-4-E2B-it-ONNX`,
`PekingU/rtdetr_r50vd_coco_o365`, `PekingU/rtdetr_r50vd`,
`TencentARC/TimeLens-8B`, `dbmdz/bert-base-turkish-cased`,
`cross-encoder/ms-marco-MiniLM-L6-v2`.

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
`briaai/Fibo-Edit-RMBG`, `stabilityai/stable-zero123`), PEFT adapter repos
(`windowseat-ai/windowseat-reflection`), custom-framework repos
(`Aleph-Alpha/Pharia-1-LLM-7B-control`, `Aleph-Alpha/Pharia-1-LLM-7B-control-aligned`),
other library-specific repos (`lerobot/pi05_base`, `timm/convnext_large.dinov3_lvd1689m`,
`ibm-granite/granite-geospatial-uki-flooddetection`), and stanza repos
(`stanfordnlp/stanza-fi`, `stanfordnlp/stanza-de`).
Also applies to: `openai/shap-e`, `apple/Sharp`, `FireRedTeam/FireRedVAD`,
`qualcomm/HRNetPose`, `SAP/sap-rpt-1-oss` (gated with `.pt` format files, no config.json).

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
`Aleph-Alpha/Pharia-1-LLM-7B-control`, `Aleph-Alpha/Pharia-1-LLM-7B-control-aligned`,
`stabilityai/stable-zero123`, `tencent/HY-Motion-1.0`,
`MiniMaxAI/MiniMax-M2.7`, `ETH-CVG/lightglue_superpoint`, `qualcomm/HRNetPose`,
`TencentARC/TimeLens-8B` (`license_name=bsd-3-clause` — an SPDX identifier used as `license_name`).

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
config schemas differ from standard decoder-only transformers.  See also §17.

**Tokenizer `model_max_length` sentinel**
Some tokenizers set `model_max_length` to `1_000_000_000_000_000_019_884_624_838_656`
(≈ 10³⁰) to indicate "unlimited".  The extractor compares against
`_TOKENIZER_MAX_LEN_UNLIMITED = 10**20` and skips values at or above that
threshold.  Examples: `UBC-NLP/serengeti-E250`, `tencent/HY-MT1.5-1.8B`,
`pythainlp/wangchanglm-7.5B-sft-enth`.  Real (small) values such as 512
(`Falconsai/medical_summarization`) and 128 000 (`openai/privacy-filter`)
are captured normally as `hf.tokenizer_max_length`.

**Multiple domains from both `pipeline_tag` and card `tags`**
When `pipeline_tag` is set *and* the `tags` list contains additional values
that are in `_DOMAIN_TAGS`, the extractor accumulates all of them into
`usage.domains`.  See §3 for examples and the dedup rule.  Models with three
domains: `facebook/seamless-m4t-v2-large` (`automatic-speech-recognition` +
`audio-to-audio` + `text-to-speech`).

**Quantized format repos with accessible `config.json`**
Unlike GGUF repos (where `config.json` returns 404), several other quantized or
converted formats retain the original `config.json`:

- **AWQ**: `LGAI-EXAONE/EXAONE-4.5-33B-AWQ` — config present; `torch_dtype`
  and standard keys captured.
- **FP8**: `LGAI-EXAONE/EXAONE-4.5-33B-FP8` — `torch_dtype=float8_e4m3fn`
  captured in hyperparameters.
- **OpenVINO**: `OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov` —
  `torch_dtype=int8` captured; `library_name=openvino`.
- **MLX**: `mlx-community/gemma-4-e2b-it-4bit` — config present;
  `library_name=mlx`.
- **ONNX / Transformers.js**: `onnx-community/gemma-4-E2B-it-ONNX` — config
  present; `library_name=transformers.js`.

All carry `base_model_relation=quantized` from the Hub API tags.

**RoBERTa-family `max_position_embeddings=514`**
RoBERTa (and XLM-RoBERTa) reserves one extra position for `[BOS]` and one for
`[EOS]`, yielding 514 rather than the 512 seen in BERT.  Both values are
captured normally by `_HYPER_KEYS`; 514 is correct and intentional, not an off-by-one.
Examples: `FacebookAI/xlm-roberta-base` (514).

**Minimal model cards (2–3 fields only)**
Some repos have near-empty card YAML.  `dbmdz/bert-base-turkish-cased` has only
`language: tr` and `license: mit` — no `pipeline_tag`, no `tags`, no `datasets`,
no `library_name`.  The extractor handles gracefully: language and license are
captured; `usage.domains` is empty; `type_of_model` and `architecture` still
come from `config.json`.

**Models with no card AND no standard config keys**
`polymathic-ai/aion-base` has a card and a config.json, but the config has no
`model_type` and no `architectures`, and the config keys (`decoder_depth`,
`encoder_depth`, `domains_in`) are all custom.  Result: `type_of_model=None`,
`architecture=None`, `hyperparameters={}`.  The domain still comes from
`pipeline_tag=any-to-any` in the card.

## Model zoo (165 model repos)

### Text generation and language models

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
| `FreedomIntelligence/BlenderLLM` | text-to-3d pipeline, Qwen2 LLM | Standard Qwen2 decoder fine-tuned for Blender script generation; `pipeline_tag=text-to-3d` |
| `hellork/BlenderLLM-IQ3_XXS-GGUF` | GGUF of BlenderLLM, text-to-3d, quantized | No config.json; `base_model_relation=quantized`; `text-to-3d` domain inherited |
| `MiniMaxAI/MiniMax-M2.7` | minimax_m2 arch, MoE with MTP, 1M context, vague license | `MiniMaxM2ForCausalLM`; `max_position_embeddings=1_000_000`; `license=other` |
| `apple/OpenELM-270M` | openelm arch, apple-amlr passthrough, head_dim captured | Custom efficient arch; `head_dim=64` in `_HYPER_KEYS` → captured; non-standard keys skipped |
| `sail/Sailor2-20B` | Qwen2, 10 SEA languages, apache-2.0 | Covers Thai, Khmer, Lao, Malay, Burmese, Filipino; `num_key_value_heads=8` |
| `huggingface/CodeBERTa-small-v1` | RoBERTa, fill-mask, no license, `language=["code"]` | Pre-trained on The Stack; `language="code"` preserved (non-ISO identifier) |
| `Bencode92/tradepulse-finbert-sentiment` | BERT, text-classification, finetune from finbert | `BertForSequenceClassification`; financial sentiment; `base_model_relation=finetune` |
| `OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov` | OpenVINO int8 quant, config accessible | Config.json present (unlike GGUF); `torch_dtype=int8` captured; `library_name=openvino` |
| `Unbabel/wmt22-cometkiwi-da` | Fully gated (card + config 401) | MT quality estimation; only `hf.author` captured |

### Embeddings, retrieval, and text classification

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
| `Alibaba-NLP/gte-multilingual-reranker-base` | text-ranking domain, `model_type="new"` placeholder | `NewForSequenceClassification`; `model_type="new"` is a literal string, not a typo |
| `Alibaba-NLP/gte-modernbert-base` | modernbert arch, sentence-similarity, multilingual | `ModernBertModel` (base encoder); `max_position_embeddings=8192` captured |
| `dbmdz/bert-base-turkish-cased` | bert, no `architectures` field, Turkish, no pipeline_tag | `model_type=bert` present; `architectures` absent → `architecture=None`; minimal card (2 fields) |
| `cross-encoder/ms-marco-MiniLM-L6-v2` | BERT, text-ranking, distilled, `quantized` relation | `hidden_size=384` (half of BERT-base); `base_model:quantized:` tag for layer reduction |

### Vision

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
| `stabilityai/stable-zero123` | text-to-3d, diffusers, vague license + `license_name` | No config.json; `hf.license_name=sai-nc-community`; `library_name=diffusers` |
| `openai/shap-e` | text-to-3d, MIT, no config | Generates 3D assets from text/images; no config.json; MIT |
| `apple/Sharp` | image-to-3d, apple-amlr passthrough, ml-sharp library | Single-image 3D generation; `library_name=ml-sharp`; no config.json |
| `FireRedTeam/FireRedVAD` | voice-activity-detection, no config, apache-2.0 | VAD; new `_DOMAIN_TAGS` entry; no config.json → `type_of_model=None` |
| `ETH-CVG/lightglue_superpoint` | keypoint-detection, lightglue arch, vague license | Feature matching; non-standard config keys → `hyperparameters={}`; `license=other` |
| `qualcomm/HRNetPose` | keypoint-detection, pytorch library, vague license | Native PyTorch format; `library_name=pytorch`; no config.json; `license=other` |
| `PekingU/rtdetr_r50vd_coco_o365` | rt_detr arch, object-detection, COCO+O365 | `RTDetrForObjectDetection`; only `torch_dtype=float32` from `_HYPER_KEYS`; no LM keys |
| `PekingU/rtdetr_r50vd` | rt_detr arch, object-detection, COCO-only | Same arch as coco_o365; both share arxiv:2304.08069; detection config keys not in `_HYPER_KEYS` |

### Multimodal and visual question answering

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
| `aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF` | GGUF-only VLM, `gemma` license, SEA langs | No config.json; `image-text-to-text`; 9 SEA languages; `gemma` license passthrough |
| `Gen-Verse/MMaDA-8B-Base` | llada arch, ALiBi positional bias, any-to-any, MIT | ALiBi: no `max_position_embeddings`; `vocab_size=32000` captured; masked-token diffusion |
| `mlx-community/gemma-4-e2b-it-4bit` | MLX 4-bit quant, gemma4 arch, any-to-any | `library_name=mlx`; config.json accessible; `base_model_relation=quantized` |
| `onnx-community/gemma-4-E2B-it-ONNX` | ONNX export, gemma4 arch, transformers.js | `library_name=transformers.js`; config.json accessible; `base_model_relation=quantized` |
| `ByteDance-Seed/BAGEL-7B-MoT` | bagel arch, any-to-any, nested config | Mixture-of-Tokens multimodal; `hyperparameters={}`; `library_name=bagel-mot` |
| `sensenova/SenseNova-U1-8B-MoT` | neo_chat arch, any-to-any, nested config | `NEOChatModel`; Chinese+English; `hyperparameters={}` |
| `inclusionAI/LLaDA2.0-Uni` | llada2_moe arch, discrete diffusion, any-to-any | Masked-token diffusion model; `LLaDA2MoeModelLM`; apache-2.0 |
| `XiaomiMiMo/MiMo-Audio-7B-Instruct` | qwen2 base + MiMoAudioModel wrapper, any-to-any | Architecture field captures custom wrapper; `model_type=qwen2` (base) preserved |
| `tencent/HY-Motion-1.0` | text-to-3d, custom config, vague license + `license_name` | `library_name=HY-Motion-1.0`; non-standard config → `type_of_model=None`; `hf.license_name=tencent-hunyuan-community` |
| `TencentARC/TimeLens-8B` | qwen3_vl, nested text_config, video-text-to-text, `dtype` key | All LM keys inside `text_config` → `hyperparameters={}`; `dtype` (not `torch_dtype`); `license_name=bsd-3-clause` |
| `polymathic-ai/aion-base` | aion library, any-to-any, no model_type | Scientific foundation model; `library_name=aion`; config accessible but no model_type/architectures → all None |

### Audio and speech

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

### Translation, seq2seq, and domain-specific

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
| `stanfordnlp/stanza-fi` | stanza library, no config, Finnish, empty domains | `library_name=stanza`; no pipeline_tag → empty `usage.domains`; language=`["fi"]` |
| `stanfordnlp/stanza-de` | stanza library, no config, German | Same pattern as stanza-fi; language=`["de"]`; no config.json |
| `SAP/sap-rpt-1-oss` | tabular-classification, gated config, self-referential `library_name` | Uses `.pt` files; `library_name=sap-rpt-1-oss` (same as model slug); `arxiv:2506.10707` |
