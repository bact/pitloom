# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Authors" (``authors`` in
:data:`~pitloom.messages.TOPIC_TITLES`): their entries, their lines and the
helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._authors import (
    ADDRESS_SPLIT_LINE,
    AUTHOR_AMBIGUOUS,
    AUTHOR_INVALID,
    DEPENDENCY_ADDRESS_SPLIT_LINE,
    DEPENDENCY_NAME_SPLIT_LINE,
    EMAIL_INVALID_COUNT_LINE,
    EMAIL_INVALID_LINE,
    NAME_INVALID_COUNT_LINE,
    NAME_INVALID_LINE,
    NAME_SPLIT_LINE,
    ONE_AUTHOR_LINE,
    PROJECT_UNREADABLE,
    PROJECT_UNREADABLE_LINE,
)
from pitloom.messages._authors_say import (
    note_one_author,
    warn_author_split,
    warn_dependency_split,
    warn_not_addresses,
    warn_project_unreadable,
)
from pitloom.messages._fields_authors import AUTHOR_KEYS, authors_text

__all__ = [
    "ADDRESS_SPLIT_LINE",
    "AUTHOR_AMBIGUOUS",
    "AUTHOR_INVALID",
    "AUTHOR_KEYS",
    "DEPENDENCY_ADDRESS_SPLIT_LINE",
    "DEPENDENCY_NAME_SPLIT_LINE",
    "EMAIL_INVALID_COUNT_LINE",
    "EMAIL_INVALID_LINE",
    "NAME_INVALID_COUNT_LINE",
    "NAME_INVALID_LINE",
    "NAME_SPLIT_LINE",
    "ONE_AUTHOR_LINE",
    "PROJECT_UNREADABLE",
    "PROJECT_UNREADABLE_LINE",
    "authors_text",
    "note_one_author",
    "warn_author_split",
    "warn_dependency_split",
    "warn_not_addresses",
    "warn_project_unreadable",
]
