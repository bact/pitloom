# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The description of a Hugging Face model or dataset card: its first prose
paragraph after the YAML front matter, at most :data:`MAX_DESCRIPTION_CHARS`
characters; ``None`` when it has none. Nothing is invented.

A paragraph (lines up to a blank line, its leading headings dropped) is not
prose, and is passed over, when it is a fenced code block, starts with an
HTML tag, or each of its lines is one of: a heading, a horizontal rule, a
table row, a ``Table of Contents`` title, a list item that is only a link,
only images or badges, or a bold key (``**Paper:**``) whose value is not a
sentence. One line of prose keeps the paragraph whole.

See also: :mod:`pitloom.extract.remote.huggingface_field` (a model's) and
:mod:`pitloom.extract.remote.huggingface_dataset` (a dataset's).
"""

from __future__ import annotations

import re

from pitloom.core.frontmatter import split_frontmatter

__all__ = ["MAX_DESCRIPTION_CHARS", "card_description"]

#: The longest description kept; a longer paragraph is cut.
MAX_DESCRIPTION_CHARS = 500

_LINK = r"\[[^\]]*\]\([^)]*\)"
_IMAGE = r"!" + _LINK
_BADGE = r"\[" + _IMAGE + r"\]\([^)]*\)"
_HTML_START = re.compile(r"<(?:!--|[A-Za-z][A-Za-z0-9-]*(?:[\s/>]|$))")
_FENCE = re.compile(r"(```|~~~)")
_NOT_PROSE_LINE = re.compile(
    r"#.*"  # a heading
    r"|(?:-{3,}|\*{3,}|_{3,})"  # a horizontal rule
    r"|\|.*"  # a table row
    r"|[*_]*\s*(?:table of )?contents\s*:?\s*[*_]*"  # a contents title
    r"|(?:[-*+]|\d+[.)])\s+" + _LINK + r"\s*"  # a list item that is a link
    r"|(?:(?:" + _BADGE + "|" + _IMAGE + r")\s*)+",  # images and badges
    re.IGNORECASE,
)
#: A bold key and its value: ``**Paper:** ...`` or ``**Paper**: ...``.
_BOLD_KEY = re.compile(r"(?:[-*+]\s+)?\*\*(?:[^*]+:\*\*|[^*]+\*\*\s*:)\s*(.*)")
#: A value that is a sentence: three words or more, closed by ``.!?``.
_SENTENCE = re.compile(r"\w+(?:\W+\w+){2,}.*[.!?]")


def _paragraphs(lines: list[str]) -> list[list[str]]:
    """The stripped paragraphs of *lines*, leading headings dropped; a
    fenced code block, blank lines and all, is left out."""
    paragraphs: list[list[str]] = [[]]
    fence: str | None = None
    for line in lines:
        stripped = line.strip()
        opening = _FENCE.match(stripped)
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
        elif opening is not None:
            fence = opening.group(1)
            paragraphs.append([])
        elif not stripped:
            paragraphs.append([])
        elif paragraphs[-1] or not stripped.startswith("#"):
            paragraphs[-1].append(stripped)
    return [paragraph for paragraph in paragraphs if paragraph]


def _is_prose_line(line: str) -> bool:
    """Whether *line* may be prose (see the module rules)."""
    if _NOT_PROSE_LINE.fullmatch(line):
        return False
    key = _BOLD_KEY.fullmatch(line)
    if key is None:
        return True
    value = re.sub(_LINK, lambda m: m.group(0)[1 : m.group(0).index("]")], key[1])
    return _SENTENCE.fullmatch(value.strip()) is not None


def _is_prose(paragraph: list[str]) -> bool:
    """Whether *paragraph* is prose (see the module rules)."""
    if _HTML_START.match(paragraph[0]):
        return False
    return any(_is_prose_line(line) for line in paragraph)


def card_description(card_text: str) -> str | None:
    """The first prose paragraph of *card_text* (a whole card, front
    matter included), its lines joined by a space and cut to
    :data:`MAX_DESCRIPTION_CHARS`; ``None`` when there is none."""
    split = split_frontmatter(card_text)
    lines = [] if split is None else split[1].splitlines()
    for paragraph in _paragraphs(lines):
        if _is_prose(paragraph):
            return " ".join(paragraph)[:MAX_DESCRIPTION_CHARS]
    return None
