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
    "ids": "[tool.pitloom] id-registry",
    "fragments": "[tool.pitloom.fragment] (key: files)",
    "file-headers": _FILE_HEADERS_MOVED_TO,
    "file_headers": _FILE_HEADERS_MOVED_TO,
}

#: Old flat ``[tool.pitloom]`` keys renamed to their current spelling
#: (PR A2's ``ids``/``registry`` -> ``id``/``id-registry`` rename).
_MOVED_FLAT_KEYS: dict[str, str] = {
    "ids-file": "id-registry",
    "ids_file": "id-registry",
    "update-registry": "update-id-registry",
    "update_registry": "update-id-registry",
}


def _table(is_setup_cfg: bool, *parts: str) -> str:
    """Render the source table name a moved-key error names, in the
    config's own separator style: dot-separated for ``pyproject.toml``
    (``[tool.pitloom.creation]``), colon-separated for ``setup.cfg``
    (``[tool:pitloom:creation]``) -- the same separator
    :mod:`pitloom.extract.project.setuptools_cfg` uses for its own
    sub-sections. Only the *source* location is rendered this way; the
    "moved to" destination in :data:`_MOVED_CREATION_KEYS` stays a TOML
    array-of-tables spelling regardless of source, since setup.cfg has no
    equivalent syntax to point at."""
    base = "tool:pitloom" if is_setup_cfg else "tool.pitloom"
    sep = ":" if is_setup_cfg else "."
    return f"[{sep.join((base, *parts))}]"


def _check_moved_creation_keys(
    pitloom_data: dict[str, Any],
    creation_data: dict[str, Any],
    *,
    is_setup_cfg: bool = False,
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
            f"{_table(is_setup_cfg)} {key!r} has moved to {moved_to}. "
            "Update your config."
        )
    for key in creation_data:
        moved_to = _MOVED_CREATION_KEYS.get(key)
        if moved_to is not None:
            raise ValueError(
                f"{_table(is_setup_cfg, 'creation')} {key!r} has moved to "
                f"{moved_to}. Update your config."
            )


def _check_moved_top_level_tables(
    pitloom_data: dict[str, Any], *, is_setup_cfg: bool = False
) -> None:
    """Raise a clear error if an old top-level table is present."""
    for key, moved_to in _MOVED_TOP_LEVEL_TABLES.items():
        if key in pitloom_data:
            raise ValueError(
                f"{_table(is_setup_cfg, key)} has moved to {moved_to}. "
                "Update your config."
            )
    enrich = pitloom_data.get("enrich")
    if isinstance(enrich, dict):
        raise ValueError(
            f"{_table(is_setup_cfg, 'enrich')} has moved to "
            f"{_table(is_setup_cfg)} enrich (a flat boolean, not a table). "
            "Update your config."
        )


def _check_moved_flat_keys(
    pitloom_data: dict[str, Any], *, is_setup_cfg: bool = False
) -> None:
    """Raise a clear error if an old flat ``[tool.pitloom]`` key is present."""
    for key, moved_to in _MOVED_FLAT_KEYS.items():
        if key in pitloom_data:
            raise ValueError(
                f"{_table(is_setup_cfg)} {key!r} has moved to {moved_to!r}. "
                "Update your config."
            )
