# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Croissant JSON-LD dataset metadata extractor.

Parses metadata from Croissant-formatted JSON-LD documents (local files or
URLs) and returns a :class:`~pitloom.core.dataset_metadata.DatasetMetadata`.

Croissant is a JSON-LD extension of ``schema.org/Dataset`` adopted by
Hugging Face, Kaggle, and OpenML.
See: https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html
See: https://docs.mlcommons.org/croissant/docs/croissant-rai-spec.html

This module is stdlib-only — no third-party packages are required.
To work with Croissant RDF as Python dataclass,
we can use https://github.com/mlcommons/croissant/tree/main/python/mlcroissant

Key alias tables live in :mod:`pitloom.extract._croissant_keys`.
Generic I/O and string utilities live in :mod:`pitloom.extract._extract_utils`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.extract._croissant_keys import (
    CREATOR_KEYS,
    DATA_TYPE_KEYS,
    DESCRIPTION_KEYS,
    KEYWORDS_KEYS,
    LICENSE_KEYS,
    NAME_KEYS,
    RAI_BIASES_KEYS,
    RAI_COLLECTION_KEYS,
    RAI_PREPROCESSING_KEYS,
    RAI_SENSITIVITY_KEYS,
    SCHEMA_TYPE_TO_DATASET_TYPE,
    URL_KEYS,
    VERSION_KEYS,
)
from pitloom.extract._extract_utils import fetch_json, get_first, to_str_list


def _extract_creator_name(value: Any) -> str | None:
    """Extract a plain name string from a ``schema:creator`` value.

    The value may be a ``dict`` with a ``name`` key (``Person`` or
    ``Organization`` node), a list of such dicts (first entry taken), or a
    plain string.
    """
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        name = get_first(value, "name", "sc:name", "schema:name")
        return str(name) if name else None
    return str(value) if value else None


def _normalize_sensitivity(value: Any) -> str | None:
    """Map a free-text RAI sensitivity value to
    ``"yes"``, ``"no"``, or ``"noAssertion"``.

    Returns ``None`` when *value* is ``None`` or empty.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in ("yes", "true", "1"):
        return "yes"
    if s in ("no", "false", "0"):
        return "no"
    return "noAssertion"


def _collect_data_types(obj: Any) -> list[str]:
    """Recursively collect all ``dataType`` values from a nested structure."""
    results: list[str] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in DATA_TYPE_KEYS:
                if isinstance(val, str):
                    results.append(val)
                elif isinstance(val, list):
                    results.extend(v for v in val if isinstance(v, str))
            else:
                results.extend(_collect_data_types(val))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_collect_data_types(item))
    return results


def _infer_dataset_types(data: dict[str, Any]) -> list[str]:
    """Infer ``dataset_types`` by walking all ``dataType`` values in *data*.

    Maps schema.org type references to SPDX ``dataset_DatasetType`` enum name
    strings (e.g. ``"text"``, ``"image"``).  Falls back to ``"other"`` for
    unrecognised types.  Returns a deduplicated list preserving first-seen order.
    """
    raw_types = _collect_data_types(data)
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_types:
        mapped = SCHEMA_TYPE_TO_DATASET_TYPE.get(raw, "other")
        if mapped not in seen:
            seen.add(mapped)
            result.append(mapped)
    return result


def _extract_size(data: dict[str, Any]) -> int | None:
    """Extract dataset size.
    Still have to figure out the calculation logic here.

    Returns ``None`` when data is empty or has no record sets.
    Otherwise returns ``0`` for now.
    """
    if not data:
        return None

    return 0


# pylint: disable=too-many-locals
def read_croissant(source: str | Path) -> DatasetMetadata:
    """Extract metadata from a Croissant JSON-LD document.

    Accepts a local file path or an HTTP/HTTPS URL.  No third-party packages
    are required — only the Python stdlib is used.

    Extracted fields:

    - ``name`` — from ``schema:name`` (required; raises if absent)
    - ``version`` — from ``schema:version``
    - ``description`` — from ``schema:description``
    - ``download_url`` — from ``schema:url``
    - ``license`` — from ``schema:license``
    - ``keywords`` — from ``schema:keywords``
    - ``creator`` — from ``schema:creator`` (name extracted from nested node)
    - ``dataset_types`` — inferred from all ``sc:dataType`` values in the document
    - ``data_collection_process`` — from ``rai:dataCollection``
    - ``data_preprocessing`` — from ``rai:dataPreprocessingProtocol``
    - ``known_bias`` — from ``rai:dataBiases``
    - ``has_sensitive_personal_information`` — from ``rai:personalSensitiveInformation``
    - ``croissant_url`` — the URL string of *source* (when *source* is a URL)

    Args:
        source: Path to a local ``.json`` file or an HTTP/HTTPS URL.

    Returns:
        :class:`~pitloom.core.dataset_metadata.DatasetMetadata` with available
        fields populated.

    Raises:
        ValueError: If *source* cannot be read, is not valid JSON, or has no
            ``name`` field.
    """
    try:
        data = fetch_json(source)
    except ValueError as exc:
        # Re-raise with Croissant-specific wording for context.
        raise ValueError(str(exc).replace("Source ", "Croissant source ")) from exc

    src_label = str(source)

    name_raw = get_first(data, *NAME_KEYS)
    if not name_raw:
        raise ValueError(f"Croissant source {source!r} has no 'name' field.")
    name = str(name_raw)

    provenance: dict[str, str] = {"name": f"Source: {src_label} | Field: name"}

    version_raw = get_first(data, *VERSION_KEYS)
    version = str(version_raw) if version_raw else None
    if version:
        provenance["version"] = f"Source: {src_label} | Field: version"

    description_raw = get_first(data, *DESCRIPTION_KEYS)
    description = str(description_raw) if description_raw else None
    if description:
        provenance["description"] = f"Source: {src_label} | Field: description"

    download_url_raw = get_first(data, *URL_KEYS)
    download_url = str(download_url_raw) if download_url_raw else None
    if download_url:
        provenance["download_url"] = f"Source: {src_label} | Field: url"

    license_raw = get_first(data, *LICENSE_KEYS)
    license_val = str(license_raw) if license_raw else None
    if license_val:
        provenance["license"] = f"Source: {src_label} | Field: license"

    keywords = to_str_list(get_first(data, *KEYWORDS_KEYS))
    if keywords:
        provenance["keywords"] = f"Source: {src_label} | Field: keywords"

    creator = _extract_creator_name(get_first(data, *CREATOR_KEYS))
    if creator:
        provenance["creator"] = f"Source: {src_label} | Field: creator"

    dataset_types = _infer_dataset_types(data)
    if dataset_types:
        provenance["dataset_types"] = (
            f"Source: {src_label} | Fields: cr:recordSet / sc:dataType"
        )

    dataset_size = 0

    collection_raw = get_first(data, *RAI_COLLECTION_KEYS)
    data_collection_process = str(collection_raw) if collection_raw else None
    if data_collection_process:
        provenance["data_collection_process"] = (
            f"Source: {src_label} | Field: rai:dataCollection"
        )

    preprocessing_raw = get_first(data, *RAI_PREPROCESSING_KEYS)
    data_preprocessing = to_str_list(preprocessing_raw)
    if data_preprocessing:
        provenance["data_preprocessing"] = (
            f"Source: {src_label} | Field: rai:dataPreprocessingStrategies"
        )

    biases_raw = get_first(data, *RAI_BIASES_KEYS)
    known_bias = to_str_list(biases_raw)
    if known_bias:
        provenance["known_bias"] = f"Source: {src_label} | Field: rai:dataBiases"

    intended_use = ""

    sensitivity_raw = get_first(data, *RAI_SENSITIVITY_KEYS)
    has_sensitive = _normalize_sensitivity(sensitivity_raw)
    if has_sensitive is not None:
        provenance["has_sensitive_personal_information"] = (
            f"Source: {src_label} | Field: rai:personalSensitiveInformation"
        )

    anonymization_methods: list[str] = []

    croissant_url: str | None = None
    if isinstance(source, str) and source.startswith(("http://", "https://")):
        croissant_url = source

    return DatasetMetadata(
        name=name,
        version=version,
        description=description,
        download_url=download_url,
        license=license_val,
        keywords=keywords,
        creator=creator,
        dataset_types=dataset_types,
        dataset_size=dataset_size,
        data_collection_process=data_collection_process,
        data_preprocessing=data_preprocessing,
        known_bias=known_bias,
        intended_use=intended_use,
        has_sensitive_personal_information=has_sensitive,
        anonymization_methods=anonymization_methods,
        croissant_url=croissant_url,
        provenance=provenance,
    )
