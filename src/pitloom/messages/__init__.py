# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The message catalogue: the contract between Pitloom and whoever reads its
output (a person, a script, an agent skill).

A catalogued message has a stable code, printed after its text as
`` [code]`` (``WARNING: FILE=m.bin: Git LFS pointer, content not read; run
'git lfs pull' for the content [lfs-pointer]``). The catalogue owns the
text: each :class:`Message` lists the :class:`Line` shapes it is printed in,
each value a named field (``%(file)s``), and :func:`emit`,
:class:`CodedValueError` and :class:`CodedImportError` write the line from
the caller's values. The code
travels on the log record as its ``pitloom_code`` attribute
(:data:`~pitloom.logging_config.CODE_ATTR`), which a library user's own
handler can read, and on an exception of any class as an attribute of the
same name (:func:`code_of` reads it back). A line without a code is not
catalogued yet.

Trust a code read back from a line only through :func:`trusted_message`:
the code must be catalogued and the text one of the entry's lines at that
level, after at most one frame (:data:`FRAMES`), since another program can
print anything on the same stream.

This package imports only :mod:`pitloom.logging_config`,
:mod:`pitloom.core.quote_source` and :mod:`pitloom.core.internal_error`,
none of which imports it.
"""

from __future__ import annotations

from pitloom.messages._catalogue import MESSAGES
from pitloom.messages._emit import (
    CodedImportError,
    CodedValueError,
    code_extra_of,
    code_of,
    emit,
    relay_extra,
)
from pitloom.messages._fields import FIELDS, Field, size_text
from pitloom.messages._frames import FRAMES, HANDLER_FRAMES, RELAY_FRAME, Frame
from pitloom.messages._lfs_pointer import (
    LFS_CLONE_LINE,
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
    LFS_PULL_LINE,
)
from pitloom.messages._lines import LINE_RE, LONGEST_LINE, says, trusted_message
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
    DIMENSION_REASON,
    EMPTY_LINE,
    HYPERPARAMETER_CONFLICT,
    LIBRARY_MISSING,
    MODEL_UNREADABLE,
    MODEL_WRONG_FORMAT,
    NOT_A_MODEL_LINE,
    PARAMETER_COUNT_INVALID,
    PARAMETER_COUNT_SKIPPED,
    READER_UNSAFE,
    STATED_COUNT_REASON,
)
from pitloom.messages._over_cap import (
    CLONE_LINE,
    CONFIG_MEMBER_LINE,
    GIT_OUTPUT_LINE,
    OVER_CAP,
    Cap,
)
from pitloom.messages._over_cap_warning import over_cap_of, warn_over_cap
from pitloom.messages._types import (
    ACTOR_HEADINGS,
    ACTORS,
    CODE_GRAMMAR,
    CONDITIONS,
    EFFECT_MEANINGS,
    EFFECTS,
    LEVELS,
    LONGEST_CODE,
    RESERVED_FAMILIES,
    Line,
    Message,
)

__all__ = [
    "ACTORS",
    "ACTOR_HEADINGS",
    "CLONE_LINE",
    "CODE_GRAMMAR",
    "CONDITIONS",
    "CONFIG_MEMBER_LINE",
    "DIMENSION_REASON",
    "EFFECTS",
    "EFFECT_MEANINGS",
    "EMPTY_LINE",
    "FIELDS",
    "FRAMES",
    "GIT_OUTPUT_LINE",
    "HANDLER_FRAMES",
    "HYPERPARAMETER_CONFLICT",
    "LEVELS",
    "LFS_CLONE_LINE",
    "LFS_POINTER",
    "LFS_POINTER_MALFORMED",
    "LFS_POINTER_SHIPPED",
    "LFS_PULL_LINE",
    "LIBRARY_MISSING",
    "LIMIT_GGUF_ARRAY",
    "LIMIT_GGUF_PAIRS",
    "LIMIT_GGUF_TENSORS",
    "LIMIT_GGUF_VERSION",
    "LIMIT_ZIP_MALFORMED",
    "LIMIT_ZIP_UNCHECKABLE",
    "LINE_RE",
    "LONGEST_CODE",
    "LONGEST_LINE",
    "MESSAGES",
    "MODEL_LIMIT_REASONS",
    "MODEL_UNREADABLE",
    "MODEL_WRONG_FORMAT",
    "NOT_A_MODEL_LINE",
    "OVER_CAP",
    "PARAMETER_COUNT_INVALID",
    "PARAMETER_COUNT_SKIPPED",
    "READER_UNSAFE",
    "RELAY_FRAME",
    "RESERVED_FAMILIES",
    "STATED_COUNT_REASON",
    "Cap",
    "CodedImportError",
    "CodedValueError",
    "Field",
    "Frame",
    "Line",
    "Message",
    "code_extra_of",
    "code_of",
    "emit",
    "over_cap_of",
    "relay_extra",
    "says",
    "size_text",
    "trusted_message",
    "warn_over_cap",
]
