# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "ID registry"
(``id-registry`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._registry_file import (
    COUNTER_NUMBER_LINE,
    COUNTER_PREFIX_LINE,
    COUNTERS_LINE,
    DUPLICATE_ENTRY_LINE,
    DUPLICATE_KEY_LINE,
    ELEMENTS_LINE,
    ENTRY_LINE,
    MAX_COUNTER,
    MINT_LINE,
    MISSING_KEY_LINE,
    NAMESPACE_LINE,
    NO_NAMESPACE_LINE,
    NO_RELATIVE_ROOT_LINE,
    PROJECT_ROOT_LINE,
    REGISTRY_MALFORMED,
    REGISTRY_PREFIX,
    REGISTRY_UNKNOWN_KEY,
    REGISTRY_UNUSABLE,
    REGISTRY_VERSION,
    REGISTRY_WRONG_FORMAT,
    ROOT_NOT_STORABLE_LINE,
    SHA256_LINE,
    SPDX_ID_LINE,
    TYPE_TABLE_LINE,
    UNENCODABLE_LINE,
    UNKNOWN_ENTRY_KEY_LINE,
    UNKNOWN_TOP_KEY_LINE,
    VERSION_LINE,
)
from pitloom.messages._registry_save import (
    ADDED_IDS,
    CONFIG_HINT_ADD,
    CONFIG_HINT_CHANGE,
    ENTITY_STORED_AS,
    FILE_MISSING_LINE,
    HOLDS_IDS,
    REGISTRY_FILE_MISSING,
    SAVE_PATH_MISSING_LINE,
    STALE_UPDATED,
)
from pitloom.messages._registry_save_say import (
    say_save_failure,
    warn_no_registry_file,
)

__all__ = [
    "ADDED_IDS",
    "CONFIG_HINT_ADD",
    "CONFIG_HINT_CHANGE",
    "COUNTERS_LINE",
    "COUNTER_NUMBER_LINE",
    "COUNTER_PREFIX_LINE",
    "DUPLICATE_ENTRY_LINE",
    "DUPLICATE_KEY_LINE",
    "ELEMENTS_LINE",
    "ENTITY_STORED_AS",
    "ENTRY_LINE",
    "FILE_MISSING_LINE",
    "HOLDS_IDS",
    "MAX_COUNTER",
    "MINT_LINE",
    "MISSING_KEY_LINE",
    "NAMESPACE_LINE",
    "NO_NAMESPACE_LINE",
    "NO_RELATIVE_ROOT_LINE",
    "PROJECT_ROOT_LINE",
    "REGISTRY_FILE_MISSING",
    "REGISTRY_MALFORMED",
    "REGISTRY_PREFIX",
    "REGISTRY_UNKNOWN_KEY",
    "REGISTRY_UNUSABLE",
    "REGISTRY_VERSION",
    "REGISTRY_WRONG_FORMAT",
    "ROOT_NOT_STORABLE_LINE",
    "SAVE_PATH_MISSING_LINE",
    "SHA256_LINE",
    "SPDX_ID_LINE",
    "STALE_UPDATED",
    "TYPE_TABLE_LINE",
    "UNENCODABLE_LINE",
    "UNKNOWN_ENTRY_KEY_LINE",
    "UNKNOWN_TOP_KEY_LINE",
    "VERSION_LINE",
    "say_save_failure",
    "warn_no_registry_file",
]
