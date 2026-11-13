# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Targets"
(``targets`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._config_unsafe import (
    CONFIG_UNSAFE,
    CONFIG_UNSAFE_BUILD_CODE,
    CONFIG_UNSAFE_PYPI_LINE,
    CONFIG_UNSAFE_REMOTE_LINE,
)
from pitloom.messages._input_not_found import (
    FRAGMENT_LINE,
    GIT_FILE_IS_LINK_LINE,
    GIT_FILE_NOT_FOUND_LINE,
    GIT_FOLDER_NOT_FOUND_LINE,
    INPUT_LINE,
    INPUT_NOT_DIR_LINE,
    INPUT_NOT_FILE_LINE,
    INPUT_NOT_FOUND,
    INPUT_NOT_FOUND_FRAGMENT,
    MODEL_FILE_NOT_FOUND_LINE,
    NO_FRAGMENT_FILE_LINE,
    NO_ID_PATHS_LINE,
    NO_WHEEL_MATCH_LINE,
    REQUIRED_FRAGMENT_LINE,
)
from pitloom.messages._input_not_found_say import (
    input_not_found,
    say_input_not_found,
    warn_fragment_not_found,
)
from pitloom.messages._sbom_input import (
    NOT_SPDX3_LINE,
    SBOM_GRAPH_ELEMENT_LINE,
    SBOM_GRAPH_NOT_LIST_LINE,
    SBOM_INVALID,
    SBOM_NOT_VALID_LINE,
    SBOM_WRONG_FORMAT,
)
from pitloom.messages._sbom_target import (
    MODEL_AMBIGUOUS,
    MODEL_AMBIGUOUS_OVER_CAP,
    MODEL_FILES_LINE,
    NAMED_NOT_A_MODEL_LINE,
    NO_PROJECT_ONE_MODEL_LINE,
    NO_SBOM_TARGET,
    ONE_MODEL_LINE,
    PROJECT_NOT_FOUND,
    PROJECT_NOT_FOUND_LINE,
    PROJECT_NOT_FOUND_MODEL_FILES,
    TARGET_AMBIGUOUS,
)
from pitloom.messages._target_input import (
    HF_URL_INVALID,
    HF_URL_LINE,
    HUB_MODEL_NOT_PROJECT_LINE,
    NOT_A_WHEEL_LINE,
    TARGET_WRONG_FORMAT,
)

__all__ = [
    "CONFIG_UNSAFE",
    "CONFIG_UNSAFE_BUILD_CODE",
    "CONFIG_UNSAFE_PYPI_LINE",
    "CONFIG_UNSAFE_REMOTE_LINE",
    "FRAGMENT_LINE",
    "GIT_FILE_IS_LINK_LINE",
    "GIT_FILE_NOT_FOUND_LINE",
    "GIT_FOLDER_NOT_FOUND_LINE",
    "HF_URL_INVALID",
    "HF_URL_LINE",
    "HUB_MODEL_NOT_PROJECT_LINE",
    "INPUT_LINE",
    "INPUT_NOT_DIR_LINE",
    "INPUT_NOT_FILE_LINE",
    "INPUT_NOT_FOUND",
    "INPUT_NOT_FOUND_FRAGMENT",
    "MODEL_AMBIGUOUS",
    "MODEL_AMBIGUOUS_OVER_CAP",
    "MODEL_FILES_LINE",
    "MODEL_FILE_NOT_FOUND_LINE",
    "NAMED_NOT_A_MODEL_LINE",
    "NOT_A_WHEEL_LINE",
    "NOT_SPDX3_LINE",
    "NO_FRAGMENT_FILE_LINE",
    "NO_ID_PATHS_LINE",
    "NO_PROJECT_ONE_MODEL_LINE",
    "NO_SBOM_TARGET",
    "NO_WHEEL_MATCH_LINE",
    "ONE_MODEL_LINE",
    "PROJECT_NOT_FOUND",
    "PROJECT_NOT_FOUND_LINE",
    "PROJECT_NOT_FOUND_MODEL_FILES",
    "REQUIRED_FRAGMENT_LINE",
    "SBOM_GRAPH_ELEMENT_LINE",
    "SBOM_GRAPH_NOT_LIST_LINE",
    "SBOM_INVALID",
    "SBOM_NOT_VALID_LINE",
    "SBOM_WRONG_FORMAT",
    "TARGET_AMBIGUOUS",
    "TARGET_WRONG_FORMAT",
    "input_not_found",
    "say_input_not_found",
    "warn_fragment_not_found",
]
