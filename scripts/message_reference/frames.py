# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The frames a code's section of the message reference names: each frame
of a ``WARNING`` or ``INFO`` line that may come before the code's lines
(:meth:`pitloom.messages.Frame.allows`), so a reader knows the prefix is
not part of the line. An ``ERROR``-only frame comes before every code's
error and is listed once, in the index's table of prefixes.

See also: ``scripts/generate_message_reference.py`` (which writes the
sections).
"""

from __future__ import annotations

from collections.abc import Sequence

from pitloom.messages import FRAMES, Message


def frame_notes(message: Message, level_order: Sequence[str]) -> list[str]:
    """One sentence per frame that names its codes and allows *message*'s
    code at one of its levels, the levels in *level_order*."""
    notes: list[str] = []
    for frame in FRAMES:
        if frame.codes is None:
            continue
        levels = [
            lv
            for lv in level_order
            if lv in message.levels and frame.allows(message.code, lv)
        ]
        if levels:
            notes.append(
                f"`{frame.shown}<text>` ({frame.surface}), on its "
                f"{' and '.join(levels)} lines; the prefix is not part of the line."
            )
    return notes
