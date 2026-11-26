# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Datasets and loom runs"
(``datasets`` in :data:`~pitloom.messages.TOPIC_TITLES`): their entries,
their lines, the helpers that say them and the prefix of the loom SDK's own
lines.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._datasets import (
    CONFLICT_LINE,
    DATASET_CONFLICT,
    DATASET_CONFLICT_SPELLING,
    DATASET_FIELD_INVALID,
    DATASET_METADATA_PREFIX,
    DATASET_NAME_MISSING,
    MODEL_CONFLICT_LINE,
    NAME_ABSENT_LINE,
    NAME_NOT_TEXT_LINE,
    NOT_A_COUNT_LINE,
    NOT_A_URL_LINE,
    NOT_TEXT_LINE,
    SPELLING_LINE,
    UNQUOTED_VERSION_LINE,
)
from pitloom.messages._datasets_say import (
    NOT_A_COUNT,
    NOT_A_URL,
    NOT_TEXT,
    UNQUOTED_VERSION,
    DatasetModel,
    say_one_dataset,
    warn_dataset_conflict,
    warn_dataset_field,
)
from pitloom.messages._loom_sdk import (
    CALLER_INFO_LINE,
    CALLER_INFO_UNREADABLE,
    CALLER_SCRIPT_LINE,
    LOOM_SDK_PREFIX,
    MODEL_FILE_LINE,
    MODEL_FILE_MISSING,
)

__all__ = [
    "CALLER_INFO_LINE",
    "CALLER_INFO_UNREADABLE",
    "CALLER_SCRIPT_LINE",
    "CONFLICT_LINE",
    "DATASET_CONFLICT",
    "DATASET_CONFLICT_SPELLING",
    "DATASET_FIELD_INVALID",
    "DATASET_METADATA_PREFIX",
    "DATASET_NAME_MISSING",
    "LOOM_SDK_PREFIX",
    "MODEL_CONFLICT_LINE",
    "MODEL_FILE_LINE",
    "MODEL_FILE_MISSING",
    "NAME_ABSENT_LINE",
    "NAME_NOT_TEXT_LINE",
    "NOT_A_COUNT",
    "NOT_A_COUNT_LINE",
    "NOT_A_URL",
    "NOT_A_URL_LINE",
    "NOT_TEXT",
    "NOT_TEXT_LINE",
    "SPELLING_LINE",
    "UNQUOTED_VERSION",
    "UNQUOTED_VERSION_LINE",
    "DatasetModel",
    "say_one_dataset",
    "warn_dataset_conflict",
    "warn_dataset_field",
]
