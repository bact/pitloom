# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The message catalogue: the contract between Pitloom and whoever reads its
output (a person, a script, an agent skill).

A catalogued message has a stable code, printed after its text as
`` [code]`` (``WARNING: FILE=m.bin: Git LFS pointer, content not read; run
'git lfs pull' for the content [lfs-pointer]``). The code travels on the log
record as its ``pitloom_code`` attribute
(:data:`~pitloom.logging_config.CODE_ATTR`), which a library user's own
handler can read, and on an exception of any class as an attribute of the
same name (:class:`CodedValueError` sets it, :func:`code_of` reads it back).
A line without a code is not catalogued yet.

Trust a code read back from a line only through :func:`trusted_message`:
the code must be catalogued and the text must match one of the entry's
patterns, since a line can end in an interpolated value.

This package imports only :mod:`pitloom.logging_config`, which never
imports it.
"""

from __future__ import annotations

from pitloom.messages._catalogue import MESSAGES
from pitloom.messages._emit import (
    CodedValueError,
    code_extra,
    code_extra_of,
    code_of,
    emit,
)
from pitloom.messages._lfs_pointer import (
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
)
from pitloom.messages._lines import LINE_RE, trusted_message
from pitloom.messages._types import (
    CODE_GRAMMAR,
    CONDITIONS,
    LEVELS,
    LONGEST_CODE,
    RESERVED_FAMILIES,
    Message,
)

__all__ = [
    "CODE_GRAMMAR",
    "CONDITIONS",
    "LEVELS",
    "LFS_POINTER",
    "LFS_POINTER_MALFORMED",
    "LFS_POINTER_SHIPPED",
    "LINE_RE",
    "LONGEST_CODE",
    "MESSAGES",
    "RESERVED_FAMILIES",
    "CodedValueError",
    "Message",
    "code_extra",
    "code_extra_of",
    "code_of",
    "emit",
    "trusted_message",
]
