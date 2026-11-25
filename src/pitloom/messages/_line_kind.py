# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What kind of line Pitloom printed on stderr: catalogued, or one of the
kinds that have no code by design, or none of them.

:func:`line_kind` reads one printed line, in this order, the first that
holds winning:

1. a trailing ``\\r`` (a Windows line end) is dropped;
2. ``debug``: it starts ``DEBUG: ``;
3. ``untagged``: it starts with no ``ERROR: ``, ``WARNING: `` or ``INFO: ``
   (argparse's usage text, a traceback line, another program's output);
4. ``overlong``: it is longer than
   :data:`~pitloom.messages._lines.LONGEST_LINE`, so it is not read further
   (:func:`~pitloom.messages._lines.trusted_message` trusts no such line);
5. ``coded``: :func:`~pitloom.messages._lines.trusted_message` trusts it;
6. ``summary``: an ``INFO:`` line whose text is a
   :data:`~pitloom.messages._catalogue.SUMMARIES` template, each value of its
   field's shape;
7. ``detail``: an ``INFO: KEY=VALUE`` line (``-v``);
8. ``relay``: its text starts with a prefix of
   :data:`~pitloom.messages._relays.RELAY_PREFIXES`, after at most one frame
   of :data:`~pitloom.messages._frames.FRAMES` of the line's level;
9. ``uncoded``: anything else.

A line that ends in a code-like `` [x]`` but is not trusted is not
``coded``: another program, or a value Pitloom printed, may have written it.

See also: :mod:`pitloom.messages._lines` (trusting a code),
:data:`pitloom.logging_config.KIND_ATTR` (the kind a record carries).
"""

from __future__ import annotations

import functools
import re
from typing import Final

from pitloom.logging_config import DETAIL_KIND, RELAY_KIND, SUMMARY_KIND
from pitloom.messages._catalogue import SUMMARIES
from pitloom.messages._frames import FRAMES
from pitloom.messages._lines import LONGEST_LINE, trusted_message
from pitloom.messages._relays import RELAY_PREFIXES
from pitloom.messages._templates import template_pattern

#: A ``DEBUG`` line: never on stderr unless asked for, never coded.
DEBUG_KIND: Final = "debug"
#: A line with no level tag.
UNTAGGED_KIND: Final = "untagged"
#: A tagged line too long to be read back.
OVERLONG_KIND: Final = "overlong"
#: A catalogued line (:func:`~pitloom.messages._lines.trusted_message`).
CODED_KIND: Final = "coded"
#: A tagged line of none of the other kinds.
UNCODED_KIND: Final = "uncoded"

#: Every value :func:`line_kind` returns.
LINE_KINDS: Final = frozenset(
    {
        DEBUG_KIND,
        UNTAGGED_KIND,
        OVERLONG_KIND,
        CODED_KIND,
        SUMMARY_KIND,
        DETAIL_KIND,
        RELAY_KIND,
        UNCODED_KIND,
    }
)

#: A tagged line: groups level and text.
_TAGGED: Final = re.compile(r"(ERROR|WARNING|INFO): (.*)", re.DOTALL)
#: The text of a ``-v`` detail (:func:`pitloom.cli.kv_output.log_kv`): its
#: first key, then ``=``.
_DETAIL: Final = re.compile(r"[A-Z][A-Z0-9_]*=")


@functools.cache
def _summary_re() -> re.Pattern[str]:
    """The text of every summary, one alternation, compiled once."""
    shapes = "|".join(template_pattern(s.template) for s in SUMMARIES)
    return re.compile(f"(?:{shapes})")


@functools.cache
def _relay_re(level: str) -> re.Pattern[str]:
    """The start of a relay line's text at *level*: at most one frame of that
    level, then a relay prefix; compiled once per level."""
    frames = [template_pattern(f.template) for f in FRAMES if level in f.levels]
    head = f"(?:{'|'.join(frames)})?" if frames else ""
    prefixes = "|".join(re.escape(prefix) for prefix in RELAY_PREFIXES)
    return re.compile(f"{head}(?:{prefixes})")


def line_kind(line: str) -> str:
    """The kind of *line*, one line Pitloom printed on stderr without its
    line end (a trailing ``\\r`` is dropped): one of :data:`LINE_KINDS`, in
    the order the module docstring gives."""
    line = line.removesuffix("\r")
    if line.startswith("DEBUG: "):
        return DEBUG_KIND
    tagged = _TAGGED.fullmatch(line)
    if tagged is None:
        return UNTAGGED_KIND
    if len(line) > LONGEST_LINE:
        return OVERLONG_KIND
    if trusted_message(line) is not None:
        return CODED_KIND
    level, text = tagged.groups()
    return _kind_without_code(level, text)


def _kind_without_code(level: str, text: str) -> str:
    """The kind of a tagged line that is not ``coded``, of *level*, its
    *text* after the tag: ``summary``, ``detail``, ``relay`` or
    ``uncoded``."""
    if level == "INFO" and _summary_re().fullmatch(text) is not None:
        return SUMMARY_KIND
    if level == "INFO" and _DETAIL.match(text) is not None:
        return DETAIL_KIND
    if _relay_re(level).match(text) is not None:
        return RELAY_KIND
    return UNCODED_KIND
