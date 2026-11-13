# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "AI models"
(``models`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._lfs_pointer import (
    LFS_CLONE_ERROR_LINE,
    LFS_CLONE_LINE,
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
    LFS_PULL_ERROR_LINE,
    LFS_PULL_LINE,
)
from pitloom.messages._model_limits import (
    LIMIT_GGUF_ARRAY,
    LIMIT_GGUF_PAIRS,
    LIMIT_GGUF_TENSORS,
    LIMIT_GGUF_VERSION,
    LIMIT_ZIP_MALFORMED,
    LIMIT_ZIP_UNCHECKABLE,
    MODEL_LIMIT_REASONS,
)
from pitloom.messages._model_stub import (
    EMPTY_LINE,
    LIBRARY_MISSING,
    LIBRARY_UNUSABLE,
    LIBRARY_UNUSABLE_CONTENT_LINE,
    MODEL_UNREADABLE,
    MODEL_WRONG_FORMAT,
    NOT_A_MODEL_LINE,
    READER_UNSAFE,
    READER_UNSAFE_PYPI_LINE,
    READER_UNSAFE_REMOTE,
    READER_UNSAFE_REMOTE_LINE,
)
from pitloom.messages._usage_unparseable import (
    USAGE_UNPARSEABLE,
    USAGE_UNPARSEABLE_MENTION,
)
from pitloom.messages._usage_unusable import (
    USAGE_UNUSABLE,
)

__all__ = [
    "EMPTY_LINE",
    "LFS_CLONE_ERROR_LINE",
    "LFS_CLONE_LINE",
    "LFS_POINTER",
    "LFS_POINTER_MALFORMED",
    "LFS_POINTER_SHIPPED",
    "LFS_PULL_ERROR_LINE",
    "LFS_PULL_LINE",
    "LIBRARY_MISSING",
    "LIBRARY_UNUSABLE",
    "LIBRARY_UNUSABLE_CONTENT_LINE",
    "LIMIT_GGUF_ARRAY",
    "LIMIT_GGUF_PAIRS",
    "LIMIT_GGUF_TENSORS",
    "LIMIT_GGUF_VERSION",
    "LIMIT_ZIP_MALFORMED",
    "LIMIT_ZIP_UNCHECKABLE",
    "MODEL_LIMIT_REASONS",
    "MODEL_UNREADABLE",
    "MODEL_WRONG_FORMAT",
    "NOT_A_MODEL_LINE",
    "READER_UNSAFE",
    "READER_UNSAFE_PYPI_LINE",
    "READER_UNSAFE_REMOTE",
    "READER_UNSAFE_REMOTE_LINE",
    "USAGE_UNPARSEABLE",
    "USAGE_UNPARSEABLE_MENTION",
    "USAGE_UNUSABLE",
]
