# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hugging Face Hub I/O and licence resolution helpers.

Downloads and parses raw data from a Hugging Face Hub repository
(``config.json``, the model card, ``model_info()``, and license files) and
resolves the model's SPDX license identifier.

See also: :mod:`pitloom.extract._huggingface` (public facade) and
:mod:`pitloom.extract._huggingface_fields` (field-extraction helpers that
turn this module's raw data into :class:`~pitloom.core.ai_metadata.AiModelMetadata`
fields).
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

# HF-specific license values that mean "non-standard / unknown" -
# when the card YAML contains one of these, we fall back to license-file detection.
_VAGUE_LICENSE_VALUES: frozenset[str] = frozenset(
    {"other", "custom", "proprietary", "unknown", "unlicensed"}
)


def _canonicalize_license_id(raw: str) -> str:
    """Return the canonical SPDX License ID for *raw*, or *raw* unchanged.

    Delegates to :func:`~pitloom.extract._license.canonicalize_license_id`,
    which uses ``AggregatedLicenseMatcher.match()`` from the ``licenseid``
    library.  When *raw* is recognised as an SPDX License ID the canonical
    casing is returned (e.g. ``"bsd-3-clause"`` -> ``"BSD-3-Clause"``).

    When *raw* is not recognised it is returned verbatim -- pitloom records
    what it found and leaves further interpretation (e.g. deciding whether to
    add a ``LicenseRef-`` prefix for non-SPDX identifiers) to the
    ``licenseid`` library or downstream SBOM tooling.

    Requires a populated ``licenseid`` database (``licenseid update``).
    When the database has not been built, *raw* is returned unchanged.
    """
    # pylint: disable=import-outside-toplevel

    from pitloom.extract._license import canonicalize_license_id

    return canonicalize_license_id(raw)


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


def _safe_load_json(
    model_id: str, filename: str, revision: str | None = None
) -> dict[str, Any] | None:
    """Download *filename* from *model_id* and return parsed JSON, or ``None``."""
    if revision is None:
        log.warning(
            "Downloading %s for %s without a pinned revision; "
            "supply hub_info['sha'] to ensure reproducibility.",
            filename,
            model_id,
        )
    try:
        # pylint: disable=import-outside-toplevel

        from huggingface_hub import hf_hub_download

        local_path = hf_hub_download(  # nosec B615
            repo_id=model_id,
            filename=filename,
            revision=revision,
        )
        with open(local_path, encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.debug("Failed to load %s for %s: %s", filename, model_id, exc)
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
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.debug("Failed to load model card for %s: %s", model_id, exc)
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
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.debug("Failed to load model_info() for %s: %s", model_id, exc)
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
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.debug("Failed to list repo files for %s: %s", model_id, exc)
        return []


def _detect_license_from_hf_files(
    model_id: str,
    revision: str | None = None,
) -> tuple[str | None, str | None]:
    """Try to detect an SPDX license ID from license files in a HF repository.

    Downloads each candidate file in priority order and runs
    :func:`~pitloom.extract._license.detect_license_from_text` on the content.

    Returns ``(spdx_id, provenance_string)`` when a match is found above the
    default threshold, or ``(None, None)`` otherwise.  Requires the
    ``licenseid`` package and its database (``licenseid update``).
    """
    if revision is None:
        log.warning(
            "Scanning license files for %s without a pinned revision; "
            "supply hub_info['sha'] to ensure reproducibility.",
            model_id,
        )
    # pylint: disable=import-outside-toplevel

    from pathlib import Path as _Path

    from pitloom.extract._license import detect_license_from_text

    for filename in _list_license_files_in_repo(model_id):
        try:
            # pylint: disable=import-outside-toplevel

            from huggingface_hub import hf_hub_download

            local_path = hf_hub_download(  # nosec B615
                repo_id=model_id,
                filename=filename,
                revision=revision,
            )
            text = (
                _Path(local_path).read_text(encoding="utf-8", errors="replace").strip()
            )
        # pylint: disable=broad-exception-caught
        except Exception as exc:
            log.debug(
                "Failed to download/read license file %s for %s: %s",
                filename,
                model_id,
                exc,
            )
            continue

        if not text:
            continue

        detected = detect_license_from_text(text)
        if detected:
            return (
                detected,
                f"Source: Hugging Face Hub | File: {filename}"
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


def _fetch_all_hf_data(model_id: str) -> dict[str, Any]:
    """Fetch all remote HF data sources and return them as a single dict."""
    card_text, card_data = _load_model_card(model_id)
    hub_info = _load_model_info(model_id)
    raw_revision = hub_info.get("sha")
    revision = str(raw_revision) if raw_revision else None
    return {
        "config": _safe_load_json(model_id, "config.json", revision=revision),
        "tokenizer_config": _safe_load_json(
            model_id, "tokenizer_config.json", revision=revision
        ),
        "generation_config": _safe_load_json(
            model_id, "generation_config.json", revision=revision
        ),
        "card_text": card_text,
        "card_data": card_data,
        "hub_info": hub_info,
    }


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
    hub_info: dict[str, Any] = hf_data.get("hub_info") or {}
    raw_revision = hub_info.get("sha")
    revision = str(raw_revision) if raw_revision else None
    raw_license = card_data.get("license")
    raw_license_str: str | None = str(raw_license) if raw_license else None

    if raw_license_str and raw_license_str.lower() not in _VAGUE_LICENSE_VALUES:
        provenance["license"] = (
            "Source: Hugging Face Hub | Field: model card YAML (license)"
        )
        return _canonicalize_license_id(raw_license_str), None

    vague_raw = (
        raw_license_str
        if raw_license_str and raw_license_str.lower() in _VAGUE_LICENSE_VALUES
        else None
    )
    detected_id, detected_src = _detect_license_from_hf_files(
        model_id, revision=revision
    )
    if detected_id:
        provenance["license"] = detected_src or (
            "Source: Hugging Face Hub | Method: licenseid_detection"
        )
        return detected_id, vague_raw
    return None, vague_raw
