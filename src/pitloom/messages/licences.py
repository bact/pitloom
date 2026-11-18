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

from pitloom.messages._license_db import (
    DB_MISSING_INFO_LINE,
    DB_MISSING_LINE,
    DB_UNUSABLE_LINE,
    LICENSE_DB_MISSING,
    LICENSE_DB_UNUSABLE,
)
from pitloom.messages._license_expression import (
    AMBIGUOUS_LINE,
    CONFLICT_LINE,
    INVALID_FIELD_LINE,
    INVALID_LINE,
    LICENSE_AMBIGUOUS,
    LICENSE_CONFLICT,
    LICENSE_EXPRESSION_INVALID,
    LICENSE_EXPRESSION_MALFORMED,
    LICENSE_EXPRESSION_RESOLVED,
    MALFORMED_FIELD_LINE,
    MALFORMED_LINE,
    RESOLVED_FIELD_LINE,
    RESOLVED_LINE,
)
from pitloom.messages._license_relationship_invalid import (
    LICENSE_RELATIONSHIP_ERROR_LINE,
    LICENSE_RELATIONSHIP_FROM_LINE,
    LICENSE_RELATIONSHIP_INVALID,
    LICENSE_RELATIONSHIP_TO_LINE,
)
from pitloom.messages._license_say import (
    say_license_db_missing,
    say_license_resolved,
    warn_license_db_unusable,
    warn_license_refused,
)

__all__ = [
    "AMBIGUOUS_LINE",
    "CONFLICT_LINE",
    "DB_MISSING_INFO_LINE",
    "DB_MISSING_LINE",
    "DB_UNUSABLE_LINE",
    "INVALID_FIELD_LINE",
    "INVALID_LINE",
    "LICENSE_AMBIGUOUS",
    "LICENSE_CONFLICT",
    "LICENSE_DB_MISSING",
    "LICENSE_DB_UNUSABLE",
    "LICENSE_EXPRESSION_INVALID",
    "LICENSE_EXPRESSION_MALFORMED",
    "LICENSE_EXPRESSION_RESOLVED",
    "LICENSE_RELATIONSHIP_ERROR_LINE",
    "LICENSE_RELATIONSHIP_FROM_LINE",
    "LICENSE_RELATIONSHIP_INVALID",
    "LICENSE_RELATIONSHIP_TO_LINE",
    "MALFORMED_FIELD_LINE",
    "MALFORMED_LINE",
    "RESOLVED_FIELD_LINE",
    "RESOLVED_LINE",
    "say_license_db_missing",
    "say_license_resolved",
    "warn_license_db_unusable",
    "warn_license_refused",
]
