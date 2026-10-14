# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where a free-text author field is cut into entries (:func:`field_parts`):
an address field (``Author-email``) on every ``,`` and ``;`` outside a
quoted display name and an ``<address>``; a name field (``Author``) only
next to an address -- after a mailbox, before a bare address, and between
two closed ``<address>`` entries -- never between two names.

See also: :mod:`pitloom.extract.authors` (the reading of each entry).
"""

from __future__ import annotations

import re
from collections.abc import Iterator

__all__ = [
    "ADDRESS_MARK_RE",
    "ADDRESS_RE",
    "ANGLE_RE",
    "TRAILING_COMMENT_RE",
    "TYPOGRAPHIC_QUOTES",
    "Quoting",
    "field_parts",
    "is_contributor_group",
    "outside_entries",
    "separators",
]

#: A name standing for a group of further contributors: ``Others``, ``and
#: others (see AUTHORS)``, ``et al.`` -- whole words, so ``Jan Brothers`` is
#: a person.
_CONTRIBUTOR_GROUP_RE = re.compile(r"\b(?:others|et\s+al)\b", re.IGNORECASE)
#: A ``,`` or ``;`` between two author-field entries, outside a quoted
#: display name and an address (:func:`outside_entries`).
_ENTRY_SEPARATOR_RE = re.compile(r"[,;]")
#: An angle bracket, opening or closing an address.
ANGLE_RE = re.compile(r"[<>]")
#: What makes a part an address entry rather than a name.
ADDRESS_MARK_RE = re.compile(r"[<>@]")
#: A typographic opening quote and its closing quote.
TYPOGRAPHIC_QUOTES = {"“": "”", "‘": "’"}
#: A ``"`` or typographic quote, opening or closing a quoted display name.
_QUOTE_RE = re.compile('["“”‘’]')
#: An address Pitloom records: one ``@``, text on both sides, no space.
ADDRESS_RE = re.compile(r"[^@\s]+@[^@\s]+")
#: An RFC 5322 comment ending an address entry: ``ann@example.com (Ann)``.
TRAILING_COMMENT_RE = re.compile(r"\([^()]*\)\s*$")
#: The ``and`` or ``&`` joining the entry before an ``<address>`` cut to it.
_LEADING_JOINER_RE = re.compile(r"^\s*(?:&|and(?!\S))", re.IGNORECASE)


def is_contributor_group(name: str | None) -> bool:
    """Whether the author *name* stands for a group of contributors."""
    return bool(name and _CONTRIBUTOR_GROUP_RE.search(name))


def _split_at(text: str, spans: Iterator[tuple[int, int]]) -> list[str]:
    """*text* cut at each separator span, the separators left out."""
    parts: list[str] = []
    start = 0
    for begin, end in spans:
        parts.append(text[start:begin])
        start = end
    parts.append(text[start:])
    return parts


# pylint: disable-next=too-few-public-methods
class Quoting:
    """Whether a position of a text is inside a quoted display name, asked
    in increasing order: where an odd number of ``"`` follow, or between a
    typographic opening quote (U+201C, U+2018) and its closing quote later
    in the text (a closing quote alone, an apostrophe, quotes nothing).
    Each quote is looked at once."""

    def __init__(self, text: str) -> None:
        self._quotes = [(m.start(), m.group()) for m in _QUOTE_RE.finditer(text)]
        self._last = {c: text.rfind(c) for c in TYPOGRAPHIC_QUOTES.values()}
        self._next = 0
        self._after = text.count('"')
        self._awaited = ""  # the closing quote of an open typographic quote

    def inside(self, position: int) -> bool:
        """Whether *position* is inside a quoted display name."""
        quotes = self._quotes
        while self._next < len(quotes) and quotes[self._next][0] < position:
            start, mark = quotes[self._next]
            self._next += 1
            close = TYPOGRAPHIC_QUOTES.get(mark, "")
            if mark == '"':
                self._after -= 1
            elif close and not self._awaited and self._last[close] > start:
                self._awaited = close
            elif mark == self._awaited:
                self._awaited = ""
        return bool(self._awaited) or self._after % 2 == 1


def _bare_address(segment: str) -> bool:
    """Whether *segment*, less a trailing comment, is one bare address
    (``a@x.org``, ``a@x.org (Ann)``): it carries no display name before
    it."""
    return bool(ADDRESS_RE.fullmatch(TRAILING_COMMENT_RE.sub("", segment).strip()))


def _ends_mailbox(segment: str) -> bool:
    """Whether *segment*, the text between two separators, ends a mailbox,
    less a trailing comment: a closed ``<address>`` (``Ann <a@x.org>``) or
    a bare address (``a@x.org``)."""
    text = TRAILING_COMMENT_RE.sub("", segment).strip()
    return (text.endswith(">") and "<" in text) or _bare_address(text)


def separators(
    text: str, pattern: re.Pattern[str] = _ENTRY_SEPARATOR_RE
) -> Iterator[tuple[int, int]]:
    """The spans of the ``,`` and ``;`` (*pattern*) in *text* neither
    inside a quoted display name (:class:`Quoting`) nor inside a
    ``<...>`` address: where the next angle bracket after it is not ``>``.
    One pass, each bracket and quote looked at once."""
    angles = [(m.start(), m.group()) for m in ANGLE_RE.finditer(text)]
    quoting = Quoting(text)
    index = 0
    for found in pattern.finditer(text):
        while index < len(angles) and angles[index][0] < found.end():
            index += 1
        in_address = index < len(angles) and angles[index][1] == ">"
        if not in_address and not quoting.inside(found.start()):
            yield found.span()


def _mailbox_cuts(
    text: str, spans: Iterator[tuple[int, int]]
) -> Iterator[tuple[int, int]]:
    """The separator *spans* of a name field *text* that are cuts: after a
    segment (the text between two separators) that ends a mailbox
    (:func:`_ends_mailbox`) or a blank one right after a cut (``;;``), and
    before a bare address (:func:`_bare_address`). Each segment looked at
    once."""
    last = 0  # where the last separator ended
    fresh = True  # whether the segment from *last* follows a cut
    held: tuple[int, int] | None = None  # a cut only before a bare address
    for begin, end in spans:
        segment = text[last:begin]
        if held and _bare_address(segment):
            yield held
            fresh = True
        if _ends_mailbox(segment) or (fresh and not segment.strip()):
            held, fresh = None, True
            yield begin, end
        else:
            held, fresh = (begin, end), False
        last = end
    if held and _bare_address(text[last:]):
        yield held


def _closed_address_ends(text: str) -> list[int]:
    """Where each closed ``<address>`` of *text* ends: after a ``>`` whose
    angle bracket before it is ``<``, both outside a quoted display name
    (:class:`Quoting`), with one address (:data:`ADDRESS_RE`) between."""
    quoting = Quoting(text)
    ends: list[int] = []
    opened = -1  # where the open ``<`` ends
    for found in ANGLE_RE.finditer(text):
        if quoting.inside(found.start()):
            continue
        if found.group() == "<":
            opened = found.end()
        elif opened >= 0:
            if ADDRESS_RE.fullmatch(text[opened : found.start()].strip()):
                ends.append(found.end())
            opened = -1
    return ends


def _between_mailboxes(piece: str) -> list[str]:
    """A name-field *piece* cut after each closed ``<address>`` but its
    last (:func:`_closed_address_ends`), so ``Ann <a@x.org> and Bob
    <b@x.org>`` is two entries, a leading ``and`` or ``&`` left out of the
    one after a cut; text after the last address stays with it."""
    ends = _closed_address_ends(piece)[:-1]
    entries = _split_at(piece, ((end, end) for end in ends))
    return [entries[0], *(_LEADING_JOINER_RE.sub("", e) for e in entries[1:])]


def outside_entries(text: str, named: bool = False) -> list[str]:
    """*text* split on its separators (:func:`separators`); a *named*
    field (a name field) only next to an address (:func:`_mailbox_cuts`),
    and between two closed ``<address>`` entries
    (:func:`_between_mailboxes`)."""
    spans = separators(text)
    if not named:
        return _split_at(text, spans)
    pieces = _split_at(text, _mailbox_cuts(text, spans))
    return [entry for piece in pieces for entry in _between_mailboxes(piece)]


def _group_split(part: str) -> list[str]:
    """One comma-separated *part* of an author field as entries: a
    contributor group after an ``<address>`` (``Jane <j@x.org> et al.``)
    is an entry of its own, the address ending the one before it."""
    closed = part.rfind(">") + 1
    if closed and is_contributor_group(part[closed:]):
        return [part[:closed], part[closed:]]
    return [part]


def field_parts(field: str, named: bool = False) -> tuple[list[str], bool]:
    """An author *field* as stripped parts (:func:`outside_entries`,
    :func:`_group_split`), and whether a cut is warned about: in a *named*
    field, any cut; in an address field, a cut after a name (a part with no
    ``<``, ``>`` or ``@``; an address entry ends an author), which could be
    inside one name."""
    pieces = outside_entries(field, named)
    raw = [name for part in pieces for name in _group_split(part)]
    parts = [part.strip() for part in raw if part.strip()]
    if named:
        return parts, len(pieces) > 1
    return parts, any(not ADDRESS_MARK_RE.search(left) for left in parts[:-1])
