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
* ``model_info()`` Hub API response - author, sha, dates, computed tags
  (``base_model:relation:id``, ``arxiv:*``, ``doi:*``, ``dataset:*`` prefixes)
  and the stated parameter count (``safetensors.total``, else ``gguf.total``)
* License files (``LICENSE``, ``LICENCE``, ``COPYING``, etc.) - used when
  the model card has no licence or a vague value such as ``"other"``

Standard fields populated:

* ``name``, ``description``, ``license`` - from model ID, model card, and
  license-file detection via the LicenseID library
* ``originators``, ``supplier`` - the repository owner (``model_info()``
  ``author``)
* ``parameter_count`` - ``safetensors.total``, else ``gguf.total``
* ``type_of_model``, ``architecture`` - from ``config.json``
* ``hyperparameters`` - selected numeric/type fields from ``config.json``
  and ``generation_config.json``
* ``usage.domains`` - pipeline tag and broad category tags (-> SPDX ``ai_domain``)
* ``datasets`` - from model card ``datasets:`` list; falls back to
  ``dataset:*`` prefix tags in ``model_info()`` when no card datasets exist
  (-> SPDX ``trainedOn``); each one's licence, description, keywords,
  version and owner from its own Hub dataset repository
  (:mod:`pitloom.extract.remote.huggingface_dataset`)

Extension slots populated:

* ``extra_data`` - hub provenance (author, sha, dates, URL), tokenizer class,
  library name, secondary license name, raw evaluation results (``model-index``),
  the raw card YAML licence value when it is overridden by file detection
  (``hf.license_raw``), base model ID (``hf.base_model``), base model
  relationship type (``hf.base_model_relation``: ``finetune`` / ``quantized``
  / ``merge`` / ``adapter``), and DOI (``hf.doi``)
* ``extra_lists`` - language codes (``hf.language``), model-specific tags
  (``hf.tags``), arXiv paper IDs (``hf.arxiv``)

Requires ``huggingface_hub`` (``pip install pitloom[huggingface_hub]``).
License detection uses LicenseID (a core dependency) with an up-to-date
database (``licenseid update --source packaged``).

See also: this module is a thin facade. Fetching raw Hugging Face Hub data
and resolving the licence lives in
:mod:`pitloom.extract.remote.huggingface_fetch`; mapping that raw data onto
:class:`~pitloom.core.ai_metadata.AiModelMetadata` fields lives in
:mod:`pitloom.extract.remote.huggingface_field`.
"""

from __future__ import annotations

import logging
import re

from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    AiModelUsage,
)
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.optional_libraries import HUB, import_failed
from pitloom.core.url_masking import sanitize_url
from pitloom.extract.ai_model.limits import settle_read_text
from pitloom.extract.remote._http_errors import remote_error, shown_url
from pitloom.extract.remote._hub_files import ROUTE, HubFiles, hub_files
from pitloom.extract.remote.git_url import HUB_HOST_PATTERN
from pitloom.extract.remote.huggingface_dataset import add_hub_dataset_metadata
from pitloom.extract.remote.huggingface_fetch import (
    _fetch_all_hf_data,
    _resolve_license,
)
from pitloom.extract.remote.huggingface_field import (
    _build_extra_data,
    _build_extra_lists,
    _extract_datasets,
    _extract_description,
    _extract_domains,
    _get_library_name,
    _parse_config_data,
    _parse_info_tags,
    _resolve_base_model_id,
    hub_producer_and_count,
    hub_revision,
)
from pitloom.logging_config import loggable
from pitloom.messages import CodedValueError
from pitloom.messages.network import (
    OFFLINE_LINE,
    OFFLINE_UNUSABLE,
)
from pitloom.messages.targets import HF_URL_INVALID

log = logging.getLogger(__name__)

__all__ = [
    "is_huggingface_source",
    "log_hf_url_rewrite",
    "parse_hf_model_id",
    "read_huggingface",
]

# Match full HF model URLs: https://huggingface.co/owner/name[/anything], also
# as http, www.huggingface.co or hf.co, in any case of the scheme and host. A
# Space or a dataset (``/spaces/...``, ``/datasets/...``) is a Git repository,
# not a model.
_HF_URL_RE = re.compile(
    rf"https?://{HUB_HOST_PATTERN}/(?!(?:spaces|datasets)/)"
    r"([^/?#]+/[^/?#]+?)(?:[/?#].*)?$",
    re.IGNORECASE,
)
_CANONICAL_PREFIX = "https://huggingface.co/"

# Loose model-ID pattern: two segments separated by exactly one slash,
# each segment matching HF naming conventions. A one-character name is valid
# on the Hub, and :data:`_HF_URL_RE` takes one, so this must too: a URL's id
# goes back through :func:`is_huggingface_source`.
_HF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.\-]*$")


def log_hf_url_rewrite(source: str, model_id: str) -> None:
    """One ``INFO:`` when *source* is a Hub URL spelt other than
    ``https://huggingface.co/<id>`` (``hf.co``, ``www.``, ``http://``, a
    mixed-case host), naming the URL it is read as; credentials and query
    tokens are masked. ``loom model`` calls it before fetching, the other
    routes through :func:`read_huggingface`."""
    if _HF_URL_RE.match(source) and not source.startswith(_CANONICAL_PREFIX):
        log.info(
            "Hugging Face URL %s is read as %s%s",
            loggable(sanitize_url(source)),
            _CANONICAL_PREFIX,
            model_id,
        )


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


def read_huggingface(
    source: str, *, policy: RemoteFetchPolicy = RemoteFetchPolicy()
) -> AiModelMetadata:
    """Extract metadata from a Hugging Face model repository.

    Args:
        source: Full HF URL
            (e.g. ``https://huggingface.co/mistralai/Mistral-7B-v0.1``) or
            bare model ID (e.g. ``Qwen/Qwen3-235B-A22B`` or
            ``openthaigpt/openthaigpt-r1-32b-instruct``).
        policy: What the downloads may do
            (:func:`~pitloom.core.config_cascade.resolve_fetch_policy`): each
            metadata file is capped at the smaller of its ``max_bytes`` and
            the file's own cap
            (:func:`~pitloom.extract.remote._hub_files.file_cap`) and
            passed, with each redirect target, to its ``check_url``; with
            ``offline`` nothing is fetched. The ``model_info()``,
            ``dataset_info()`` and file listing requests are
            ``huggingface_hub``'s own and pass through neither. With
            ``HF_ENDPOINT`` refused (not https, or holding credentials),
            nothing at all is asked of the Hub: the model keeps its id and
            URL only, with one ``WARNING:``.

    Returns:
        :class:`~pitloom.core.ai_metadata.AiModelMetadata` populated from all
        available HF sources.  Standard fields are filled where possible;
        HF-specific data that has no standard mapping goes into
        ``extra_data`` and ``extra_lists``.

    Raises:
        ImportError: If ``huggingface_hub`` is not installed, or fails to
            import: a :class:`~pitloom.messages.CodedImportError`,
            ``library-missing`` (``library-unusable`` when installed).
        ValueError: If *source* is not a valid Hugging Face URL or model ID.
        pitloom.extract.remote.errors.RemoteSourceError: The policy is
            offline (``huggingface.offline``, ``offline-unusable``).
        Exception: Whatever the policy's ``check_url`` raises, unchanged.
    """
    try:
        __import__(HUB.module)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:  # a broken install raises more than ImportError
        raise import_failed(HUB, exc) from exc

    model_id = parse_hf_model_id(source)
    if model_id is None:
        raise CodedValueError(HF_URL_INVALID, url=sanitize_url(source))

    hf_url = f"{_CANONICAL_PREFIX}{model_id}"
    if policy.offline:
        raise remote_error(
            f"{ROUTE}.offline", OFFLINE_UNUSABLE, OFFLINE_LINE, url=shown_url(hf_url)
        )
    log_hf_url_rewrite(source, model_id)
    with hub_files(policy) as hub:
        return _read_repository(hub, model_id, hf_url)


# pylint: disable-next=too-many-locals
def _read_repository(hub: HubFiles, model_id: str, hf_url: str) -> AiModelMetadata:
    """:func:`read_huggingface` of *model_id*, its files downloaded by
    *hub*."""
    model_name = model_id.split("/")[-1]
    provenance: dict[str, str] = {"name": "Source: Hugging Face Hub | Field: model_id"}

    hf_data = _fetch_all_hf_data(hub, model_id)
    description = _extract_description(hf_data, provenance)
    license_val, vague_raw_license = _resolve_license(
        hub, hf_data, model_id, provenance
    )
    type_of_model, architecture, hyperparameters = _parse_config_data(
        hf_data, provenance
    )
    tag_data = _parse_info_tags(
        [str(t) for t in (hf_data.get("hub_info") or {}).get("tags", [])]
    )
    usage_domains = _extract_domains(hf_data, provenance)
    datasets = _extract_datasets(hf_data, tag_data.info_dataset_ids, provenance, hf_url)
    add_hub_dataset_metadata(datasets, hf_url, hub)
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
    producer = hub_producer_and_count(
        hf_data.get("hub_info") or {}, provenance, loggable(hf_url)
    )
    revision = hub_revision(hf_data.get("hub_info") or {}, provenance)

    meta = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=None,
            model_format=AiModelFormat.UNKNOWN,
            framework=library_name or type_of_model,
        ),
        name=model_name,
        version=revision.version,
        release_time=revision.release_time,
        description=description,
        license=license_val,
        originators=producer.originators,
        supplier=producer.supplier,
        parameter_count=producer.parameter_count,
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
    settle_read_text(meta, "huggingface", loggable(hf_url))
    return meta
