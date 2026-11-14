# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Options"
(``options`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._options import (
    BUILD_PREFIX,
    CANNOT_BE_USED_LINE,
    NAMESPACE_CONFLICT_LINE,
    OPTION_CONFLICT,
    OPTION_INVALID,
    OPTION_MISSING,
    OPTION_NO_EFFECT,
    OPTIONS_PREFIX,
    OUTPUT_REQUIRED_LINE,
    PATH_OUTSIDE_LINE,
    PROJECT_ROOT_CONFLICT_LINE,
    REGISTRY_PATH_OUTSIDE_LINE,
)
from pitloom.messages._options_say import (
    usage_code,
    warn_option_no_effect,
)

__all__ = [
    "BUILD_PREFIX",
    "CANNOT_BE_USED_LINE",
    "NAMESPACE_CONFLICT_LINE",
    "OPTION_CONFLICT",
    "OPTION_INVALID",
    "OPTION_MISSING",
    "OPTION_NO_EFFECT",
    "OPTIONS_PREFIX",
    "OUTPUT_REQUIRED_LINE",
    "PATH_OUTSIDE_LINE",
    "PROJECT_ROOT_CONFLICT_LINE",
    "REGISTRY_PATH_OUTSIDE_LINE",
    "usage_code",
    "warn_option_no_effect",
]
