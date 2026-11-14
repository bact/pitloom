# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Model fields"
(``model-fields`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._model_field import (
    ATTRIBUTE_LINE,
    CONFIG_KEPT_LINE,
    CONFIG_RAW_CUT_LINE,
    CONFIG_RAW_LINE,
    FASTTEXT_ARGS_LINE,
    FASTTEXT_LABELS_LINE,
    FICKLING_PARSE_LINE,
    FICKLING_WALK_LINE,
    FIELD_NOT_RECORDABLE,
    GGUF_LENGTH_LINE,
    KERAS_MEMBER_LINE,
    MODEL_FIELD_CONFLICT,
    MODEL_FIELD_UNREADABLE,
    ONNX_REPEATED_LINE,
    PICKLE_MEMBER_LINE,
    PT2_EXTRA_LINE,
    PT2_GRAPH_LINE,
    PT2_META_LINE,
    PT2_TAGS_LINE,
    PT2_VERSION_LINE,
    TRAINING_CONFIG_LINE,
)
from pitloom.messages._model_stub import (
    DIMENSION_REASON,
    HYPERPARAMETER_CONFLICT,
    PARAMETER_COUNT_INVALID,
    PARAMETER_COUNT_SKIPPED,
    STATED_COUNT_REASON,
)

__all__ = [
    "ATTRIBUTE_LINE",
    "CONFIG_KEPT_LINE",
    "CONFIG_RAW_CUT_LINE",
    "CONFIG_RAW_LINE",
    "DIMENSION_REASON",
    "FASTTEXT_ARGS_LINE",
    "FASTTEXT_LABELS_LINE",
    "FICKLING_PARSE_LINE",
    "FICKLING_WALK_LINE",
    "FIELD_NOT_RECORDABLE",
    "GGUF_LENGTH_LINE",
    "HYPERPARAMETER_CONFLICT",
    "KERAS_MEMBER_LINE",
    "MODEL_FIELD_CONFLICT",
    "MODEL_FIELD_UNREADABLE",
    "ONNX_REPEATED_LINE",
    "PARAMETER_COUNT_INVALID",
    "PARAMETER_COUNT_SKIPPED",
    "PICKLE_MEMBER_LINE",
    "PT2_EXTRA_LINE",
    "PT2_GRAPH_LINE",
    "PT2_META_LINE",
    "PT2_TAGS_LINE",
    "PT2_VERSION_LINE",
    "STATED_COUNT_REASON",
    "TRAINING_CONFIG_LINE",
]
