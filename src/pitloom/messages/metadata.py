# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Project metadata"
(``metadata`` in :data:`~pitloom.messages.TOPIC_TITLES`): their entries,
their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._field_tables import METADATA_USE
from pitloom.messages._metadata_dynamic import (
    CANDIDATES_LINE,
    DYNAMIC_FIELD_NEEDS_BUILD,
    DYNAMIC_FIELD_UNUSABLE,
    EMBED_PROJECT_LINE,
    FLIT_FAILED_LINE,
    INSTALLED_LINE,
    INSTALLED_METADATA_AMBIGUOUS,
    INSTALLED_METADATA_UNUSABLE,
    INSTALLED_NO_NAME_LINE,
    METADATA_CONFLICT,
    METADATA_NO_EFFECT,
    NO_MARKER_LINE,
    OTHER_NAME_LINE,
    PDM_FAILED_LINE,
    PDM_SOURCE_LINE,
    PIP_OPTIONS_LINE,
    POETRY_BACKEND_LINE,
    POETRY_TABLE_LINE,
    SDIST_DYNAMIC_LINE,
    SETUP_CFG_KEPT_LINE,
    SETUP_PY_KEPT_LINE,
)
from pitloom.messages._metadata_read import (
    DIRECTIVE_ATTR_LINE,
    DIRECTIVE_NOT_FILE_LINE,
    KEYWORD_BLANK_LINE,
    KEYWORD_NOT_LITERAL_LINE,
    KEYWORD_UNPACKED_LINE,
    KEYWORD_UNREAD_LINE,
    LISTED_NO_FILE_LINE,
    LISTED_NOT_FOUND_LINE,
    METADATA_INVALID,
    METADATA_MALFORMED,
    NESTED_LINE,
    NUMBER_LINE,
    POETRY_NAME_LINE,
    PROJECT_LINE,
    PROJECT_NAME_MISSING,
    PROJECT_NO_NAME_LINE,
    PYTHON_LINE,
    SETUP_CFG_NAME_LINE,
    SETUP_PY_NAME_LINE,
    SETUPTOOLS_NAME_LINE,
    TYPE_ERROR_LINE,
    TYPE_LINE,
)
from pitloom.messages._metadata_say import relay_coded_warning

__all__ = [
    "CANDIDATES_LINE",
    "DIRECTIVE_ATTR_LINE",
    "DIRECTIVE_NOT_FILE_LINE",
    "DYNAMIC_FIELD_NEEDS_BUILD",
    "DYNAMIC_FIELD_UNUSABLE",
    "FLIT_FAILED_LINE",
    "EMBED_PROJECT_LINE",
    "INSTALLED_LINE",
    "INSTALLED_METADATA_AMBIGUOUS",
    "INSTALLED_METADATA_UNUSABLE",
    "INSTALLED_NO_NAME_LINE",
    "KEYWORD_BLANK_LINE",
    "KEYWORD_NOT_LITERAL_LINE",
    "KEYWORD_UNPACKED_LINE",
    "KEYWORD_UNREAD_LINE",
    "LISTED_NOT_FOUND_LINE",
    "LISTED_NO_FILE_LINE",
    "METADATA_CONFLICT",
    "METADATA_INVALID",
    "METADATA_MALFORMED",
    "METADATA_NO_EFFECT",
    "METADATA_USE",
    "NESTED_LINE",
    "NO_MARKER_LINE",
    "NUMBER_LINE",
    "OTHER_NAME_LINE",
    "PDM_FAILED_LINE",
    "PDM_SOURCE_LINE",
    "PIP_OPTIONS_LINE",
    "POETRY_BACKEND_LINE",
    "POETRY_TABLE_LINE",
    "POETRY_NAME_LINE",
    "PROJECT_LINE",
    "PROJECT_NAME_MISSING",
    "PROJECT_NO_NAME_LINE",
    "PYTHON_LINE",
    "SDIST_DYNAMIC_LINE",
    "SETUPTOOLS_NAME_LINE",
    "SETUP_CFG_KEPT_LINE",
    "SETUP_CFG_NAME_LINE",
    "SETUP_PY_KEPT_LINE",
    "SETUP_PY_NAME_LINE",
    "TYPE_ERROR_LINE",
    "TYPE_LINE",
    "relay_coded_warning",
]
