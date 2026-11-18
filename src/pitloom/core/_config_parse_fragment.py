# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reader for ``[tool.pitloom.fragment] files``.

See also: :mod:`pitloom.core._config_parse` (the other ``[tool.pitloom]``
readers) and :mod:`pitloom.core._config_read` (read primitives).
"""

from __future__ import annotations

from typing import Any

from pitloom.core._config_read import _optional_str, _read_bool_setting, _read_table
from pitloom.core._config_types import FragmentConfig
from pitloom.messages.config import MISSING, ConfigPlace, config_invalid

_FRAGMENT = ConfigPlace("tool.pitloom.fragment")
_FILES = ConfigPlace("tool.pitloom.fragment", "files")


def _read_fragments(pitloom_data: dict[str, Any]) -> list[FragmentConfig]:
    """Read ``[tool.pitloom.fragment] files`` into ``FragmentConfig`` entries.

    Each entry is either a plain path string (shorthand for
    ``FragmentConfig(path=...)``) or an inline table with ``path`` plus any
    of ``role``, ``description``, ``required``, ``sha256``, ``link-to-main``.
    """
    raw = _read_table(pitloom_data, "fragment", _FRAGMENT).get("files", [])
    if not isinstance(raw, list):
        raise config_invalid(_FILES, "array", got=raw)
    fragments: list[FragmentConfig] = []
    for index, entry in enumerate(raw):
        place = _FILES.entry_at(index)
        if isinstance(entry, str):
            if not entry:
                raise config_invalid(place, "non-empty", got=entry)
            fragments.append(FragmentConfig(path=entry))
        elif isinstance(entry, dict):
            fragments.append(_read_fragment_entry(entry, place))
        else:
            raise config_invalid(place, "string-or-table", got=entry)
    return fragments


def _read_fragment_entry(entry: dict[str, Any], place: ConfigPlace) -> FragmentConfig:
    """Parse one ``[tool.pitloom.fragment] files`` table entry at *place*
    (:meth:`~pitloom.messages.config.ConfigPlace.entry_at` of ``files``).

    Every field here raises ``config-invalid`` on the wrong type, matching
    every ``_read_*`` config reader (``_read_creators``,
    ``_read_content_type_overrides``, ``_read_bool_setting``, ...) --
    config errors are never silently coerced or defaulted around, only
    genuinely-absent optional fields get a default.
    """
    declared = entry.get("path")
    if not isinstance(declared, str) or not declared:
        raise config_invalid(
            place.at("path"), "non-empty", got=entry.get("path", MISSING)
        )
    role = _optional_str(entry, "role", place)
    description = _optional_str(entry, "description", place)
    required = _read_bool_setting(entry, "required", False, place)
    sha256 = _optional_str(entry, "sha256", place)
    link_key = "link-to-main" if "link-to-main" in entry else "link_to_main"
    link_to_main = _optional_str(entry, link_key, place)
    return FragmentConfig(
        path=declared,
        role=role,
        description=description,
        required=required,
        sha256=sha256,
        link_to_main=link_to_main,
    )
