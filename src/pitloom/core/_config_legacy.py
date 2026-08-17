# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Legacy TOML configuration migration checks for ``[tool.pitloom]``.

See also: :mod:`pitloom.core._config_parse`.
"""

from __future__ import annotations

from typing import Any

#: Old (pre-multi-creator) ``[tool.pitloom.creation]`` keys that moved to
#: ``[[tool.pitloom.creator]]`` / ``[[tool.pitloom.creation-tool]]``.
_MOVED_CREATION_KEYS: dict[str, str] = {
    "creator-name": "[[tool.pitloom.creator]] (key: name)",
    "creator_name": "[[tool.pitloom.creator]] (key: name)",
    "creator-email": "[[tool.pitloom.creator]] (key: email)",
    "creator_email": "[[tool.pitloom.creator]] (key: email)",
    "creator-type": "[[tool.pitloom.creator]] (key: type)",
    "creator_type": "[[tool.pitloom.creator]] (key: type)",
    "creation-tool": "[[tool.pitloom.creation-tool]] (key: name)",
    "creation_tool": "[[tool.pitloom.creation-tool]] (key: name)",
}

#: Subset of ``_MOVED_CREATION_KEYS`` where a top-level ``list`` value is
#: valid (the new array-of-tables form) rather than stale.
_MOVED_CREATION_KEYS_LIST_VALID: frozenset[str] = frozenset(
    {"creation-tool", "creation_tool"}
)

#: Old ``[tool.pitloom.*]`` sub-tables flattened/renamed directly under
#: ``[tool.pitloom]``.
_FILE_HEADERS_MOVED_TO = (
    "[tool.pitloom] extract-file-header and [tool.pitloom.content-type]"
)
_MOVED_TOP_LEVEL_TABLES: dict[str, str] = {
    "ids": "[tool.pitloom] ids-file",
    "fragments": "[tool.pitloom.fragment] (key: files)",
    "file-headers": _FILE_HEADERS_MOVED_TO,
    "file_headers": _FILE_HEADERS_MOVED_TO,
}


def _check_moved_creation_keys(
    pitloom_data: dict[str, Any], creation_data: dict[str, Any]
) -> None:
    """Raise a clear error if single-valued creator/tool keys are present."""
    for key in pitloom_data:
        moved_to = _MOVED_CREATION_KEYS.get(key)
        if moved_to is None:
            continue
        if key in _MOVED_CREATION_KEYS_LIST_VALID and isinstance(
            pitloom_data[key], list
        ):
            continue
        raise ValueError(
            f"[tool.pitloom] {key!r} has moved to {moved_to}. "
            "Update your pyproject.toml."
        )
    for key in creation_data:
        moved_to = _MOVED_CREATION_KEYS.get(key)
        if moved_to is not None:
            raise ValueError(
                f"[tool.pitloom.creation] {key!r} has moved to {moved_to}. "
                "Update your pyproject.toml."
            )


def _check_moved_top_level_tables(pitloom_data: dict[str, Any]) -> None:
    """Raise a clear error if an old top-level table is present."""
    for key, moved_to in _MOVED_TOP_LEVEL_TABLES.items():
        if key in pitloom_data:
            raise ValueError(
                f"[tool.pitloom.{key}] has moved to {moved_to}. "
                "Update your pyproject.toml."
            )
    enrich = pitloom_data.get("enrich")
    if isinstance(enrich, dict):
        raise ValueError(
            "[tool.pitloom.enrich] has moved to [tool.pitloom] enrich "
            "(a flat boolean, not a table). Update your pyproject.toml."
        )
