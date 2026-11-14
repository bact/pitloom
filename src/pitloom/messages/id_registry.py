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

__all__ = [
    "COUNTERS_LINE",
    "COUNTER_NUMBER_LINE",
    "COUNTER_PREFIX_LINE",
    "DUPLICATE_ENTRY_LINE",
    "DUPLICATE_KEY_LINE",
    "ELEMENTS_LINE",
    "ENTRY_LINE",
    "MAX_COUNTER",
    "MISSING_KEY_LINE",
    "NAMESPACE_LINE",
    "NO_NAMESPACE_LINE",
    "NO_RELATIVE_ROOT_LINE",
    "PROJECT_ROOT_LINE",
    "REGISTRY_MALFORMED",
    "REGISTRY_PREFIX",
    "REGISTRY_UNKNOWN_KEY",
    "REGISTRY_UNUSABLE",
    "REGISTRY_VERSION",
    "REGISTRY_WRONG_FORMAT",
    "ROOT_NOT_STORABLE_LINE",
    "SHA256_LINE",
    "SPDX_ID_LINE",
    "TYPE_TABLE_LINE",
    "UNENCODABLE_LINE",
    "UNKNOWN_ENTRY_KEY_LINE",
    "UNKNOWN_TOP_KEY_LINE",
    "VERSION_LINE",
]
