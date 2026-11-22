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
:mod:`~pitloom.messages.config`, :mod:`~pitloom.messages.metadata`,
:mod:`~pitloom.messages.file_discovery`, :mod:`~pitloom.messages.build`,
:mod:`~pitloom.messages.models`, :mod:`~pitloom.messages.model_fields`,
:mod:`~pitloom.messages.files`, :mod:`~pitloom.messages.pypi`,
:mod:`~pitloom.messages.network`, :mod:`~pitloom.messages.git`,
:mod:`~pitloom.messages.id_registry`,
:mod:`~pitloom.messages.id_registry_ids` and :mod:`~pitloom.messages.licences`.
A :class:`Summary` (:func:`say_summary`) is an ``INFO:`` line with no
condition, so no code.

This package imports only :mod:`pitloom.logging_config`,
:mod:`pitloom.core.quote_source`, :mod:`pitloom.core.internal_error`,
:mod:`pitloom.core.path_probe` and :mod:`pitloom.core.path_confine`, none of
which imports it.
"""

from __future__ import annotations

from pitloom.messages._catalogue import MESSAGES, SUMMARIES
from pitloom.messages._emit import (
    CodedFileNotFoundError,
    CodedImportError,
    CodedValueError,
    code_extra_of,
    code_of,
    emit,
    recoded,
    relay_extra,
)
from pitloom.messages._field_tables import (
    CARD_KINDS,
    CONFIG_TABLES,
    INPUT_KINDS,
    LOOM_COMMANDS,
    READ_USES,
    REF_KINDS,
)
from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import size_text
from pitloom.messages._fields import FIELDS
from pitloom.messages._frames import (
    BUILD_FRAME,
    BUILD_PREFIX,
    COMMAND_FRAME,
    FRAMES,
    GIT_FRAME,
    GIT_PREFIX,
    HF_FRAME,
    HOOK_FRAME,
    HOOK_PREFIX,
    HOOK_STEP_FRAME,
    PYPI_FRAME,
    RELAY_FRAME,
    SCAN_FRAME,
    TOP_FRAME,
    Frame,
)
from pitloom.messages._lines import LINE_RE, LONGEST_LINE, says, trusted_message
from pitloom.messages._summary import Summary, say_summary
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
    "BUILD_FRAME",
    "BUILD_PREFIX",
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
    "GIT_FRAME",
    "GIT_PREFIX",
    "HF_FRAME",
    "HOOK_FRAME",
    "HOOK_PREFIX",
    "HOOK_STEP_FRAME",
    "INPUT_KINDS",
    "LEVELS",
    "LINE_RE",
    "LONGEST_CODE",
    "LONGEST_LINE",
    "LOOM_COMMANDS",
    "MESSAGES",
    "PYPI_FRAME",
    "READ_USES",
    "REF_KINDS",
    "RELAY_FRAME",
    "RESERVED_FAMILIES",
    "SCAN_FRAME",
    "SUMMARIES",
    "TOPIC_TITLES",
    "TOP_FRAME",
    "CodedFileNotFoundError",
    "CodedImportError",
    "CodedValueError",
    "Field",
    "Frame",
    "Line",
    "Message",
    "Summary",
    "code_extra_of",
    "code_of",
    "emit",
    "recoded",
    "relay_extra",
    "say_summary",
    "says",
    "size_text",
    "topic_of",
    "trusted_message",
]
