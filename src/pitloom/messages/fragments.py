# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "SBOM fragments"
(``fragments`` in :data:`~pitloom.messages.TOPIC_TITLES`): their entries,
their lines, the summaries of the fragment commands and the helpers that
say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._field_writers import DescribedValue
from pitloom.messages._fragments import (
    DATETIME_MISSING,
    DIGEST_MISMATCH_LINE,
    FRAGMENT_DIGEST_INVALID,
    FRAGMENT_INVALID,
    FRAGMENT_MISSING,
    FRAGMENT_UNREADABLE,
    FRAGMENT_UNUSABLE,
    MERGE_PREFIX,
    MERGE_WILL_FAIL,
    NO_CREATED_LINE,
    NONE_MERGED_LINE,
    NOT_JSON_LINE,
    NOT_MERGED,
    NOT_SPDX_LINE,
    REFERENCE_LINE,
    REFERENCE_NOT_FOUND,
    REFERENCES_LINE,
    REQUIRED_MISSING_LINE,
    REQUIRED_NOT_JSON_LINE,
    REQUIRED_NOT_SPDX_LINE,
    REQUIRED_SAME_DOCUMENT_LINE,
    REQUIRED_UNREADABLE_LINE,
    SAME_DOCUMENT_LINE,
    UNREADABLE_LINE,
)
from pitloom.messages._fragments_merge import (
    ENRICH_REGISTER_HINT,
    ENTRY_CONFLICT_LINE,
    FRAGMENT_CONFLICT,
    FRAGMENT_HASH_CONFLICT,
    FRAGMENT_ID_CONFLICT,
    FRAGMENT_LIST_NONE,
    FRAGMENT_VALIDATE_VALID,
    GENERATED_REPLACED_LINE,
    GENERATED_VALUE_CONFLICT,
    HASH_CONFLICT_LINE,
    ID_OTHER_CONTENT_LINE,
    ID_OTHER_TYPE_LINE,
    MERGE_MERGED,
    MODEL_NAME_REPLACED_LINE,
    NOT_MEASURED_DROPPED_LINE,
    PROPERTY_CONFLICT_LINE,
)
from pitloom.messages._fragments_say import (
    READ_STAGES,
    SHOWN_FILES,
    FragmentReadError,
    missing_files_text,
    say_generated_value_replaced,
    say_model_name_replaced,
    say_not_measured_dropped,
    warn_fragment_unread,
    warn_hash_conflict,
    warn_id_conflict,
    warn_property_conflict,
    warn_reference_not_found,
    warn_same_document,
)
from pitloom.messages._loom_sdk import (
    DATASET_REFERENCE_LINE,
    REFERENCE_NOT_FOUND_DATASET,
)

__all__ = [
    "DATETIME_MISSING",
    "DIGEST_MISMATCH_LINE",
    "ENRICH_REGISTER_HINT",
    "ENTRY_CONFLICT_LINE",
    "FRAGMENT_CONFLICT",
    "FRAGMENT_DIGEST_INVALID",
    "FRAGMENT_HASH_CONFLICT",
    "FRAGMENT_ID_CONFLICT",
    "FRAGMENT_INVALID",
    "FRAGMENT_LIST_NONE",
    "FRAGMENT_MISSING",
    "FRAGMENT_UNREADABLE",
    "FRAGMENT_UNUSABLE",
    "FRAGMENT_VALIDATE_VALID",
    "GENERATED_REPLACED_LINE",
    "GENERATED_VALUE_CONFLICT",
    "HASH_CONFLICT_LINE",
    "ID_OTHER_CONTENT_LINE",
    "ID_OTHER_TYPE_LINE",
    "MERGE_MERGED",
    "MERGE_PREFIX",
    "MERGE_WILL_FAIL",
    "MODEL_NAME_REPLACED_LINE",
    "NONE_MERGED_LINE",
    "NO_CREATED_LINE",
    "NOT_JSON_LINE",
    "NOT_MEASURED_DROPPED_LINE",
    "NOT_MERGED",
    "NOT_SPDX_LINE",
    "PROPERTY_CONFLICT_LINE",
    "READ_STAGES",
    "REFERENCES_LINE",
    "REFERENCE_LINE",
    "REFERENCE_NOT_FOUND",
    "REFERENCE_NOT_FOUND_DATASET",
    "DATASET_REFERENCE_LINE",
    "REQUIRED_MISSING_LINE",
    "REQUIRED_NOT_JSON_LINE",
    "REQUIRED_NOT_SPDX_LINE",
    "REQUIRED_SAME_DOCUMENT_LINE",
    "REQUIRED_UNREADABLE_LINE",
    "SAME_DOCUMENT_LINE",
    "SHOWN_FILES",
    "UNREADABLE_LINE",
    "DescribedValue",
    "FragmentReadError",
    "missing_files_text",
    "say_generated_value_replaced",
    "say_model_name_replaced",
    "say_not_measured_dropped",
    "warn_fragment_unread",
    "warn_hash_conflict",
    "warn_id_conflict",
    "warn_property_conflict",
    "warn_reference_not_found",
    "warn_same_document",
]
