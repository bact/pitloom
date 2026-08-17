# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hugging Face model repository metadata extractor.

Fetches model metadata from a Hugging Face Hub repository URL or model ID
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

See also: this module is a thin facade. Fetching raw Hugging Face Hub data
and resolving the license lives in
:mod:`pitloom.extract._huggingface_fetch`; mapping that raw data onto
:class:`~pitloom.core.ai_metadata.AiModelMetadata` fields lives in
:mod:`pitloom.extract._huggingface_fields`.
"""

from __future__ import annotations

import re

from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    AiModelUsage,
)
from pitloom.extract._huggingface_fetch import _fetch_all_hf_data, _resolve_license
from pitloom.extract._huggingface_fields import (
    _build_extra_data,
    _build_extra_lists,
    _extract_datasets,
    _extract_description,
    _extract_domains,
    _get_library_name,
    _parse_config_data,
    _parse_info_tags,
    _resolve_base_model_id,
)

__all__ = ["is_huggingface_source", "parse_hf_model_id", "read_huggingface"]

# Match full HF URLs: https://huggingface.co/owner/name[/anything]
_HF_URL_RE = re.compile(r"https?://huggingface\.co/([^/]+/[^/]+?)(?:/.*)?$")

# Loose model-ID pattern: two segments separated by exactly one slash,
# each segment matching HF naming conventions.
_HF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.\-]+$")


def parse_hf_model_id(source: str) -> str | None:
    """Return the HF model ID (``owner/name``) from a URL or direct ID.

    Returns ``None`` when *source* does not look like a Hugging Face reference.
    The check is intentionally conservative: the ``owner/name`` pattern is
    only accepted when the path does *not* exist on the local filesystem,
    to avoid misidentifying relative project paths like ``models/my_model``.
    """
    url_match = _HF_URL_RE.match(source)
    if url_match:
        return url_match.group(1)

    # Accept bare owner/name that has no local counterpart
    if _HF_ID_RE.match(source):
        # pylint: disable=import-outside-toplevel
        from pathlib import Path

        if not Path(source).exists():
            return source

    return None


def is_huggingface_source(source: str) -> bool:
    """Return ``True`` when *source* is a Hugging Face URL or model ID."""
    return parse_hf_model_id(source) is not None


# pylint: disable-next=too-many-locals
def read_huggingface(source: str) -> AiModelMetadata:
    """Extract metadata from a Hugging Face model repository.

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
        ValueError: If *source* is not a valid Hugging Face URL or model ID.
    """
    try:
        # pylint: disable=import-outside-toplevel

        __import__("huggingface_hub")
    except ImportError as exc:
        raise ImportError(
            "The 'huggingface_hub' package is required "
            "to extract Hugging Face model metadata. "
            "Install it with: pip install pitloom[huggingface]"
        ) from exc

    model_id = parse_hf_model_id(source)
    if model_id is None:
        raise ValueError(f"Not a valid Hugging Face URL or model ID: {source!r}")

    hf_url = f"https://huggingface.co/{model_id}"
    model_name = model_id.split("/")[-1]
    provenance: dict[str, str] = {"name": "Source: Hugging Face Hub | Field: model_id"}

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
        doi=tag_data.doi_val,
        arxiv_ids=tag_data.arxiv_ids,
        url=hf_url,
        base_model=base_model_id,
        base_model_relation=tag_data.base_model_relation,
        type_of_model=type_of_model,
        architecture=architecture,
        hyperparameters=hyperparameters,
        usage=AiModelUsage(domains=usage_domains),
        datasets=datasets,
        provenance=provenance,
        extra_data=extra_data,
        extra_lists=extra_lists,
    )
