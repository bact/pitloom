# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reading a printed line back: its code, and whether to trust it.

A line ending in `` [x]`` may end in a value Pitloom interpolated (a file
named ``x [lfs-pointer]``), so a code is trusted only when it is catalogued
and the text before it matches one of that entry's patterns
(:func:`trusted_message`).

See also: :mod:`pitloom.messages` (the catalogue).
"""

from __future__ import annotations

import functools
import re
from typing import Final

from pitloom.logging_config import CODE_PATTERN
from pitloom.messages._catalogue import MESSAGES
from pitloom.messages._types import Message

#: A printed line with a code: groups level, text and code.
LINE_RE: Final = re.compile(rf"^(ERROR|WARNING|INFO): (.*) \[({CODE_PATTERN})\]$")


@functools.cache
def _pattern_re(pattern: str) -> re.Pattern[str]:
    """*pattern* (``%s`` for a value) as a regular expression; an ``ERROR:``
    raised as an exception may follow a surface's ``<command> failed: ``,
    which a leading ``%s`` takes in."""
    return re.compile(".*".join(map(re.escape, pattern.split("%s"))))


def trusted_message(line: str) -> Message | None:
    """The catalogued message *line* (one printed line, no line ending)
    says, or ``None``: no code, an uncatalogued one, a level the entry is not
    said at, or a text none of the entry's patterns matches."""
    found = LINE_RE.fullmatch(line)
    if found is None:
        return None
    level, text, code = found.groups()
    message = MESSAGES.get(code)
    if message is None or level not in message.levels:
        return None
    if any(_pattern_re(p).fullmatch(text) for p in message.patterns):
        return message
    return None
