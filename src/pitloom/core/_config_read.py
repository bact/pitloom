# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read primitives for ``[tool.pitloom]`` configuration tables.

Leaf module: imports nothing from ``core/_config_*``, so both
:mod:`pitloom.core._config_parse` and :mod:`pitloom.core._config_parse_scan`
can use it without an import cycle.

See also: :mod:`pitloom.core._config_parse`,
:mod:`pitloom.core._config_parse_scan` and :mod:`pitloom.core.config`.
"""

from __future__ import annotations

from typing import Any


def _read_bool_setting(
    data: dict[str, Any],
    key: str,
    default: bool,
    table_path: str = "[tool.pitloom]",
) -> bool:
    """Read a boolean key from data, defaulting to default when absent."""
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(
            f"{table_path} {key!r} must be a boolean, got "
            f"{type(value).__name__}: {value!r}"
        )
    return value


def _read_int_setting(
    data: dict[str, Any],
    key: str,
    default: int,
    table_path: str = "[tool.pitloom]",
) -> int:
    """Read an int key from data, defaulting to default when absent.

    Rejects a bool value explicitly -- ``isinstance(True, int)`` is ``True``
    in Python, so a TOML ``key = true`` would otherwise silently pass as 1.
    """
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"{table_path} {key!r} must be an integer, got "
            f"{type(value).__name__}: {value!r}"
        )
    return value


def _require_choice(
    value: str, valid: frozenset[str], table_path: str, key: str
) -> None:
    """Raise ValueError unless value is one of valid."""
    if value not in valid:
        options = ", ".join(sorted(valid))
        raise ValueError(
            f"{table_path} {key!r} must be one of {options}, got {value!r}"
        )


def _read_array_of_tables(raw: Any, table_repr: str) -> list[dict[str, Any]]:
    """Validate raw is a TOML array-of-tables and return its entries."""
    if not isinstance(raw, list):
        raise ValueError(
            f"{table_repr} must be an array of tables, got "
            f"{type(raw).__name__}: {raw!r}"
        )
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(
                f"{table_repr} entry must be a table, got "
                f"{type(entry).__name__}: {entry!r}"
            )
    return raw


def _read_table(parent: dict[str, Any], key: str, name: str) -> dict[str, Any]:
    """*parent*'s sub-table *key* (``{}`` when absent), named *name* in the
    error for a value that is not a table."""
    value = parent.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            f"{name} must be a table, got {type(value).__name__}: {value!r}"
        )
    return value
