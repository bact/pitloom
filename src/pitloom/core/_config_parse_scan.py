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
    _require_choice,
)
from pitloom.core._config_types import (
    DEFAULT_MAX_MODEL_EXTRACT_BYTES,
    VALID_CONTENT_TYPE_METHODS,
)
from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.model_extract_limit import require_max_model_extract_bytes

_CONTENT_TYPE_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


def _read_content_type_overrides(
    raw: dict[str, Any],
) -> tuple[ContentTypeOverride, ...]:
    """Read ``[[tool.pitloom.content-type.override]]``."""
    raw_overrides = raw.get("override", [])
    overrides: list[ContentTypeOverride] = []
    for entry in _read_array_of_tables(
        raw_overrides, "[[tool.pitloom.content-type.override]]"
    ):
        pattern = entry.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(
                "[[tool.pitloom.content-type.override]] "
                f"'pattern' must be a non-empty string, got {pattern!r}"
            )
        content_type = entry.get("content-type")
        if not isinstance(content_type, str) or not _CONTENT_TYPE_RE.match(
            content_type
        ):
            raise ValueError(
                "[[tool.pitloom.content-type.override]] "
                "'content-type' must be a MIME type in 'type/subtype' form "
                f"(e.g. 'image/png'), got {content_type!r}"
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


def _read_content_type_settings(
    pitloom_data: dict[str, Any],
) -> tuple[bool, str, tuple[ContentTypeOverride, ...]]:
    """Read ``[tool.pitloom.content-type]`` settings."""
    raw = pitloom_data.get("content-type", {})
    if not isinstance(raw, dict):
        raise ValueError(
            "[tool.pitloom.content-type] must be a table, got "
            f"{type(raw).__name__}: {raw!r}"
        )
    enabled = _read_bool_setting(
        raw, "enabled", False, table_path="[tool.pitloom.content-type]"
    )
    method = raw.get("method", "auto")
    _require_choice(
        method, VALID_CONTENT_TYPE_METHODS, "[tool.pitloom.content-type]", "method"
    )
    overrides = _read_content_type_overrides(raw)
    return enabled, method, overrides
