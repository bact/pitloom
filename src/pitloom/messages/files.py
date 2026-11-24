# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Files and size caps"
(``files`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism),
:mod:`pitloom.messages.text` (the page split from this one) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._field_tables import (
    CONFIG_USE,
    INPUT_USE,
    METADATA_USE,
    REGISTRY_USE,
    SBOM_USE,
)
from pitloom.messages._file_unreadable import (
    DIR_READ_LINE,
    DIR_UNLISTABLE,
    FILE_UNREADABLE,
    FILE_UNREADABLE_NOT_UTF8,
    FILE_UNREADABLE_OUTSIDE,
    FILE_UNREADABLE_OUTSIDE_REPOSITORY,
)
from pitloom.messages._file_unreadable_warning import (
    dir_unlistable_error,
    file_unreadable_error,
    file_unwritable_error,
    system_failure,
    warn_dir_unlistable,
    warn_file_unreadable,
)
from pitloom.messages._file_unwritable import (
    FILE_UNWRITABLE,
    FILE_UNWRITABLE_MODE,
    MODE_NOT_RESTORED_LINE,
    WRITE_ERROR_LINE,
    WRITE_LINE,
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

__all__ = [
    "CLONE_LINE",
    "CONFIG_MEMBER_LINE",
    "Cap",
    "DIR_READ_LINE",
    "DIR_UNLISTABLE",
    "DOWNLOAD_LINE",
    "FILE_UNREADABLE",
    "FILE_UNREADABLE_NOT_UTF8",
    "FILE_UNREADABLE_OUTSIDE",
    "FILE_UNREADABLE_OUTSIDE_REPOSITORY",
    "FILE_UNWRITABLE",
    "FILE_UNWRITABLE_MODE",
    "GIT_OUTPUT_LINE",
    "MODE_NOT_RESTORED_LINE",
    "OVER_CAP",
    "SAVE_FAILED_LINE",
    "SAVE_FAILED_WARNING_LINE",
    "CONFIG_USE",
    "INPUT_USE",
    "METADATA_USE",
    "REGISTRY_USE",
    "SBOM_USE",
    "SOURCE_LINE",
    "TEMP_DIR_UNUSABLE",
    "WRITE_ERROR_LINE",
    "WRITE_LINE",
    "dir_unlistable_error",
    "file_unreadable_error",
    "file_unwritable_error",
    "over_cap_of",
    "system_failure",
    "warn_archive_member_over_cap",
    "warn_dir_unlistable",
    "warn_file_unreadable",
    "warn_over_cap",
]
