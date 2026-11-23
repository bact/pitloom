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

from pitloom.messages._config_place import FINGERPRINT_SHAPE
from pitloom.messages._fields_credentials import FINGERPRINT as FINGERPRINT_PATTERN
from pitloom.messages._frames import BUILD_PREFIX
from pitloom.messages._options import (
    CANNOT_BE_USED_LINE,
    CONFIG_NO_TABLE_LINE,
    FINGERPRINT_LINE,
    LOOM_SDK_VALUE_LINE,
    MODE_UNREAD_LINE,
    NAMESPACE_CONFLICT_LINE,
    NAMESPACE_CONFLICT_MASKED_LINE,
    NAMESPACE_EMPTY_LINE,
    NAMESPACE_INVALID_LINE,
    NO_MODEL_LINE,
    OPTION_CONFLICT,
    OPTION_INVALID,
    OPTION_MISSING,
    OPTION_MISSING_PROJECT_DIR,
    OPTION_NO_EFFECT,
    OPTIONS_PREFIX,
    OUTPUT_REQUIRED_LINE,
    PATH_OUTSIDE_LINE,
    PROJECT_DIR_NOT_GIVEN_LINE,
    PROJECT_ROOT_CONFLICT_LINE,
    REFUSE_ARGUMENT_LINE,
    REGISTRY_PATH_OUTSIDE_LINE,
    STALE_FINGERPRINT_LINE,
    URL_CREDENTIALS_MODE_ARGUMENT_LINE,
    VALUE_LINE,
    namespace_conflict_line,
)
from pitloom.messages._options_say import (
    namespace_invalid,
    usage_code,
    warn_option_no_effect,
)
from pitloom.messages._sbom_name import (
    CONFIG_NAME_LINE,
    OPTION_NAME_LINE,
    SBOM_NAME_INVALID,
)

__all__ = [
    "BUILD_PREFIX",
    "CANNOT_BE_USED_LINE",
    "CONFIG_NAME_LINE",
    "CONFIG_NO_TABLE_LINE",
    "FINGERPRINT_LINE",
    "LOOM_SDK_VALUE_LINE",
    "FINGERPRINT_PATTERN",
    "FINGERPRINT_SHAPE",
    "NAMESPACE_CONFLICT_LINE",
    "NAMESPACE_CONFLICT_MASKED_LINE",
    "NAMESPACE_EMPTY_LINE",
    "NAMESPACE_INVALID_LINE",
    "NO_MODEL_LINE",
    "OPTION_CONFLICT",
    "OPTION_INVALID",
    "OPTION_MISSING",
    "OPTION_MISSING_PROJECT_DIR",
    "OPTION_NO_EFFECT",
    "OPTIONS_PREFIX",
    "OPTION_NAME_LINE",
    "OUTPUT_REQUIRED_LINE",
    "PATH_OUTSIDE_LINE",
    "PROJECT_DIR_NOT_GIVEN_LINE",
    "PROJECT_ROOT_CONFLICT_LINE",
    "REFUSE_ARGUMENT_LINE",
    "REGISTRY_PATH_OUTSIDE_LINE",
    "MODE_UNREAD_LINE",
    "SBOM_NAME_INVALID",
    "STALE_FINGERPRINT_LINE",
    "URL_CREDENTIALS_MODE_ARGUMENT_LINE",
    "VALUE_LINE",
    "namespace_conflict_line",
    "namespace_invalid",
    "usage_code",
    "warn_option_no_effect",
]
