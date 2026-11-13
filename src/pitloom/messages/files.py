# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Files and text"
(``files`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._card_malformed import CARD_MALFORMED
from pitloom.messages._field_tables import SBOM_USE
from pitloom.messages._file_unreadable import (
    DIR_UNLISTABLE,
    FILE_UNREADABLE,
    FILE_UNREADABLE_NOT_UTF8,
    FILE_UNREADABLE_OUTSIDE,
    FILE_UNREADABLE_OUTSIDE_REPOSITORY,
)
from pitloom.messages._file_unreadable_warning import (
    file_unreadable_error,
    warn_dir_unlistable,
    warn_file_unreadable,
)
from pitloom.messages._json_malformed import (
    JSON_MALFORMED,
    NOT_JSON_LINE,
    NOT_OBJECT_LINE,
)
from pitloom.messages._over_cap import (
    CLONE_LINE,
    CONFIG_MEMBER_LINE,
    DOWNLOAD_LINE,
    GIT_OUTPUT_LINE,
    OVER_CAP,
    SOURCE_LINE,
    Cap,
)
from pitloom.messages._over_cap_warning import (
    over_cap_of,
    warn_archive_member_over_cap,
    warn_over_cap,
)
from pitloom.messages._remote_fetch import (
    SAVE_FAILED_LINE,
    SAVE_FAILED_WARNING_LINE,
    TEMP_DIR_UNUSABLE,
)
from pitloom.messages._text_malformed import TEXT_MALFORMED
from pitloom.messages._text_malformed_warning import warn_lone_surrogates

__all__ = [
    "CARD_MALFORMED",
    "CLONE_LINE",
    "CONFIG_MEMBER_LINE",
    "Cap",
    "DIR_UNLISTABLE",
    "DOWNLOAD_LINE",
    "FILE_UNREADABLE",
    "FILE_UNREADABLE_NOT_UTF8",
    "FILE_UNREADABLE_OUTSIDE",
    "FILE_UNREADABLE_OUTSIDE_REPOSITORY",
    "GIT_OUTPUT_LINE",
    "JSON_MALFORMED",
    "NOT_JSON_LINE",
    "NOT_OBJECT_LINE",
    "OVER_CAP",
    "SAVE_FAILED_LINE",
    "SAVE_FAILED_WARNING_LINE",
    "SBOM_USE",
    "SOURCE_LINE",
    "TEMP_DIR_UNUSABLE",
    "TEXT_MALFORMED",
    "file_unreadable_error",
    "over_cap_of",
    "warn_archive_member_over_cap",
    "warn_dir_unlistable",
    "warn_file_unreadable",
    "warn_lone_surrogates",
    "warn_over_cap",
]
