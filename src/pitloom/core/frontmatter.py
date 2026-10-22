# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The YAML frontmatter of a model or dataset card: the one delimiter rule.

A card's frontmatter opens with a ``---`` line at the start of the text (a
byte order mark and blank lines before it are allowed, and the line may be
indented) and closes with the next ``---`` line indented the same. A
delimiter is a whole line (trailing spaces and tabs allowed, ``\\n`` or
``\\r\\n`` ending it, or the end of the text for the closing one):
``my---set``, ``---not`` and a ``-----`` rule are not.

See also: :mod:`pitloom.enrich.readme` and
:mod:`pitloom.extract.remote._card_description`, the two readers.
"""

from __future__ import annotations

import re

__all__ = ["opens_frontmatter", "split_frontmatter"]

_LEAD = r"\ufeff?(?:[ \t]*\r?\n)*"
_OPEN = re.compile(_LEAD + r"[ \t]*---[ \t]*\r?\n")
_FRONTMATTER = re.compile(
    _LEAD
    + r"(?P<indent>[ \t]*)---[ \t]*\r?\n"
    + r"(?P<block>.*?)^(?P=indent)---[ \t]*(?:\r?\n|\Z)(?P<rest>.*)",
    re.DOTALL | re.MULTILINE,
)


def opens_frontmatter(text: str) -> bool:
    """Whether *text* starts with a frontmatter opening line."""
    return _OPEN.match(text) is not None


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """The frontmatter block of *text* (between its delimiter lines, empty
    for an empty frontmatter) and the text after the closing delimiter;
    ``None`` when *text* does not open one or it is not closed."""
    match = _FRONTMATTER.match(text)
    return None if match is None else (match["block"], match["rest"])
