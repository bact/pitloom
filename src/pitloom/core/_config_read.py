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

from pitloom.messages.config import ConfigPlace, config_invalid

_PITLOOM = ConfigPlace("tool.pitloom")


def _read_bool_setting(
    data: dict[str, Any],
    key: str,
    default: bool,
    within: ConfigPlace = _PITLOOM,
) -> bool:
    """Read a boolean key from data, defaulting to default when absent.

    Raises:
        pitloom.messages.config.ConfigError: ``config-invalid``: the value is
            not a boolean; *within* is the table or entry that holds *key*.
    """
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise config_invalid(within.at(key), "boolean", got=value)
    return value


def _read_int_setting(
    data: dict[str, Any],
    key: str,
    default: int,
    within: ConfigPlace = _PITLOOM,
) -> int:
    """Read an int key from data, defaulting to default when absent.

    Rejects a bool value explicitly -- ``isinstance(True, int)`` is ``True``
    in Python, so a TOML ``key = true`` would otherwise silently pass as 1.

    Raises:
        pitloom.messages.config.ConfigError: ``config-invalid``: the value is
            not an integer.
    """
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise config_invalid(within.at(key), "integer", got=value)
    return value


def _optional_str(entry: dict[str, Any], key: str, place: ConfigPlace) -> str | None:
    """*entry*'s *key* (``None`` when absent), a string: ``config-invalid``
    at *place* (the entry or table that holds *key*) otherwise."""
    value = entry.get(key)
    if value is not None and not isinstance(value, str):
        raise config_invalid(place.at(key), "string", got=value)
    return value


def _require_choice(
    value: object, valid: frozenset[str], place: ConfigPlace, expected: str
) -> None:
    """Raise unless *value* is a string of *valid*: ``config-invalid`` at
    *place* (the key), *expected* being the id of the choices
    (``one-of-format`` ...)."""
    if not isinstance(value, str) or value not in valid:
        raise config_invalid(place, expected, got=value)


def _read_array_of_tables(raw: Any, place: ConfigPlace) -> list[dict[str, Any]]:
    """Validate raw is a TOML array-of-tables at *place* (an array of
    :data:`~pitloom.messages.config.ARRAY_TABLES`) and return its entries."""
    if not isinstance(raw, list):
        raise config_invalid(place, "array-of-tables", got=raw)
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise config_invalid(place.entry_at(index), "table", got=entry)
    return raw


def _read_table(parent: dict[str, Any], key: str, place: ConfigPlace) -> dict[str, Any]:
    """*parent*'s sub-table *key* (``{}`` when absent), named *place* in the
    error for a value that is not a table."""
    value = parent.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise config_invalid(place, "table", got=value)
    return value
