# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Text and documents"
(``text`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism),
:mod:`pitloom.messages.files` (the page split from this one) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._card_malformed import CARD_MALFORMED
from pitloom.messages._json_malformed import (
    BOM_DROPPED_LINE,
    JSON_MALFORMED,
    JSON_MALFORMED_BOM,
    NOT_JSON_LINE,
    NOT_OBJECT_LINE,
)
from pitloom.messages._text_malformed import (
    TEXT_MALFORMED,
    TEXT_MALFORMED_REGISTRY,
)
from pitloom.messages._text_malformed_warning import (
    registry_name_error,
    warn_element_surrogates,
    warn_license_surrogates,
    warn_lone_surrogates,
    warn_registry_file_name,
    warn_registry_name_skipped,
)
from pitloom.messages._text_unsafe import (
    DATASET_TEXT_LINE,
    MODEL_TEXT_LINE,
    TEXT_UNSAFE,
)
from pitloom.messages._text_unsafe_say import warn_text_unsafe

__all__ = [
    "BOM_DROPPED_LINE",
    "CARD_MALFORMED",
    "DATASET_TEXT_LINE",
    "JSON_MALFORMED",
    "JSON_MALFORMED_BOM",
    "MODEL_TEXT_LINE",
    "NOT_JSON_LINE",
    "NOT_OBJECT_LINE",
    "TEXT_MALFORMED",
    "TEXT_MALFORMED_REGISTRY",
    "TEXT_UNSAFE",
    "registry_name_error",
    "warn_element_surrogates",
    "warn_license_surrogates",
    "warn_lone_surrogates",
    "warn_registry_file_name",
    "warn_registry_name_skipped",
    "warn_text_unsafe",
]
