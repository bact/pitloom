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
each value a named field (``%(file)s``), and :func:`emit` and
:class:`CodedValueError` write the line from the caller's values. The code
travels on the log record as its ``pitloom_code`` attribute
(:data:`~pitloom.logging_config.CODE_ATTR`), which a library user's own
handler can read, and on an exception of any class as an attribute of the
same name (:func:`code_of` reads it back). A line without a code is not
catalogued yet.

Trust a code read back from a line only through :func:`trusted_message`:
the code must be catalogued and the text one of the entry's lines at that
level, after at most one frame (:data:`FRAMES`), since another program can
print anything on the same stream.

This package imports only :mod:`pitloom.logging_config` (and, when it
writes a quoted path, :mod:`pitloom.core.quote_source`), neither of which
imports it.
"""

from __future__ import annotations

from pitloom.messages._catalogue import MESSAGES
from pitloom.messages._emit import CodedValueError, code_extra_of, code_of, emit
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
from pitloom.messages._types import (
    ACTORS,
    CODE_GRAMMAR,
    CONDITIONS,
    EFFECTS,
    LEVELS,
    LONGEST_CODE,
    RESERVED_FAMILIES,
    Line,
    Message,
)

__all__ = [
    "ACTORS",
    "CODE_GRAMMAR",
    "CONDITIONS",
    "EFFECTS",
    "FIELDS",
    "FRAMES",
    "HANDLER_FRAMES",
    "LEVELS",
    "LFS_CLONE_LINE",
    "LFS_POINTER",
    "LFS_POINTER_MALFORMED",
    "LFS_POINTER_SHIPPED",
    "LFS_PULL_LINE",
    "LINE_RE",
    "LONGEST_CODE",
    "LONGEST_LINE",
    "MESSAGES",
    "RELAY_FRAME",
    "RESERVED_FAMILIES",
    "CodedValueError",
    "Field",
    "Frame",
    "Line",
    "Message",
    "code_extra_of",
    "code_of",
    "emit",
    "says",
    "size_text",
    "trusted_message",
]
