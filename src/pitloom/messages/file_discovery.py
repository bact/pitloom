# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "File discovery"
(``file-discovery`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helper that says them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._fields_metadata import (
    DISCOVERERS,
)
from pitloom.messages._file_discovery import (
    BUILD_FAILED_LINE,
    BUILD_FAILED_NO_PROJECT_LINE,
    FAILED_HEURISTIC_LINE,
    FAILED_LINE,
    FAILED_NO_PROJECT_LINE,
    FILE_DISCOVERY_CONFLICT,
    FILE_DISCOVERY_NEEDS_BUILD,
    FILE_DISCOVERY_UNUSABLE,
    FLIT_EXTERNAL_DATA_LINE,
    IMPERATIVE_LINE,
    INTROSPECTION_LINE,
    NO_STATIC_HEURISTIC_LINE,
    NO_STATIC_LINE,
    NOT_AWARE_LINE,
    NOT_AWARE_NO_PROJECT_LINE,
    PACKAGES_AMBIGUOUS_LINE,
    UV_OVERRIDES_LINES,
    WHEEL_PATH_LINE,
)
from pitloom.messages._metadata_say import warn_discovery

__all__ = [
    "BUILD_FAILED_LINE",
    "BUILD_FAILED_NO_PROJECT_LINE",
    "DISCOVERERS",
    "FAILED_HEURISTIC_LINE",
    "FAILED_LINE",
    "FAILED_NO_PROJECT_LINE",
    "FILE_DISCOVERY_CONFLICT",
    "FILE_DISCOVERY_NEEDS_BUILD",
    "FILE_DISCOVERY_UNUSABLE",
    "FLIT_EXTERNAL_DATA_LINE",
    "IMPERATIVE_LINE",
    "INTROSPECTION_LINE",
    "NOT_AWARE_LINE",
    "NOT_AWARE_NO_PROJECT_LINE",
    "NO_STATIC_HEURISTIC_LINE",
    "NO_STATIC_LINE",
    "PACKAGES_AMBIGUOUS_LINE",
    "UV_OVERRIDES_LINES",
    "WHEEL_PATH_LINE",
    "warn_discovery",
]
