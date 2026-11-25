# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers of the quote drift tests: is a line quoted in the docs or the
skills (a backticked ``LEVEL: ...`` span) one Pitloom can print?

:func:`quote_matches` reads a quote against one family's lines;
:func:`quote_kind` says which kind of printed line a quote is, so a quote
holding no family marker is checked too.

See also: tests/_message_drift.py (records and sources against the
catalogue), tests/messages/test_drift_quotes.py (quotes holding a marker),
tests/messages/test_drift_quote_kinds.py (every ``LEVEL:`` quote).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Iterable, Mapping

from pitloom.logging_config import CODE_PATTERN
from pitloom.messages import FIELDS, FRAMES, MESSAGES, RELAY_PREFIXES, SUMMARIES
from pitloom.messages._templates import PLACEHOLDER

#: What a quote leaves out or fills in: an ellipsis, ``<placeholder>``, a
#: ``%s`` value, ``(N files)`` or ``byte(s)``, space around it too; a bare
#: ``N`` before a hyphen (``N-byte``); or a bare ``N``, ``NAME`` or ``KEY``
#: word (``holds N id(s)``, ``-e NAME stored as KEY``).
_WILD = re.compile(
    r"\s*(?:\.\.\.|…|<[^<>]*>|%s|\(N [^)]*\)|byte\(s\))\s*"
    r"|(?<![\w-])N(?=-)"
    r"|(?<![\w=-])(?:N|NAME|KEY)(?![\w=-])"
)
_LEVEL = re.compile(r"^(ERROR|WARNING|INFO): ")
_CODE = re.compile(rf" \[({CODE_PATTERN})\]$")

#: A quote's wildcard (:data:`_WILD`) as one token; a quote's other tokens
#: are its characters.
_ANY = object()
#: A line token standing for any text to the line's end (a relay's words).
_REST = "\x00rest"
#: Before a field's name in a line token: the field prints only where the
#: quote has a wildcard (or nothing, when it may be empty).
_WILD_ONLY = "\x01"
#: A marker no quote holds: a free value may then be any text.
_NO_MARKER = "\x00"
#: A marker every text holds: a free value then takes no literal text of
#: the quote, only a wildcard (a prefix or a summary names its values).
_LITERAL = ""

#: The kinds :func:`quote_kind` returns.
MARKED = "marked"
CODED = "coded"
CATALOGUED = "catalogued"
PREFIX = "prefix"
SUMMARY = "summary"
RELAY = "relay"
DETAIL = "detail"

#: The literal text a quote with no marker and no code needs, at least, to
#: be read as one family's line.
LITERAL_RUN = 12

#: A prefix quote: text, ending in ``:`` or ``=``, then nothing or one
#: wildcard (``loom <command>: ...``, ``Build:``).
_PREFIX_SHAPE = re.compile(r".*[:=](?:\s*(?:\.\.\.|…|<[^<>]*>))?", re.DOTALL)
#: A ``-v`` detail: ``KEY=VALUE`` pairs, no ``SUBJECT: `` condition.
_DETAIL_SHAPE = re.compile(r"[A-Z][A-Z0-9_]*=")


def _quote_tokens(text: str) -> tuple[object, ...]:
    """*text* as its characters, each wildcard of :data:`_WILD` one
    :data:`_ANY`."""
    tokens: list[object] = []
    end = 0
    for found in _WILD.finditer(text):
        tokens += text[end : found.start()]
        tokens.append(_ANY)
        end = found.end()
    return (*tokens, *text[end:])


def _line_tokens(template: str) -> tuple[str, ...]:
    """*template* as its characters, each ``%(name)s`` the field's name (a
    token longer than one character)."""
    tokens: list[str] = []
    end = 0
    for found in PLACEHOLDER.finditer(template):
        tokens += template[end : found.start()]
        tokens.append(found.group(1))
        end = found.end()
    return (*tokens, *template[end:])


def _takes(name: str, run: tuple[object, ...], marker: str) -> bool:
    """Whether field *name* can print as the quote's *run*, which starts
    with text (:func:`_piece_of` reads a wildcard standing for the field):
    the value as the reference shows it (``'<path>'``); for a free field,
    any text without the family's *marker*, but never one placeholder in
    quotes, which says the field prints quoted when it does not
    (``'<key>'`` for ``<entity>``); for any other, text of its own shape."""
    field = FIELDS[name]
    if run == _quote_tokens(field.shown):
        return True
    text = "".join(t for t in run if isinstance(t, str))
    if field.free:
        return marker not in text and run != ("'", _ANY, "'")
    return _ANY not in run and re.fullmatch(field.pattern, text) is not None


def _piece_of(
    quote: tuple[object, ...],
    line: tuple[str, ...],
    marker: str,
    *,
    anchored: bool = False,
) -> bool:
    """Whether some printing of the template *line* holds *quote*, a
    wildcard of it standing for any text; with *anchored*, *quote* starts
    where the line starts. A :data:`_REST` token of *line* prints any
    text; a :data:`_WILD_ONLY` field prints only as a wildcard."""
    size, width = len(quote), len(line)

    @functools.cache
    def placed(i: int, j: int) -> bool:
        """Whether ``quote[i:]`` is printed from ``line[j:]`` on."""
        if i == size or (j < width and line[j] is _REST):
            return True
        if j == width:
            return all(t is _ANY for t in quote[i:])
        here, there = quote[i], line[j]
        if here is _ANY:
            return placed(i + 1, j) or placed(i, j + 1)
        if len(there) > 1:  # a field, maybe one printing only as a wildcard
            name = there.removeprefix(_WILD_ONLY)
            if re.fullmatch(FIELDS[name].pattern, "") and placed(i, j + 1):
                return True
            return name == there and any(
                _takes(name, quote[i:k], marker) and placed(k, j + 1)
                for k in range(i + 1, size + 1)
            )
        return here == there and placed(i + 1, j + 1)

    return placed(0, 0) if anchored else any(placed(0, j) for j in range(width))


def quote_matches(quote: str, family: str, marker: str) -> bool:
    """Whether *quote* (a backticked line or piece of one, optionally with
    its ``LEVEL: `` and its `` [code]``) is part of a line of *family*, at
    that line's level and with its entry's code, a frame of that level
    before it or not (one that allows the entry's code at that level); a
    quote with its ``LEVEL: `` starts where the line (or its frame) starts.
    A value stands in the quote as a wildcard, as the reference shows it, or
    as itself (``10000`` for ``<limit>``); a free value never holds the
    family's *marker*, so a quote cannot be all value."""
    level = _LEVEL.match(quote)
    text = quote[level.end() :] if level else quote
    coded = _CODE.search(text)
    tokens = _quote_tokens(text[: coded.start()] if coded else text)
    return any(
        _piece_of(
            tokens,
            _line_tokens(head + line.template),
            marker,
            anchored=level is not None,
        )
        for entry in MESSAGES.values()
        if entry.family == family and (coded is None or coded.group(1) == entry.code)
        for line in entry.lines
        if level is None or level.group(1) == line.level
        for head in [
            "",
            *(f.template for f in FRAMES if f.allows(entry.code, line.level)),
        ]
    )


@functools.cache
def _printed(level: str) -> tuple[tuple[str, str, str], ...]:
    """(family, frame, template) for every catalogued line of *level*, with
    no frame (``""``) and with each frame allowing its code."""
    return tuple(
        (entry.family, head, line.template)
        for entry in MESSAGES.values()
        for line in entry.lines
        if line.level == level
        for head in [
            "",
            *(f.template for f in FRAMES if f.allows(entry.code, level)),
        ]
    )


@functools.cache
def _starts(level: str) -> tuple[tuple[str, ...], ...]:
    """Every text a line of *level* can start with, as line tokens: a frame
    alone, a catalogued line (:func:`_printed`), whose values print only as
    wildcards (a prefix names a value, it does not give one: ``%(option)s``
    would otherwise print any word), and at ``INFO`` a summary."""
    found = [_line_tokens(f.template) for f in FRAMES if level in f.levels]
    found += [
        (
            *_line_tokens(head),
            *(t if len(t) == 1 else _WILD_ONLY + t for t in _line_tokens(template)),
        )
        for _, head, template in _printed(level)
    ]
    if level == "INFO":
        found += [_line_tokens(s.template) for s in SUMMARIES]
    return tuple(found)


@functools.cache
def _relay_starts(level: str) -> tuple[tuple[str, ...], ...]:
    """A relay line's text at *level* as line tokens: a frame of that level
    (required at ``ERROR``, where a relay is always framed), a relay prefix,
    then any text."""
    heads = [f.template for f in FRAMES if level in f.levels]
    if level != "ERROR":
        heads.append("")
    return tuple(
        (*_line_tokens(head), *prefix, _REST)
        for head in heads
        for prefix in RELAY_PREFIXES
    )


def _literal_runs(text: str) -> list[str]:
    """The literal pieces of a quote's *text* between its wildcards."""
    return [run.strip() for run in _WILD.split(text) if run.strip()]


def _is_coded(quote: str, text: str, code: str) -> bool:
    """Whether *quote*, ending in `` [code]``, is a piece of one of that
    code's lines; the longest literal run of its *text* (before the code)
    is the marker, so a free value cannot stand for the quote's own words.
    A quote of wildcards only checks the level and the code."""
    entry = MESSAGES.get(code)
    if entry is None:
        return False
    run = max(_literal_runs(text), key=len, default="")
    return quote_matches(quote, entry.family, run or _NO_MARKER)


def _is_catalogued(level: str, tokens: tuple[object, ...], text: str) -> bool:
    """Whether the longest literal run of *text* has :data:`LITERAL_RUN`
    characters or more and the lines of *level* holding it as their own
    text (not as a value) and holding the quote are of exactly one
    family."""
    run = max(_literal_runs(text), key=len, default="")
    if len(run) < LITERAL_RUN:
        return False
    families = {
        family
        for family, head, template in _printed(level)
        if any(run in piece for piece in PLACEHOLDER.split(head + template))
        and _piece_of(tokens, _line_tokens(head + template), run)
    }
    return len(families) == 1


def _is_prefix(level: str, tokens: tuple[object, ...], text: str) -> bool:
    """Whether *text* is prefix-shaped (:data:`_PREFIX_SHAPE`), holds a
    letter or digit, and starts some line of *level*."""
    return (
        _PREFIX_SHAPE.fullmatch(text) is not None
        and any(c.isalnum() for run in _literal_runs(text) for c in run)
        and any(
            _piece_of(tokens, line, _LITERAL, anchored=True) for line in _starts(level)
        )
    )


def _is_summary(level: str, tokens: tuple[object, ...], text: str) -> bool:
    """Whether *tokens* start a summary (an ``INFO`` line), no free value
    holding the longest literal run of *text*."""
    run = max(_literal_runs(text), key=len, default="")
    return level == "INFO" and any(
        _piece_of(tokens, _line_tokens(s.template), run, anchored=True)
        for s in SUMMARIES
    )


def _is_relay(level: str, tokens: tuple[object, ...], text: str) -> bool:
    """Whether *tokens* start a relay line of *level*, its *text* naming the
    relay prefix (a wildcard never stands for it) and, at ``ERROR``, showing
    the frame (not starting with a wildcard)."""
    if not any(prefix in text for prefix in RELAY_PREFIXES):
        return False
    if level == "ERROR" and tokens[0] is _ANY:
        return False
    return any(
        _piece_of(tokens, line, _LITERAL, anchored=True)
        for line in _relay_starts(level)
    )


def _is_detail(level: str, tokens: tuple[object, ...], text: str) -> bool:
    """Whether *text* is a ``-v`` detail: ``INFO: KEY=VALUE ...``, no
    ``SUBJECT: `` condition (*tokens* unused)."""
    del tokens
    return level == "INFO" and bool(_DETAIL_SHAPE.match(text)) and ": " not in text


#: The kinds of a quote with no marker and no code, each with its check, in
#: the order :func:`quote_kind` tries them.
_CHECKS: tuple[tuple[str, Callable[[str, tuple[object, ...], str], bool]], ...] = (
    (CATALOGUED, _is_catalogued),
    (PREFIX, _is_prefix),
    (SUMMARY, _is_summary),
    (RELAY, _is_relay),
    (DETAIL, _is_detail),
)


def quote_kind(quote: str, markers: Mapping[str, Iterable[str]]) -> str | None:
    """The kind of line *quote* (a backticked ``LEVEL: ...`` span) is, or
    ``None`` when Pitloom prints no such line; the first that holds wins:

    - :data:`MARKED`: it holds a family's marker (one of *markers*); the
      marker's family says whether it matches;
    - :data:`CODED`: it ends `` [code]`` and is a piece of a line of that
      code, at its level (a quote may leave the frame out: the code names
      it);
    - :data:`CATALOGUED`: no code, but its longest literal run is
      :data:`LITERAL_RUN` characters or more and exactly one family has a
      line holding the quote;
    - :data:`PREFIX`: a frame or sub-prefix ending in ``:`` or ``=``, then
      nothing or one wildcard, that some line of its level starts with;
    - :data:`SUMMARY`: the start of a summary (``INFO``);
    - :data:`RELAY`: a relay prefix after at most one frame of its level;
      at ``ERROR`` a frame (``loom <command>: ``) must come first;
    - :data:`DETAIL`: an ``INFO: KEY=VALUE ...`` line with no ``: ``.

    A quote ending in a code its line does not have is ``None``, never read
    as another kind."""
    if any(m in quote for family in markers.values() for m in family):
        return MARKED
    level_match = _LEVEL.match(quote)
    if level_match is None:
        return None
    level, text = level_match.group(1), quote[level_match.end() :]
    coded = _CODE.search(text)
    if coded is not None:
        said = _is_coded(quote, text[: coded.start()], coded.group(1))
        return CODED if said else None
    tokens = _quote_tokens(text)
    return next((kind for kind, check in _CHECKS if check(level, tokens, text)), None)
