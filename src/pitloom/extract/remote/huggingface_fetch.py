# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hugging Face Hub I/O and licence resolution helpers.

Downloads and parses raw data from a Hugging Face Hub repository
(``config.json``, the model card, ``model_info()``, and licence files) and
resolves the model's SPDX license identifier. The files are downloaded by
:class:`~pitloom.extract.remote._hub_files.HubFiles` (each capped by its kind:
a JSON file at :data:`~pitloom.extract.remote._hub_files.HUB_JSON_CAP`, the
card at :data:`~pitloom.enrich.readme.MODEL_CARD_CAP`, a licence file at
:data:`~pitloom.extract._license_detect.LICENSE_FILE_CAP`; each redirect
checked, removed after the read) and read within the same caps;
``model_info()`` and the file listing are ``huggingface_hub`` API requests.
With the Hub refused (``HubFiles.asks_hub`` false), nothing is asked of it:
the model keeps its id and URL only.

See also: :mod:`pitloom.extract.remote.huggingface` (public facade) and
:mod:`pitloom.extract.remote.huggingface_field` (field-extraction helpers that
turn this module's raw data into :class:`~pitloom.core.ai_metadata.AiModelMetadata`
fields).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from pitloom.core.provenance import provenance_segment, provenance_source
from pitloom.core.quote_source import quote_source
from pitloom.enrich.readme import MODEL_CARD_CAP, CardKind, read_card
from pitloom.extract._license_classify import is_vague_license_value
from pitloom.extract._license_detect import LICENSE_FILE_CAP, read_license_file
from pitloom.extract.remote._hub_files import (
    HUB_JSON_CAP,
    FileKind,
    HubFiles,
    local_reason,
)
from pitloom.logging_config import field_loss_suffix, loggable, one_line

log = logging.getLogger(__name__)

# A card YAML licence that is a placeholder (``other``, ``custom``, ...) falls
# back to license-file detection (:func:`is_vague_license_value`).
# Filenames (case-sensitive, root of repo) considered licence candidates.
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

#: The card fields a model card that cannot be read leaves unset.
_CARD_FIELDS_SKIPPED = field_loss_suffix(
    "skipped",
    "license",
    "datasets",
    "tags",
    "base_model",
    "library_name",
    "language",
    "pipeline_tag",
    "model-index",
)

#: A Hub model card: the model repository's ``README.md``, read as a local
#: one is (within :data:`~pitloom.enrich.readme.MODEL_CARD_MAX_BYTES`).
HUB_MODEL_CARD = CardKind(
    ("README.md",),
    "model card",
    MODEL_CARD_CAP,
    _CARD_FIELDS_SKIPPED,
    use="for the model card",
)


def _safe_load_json(
    hub: HubFiles, model_id: str, filename: str, revision: str | None = None
) -> dict[str, Any] | None:
    """Download *filename* from *model_id* (within :data:`HUB_JSON_CAP`)
    and return the JSON object it holds, or ``None``: silently when the
    repository does not hold it (a model without ``generation_config.json``),
    with one ``WARNING:`` when the download fails or is over the cap
    (:meth:`HubFiles.read`), at ``DEBUG`` when it is not a JSON object."""
    if revision is None:
        log.warning(
            "Downloading %s for %s without a pinned revision; "
            "supply hub_info['sha'] to ensure reproducibility.",
            quote_source(filename),
            loggable(model_id),
        )
    kind = FileKind(HUB_JSON_CAP, f"{filename} not read")
    local_path = hub.read(model_id, filename, revision=revision, kind=kind)
    if local_path is None:
        return None
    try:
        # Bytes, not text: a UTF-8 BOM is accepted, as the format allows.
        data = json.loads(local_path.read_bytes())
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to load %s for %s: %s",
            quote_source(filename),
            model_id,
            one_line(local_reason(exc)),
        )
        return None
    return data if isinstance(data, dict) else None


def _load_model_card(
    hub: HubFiles, model_id: str, revision: str | None = None
) -> tuple[str | None, dict[str, Any]]:
    """The whole model card (front matter included, as the description
    helper expects), within :data:`~pitloom.enrich.readme.MODEL_CARD_MAX_BYTES`
    (:func:`~pitloom.enrich.readme.read_card`, as a local card is read), and
    its YAML frontmatter as a dict, as the file states it (``tags`` as a list
    without repeats, as ``huggingface_hub`` gives it); ``(None, {})``
    silently when the repository has no ``README.md``, with one ``WARNING:``
    when it cannot be fetched or read."""
    kind = FileKind(MODEL_CARD_CAP, "model card not read")
    local_path = hub.read(model_id, "README.md", revision=revision, kind=kind)
    if local_path is None:
        return None, {}
    try:
        # A third party's card: whatever reading it raises fails only it.
        read = read_card(local_path, HUB_MODEL_CARD, name=model_id)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        msg = "Failed to load model card for %s: %s" + _CARD_FIELDS_SKIPPED
        log.warning(msg, loggable(model_id), one_line(local_reason(exc)))
        return None, {}
    if read is None:
        return None, {}
    text, frontmatter = read
    card_data = dict(frontmatter or {})
    if "tags" in card_data:
        card_data["tags"] = _unique_list(card_data["tags"])
    return text or None, card_data


def _unique_list(value: Any) -> Any:
    """*value* as ``huggingface_hub``'s card data gives ``tags``: a string
    as a one-item list, a list without its repeats (first kept, in order);
    anything else unchanged."""
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return value
    unique: list[Any] = []
    for item in value:
        if item not in unique:
            unique.append(item)
    return unique


def _load_model_info(model_id: str) -> dict[str, Any]:
    """Return a subset of ``model_info()`` fields as a plain dict.

    The returned dict may contain:

    * ``author``, ``sha``, ``created_at``, ``last_modified``, ``downloads``
      - standard Hub metadata
    * ``tags`` - the full computed tag list from the Hub API, which includes
      prefix-encoded metadata (``base_model:relation:id``, ``arxiv:*``,
      ``doi:*``, ``dataset:*``) that is not always present in the model card
      YAML ``tags`` field.
    * ``safetensors_total`` - the Hub's stated parameter count
      (``safetensors.total``), kept as the Hub sent it; absent when the
      repository has no Safetensors metadata.
    * ``gguf_total`` - the same from the GGUF metadata (``gguf.total``),
      kept only when there is no Safetensors metadata.
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
        if info.safetensors is not None:
            result["safetensors_total"] = info.safetensors.total
        else:
            gguf = getattr(info, "gguf", None)  # a plain dict, as the Hub sent it
            if isinstance(gguf, Mapping) and "total" in gguf:
                result["gguf_total"] = gguf["total"]
        return result
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        msg = "Failed to load model_info() for %s: %s" + field_loss_suffix(
            "skipped",
            "author",
            "sha",
            "created_at",
            "last_modified",
            "downloads",
            "tags",
            "safetensors.total",
            "gguf.total",
        )
        log.warning(msg, loggable(model_id), one_line(exc))
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
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        msg = "Failed to list repo files for %s: %s" + field_loss_suffix(
            "skipped", "license (file-based detection)"
        )
        log.warning(msg, loggable(model_id), one_line(exc))
        return []


def _detect_license_from_hf_files(
    hub: HubFiles,
    model_id: str,
    revision: str | None = None,
) -> tuple[str | None, str | None]:
    """Try to detect an SPDX license ID from licence files in a HF repository.

    Downloads each candidate file in priority order and runs
    :func:`~pitloom.extract._license_text_match.detect_license_from_text`
    on the content.

    Returns ``(spdx_id, provenance_string)`` when a match is found above the
    default threshold, or ``(None, None)`` otherwise (at once, asking
    nothing, with the Hub refused: :attr:`HubFiles.asks_hub`). Each file is
    downloaded and read within
    :data:`~pitloom.extract._license_detect.LICENSE_FILE_CAP`, as every
    licence file Pitloom reads is. Requires the ``licenseid`` package and
    its database (``licenseid update --source packaged``).
    """
    if not hub.asks_hub:
        return None, None
    if revision is None:
        log.warning(
            "Scanning license files for %s without a pinned revision; "
            "supply hub_info['sha'] to ensure reproducibility.",
            loggable(model_id),
        )
    # pylint: disable-next=import-outside-toplevel
    from pitloom.extract._license_text_match import detect_license_from_text

    kind = FileKind(LICENSE_FILE_CAP, "license file not read")
    for filename in _list_license_files_in_repo(model_id):
        local_path = hub.read(model_id, filename, revision=revision, kind=kind)
        if local_path is None:
            continue
        raw = read_license_file(local_path, shown=f"{model_id}/{filename}")
        if raw is None:
            continue
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            continue

        detected = detect_license_from_text(text)
        if detected:
            return detected, provenance_segment(
                provenance_source("Hugging Face Hub", file=filename),
                "Method",
                "licenseid_detection",
            )

    return None, None


def _fetch_all_hf_data(hub: HubFiles, model_id: str) -> dict[str, Any]:
    """Fetch all remote HF data sources and return them as a single dict;
    each file at the revision ``model_info()`` states. With the Hub refused
    (:attr:`HubFiles.asks_hub`), nothing is asked of it: every source is
    absent, said by nothing more (the refusal was said once)."""
    if not hub.asks_hub:
        return {
            "config": None,
            "tokenizer_config": None,
            "generation_config": None,
            "card_text": None,
            "card_data": {},
            "hub_info": {},
        }
    hub_info = _load_model_info(model_id)
    raw_revision = hub_info.get("sha")
    revision = str(raw_revision) if raw_revision else None
    card_text, card_data = _load_model_card(hub, model_id, revision)
    return {
        "config": _safe_load_json(hub, model_id, "config.json", revision=revision),
        "tokenizer_config": _safe_load_json(
            hub, model_id, "tokenizer_config.json", revision=revision
        ),
        "generation_config": _safe_load_json(
            hub, model_id, "generation_config.json", revision=revision
        ),
        "card_text": card_text,
        "card_data": card_data,
        "hub_info": hub_info,
    }


def _resolve_license(
    hub: HubFiles,
    hf_data: dict[str, Any],
    model_id: str,
    provenance: dict[str, str],
) -> tuple[str | None, str | None]:
    """Resolve the model's SPDX licence identifier.

    Returns ``(license_val, vague_raw_license)`` where *vague_raw_license* is
    the original card YAML value when it was a recognised vague sentinel (e.g.
    ``"other"``), so it can be preserved in ``extra_data["hf.license_raw"]``.
    A vague value falls back to licence-file detection; ``unknown`` that
    detection cannot improve is returned as stated (a ``NOASSERTION``).
    """
    card_data: dict[str, Any] = hf_data.get("card_data") or {}
    hub_info: dict[str, Any] = hf_data.get("hub_info") or {}
    raw_revision = hub_info.get("sha")
    revision = str(raw_revision) if raw_revision else None
    raw_license = card_data.get("license")
    raw_license_str: str | None = (
        (str(raw_license).strip() or None) if raw_license else None
    )

    if raw_license_str and not is_vague_license_value(raw_license_str):
        provenance["license"] = (
            "Source: Hugging Face Hub | Field: model card YAML (license)"
        )
        return raw_license_str, None

    vague_raw = (
        raw_license_str
        if raw_license_str and is_vague_license_value(raw_license_str)
        else None
    )
    detected_id, detected_src = _detect_license_from_hf_files(
        hub, model_id, revision=revision
    )
    if detected_id:
        provenance["license"] = detected_src or (
            "Source: Hugging Face Hub | Method: licenseid_detection"
        )
        return detected_id, vague_raw
    if vague_raw and vague_raw.lower() == "unknown":
        # Nothing detected: the card itself says it does not know, which is a
        # statement (``NOASSERTION``), unlike ``other``/``custom``.
        provenance["license"] = (
            "Source: Hugging Face Hub | Field: model card YAML (license)"
        )
        return vague_raw, vague_raw
    return None, vague_raw
