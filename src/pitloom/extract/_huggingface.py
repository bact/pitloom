# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""HuggingFace model repository metadata extractor.

Fetches model metadata from a HuggingFace Hub repository URL or model ID
and maps it to :class:`~pitloom.core.ai_metadata.AiModelMetadata`.

Sources used (all optional - missing files are silently skipped):

* ``config.json`` - architecture, model type, core hyperparameters
* ``tokenizer_config.json`` - tokenizer class and related settings
* ``generation_config.json`` - generation-time hyperparameters
* Model card (``README.md``) YAML frontmatter - license, language, tags,
  pipeline tag, library name, base model, and linked datasets
* ``model_info()`` Hub API response - author, sha, dates, and computed tags
  (``base_model:relation:id``, ``arxiv:*``, ``doi:*``, ``dataset:*`` prefixes)
* License files (``LICENSE``, ``LICENCE``, ``COPYING``, etc.) - used when
  the model card has no license or a vague value such as ``"other"``

Standard fields populated:

* ``name``, ``description``, ``license`` - from model ID, model card, and
  license-file detection via the ``licenseid`` library
* ``type_of_model``, ``architecture`` - from ``config.json``
* ``hyperparameters`` - selected numeric/type fields from ``config.json``
  and ``generation_config.json``
* ``usage.domains`` - pipeline tag and broad category tags (-> SPDX ``ai_domain``)
* ``datasets`` - from model card ``datasets:`` list; falls back to
  ``dataset:*`` prefix tags in ``model_info()`` when no card datasets exist
  (-> SPDX ``trainedOn``)

Extension slots populated:

* ``extra_data`` - hub provenance (author, sha, dates, URL), tokenizer class,
  library name, secondary license name, raw evaluation results (``model-index``),
  the raw card YAML license value when it is overridden by file detection
  (``hf.license_raw``), base model ID (``hf.base_model``), base model
  relationship type (``hf.base_model_relation``: ``finetune`` / ``quantized``
  / ``merge`` / ``adapter``), and DOI (``hf.doi``)
* ``extra_lists`` - language codes (``hf.language``), model-specific tags
  (``hf.tags``), arXiv paper IDs (``hf.arxiv``)

Requires ``huggingface_hub`` (``pip install pitloom[huggingface]``).
License detection also requires ``licenseid`` (``pip install pitloom[license]``)
with an up-to-date database (``licenseid update``).
"""

from __future__ import annotations

import json
import re
from typing import Any, NamedTuple

from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    AiModelUsage,
)
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference

# Match full HF URLs: https://huggingface.co/owner/name[/anything]
_HF_URL_RE = re.compile(r"https?://huggingface\.co/([^/]+/[^/]+?)(?:/.*)?$")

# Loose model-ID pattern: two segments separated by exactly one slash,
# each segment matching HF naming conventions.
_HF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.\-]+$")

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

# HF-specific license values that mean "non-standard / unknown" -
# when the card YAML contains one of these, we fall back to license-file detection.
_VAGUE_LICENSE_VALUES: frozenset[str] = frozenset(
    {"other", "custom", "proprietary", "unknown", "unlicensed"}
)

# Filenames (case-sensitive, root of repo) considered license candidates.
# Listed in priority order: no extension first, then common suffixes.
_HF_LICENSE_FILENAMES: tuple[str, ...] = (
    "LICENSE",
    "LICENCE",
    "COPYING",
    "NOTICE",
    "LICENSE.txt",
    "LICENSE.md",
    "LICENCE.txt",
    "LICENCE.md",
    "COPYING.txt",
    "COPYING.md",
)

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
        # Specialised
        "any-to-any",
        "code",
        "reinforcement-learning",
        "robotics",
        "tabular-classification",
        "tabular-regression",
        "video-classification",
    }
)

# Relation keywords that can appear in ``base_model:{relation}:{id}`` Hub tags.
_BASE_MODEL_RELATIONS: frozenset[str] = frozenset(
    {"finetune", "quantized", "merge", "adapter"}
)


def parse_hf_model_id(source: str) -> str | None:
    """Return the HF model ID (``owner/name``) from a URL or direct ID.

    Returns ``None`` when *source* does not look like a HuggingFace reference.
    The check is intentionally conservative: the ``owner/name`` pattern is
    only accepted when the path does *not* exist on the local filesystem,
    to avoid misidentifying relative project paths like ``models/my_model``.
    """
    url_match = _HF_URL_RE.match(source)
    if url_match:
        return url_match.group(1)

    # Accept bare owner/name that has no local counterpart
    if _HF_ID_RE.match(source):
        from pathlib import Path  # pylint: disable=import-outside-toplevel

        if not Path(source).exists():
            return source

    return None


def is_huggingface_source(source: str) -> bool:
    """Return ``True`` when *source* is a HuggingFace URL or model ID."""
    return parse_hf_model_id(source) is not None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _safe_load_json(model_id: str, filename: str) -> dict[str, Any] | None:
    """Download *filename* from *model_id* and return parsed JSON, or ``None``."""
    try:
        # pylint: disable=import-outside-toplevel
        from huggingface_hub import hf_hub_download

        local_path = hf_hub_download(repo_id=model_id, filename=filename)
        with open(local_path, encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _load_model_card(
    model_id: str,
) -> tuple[str | None, dict[str, Any]]:
    """Load model card text and YAML frontmatter as a dict."""
    try:
        # pylint: disable=import-outside-toplevel
        from huggingface_hub import ModelCard

        card = ModelCard.load(model_id)
        card_data: dict[str, Any] = card.data.to_dict() if card.data else {}
        return card.text or None, card_data
    except Exception:  # pylint: disable=broad-exception-caught
        return None, {}


def _load_model_info(model_id: str) -> dict[str, Any]:
    """Return a subset of ``model_info()`` fields as a plain dict.

    The returned dict may contain:

    * ``author``, ``sha``, ``created_at``, ``last_modified``, ``downloads``
      - standard Hub metadata
    * ``tags`` - the full computed tag list from the Hub API, which includes
      prefix-encoded metadata (``base_model:relation:id``, ``arxiv:*``,
      ``doi:*``, ``dataset:*``) that is not always present in the model card
      YAML ``tags`` field.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from huggingface_hub import model_info

        info = model_info(model_id)
        result: dict[str, Any] = {}
        if info.author:
            result["author"] = str(info.author)
        if info.sha:
            result["sha"] = str(info.sha)
        if info.created_at:
            result["created_at"] = info.created_at.isoformat()
        if info.last_modified:
            result["last_modified"] = info.last_modified.isoformat()
        if getattr(info, "downloads", None) is not None:
            result["downloads"] = info.downloads
        if info.tags:
            result["tags"] = list(info.tags)
        return result
    except Exception:  # pylint: disable=broad-exception-caught
        return {}


def _list_license_files_in_repo(model_id: str) -> list[str]:
    """Return the subset of :data:`_HF_LICENSE_FILENAMES` that exist in the repo.

    Uses :func:`huggingface_hub.list_repo_files` to avoid spurious 404 requests.
    Returns an empty list on any error (network, auth, etc.).
    """
    try:
        # pylint: disable=import-outside-toplevel
        from huggingface_hub import list_repo_files

        existing: set[str] = set(list_repo_files(model_id))
        return [f for f in _HF_LICENSE_FILENAMES if f in existing]
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _detect_license_from_hf_files(
    model_id: str,
) -> tuple[str | None, str | None]:
    """Try to detect an SPDX license ID from license files in a HF repository.

    Downloads each candidate file in priority order and runs
    :func:`~pitloom.extract._license.detect_license_from_text` on the content.

    Returns ``(spdx_id, provenance_string)`` when a match is found above the
    default threshold, or ``(None, None)`` otherwise.  Requires the
    ``licenseid`` package and its database (``licenseid update``).
    """
    # pylint: disable=import-outside-toplevel
    from pathlib import Path as _Path

    from pitloom.extract._license import detect_license_from_text

    for filename in _list_license_files_in_repo(model_id):
        try:
            # pylint: disable=import-outside-toplevel
            from huggingface_hub import hf_hub_download

            local_path = hf_hub_download(repo_id=model_id, filename=filename)
            text = (
                _Path(local_path).read_text(encoding="utf-8", errors="replace").strip()
            )
        except Exception:  # pylint: disable=broad-exception-caught
            continue

        if not text:
            continue

        detected = detect_license_from_text(text)
        if detected:
            return (
                detected,
                f"Source: HuggingFace Hub | File: {filename}"
                " | Method: licenseid_detection",
            )

    return None, None


def _extract_card_description(card_text: str) -> str | None:
    """Return the first non-empty prose paragraph from a model card."""
    in_yaml = False
    yaml_done = False
    lines = card_text.splitlines()
    collected: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            if not yaml_done:
                in_yaml = not in_yaml
                if not in_yaml:
                    yaml_done = True
                continue
        if in_yaml:
            continue
        if not yaml_done:
            continue
        # Skip headings and blank lines at the start
        if not collected and (not stripped or stripped.startswith("#")):
            continue
        if not stripped:
            if collected:
                break  # end of first paragraph
            continue
        collected.append(stripped)
        if len(" ".join(collected)) > 500:
            break

    text = " ".join(collected).strip()
    return text[:500] if text else None


# ---------------------------------------------------------------------------
# Structured container for prefix-encoded Hub API tag data
# ---------------------------------------------------------------------------


class _InfoTagData(NamedTuple):
    """Structured data extracted from prefix-encoded Hub API tags."""

    base_model_relation: str | None
    arxiv_ids: list[str]
    doi_val: str | None
    info_dataset_ids: list[str]


# ---------------------------------------------------------------------------
# Data-gathering helper
# ---------------------------------------------------------------------------


def _fetch_all_hf_data(model_id: str) -> dict[str, Any]:
    """Fetch all remote HF data sources and return them as a single dict."""
    card_text, card_data = _load_model_card(model_id)
    return {
        "config": _safe_load_json(model_id, "config.json"),
        "tokenizer_config": _safe_load_json(model_id, "tokenizer_config.json"),
        "generation_config": _safe_load_json(model_id, "generation_config.json"),
        "card_text": card_text,
        "card_data": card_data,
        "hub_info": _load_model_info(model_id),
    }


# ---------------------------------------------------------------------------
# Field-extraction helpers - each populates *provenance* in-place
# ---------------------------------------------------------------------------


def _extract_description(
    hf_data: dict[str, Any], provenance: dict[str, str]
) -> str | None:
    """Return prose description from the model card, or ``None``."""
    card_text: str | None = hf_data.get("card_text")
    if not card_text:
        return None
    desc = _extract_card_description(card_text)
    if desc:
        provenance["description"] = "Source: HuggingFace Hub | Field: model card"
    return desc


def _resolve_license(
    hf_data: dict[str, Any],
    model_id: str,
    provenance: dict[str, str],
) -> tuple[str | None, str | None]:
    """Resolve the model's SPDX licence identifier.

    Returns ``(license_val, vague_raw_license)`` where *vague_raw_license* is
    the original card YAML value when it was a recognised vague sentinel (e.g.
    ``"other"``), so it can be preserved in ``extra_data["hf.license_raw"]``.
    """
    card_data: dict[str, Any] = hf_data.get("card_data") or {}
    raw_license = card_data.get("license")
    raw_license_str: str | None = str(raw_license) if raw_license else None

    if raw_license_str and raw_license_str.lower() not in _VAGUE_LICENSE_VALUES:
        provenance["license"] = (
            "Source: HuggingFace Hub | Field: model card YAML (license)"
        )
        return raw_license_str, None

    vague_raw = (
        raw_license_str
        if raw_license_str and raw_license_str.lower() in _VAGUE_LICENSE_VALUES
        else None
    )
    detected_id, detected_src = _detect_license_from_hf_files(model_id)
    if detected_id:
        provenance["license"] = detected_src or (
            "Source: HuggingFace Hub | Method: licenseid_detection"
        )
        return detected_id, vague_raw
    return None, vague_raw


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
                "Source: HuggingFace Hub | Field: config.json (model_type)"
            )
        architectures = config.get("architectures")
        if isinstance(architectures, list) and architectures:
            architecture = str(architectures[0])
            provenance["architecture"] = (
                "Source: HuggingFace Hub | Field: config.json (architectures)"
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
    if hyperparameters:
        provenance["hyperparameters"] = (
            "Source: HuggingFace Hub | Field: config.json / generation_config.json"
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
            "Source: HuggingFace Hub | Field: model card YAML (pipeline_tag)"
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
                                "Source: HuggingFace Hub"
                                " | Field: model card YAML (datasets)"
                            )
                        },
                    ),
                )
            )
        provenance["datasets"] = (
            "Source: HuggingFace Hub | Field: model card YAML (datasets)"
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
                                "Source: HuggingFace Hub"
                                " | Field: model_info tags (dataset:*)"
                            )
                        },
                    ),
                )
            )
        provenance["datasets"] = (
            "Source: HuggingFace Hub | Field: model_info tags (dataset:*)"
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

    extra_data: dict[str, Any] = {"hf.model_id": model_id, "hf.url": hf_url}

    if vague_raw_license:
        extra_data["hf.license_raw"] = vague_raw_license
    if hub_info.get("author"):
        extra_data["hf.author"] = str(hub_info["author"])
    if hub_info.get("sha"):
        extra_data["hf.sha"] = str(hub_info["sha"])
    if hub_info.get("created_at"):
        extra_data["hf.created_at"] = str(hub_info["created_at"])
    if hub_info.get("last_modified"):
        extra_data["hf.last_modified"] = str(hub_info["last_modified"])

    library_name = card_data.get("library_name")
    if library_name:
        extra_data["hf.library_name"] = str(library_name)
    license_name = card_data.get("license_name")
    if license_name:
        extra_data["hf.license_name"] = str(license_name)

    if tokenizer_config:
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

    model_index = card_data.get("model-index")
    if model_index:
        extra_data["hf.model_index"] = model_index

    if base_model_id:
        extra_data["hf.base_model"] = base_model_id
        provenance["base_model"] = (
            "Source: HuggingFace Hub | Field: model card YAML (base_model)"
        )
    if tag_data.base_model_relation:
        extra_data["hf.base_model_relation"] = tag_data.base_model_relation
        provenance["base_model_relation"] = (
            "Source: HuggingFace Hub | Field: model_info tags (base_model:relation)"
        )
    if tag_data.doi_val:
        extra_data["hf.doi"] = tag_data.doi_val
        provenance["doi"] = "Source: HuggingFace Hub | Field: model_info tags (doi:*)"
    if extra_data:
        provenance["extra_data"] = (
            "Source: HuggingFace Hub"
            " | Field: hub API / model card / tokenizer_config.json"
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
            "Source: HuggingFace Hub"
            " | Field: model card YAML (language / tags)"
            " / model_info tags (arxiv:*)"
        )
    return extra_lists


# ---------------------------------------------------------------------------
# Public reader
# ---------------------------------------------------------------------------


def read_huggingface(source: str) -> AiModelMetadata:
    """Extract metadata from a HuggingFace model repository.

    Args:
        source: Full HF URL
            (e.g. ``https://huggingface.co/mistralai/Mistral-7B-v0.1``) or
            bare model ID (e.g. ``Qwen/Qwen3-235B-A22B`` or
            ``openthaigpt/openthaigpt-r1-32b-instruct``).

    Returns:
        :class:`~pitloom.core.ai_metadata.AiModelMetadata` populated from all
        available HF sources.  Standard fields are filled where possible;
        HF-specific data that has no standard mapping goes into
        ``extra_data`` and ``extra_lists``.

    Raises:
        ImportError: If ``huggingface_hub`` is not installed.
        ValueError: If *source* is not a valid HuggingFace URL or model ID.
    """
    try:
        # pylint: disable=import-outside-toplevel
        __import__("huggingface_hub")
    except ImportError as exc:
        raise ImportError(
            "The 'huggingface_hub' package is required "
            "to extract HuggingFace model metadata. "
            "Install it with: pip install pitloom[huggingface]"
        ) from exc

    model_id = parse_hf_model_id(source)
    if model_id is None:
        raise ValueError(f"Not a valid HuggingFace URL or model ID: {source!r}")

    hf_url = f"https://huggingface.co/{model_id}"
    model_name = model_id.split("/")[-1]
    provenance: dict[str, str] = {"name": "Source: HuggingFace Hub | Field: model_id"}

    hf_data = _fetch_all_hf_data(model_id)
    description = _extract_description(hf_data, provenance)
    license_val, vague_raw_license = _resolve_license(hf_data, model_id, provenance)
    type_of_model, architecture, hyperparameters = _parse_config_data(
        hf_data, provenance
    )
    tag_data = _parse_info_tags(
        [str(t) for t in (hf_data.get("hub_info") or {}).get("tags", [])]
    )
    usage_domains = _extract_domains(hf_data, provenance)
    datasets = _extract_datasets(hf_data, tag_data.info_dataset_ids, provenance)
    base_model_id = _resolve_base_model_id(hf_data)
    extra_data = _build_extra_data(
        model_id,
        hf_url,
        hf_data,
        tag_data,
        vague_raw_license,
        base_model_id,
        provenance,
    )
    extra_lists = _build_extra_lists(hf_data, tag_data.arxiv_ids, provenance)
    library_name = _get_library_name(hf_data)

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=None,
            model_format=AiModelFormat.UNKNOWN,
            framework=library_name or type_of_model,
        ),
        name=model_name,
        description=description,
        license=license_val,
        type_of_model=type_of_model,
        architecture=architecture,
        hyperparameters=hyperparameters,
        usage=AiModelUsage(domains=usage_domains),
        datasets=datasets,
        provenance=provenance,
        extra_data=extra_data,
        extra_lists=extra_lists,
    )


__all__ = ["is_huggingface_source", "parse_hf_model_id", "read_huggingface"]
