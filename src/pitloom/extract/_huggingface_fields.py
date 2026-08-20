# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Field-extraction helpers for Hugging Face model metadata.

Each function here maps some slice of the raw data gathered by
:func:`pitloom.extract._huggingface_fetch._fetch_all_hf_data` onto fields of
:class:`~pitloom.core.ai_metadata.AiModelMetadata`, populating *provenance*
in-place as it goes.

See also: :mod:`pitloom.extract._huggingface` (public facade) and
:mod:`pitloom.extract._huggingface_fetch` (Hugging Face Hub I/O and license
resolution).
"""

from __future__ import annotations

from typing import Any, NamedTuple

from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.extract._extract_utils import record_dict_field_provenance
from pitloom.extract._huggingface_fetch import _extract_card_description

# config.json keys that map directly to SPDX AI hyperparameters
_HYPER_KEYS: tuple[str, ...] = (
    "vocab_size",
    "hidden_size",
    "num_hidden_layers",
    "num_attention_heads",
    "num_key_value_heads",
    "head_dim",
    "intermediate_size",
    "max_position_embeddings",
    "torch_dtype",
    "rope_theta",
    "sliding_window",
    "seq_length",
)

# generation_config.json keys included as hyperparameters
_GEN_HYPER_KEYS: tuple[str, ...] = (
    "temperature",
    "top_p",
    "top_k",
    "repetition_penalty",
    "max_new_tokens",
)

# Sentinel used by some tokenizers for "unlimited" context length
_TOKENIZER_MAX_LEN_UNLIMITED = 10**20

# Tags that describe broad model categories - kept in usage.domains (-> ai_domain)
# rather than in extra_lists["hf.tags"].
_DOMAIN_TAGS: frozenset[str] = frozenset(
    {
        # Text / NLP
        "text-generation",
        "text-classification",
        "text2text-generation",
        "question-answering",
        "summarization",
        "translation",
        "conversational",
        "token-classification",
        "fill-mask",
        "sentence-similarity",
        "feature-extraction",
        # Image / vision
        "image-classification",
        "image-feature-extraction",
        "image-segmentation",
        "image-to-image",
        "image-to-text",
        "image-text-to-text",
        "object-detection",
        "text-to-image",
        "depth-estimation",
        "keypoint-detection",
        "zero-shot-image-classification",
        # Document / multimodal
        "document-question-answering",
        "table-question-answering",
        "video-text-to-text",
        "visual-document-retrieval",
        "visual-question-answering",
        # Audio / speech
        "automatic-speech-recognition",
        "audio-classification",
        "audio-to-audio",
        "speaker-diarization",
        "text-to-speech",
        # Specialised
        "any-to-any",
        "code",
        "image-to-3d",
        "reinforcement-learning",
        "robotics",
        "tabular-classification",
        "tabular-regression",
        "text-ranking",
        "text-to-3d",
        "time-series-forecasting",
        "video-classification",
        "voice-activity-detection",
    }
)

# Relation keywords that can appear in ``base_model:{relation}:{id}`` Hub tags.
_BASE_MODEL_RELATIONS: frozenset[str] = frozenset(
    {"finetune", "quantized", "merge", "adapter"}
)


class _InfoTagData(NamedTuple):
    """Structured data extracted from prefix-encoded Hub API tags."""

    base_model_relation: str | None
    arxiv_ids: list[str]
    doi_val: str | None
    info_dataset_ids: list[str]


def _extract_description(
    hf_data: dict[str, Any], provenance: dict[str, str]
) -> str | None:
    """Return prose description from the model card, or ``None``."""
    card_text: str | None = hf_data.get("card_text")
    if not card_text:
        return None
    desc = _extract_card_description(card_text)
    if desc:
        provenance["description"] = "Source: Hugging Face Hub | Field: model card"
    return desc


def _parse_config_data(
    hf_data: dict[str, Any],
    provenance: dict[str, str],
) -> tuple[str | None, str | None, dict[str, Any]]:
    """Extract model type, architecture, and hyperparameters from config files."""
    config: dict[str, Any] | None = hf_data.get("config")
    generation_config: dict[str, Any] | None = hf_data.get("generation_config")

    type_of_model: str | None = None
    architecture: str | None = None
    if config:
        model_type = config.get("model_type")
        if model_type:
            type_of_model = str(model_type)
            provenance["type_of_model"] = (
                "Source: Hugging Face Hub | Field: config.json (model_type)"
            )
        architectures = config.get("architectures")
        if isinstance(architectures, list) and architectures:
            architecture = str(architectures[0])
            provenance["architecture"] = (
                "Source: Hugging Face Hub | Field: config.json (architectures)"
            )

    hyperparameters: dict[str, Any] = {}
    if config:
        for key in _HYPER_KEYS:
            val = config.get(key)
            if val is not None:
                hyperparameters[key] = val
    if generation_config:
        for key in _GEN_HYPER_KEYS:
            val = generation_config.get(key)
            if val is not None:
                hyperparameters[f"generation.{key}"] = val
    # Exact per-key provenance: each hyperparameter is traceable to its own
    # config.json key (``generation.*`` keys come from generation_config.json).
    record_dict_field_provenance(
        provenance, "hyperparameters", hyperparameters, "Source: Hugging Face Hub"
    )
    return type_of_model, architecture, hyperparameters


def _parse_info_tags(info_tags: list[str]) -> _InfoTagData:
    """Parse prefix-encoded metadata from Hub API computed tags."""
    base_model_relation: str | None = None
    arxiv_ids: list[str] = []
    doi_val: str | None = None
    info_dataset_ids: list[str] = []

    for tag in info_tags:
        if tag.startswith("base_model:") and ":" in tag[11:]:
            rest = tag[11:]
            colon_pos = rest.index(":")
            relation = rest[:colon_pos]
            if base_model_relation is None and relation in _BASE_MODEL_RELATIONS:
                base_model_relation = relation
        elif tag.startswith("arxiv:"):
            arxiv_id = tag[6:].strip()
            if arxiv_id:
                arxiv_ids.append(arxiv_id)
        elif tag.startswith("doi:"):
            doi_val = tag[4:].strip() or None
        elif tag.startswith("dataset:"):
            ds_id = tag[8:].strip()
            if ds_id:
                info_dataset_ids.append(ds_id)

    return _InfoTagData(
        base_model_relation=base_model_relation,
        arxiv_ids=arxiv_ids,
        doi_val=doi_val,
        info_dataset_ids=info_dataset_ids,
    )


def _extract_domains(
    hf_data: dict[str, Any],
    provenance: dict[str, str],
) -> list[str]:
    """Return task/capability domains for ``AiModelUsage.domains``."""
    card_data: dict[str, Any] = hf_data.get("card_data") or {}
    usage_domains: list[str] = []
    pipeline_tag = card_data.get("pipeline_tag")
    if pipeline_tag:
        usage_domains.append(str(pipeline_tag))
        provenance["domain"] = (
            "Source: Hugging Face Hub | Field: model card YAML (pipeline_tag)"
        )
    for tag in card_data.get("tags") or []:
        tag_str = str(tag)
        if tag_str in _DOMAIN_TAGS and tag_str not in usage_domains:
            usage_domains.append(tag_str)
    return usage_domains


def _extract_datasets(
    hf_data: dict[str, Any],
    info_dataset_ids: list[str],
    provenance: dict[str, str],
) -> list[DatasetReference]:
    """Return a list of training dataset references."""
    card_data: dict[str, Any] = hf_data.get("card_data") or {}
    datasets: list[DatasetReference] = []
    card_dataset_ids = [str(ds) for ds in (card_data.get("datasets") or [])]

    if card_dataset_ids:
        for ds_name in card_dataset_ids:
            datasets.append(
                DatasetReference(
                    role="trainedOn",
                    metadata=DatasetMetadata(
                        name=ds_name,
                        download_url=f"https://huggingface.co/datasets/{ds_name}",
                        provenance={
                            "name": (
                                "Source: Hugging Face Hub"
                                " | Field: model card YAML (datasets)"
                            )
                        },
                    ),
                )
            )
        provenance["datasets"] = (
            "Source: Hugging Face Hub | Field: model card YAML (datasets)"
        )
    elif info_dataset_ids:
        for ds_name in info_dataset_ids:
            datasets.append(
                DatasetReference(
                    role="trainedOn",
                    metadata=DatasetMetadata(
                        name=ds_name,
                        download_url=f"https://huggingface.co/datasets/{ds_name}",
                        provenance={
                            "name": (
                                "Source: Hugging Face Hub"
                                " | Field: model_info tags (dataset:*)"
                            )
                        },
                    ),
                )
            )
        provenance["datasets"] = (
            "Source: Hugging Face Hub | Field: model_info tags (dataset:*)"
        )
    return datasets


def _resolve_base_model_id(hf_data: dict[str, Any]) -> str | None:
    """Return the fine-tuning base model ID from the model card YAML."""
    card_data: dict[str, Any] = hf_data.get("card_data") or {}
    raw_base_model = card_data.get("base_model")
    if isinstance(raw_base_model, list) and raw_base_model:
        return str(raw_base_model[0])
    if isinstance(raw_base_model, str) and raw_base_model:
        return raw_base_model
    return None


def _get_library_name(hf_data: dict[str, Any]) -> str | None:
    """Return the ML framework / library name from the model card YAML."""
    card_data: dict[str, Any] = hf_data.get("card_data") or {}
    lib = card_data.get("library_name")
    return str(lib) if lib else None


def _populate_hub_info(extra_data: dict[str, Any], hub_info: dict[str, Any]) -> None:
    """Populate Hub metadata keys on extra_data."""
    for key in ("author", "sha", "created_at", "last_modified"):
        val = hub_info.get(key)
        if val:
            extra_data[f"hf.{key}"] = str(val)


def _populate_tokenizer_info(
    extra_data: dict[str, Any], tokenizer_config: dict[str, Any] | None
) -> None:
    """Populate tokenizer configuration keys on extra_data."""
    if not tokenizer_config:
        return
    tc_class = tokenizer_config.get("tokenizer_class")
    if tc_class:
        extra_data["hf.tokenizer_class"] = str(tc_class)
    max_len = tokenizer_config.get("model_max_length")
    if (
        max_len is not None
        and isinstance(max_len, (int, float))
        and max_len < _TOKENIZER_MAX_LEN_UNLIMITED
    ):
        extra_data["hf.tokenizer_max_length"] = int(max_len)


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _build_extra_data(
    model_id: str,
    hf_url: str,
    hf_data: dict[str, Any],
    tag_data: _InfoTagData,
    vague_raw_license: str | None,
    base_model_id: str | None,
    provenance: dict[str, str],
) -> dict[str, Any]:
    """Build the ``extra_data`` mapping with HF-specific fields."""
    card_data: dict[str, Any] = hf_data.get("card_data") or {}
    hub_info: dict[str, Any] = hf_data.get("hub_info") or {}
    tokenizer_config: dict[str, Any] | None = hf_data.get("tokenizer_config")

    # hf.model_id/hf.url are seeded unconditionally, so extra_data is never
    # empty by the time provenance["extra_data"] is set below.
    extra_data: dict[str, Any] = {"hf.model_id": model_id, "hf.url": hf_url}

    if vague_raw_license:
        extra_data["hf.license_raw"] = vague_raw_license
    _populate_hub_info(extra_data, hub_info)

    library_name = card_data.get("library_name")
    if library_name:
        extra_data["hf.library_name"] = str(library_name)
    license_name = card_data.get("license_name")
    if license_name:
        extra_data["hf.license_name"] = str(license_name)

    _populate_tokenizer_info(extra_data, tokenizer_config)

    model_index = card_data.get("model-index")
    if model_index:
        extra_data["hf.model_index"] = model_index

    if base_model_id:
        extra_data["hf.base_model"] = base_model_id
        provenance["base_model"] = (
            "Source: Hugging Face Hub | Field: model card YAML (base_model)"
        )
    if tag_data.base_model_relation:
        extra_data["hf.base_model_relation"] = tag_data.base_model_relation
        provenance["base_model_relation"] = (
            "Source: Hugging Face Hub | Field: model_info tags (base_model:relation)"
        )
    if tag_data.doi_val:
        extra_data["hf.doi"] = tag_data.doi_val
        provenance["doi"] = "Source: Hugging Face Hub | Field: model_info tags (doi:*)"
    provenance["extra_data"] = (
        "Source: Hugging Face Hub | Field: hub API / model card / tokenizer_config.json"
    )
    return extra_data


def _build_extra_lists(
    hf_data: dict[str, Any],
    arxiv_ids: list[str],
    provenance: dict[str, str],
) -> dict[str, list[Any]]:
    """Build the ``extra_lists`` mapping with HF-specific list fields."""
    card_data: dict[str, Any] = hf_data.get("card_data") or {}
    extra_lists: dict[str, list[Any]] = {}

    # Language normalisation: card YAML may give "language" as a string scalar
    # ("ja") or as a list. YAML 1.1 parses the ISO 639-1 code "no" (Norwegian)
    # as the boolean False - filter those out.
    raw_language = card_data.get("language")
    if isinstance(raw_language, str):
        language_list: list[Any] = [raw_language] if raw_language else []
    elif isinstance(raw_language, list):
        language_list = raw_language
    else:
        language_list = []
    valid_languages = [
        str(lang) for lang in language_list if lang is not False and lang
    ]
    if valid_languages:
        extra_lists["hf.language"] = valid_languages

    specific_tags = [
        str(t) for t in (card_data.get("tags") or []) if str(t) not in _DOMAIN_TAGS
    ]
    if specific_tags:
        extra_lists["hf.tags"] = specific_tags

    if arxiv_ids:
        extra_lists["hf.arxiv"] = arxiv_ids

    if extra_lists:
        provenance["extra_lists"] = (
            "Source: Hugging Face Hub"
            " | Field: model card YAML (language / tags)"
            " / model_info tags (arxiv:*)"
        )
    return extra_lists
