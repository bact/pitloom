# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Git URLs"
(``git`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the git command echo.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._git import (
    GIT_COMMAND,
    GIT_EMPTY_LINE,
    GIT_FAILED_LINE,
    GIT_MISSING,
    GIT_MISSING_LINE,
    GIT_REF_NOT_FOUND,
    GIT_REF_NOT_FOUND_LINE,
    GIT_REPOSITORY_EMPTY,
    GIT_REPOSITORY_UNUSABLE,
    GIT_URL_INVALID,
    GIT_URL_PATH_LINE,
    GIT_URL_PORT_LINE,
    GIT_URL_SCHEME_LINE,
)
from pitloom.messages._git_decisions import (
    GIT_FILTER_UNUSABLE,
    GIT_LINK_UNSAFE,
    GIT_REDIRECT_UNUSABLE,
)

__all__ = [
    "GIT_COMMAND",
    "GIT_EMPTY_LINE",
    "GIT_FAILED_LINE",
    "GIT_FILTER_UNUSABLE",
    "GIT_LINK_UNSAFE",
    "GIT_MISSING",
    "GIT_MISSING_LINE",
    "GIT_REDIRECT_UNUSABLE",
    "GIT_REF_NOT_FOUND",
    "GIT_REF_NOT_FOUND_LINE",
    "GIT_REPOSITORY_EMPTY",
    "GIT_REPOSITORY_UNUSABLE",
    "GIT_URL_INVALID",
    "GIT_URL_PATH_LINE",
    "GIT_URL_PORT_LINE",
    "GIT_URL_SCHEME_LINE",
]
