# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Readers for the file and model scanning keys of ``[tool.pitloom]``.

See also: :mod:`pitloom.core._config_read` (read primitives),
:mod:`pitloom.core._config_parse` and :mod:`pitloom.core.config`.
"""

from __future__ import annotations

import re
from typing import Any

from pitloom.core._config_read import (
    _read_array_of_tables,
    _read_bool_setting,
    _read_int_setting,
    _require_choice,
)
from pitloom.core._config_types import (
    DEFAULT_MAX_DATASET_HASH_BYTES,
    DEFAULT_MAX_MODEL_EXTRACT_BYTES,
    VALID_CONTENT_TYPE_METHODS,
)
from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.model_extract_limit import (
    DEFAULT_MAX_DOWNLOAD_BYTES,
    MAX_DOWNLOAD_BYTES_KEY,
    require_max_dataset_hash_bytes,
    require_max_download_bytes,
    require_max_model_extract_bytes,
)
from pitloom.core.provenance import require_max_source_metadata_bytes
from pitloom.messages.config import MISSING, ConfigPlace, config_invalid

_CONTENT_TYPE = ConfigPlace("tool.pitloom.content-type")
_OVERRIDE = ConfigPlace("tool.pitloom.content-type.override")
_PROVENANCE = ConfigPlace("tool.pitloom.provenance")
_CONTENT_TYPE_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


def _read_content_type_overrides(
    raw: dict[str, Any],
) -> tuple[ContentTypeOverride, ...]:
    """Read ``[[tool.pitloom.content-type.override]]``."""
    raw_overrides = raw.get("override", [])
    overrides: list[ContentTypeOverride] = []
    for index, entry in enumerate(_read_array_of_tables(raw_overrides, _OVERRIDE)):
        place = _OVERRIDE.entry_at(index)
        pattern = entry.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise config_invalid(
                place.at("pattern"), "non-empty", got=entry.get("pattern", MISSING)
            )
        content_type = entry.get("content-type")
        if not isinstance(content_type, str) or not _CONTENT_TYPE_RE.match(
            content_type
        ):
            raise config_invalid(
                place.at("content-type"),
                "media-type",
                got=entry.get("content-type", MISSING),
            )
        overrides.append(
            ContentTypeOverride(pattern=pattern, content_type=content_type)
        )
    return tuple(overrides)


def _read_extract_file_header(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] extract-file-header``."""
    return _read_bool_setting(pitloom_data, "extract-file-header", True)


def _read_scan_model_usage(pitloom_data: dict[str, Any]) -> bool | None:
    """Read ``[tool.pitloom] scan-model-usage``; ``None`` when the key is absent.

    An explicit ``false`` stays ``False``: it silences the usage-scan hint.
    """
    key = "scan-model-usage"
    if key not in pitloom_data:
        return None
    return _read_bool_setting(pitloom_data, key, False)


def _read_max_model_extract_bytes(pitloom_data: dict[str, Any]) -> int:
    """Read ``[tool.pitloom] max-model-extract-bytes``, a positive integer
    (see :func:`~pitloom.core.model_extract_limit.require_max_model_extract_bytes`)."""
    return require_max_model_extract_bytes(
        pitloom_data.get("max-model-extract-bytes", DEFAULT_MAX_MODEL_EXTRACT_BYTES)
    )


def _read_max_dataset_hash_bytes(pitloom_data: dict[str, Any]) -> int:
    """Read ``[tool.pitloom] max-dataset-hash-bytes``, a positive integer
    (see :func:`~pitloom.core.model_extract_limit.require_max_dataset_hash_bytes`)."""
    return require_max_dataset_hash_bytes(
        pitloom_data.get("max-dataset-hash-bytes", DEFAULT_MAX_DATASET_HASH_BYTES)
    )


def _read_max_download_bytes(pitloom_data: dict[str, Any]) -> int:
    """Read ``[tool.pitloom] max-download-bytes``, a positive integer
    (see :func:`~pitloom.core.model_extract_limit.require_max_download_bytes`)."""
    return require_max_download_bytes(
        pitloom_data.get(MAX_DOWNLOAD_BYTES_KEY, DEFAULT_MAX_DOWNLOAD_BYTES)
    )


def _read_max_source_metadata_bytes(provenance_data: dict[str, Any]) -> int:
    """Read ``[tool.pitloom.provenance] max-source-metadata-bytes`` (either
    spelling): ``0`` or a budget of at least 8
    (:func:`~pitloom.core.provenance.require_max_source_metadata_bytes`). An
    error names the key as written."""
    keys = ("max-source-metadata-bytes", "max_source_metadata_bytes")
    key = next((k for k in keys if k in provenance_data), keys[0])
    place = _PROVENANCE.at(key)
    return require_max_source_metadata_bytes(
        _read_int_setting(provenance_data, key, 0, _PROVENANCE), place
    )


def _read_content_type_settings(
    pitloom_data: dict[str, Any],
) -> tuple[bool, str, tuple[ContentTypeOverride, ...]]:
    """Read ``[tool.pitloom.content-type]`` settings."""
    raw = pitloom_data.get("content-type", {})
    if not isinstance(raw, dict):
        raise config_invalid(_CONTENT_TYPE, "table", got=raw)
    enabled = _read_bool_setting(raw, "enabled", False, _CONTENT_TYPE)
    method = raw.get("method", "auto")
    _require_choice(
        method, VALID_CONTENT_TYPE_METHODS, _CONTENT_TYPE.at("method"), "one-of-method"
    )
    overrides = _read_content_type_overrides(raw)
    return enabled, method, overrides
