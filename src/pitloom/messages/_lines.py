# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reading a printed line back: its code, and whether to trust it.

Pitloom ends a line in `` [x]`` only when x is its code
(:mod:`pitloom.logging_config` escapes such an ending on any other line), but
another program writing to the same stream can print anything. So a code is
trusted only when it is catalogued and the text before it is one of that
entry's lines at that line's level: the line's template, each value of its
field's shape (a path in quotes, a 64-digit ``oid``), after at most one frame
of :data:`~pitloom.messages._frames.FRAMES` (:func:`trusted_message`).

See also: :mod:`pitloom.messages` (the catalogue).
"""

from __future__ import annotations

import functools
import re
from typing import Final

from pitloom.logging_config import CODE_PATTERN
from pitloom.messages._catalogue import MESSAGES
from pitloom.messages._fields import template_pattern
from pitloom.messages._frames import FRAMES
from pitloom.messages._types import Message

#: A printed line with a code: groups level, text and code.
LINE_RE: Final = re.compile(rf"^(ERROR|WARNING|INFO): (.*) \[({CODE_PATTERN})\]$")

#: The longest line :func:`trusted_message` reads back, in characters; a
#: longer one is never trusted. A hostile line naming two paths, a frame's and
#: a shape's, costs time in the square of its length: about a second at this
#: one, at worst.
LONGEST_LINE: Final = 65536


@functools.cache
def _text_re(message: Message, level: str) -> re.Pattern[str] | None:
    """The text of *message*'s lines at *level*, after at most one frame of
    that level; ``None`` when it has no line at *level*."""
    shapes = [
        template_pattern(ln.template) for ln in message.lines if ln.level == level
    ]
    if not shapes:
        return None
    frames = [template_pattern(f.template) for f in FRAMES if level in f.levels]
    head = f"(?:{'|'.join(frames)})?" if frames else ""
    return re.compile(f"{head}(?:{'|'.join(shapes)})")


def says(message: Message, level: str, text: str) -> bool:
    """Whether *text*, as printed between ``LEVEL: `` and the code, is one
    of *message*'s lines at *level* (``"WARNING"``), after at most one frame
    of that level."""
    regex = _text_re(message, level)
    return regex is not None and regex.fullmatch(text) is not None


def trusted_message(line: str) -> Message | None:
    """The catalogued message *line* (one printed line, no line ending)
    says, or ``None``: no code, an uncatalogued one, a text that is not
    one of the entry's lines at that level (:func:`says`), or a line longer
    than :data:`LONGEST_LINE`."""
    if len(line) > LONGEST_LINE:
        return None
    found = LINE_RE.fullmatch(line)
    if found is None:
        return None
    level, text, code = found.groups()
    message = MESSAGES.get(code)
    return message if message is not None and says(message, level, text) else None
