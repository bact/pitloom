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
the caller's values. The code travels on the log record as its
``pitloom_code`` attribute (:data:`~pitloom.logging_config.CODE_ATTR`),
which a library user's own handler can read, and on an exception of any
class as an attribute of the same name (:func:`code_of` reads it back). A
line without a code is not catalogued yet.

Trust a code read back from a line only through :func:`trusted_message`:
the code must be catalogued and the text one of the entry's lines at that
level, after at most one frame (:data:`FRAMES`), since another program can
print anything on the same stream.

This module holds the mechanism only. The entries, their lines and the
helpers that say them are in one public module per page of the generated
reference (:data:`TOPIC_TITLES`, a hyphen spelt ``_``):
:mod:`pitloom.messages.targets`, :mod:`~pitloom.messages.options`,
:mod:`~pitloom.messages.models`, :mod:`~pitloom.messages.model_fields`,
:mod:`~pitloom.messages.files`, :mod:`~pitloom.messages.pypi`,
:mod:`~pitloom.messages.network` and :mod:`~pitloom.messages.licences`.

This package imports only :mod:`pitloom.logging_config`,
:mod:`pitloom.core.quote_source`, :mod:`pitloom.core.internal_error`,
:mod:`pitloom.core.path_probe` and :mod:`pitloom.core.path_confine`, none of
which imports it.
"""

from __future__ import annotations

from pitloom.messages._catalogue import MESSAGES
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
from pitloom.messages._fields import (
    CARD_KINDS,
    CONFIG_TABLES,
    FIELDS,
    INPUT_KINDS,
    LOOM_COMMANDS,
    READ_USES,
    Field,
)
from pitloom.messages._frames import (
    COMMAND_FRAME,
    FRAMES,
    HOOK_FRAME,
    RELAY_FRAME,
    TOP_FRAME,
    Frame,
)
from pitloom.messages._lines import LINE_RE, LONGEST_LINE, says, trusted_message
from pitloom.messages._topics import FAMILY_TOPICS, TOPIC_TITLES, topic_of
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
    "CARD_KINDS",
    "CODE_GRAMMAR",
    "COMMAND_FRAME",
    "CONDITIONS",
    "CONFIG_TABLES",
    "EFFECTS",
    "EFFECT_MEANINGS",
    "FAMILY_TOPICS",
    "FIELDS",
    "FRAMES",
    "HOOK_FRAME",
    "INPUT_KINDS",
    "LEVELS",
    "LINE_RE",
    "LONGEST_CODE",
    "LONGEST_LINE",
    "LOOM_COMMANDS",
    "MESSAGES",
    "READ_USES",
    "RELAY_FRAME",
    "RESERVED_FAMILIES",
    "TOPIC_TITLES",
    "TOP_FRAME",
    "CodedFileNotFoundError",
    "CodedImportError",
    "CodedValueError",
    "Field",
    "Frame",
    "Line",
    "Message",
    "code_extra_of",
    "code_of",
    "emit",
    "relay_extra",
    "says",
    "size_text",
    "topic_of",
    "trusted_message",
]
