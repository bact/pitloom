# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "ID registry ids and keys"
(``id-registry-ids`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines, its summaries and the helpers that say them.

See also: :mod:`pitloom.messages.id_registry` (the registry file's own
errors) and :mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

import logging

from pitloom.messages._emit import emit
from pitloom.messages._field_tables import (
    KEY_IMPORT_NOT_FOUND,
    KEY_MODEL_PIN,
    KEY_NOT_A_FILE,
    KEY_NOT_FOUND,
    KEY_OUTSIDE_ROOT,
    KEY_PATH_OUTSIDE,
    KEY_PATH_OUTSIDE_ARCHIVE,
    KEY_PROJECT_OUTSIDE,
)
from pitloom.messages._registry_conflict import (
    ALIAS_TIE_LINE,
    CLAIM_LINE,
    CONCURRENT_LINE,
    DATASET_DIR_LINE,
    FILE_SET_LINE,
    GATE_DROPPED_LINE,
    GATE_KEPT_LINE,
    GATE_KEPT_OLDER_LINE,
    HASH_CHANGED_LINE,
    HASH_CHANGED_WARNING_LINE,
    HELD_LINE,
    MODEL_GATE_MISS_LINE,
    NAME_HELD_LINE,
    NFC_CLASH_LINE,
    REGISTRY_CONFLICT,
    REGISTRY_CONFLICT_CONCURRENT,
    REGISTRY_CONFLICT_FILE_SET,
    REGISTRY_CONFLICT_HELD,
    REGISTRY_CONFLICT_SPELLING,
    REGISTRY_CONFLICT_TYPE,
    REGISTRY_HASH_CONFLICT,
    REGISTRY_HASH_CONFLICT_GATE,
    REGISTRY_KEY_AMBIGUOUS,
    SPELLING_LINE,
    TYPE_LINE,
)
from pitloom.messages._registry_keys import (
    ALIAS_CHANGED_LINE,
    ALIAS_HITS_LINE,
    ALIAS_IMPORTED_LINE,
    ALIAS_PROMOTED_LINE,
    DATASET_PATH_KEY,
    ENTITY_BY_NAME_LINE,
    FALLBACK_KEYS_LINE,
    HASHLESS_PIN_LINE,
    IDENTITY_UNKNOWN_LINE,
    INDEX_PATH_NO_EFFECT,
    MODEL_FILE_ENTRY_KEY,
    MODEL_IMPORTED_BY_NAME_LINE,
    MODEL_NOT_RECORDED_LINE,
    NAME_KEY_LINE,
    NO_VERSION_LINE,
    NOT_FOUND_LINE,
    OUTSIDE_ROOT_LINE,
    PIN_GATED_LINE,
    PIN_WITHOUT_HASH_LINE,
    REGISTRY_ENTRY_MISSING,
    REGISTRY_HASH_MISSING,
    REGISTRY_IDENTITY_MISSING,
    REGISTRY_KEY_MOVED,
    REGISTRY_PATH_KEY_UNUSABLE,
    SKIPPED_PATH_LINE,
    UNGATED_LINE,
    UNHASHED_LINE,
)


def info_name_key(
    log: logging.Logger, element_kind: str, entity: str, key_reason: str
) -> None:
    """The one ``INFO:`` (``registry-path-key-unusable``) for a model or a
    dataset keyed by its name, *key_reason* saying why."""
    emit(
        log,
        REGISTRY_PATH_KEY_UNUSABLE,
        logging.INFO,
        line=NAME_KEY_LINE,
        element_kind=element_kind,
        entity=entity,
        key_reason=key_reason,
    )


__all__ = [
    "ALIAS_CHANGED_LINE",
    "ALIAS_HITS_LINE",
    "ALIAS_IMPORTED_LINE",
    "ALIAS_PROMOTED_LINE",
    "ALIAS_TIE_LINE",
    "CLAIM_LINE",
    "CONCURRENT_LINE",
    "DATASET_DIR_LINE",
    "DATASET_PATH_KEY",
    "ENTITY_BY_NAME_LINE",
    "FALLBACK_KEYS_LINE",
    "FILE_SET_LINE",
    "GATE_DROPPED_LINE",
    "GATE_KEPT_LINE",
    "GATE_KEPT_OLDER_LINE",
    "HASHLESS_PIN_LINE",
    "HASH_CHANGED_LINE",
    "HASH_CHANGED_WARNING_LINE",
    "HELD_LINE",
    "IDENTITY_UNKNOWN_LINE",
    "INDEX_PATH_NO_EFFECT",
    "KEY_IMPORT_NOT_FOUND",
    "KEY_MODEL_PIN",
    "KEY_NOT_A_FILE",
    "KEY_NOT_FOUND",
    "KEY_OUTSIDE_ROOT",
    "KEY_PATH_OUTSIDE",
    "KEY_PATH_OUTSIDE_ARCHIVE",
    "KEY_PROJECT_OUTSIDE",
    "MODEL_FILE_ENTRY_KEY",
    "MODEL_GATE_MISS_LINE",
    "MODEL_IMPORTED_BY_NAME_LINE",
    "MODEL_NOT_RECORDED_LINE",
    "NAME_HELD_LINE",
    "NAME_KEY_LINE",
    "NFC_CLASH_LINE",
    "NOT_FOUND_LINE",
    "NO_VERSION_LINE",
    "OUTSIDE_ROOT_LINE",
    "PIN_GATED_LINE",
    "PIN_WITHOUT_HASH_LINE",
    "REGISTRY_CONFLICT",
    "REGISTRY_CONFLICT_CONCURRENT",
    "REGISTRY_CONFLICT_FILE_SET",
    "REGISTRY_CONFLICT_HELD",
    "REGISTRY_CONFLICT_SPELLING",
    "REGISTRY_CONFLICT_TYPE",
    "REGISTRY_ENTRY_MISSING",
    "REGISTRY_HASH_CONFLICT",
    "REGISTRY_HASH_CONFLICT_GATE",
    "REGISTRY_HASH_MISSING",
    "REGISTRY_IDENTITY_MISSING",
    "REGISTRY_KEY_AMBIGUOUS",
    "REGISTRY_KEY_MOVED",
    "REGISTRY_PATH_KEY_UNUSABLE",
    "SKIPPED_PATH_LINE",
    "SPELLING_LINE",
    "TYPE_LINE",
    "UNGATED_LINE",
    "UNHASHED_LINE",
    "info_name_key",
]
