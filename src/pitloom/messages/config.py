# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Configuration"
(``config`` in :data:`~pitloom.messages.TOPIC_TITLES`): their entries,
their lines and the helpers that say them, and the closed tables a
configuration line draws on (:class:`ConfigPlace`, :data:`EXPECTED`,
:data:`DESTINATIONS`).

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._config import (
    CLOCK_LINE,
    CONFIG_INVALID,
    CONFIG_MALFORMED,
    CONFIG_MOVED,
    CONFIG_UNKNOWN_KEY,
    DATETIME_UNPINNED,
    EPOCH_NOT_INTEGER_LINE,
    EPOCH_OUT_OF_RANGE_LINE,
    HOOK_UNKNOWN_LINE,
    INI_FILE_LINE,
    INI_LINE,
    INTERPOLATION_FILE_LINE,
    INTERPOLATION_LINE,
    INVALID_FILE_LINE,
    INVALID_LINE,
    MOVED_FILE_LINE,
    MOVED_LINE,
    SOURCE_DATE_EPOCH_INVALID,
    TOML_LINE,
    UNKNOWN_CLOSE_FILE_LINE,
    UNKNOWN_CLOSE_LINE,
    UNKNOWN_ELSEWHERE_FILE_LINE,
    UNKNOWN_ELSEWHERE_LINE,
    UNKNOWN_FILE_LINE,
    UNKNOWN_LINE,
)
from pitloom.messages._config_found import MISSING, SHOWN_CHARS, found_text, kind_text
from pitloom.messages._config_place import (
    ARRAY_TABLES,
    BUDGET_MINIMUM,
    DESTINATIONS,
    EXPECTED,
    TABLES,
    ConfigPlace,
    Parameter,
)
from pitloom.messages._config_say import (
    ConfigError,
    config_invalid,
    config_moved,
    hook_unknown_keys,
    invalid_type,
    invalid_value,
    loom_sdk_invalid_value,
    loom_sdk_type_error,
    must_be,
    require_path_argument,
    warn_config_unknown_key,
)
from pitloom.messages._field_tables import CONFIG_USE

__all__ = [
    "ARRAY_TABLES",
    "BUDGET_MINIMUM",
    "CLOCK_LINE",
    "CONFIG_INVALID",
    "CONFIG_MALFORMED",
    "CONFIG_MOVED",
    "CONFIG_UNKNOWN_KEY",
    "CONFIG_USE",
    "DATETIME_UNPINNED",
    "DESTINATIONS",
    "EPOCH_NOT_INTEGER_LINE",
    "EPOCH_OUT_OF_RANGE_LINE",
    "EXPECTED",
    "HOOK_UNKNOWN_LINE",
    "INI_FILE_LINE",
    "INI_LINE",
    "INTERPOLATION_FILE_LINE",
    "INTERPOLATION_LINE",
    "INVALID_FILE_LINE",
    "INVALID_LINE",
    "MISSING",
    "MOVED_FILE_LINE",
    "MOVED_LINE",
    "SHOWN_CHARS",
    "SOURCE_DATE_EPOCH_INVALID",
    "TABLES",
    "TOML_LINE",
    "UNKNOWN_CLOSE_FILE_LINE",
    "UNKNOWN_CLOSE_LINE",
    "UNKNOWN_ELSEWHERE_FILE_LINE",
    "UNKNOWN_ELSEWHERE_LINE",
    "UNKNOWN_FILE_LINE",
    "UNKNOWN_LINE",
    "ConfigError",
    "ConfigPlace",
    "Parameter",
    "config_invalid",
    "config_moved",
    "found_text",
    "hook_unknown_keys",
    "invalid_type",
    "invalid_value",
    "kind_text",
    "loom_sdk_invalid_value",
    "loom_sdk_type_error",
    "must_be",
    "require_path_argument",
    "warn_config_unknown_key",
]
