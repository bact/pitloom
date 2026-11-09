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
:mod:`pitloom.core.quote_source`, :mod:`pitloom.core.internal_error`,
:mod:`pitloom.core.path_probe` and :mod:`pitloom.core.path_confine`, none of
which imports it.
"""

from __future__ import annotations

from pitloom.messages._card_malformed import CARD_MALFORMED
from pitloom.messages._catalogue import MESSAGES
from pitloom.messages._config_unsafe import CONFIG_UNSAFE, CONFIG_UNSAFE_BUILD_CODE
from pitloom.messages._emit import (
    CodedFileNotFoundError,
    CodedImportError,
    CodedValueError,
    code_extra_of,
    code_of,
    emit,
    relay_extra,
)
from pitloom.messages._field_writers import size_text
from pitloom.messages._fields import CARD_KINDS, FIELDS, READ_USES, Field
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
from pitloom.messages._frames import FRAMES, HANDLER_FRAMES, RELAY_FRAME, Frame
from pitloom.messages._input_not_found import (
    GIT_FILE_IS_LINK_LINE,
    GIT_FILE_NOT_FOUND_LINE,
    GIT_FOLDER_NOT_FOUND_LINE,
    INPUT_NOT_FOUND,
    MODEL_FILE_NOT_FOUND_LINE,
)
from pitloom.messages._json_malformed import (
    JSON_MALFORMED,
    NOT_JSON_LINE,
    NOT_OBJECT_LINE,
)
from pitloom.messages._lfs_pointer import (
    LFS_CLONE_ERROR_LINE,
    LFS_CLONE_LINE,
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
    LFS_PULL_ERROR_LINE,
    LFS_PULL_LINE,
)
from pitloom.messages._lines import LINE_RE, LONGEST_LINE, says, trusted_message
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
    LIBRARY_UNUSABLE,
    LIBRARY_UNUSABLE_CONTENT_LINE,
    MODEL_UNREADABLE,
    MODEL_WRONG_FORMAT,
    NOT_A_MODEL_LINE,
    PARAMETER_COUNT_INVALID,
    PARAMETER_COUNT_SKIPPED,
    READER_UNSAFE,
    READER_UNSAFE_REMOTE,
    STATED_COUNT_REASON,
)
from pitloom.messages._over_cap import (
    CLONE_LINE,
    CONFIG_MEMBER_LINE,
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
from pitloom.messages._sbom_target import (
    MODEL_AMBIGUOUS,
    MODEL_AMBIGUOUS_OVER_CAP,
    MODEL_FILES_LINE,
    NAMED_NOT_A_MODEL_LINE,
    NO_PROJECT_ONE_MODEL_LINE,
    NO_SBOM_TARGET,
    ONE_MODEL_LINE,
    PROJECT_NOT_FOUND,
    PROJECT_NOT_FOUND_LINE,
    PROJECT_NOT_FOUND_MODEL_FILES,
    TARGET_AMBIGUOUS,
)
from pitloom.messages._text_malformed import TEXT_MALFORMED
from pitloom.messages._text_malformed_warning import warn_lone_surrogates
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
from pitloom.messages._usage_unparseable import (
    USAGE_UNPARSEABLE,
    USAGE_UNPARSEABLE_MENTION,
)
from pitloom.messages._usage_unusable import USAGE_UNUSABLE

__all__ = [
    "ACTORS",
    "ACTOR_HEADINGS",
    "ATTRIBUTE_LINE",
    "CARD_KINDS",
    "CARD_MALFORMED",
    "CLONE_LINE",
    "CODE_GRAMMAR",
    "CONDITIONS",
    "CONFIG_KEPT_LINE",
    "CONFIG_UNSAFE",
    "CONFIG_UNSAFE_BUILD_CODE",
    "KERAS_MEMBER_LINE",
    "CONFIG_MEMBER_LINE",
    "CONFIG_RAW_CUT_LINE",
    "CONFIG_RAW_LINE",
    "Cap",
    "CodedFileNotFoundError",
    "CodedImportError",
    "CodedValueError",
    "DIMENSION_REASON",
    "DIR_UNLISTABLE",
    "EFFECTS",
    "EFFECT_MEANINGS",
    "EMPTY_LINE",
    "FASTTEXT_ARGS_LINE",
    "FASTTEXT_LABELS_LINE",
    "FICKLING_PARSE_LINE",
    "FICKLING_WALK_LINE",
    "FIELDS",
    "FIELD_NOT_RECORDABLE",
    "FILE_UNREADABLE",
    "FILE_UNREADABLE_NOT_UTF8",
    "FILE_UNREADABLE_OUTSIDE",
    "FILE_UNREADABLE_OUTSIDE_REPOSITORY",
    "FRAMES",
    "Field",
    "Frame",
    "GGUF_LENGTH_LINE",
    "GIT_FILE_IS_LINK_LINE",
    "GIT_FILE_NOT_FOUND_LINE",
    "GIT_FOLDER_NOT_FOUND_LINE",
    "GIT_OUTPUT_LINE",
    "HANDLER_FRAMES",
    "HYPERPARAMETER_CONFLICT",
    "INPUT_NOT_FOUND",
    "JSON_MALFORMED",
    "LEVELS",
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
    "LINE_RE",
    "LONGEST_CODE",
    "LONGEST_LINE",
    "Line",
    "MESSAGES",
    "MODEL_FIELD_CONFLICT",
    "MODEL_AMBIGUOUS",
    "MODEL_AMBIGUOUS_OVER_CAP",
    "MODEL_FIELD_UNREADABLE",
    "MODEL_FILE_NOT_FOUND_LINE",
    "MODEL_FILES_LINE",
    "MODEL_LIMIT_REASONS",
    "MODEL_UNREADABLE",
    "MODEL_WRONG_FORMAT",
    "Message",
    "NAMED_NOT_A_MODEL_LINE",
    "NOT_A_MODEL_LINE",
    "NO_PROJECT_ONE_MODEL_LINE",
    "NO_SBOM_TARGET",
    "NOT_JSON_LINE",
    "NOT_OBJECT_LINE",
    "ONE_MODEL_LINE",
    "ONNX_REPEATED_LINE",
    "OVER_CAP",
    "PARAMETER_COUNT_INVALID",
    "PARAMETER_COUNT_SKIPPED",
    "PICKLE_MEMBER_LINE",
    "PROJECT_NOT_FOUND",
    "PROJECT_NOT_FOUND_LINE",
    "PROJECT_NOT_FOUND_MODEL_FILES",
    "PT2_EXTRA_LINE",
    "PT2_GRAPH_LINE",
    "PT2_META_LINE",
    "PT2_TAGS_LINE",
    "PT2_VERSION_LINE",
    "READER_UNSAFE",
    "READER_UNSAFE_REMOTE",
    "READ_USES",
    "RELAY_FRAME",
    "RESERVED_FAMILIES",
    "SOURCE_LINE",
    "STATED_COUNT_REASON",
    "TARGET_AMBIGUOUS",
    "TEXT_MALFORMED",
    "TRAINING_CONFIG_LINE",
    "USAGE_UNPARSEABLE",
    "USAGE_UNPARSEABLE_MENTION",
    "USAGE_UNUSABLE",
    "code_extra_of",
    "code_of",
    "emit",
    "file_unreadable_error",
    "over_cap_of",
    "relay_extra",
    "says",
    "size_text",
    "trusted_message",
    "warn_archive_member_over_cap",
    "warn_dir_unlistable",
    "warn_file_unreadable",
    "warn_lone_surrogates",
    "warn_over_cap",
]
