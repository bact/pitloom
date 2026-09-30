# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Typed values for ``setup.cfg`` ``[tool:pitloom]`` keys.

INI values are strings; each boolean or integer key is coerced as its
``pyproject.toml`` counterpart is typed, from the one declaration
:data:`pitloom.core.config.BOOL_KEYS`/:data:`~pitloom.core.config.INT_KEYS`.
A value that does not parse stays a string, so
:func:`pitloom.core.config.parse_pitloom_config` raises its own one-line
error for it, as it does for ``pyproject.toml``.

See also: :mod:`pitloom.extract.project.setuptools_cfg`.
"""

from __future__ import annotations

from typing import Any

from pitloom.core.config import BOOL_KEYS, INT_KEYS


def _bool_val(v: str) -> bool | None:
    """An INI boolean spelling as a ``bool``, else ``None``."""
    v = v.strip().lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return None


def coerce_cfg_value(table: str, key: str, raw: str) -> Any:
    """*raw*, the value of *key* in sub-table *table* (``""`` for
    ``[tool:pitloom]`` itself), typed as ``pyproject.toml`` would type it.

    An empty or unparsable value stays the stripped string: never a default.
    """
    value = raw.strip()
    if key in BOOL_KEYS.get(table, ()):
        b = _bool_val(value)
        return value if b is None else b
    if key in INT_KEYS.get(table, ()):
        if not value.isascii():  # int() takes any Unicode digit; TOML does not
            return value
        try:
            return int(value, 10)
        except ValueError:
            return value
    return value


def parse_sub_section(table: str, sub_raw: dict[str, str]) -> dict[str, Any]:
    """Typed key-values of the ``[tool:pitloom:<table>]`` section."""
    sub: dict[str, Any] = {}
    for k, v in sub_raw.items():
        if k == "files":
            sub[k] = [f.strip() for f in v.splitlines() if f.strip()]
        else:
            sub[k] = coerce_cfg_value(table, k, v)
    return sub
