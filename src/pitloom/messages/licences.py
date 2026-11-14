# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Licences"
(``licences`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._license_relationship_invalid import (
    LICENSE_RELATIONSHIP_ERROR_LINE,
    LICENSE_RELATIONSHIP_FROM_LINE,
    LICENSE_RELATIONSHIP_INVALID,
    LICENSE_RELATIONSHIP_TO_LINE,
)

__all__ = [
    "LICENSE_RELATIONSHIP_ERROR_LINE",
    "LICENSE_RELATIONSHIP_FROM_LINE",
    "LICENSE_RELATIONSHIP_INVALID",
    "LICENSE_RELATIONSHIP_TO_LINE",
]
