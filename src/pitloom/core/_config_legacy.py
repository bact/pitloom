# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Legacy TOML configuration migration checks for ``[tool.pitloom]``.

See also: :mod:`pitloom.core._config_parse`.
"""

from __future__ import annotations

from typing import Any

from pitloom.messages.config import ConfigPlace, config_invalid, config_moved

_PITLOOM = ConfigPlace("tool.pitloom")
_CREATION = ConfigPlace("tool.pitloom.creation")

#: Old (pre-multi-creator) ``[tool.pitloom.creation]`` keys that moved to
#: ``[[tool.pitloom.creator]]`` / ``[[tool.pitloom.creation-tool]]``, mapped
#: to a destination of :data:`~pitloom.messages.config.DESTINATIONS`.
_MOVED_CREATION_KEYS: dict[str, str] = {
    "creator-name": "[[tool.pitloom.creator]] name",
    "creator_name": "[[tool.pitloom.creator]] name",
    "creator-email": "[[tool.pitloom.creator]] email",
    "creator_email": "[[tool.pitloom.creator]] email",
    "creator-type": "[[tool.pitloom.creator]] type",
    "creator_type": "[[tool.pitloom.creator]] type",
    "creation-tool": "[[tool.pitloom.creation-tool]] name",
    "creation_tool": "[[tool.pitloom.creation-tool]] name",
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
    "ids": "[tool.pitloom] id-registry",
    "fragments": "[tool.pitloom.fragment] files",
    "file-headers": _FILE_HEADERS_MOVED_TO,
    "file_headers": _FILE_HEADERS_MOVED_TO,
}

#: Old flat ``[tool.pitloom]`` keys and their current place
#: (``ids-file`` -> ``id-registry``).
_MOVED_FLAT_KEYS: dict[str, str] = {
    "ids-file": "[tool.pitloom] id-registry",
    "ids_file": "[tool.pitloom] id-registry",
    "update-registry": "[tool.pitloom] update-id-registry",
    "update_registry": "[tool.pitloom] update-id-registry",
}


def _check_moved_creation_keys(
    pitloom_data: dict[str, Any], creation_data: dict[str, Any]
) -> None:
    """Raise ``config-moved`` if single-valued creator/tool keys are present."""
    for key in pitloom_data:
        moved_to = _MOVED_CREATION_KEYS.get(key)
        if moved_to is None:
            continue
        if key in _MOVED_CREATION_KEYS_LIST_VALID and isinstance(
            pitloom_data[key], list
        ):
            continue
        raise config_moved(_PITLOOM.at(key), moved_to)
    for key in creation_data:
        moved_to = _MOVED_CREATION_KEYS.get(key)
        if moved_to is not None:
            raise config_moved(_CREATION.at(key), moved_to)


def _check_moved_top_level_tables(pitloom_data: dict[str, Any]) -> None:
    """Raise if an old top-level table is present: ``config-moved``, or
    ``config-invalid`` for ``enrich`` as a table (the key did not move, its
    shape changed: it is a flat boolean)."""
    for key, moved_to in _MOVED_TOP_LEVEL_TABLES.items():
        if key in pitloom_data:
            raise config_moved(_PITLOOM.at(key), moved_to)
    enrich = pitloom_data.get("enrich")
    if isinstance(enrich, dict):
        raise config_invalid(_PITLOOM.at("enrich"), "boolean", got=enrich)


def _check_moved_flat_keys(pitloom_data: dict[str, Any]) -> None:
    """Raise ``config-moved`` if an old flat ``[tool.pitloom]`` key is present."""
    for key, moved_to in _MOVED_FLAT_KEYS.items():
        if key in pitloom_data:
            raise config_moved(_PITLOOM.at(key), moved_to)
