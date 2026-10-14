# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one reading of a free-text author field and its address field, on
every surface: core-metadata ``Author``/``Author-email`` (wheel, sdist
``PKG-INFO``, a dependency's installed or PyPI record), ``setup.cfg``
``author``/``author_email`` and ``setup.py`` ``setup(author=...)``.

Both fields are read by one splitter (:func:`_parts`), cut on ``,`` and
``;`` outside a quoted display name and an ``<address>``, never on
``and``; they differ only in where a cut may happen. An address field
(``Author-email``) is a list (RFC 5322), cut after any separator; it
cannot tell a list from one unquoted name containing a comma, so a cut
after a name is warned about. A name field (``Author``) is cut only where
the text proves a list: after a closed ``<address>`` or a bare address
(:func:`_ends_mailbox`), never after a name, as backends write a
structured name-only author (``{name = "Doe, Jane"}``) there verbatim;
``Doe, Jane`` and ``Ann and Bob`` stay one author (an ``INFO:`` that it
may list several), and a cut is warned about. A contributor group after
an ``<address>`` (``Jane <j@x.org> et al.``) is an entry of its own in
either field. An entry holding no ``<``,
``>`` or ``@`` is a name; any other is read as one mailbox, the name
before its ``<`` held together: an address that is no address is not
recorded, the name stated before it kept, with one ``WARNING:`` per field
naming the count and the first few. A display name has each run of white
space read as one space (:func:`collapse_whitespace`), on every surface.
One pass reads each field, capped (:data:`AUTHOR_FIELD_MAX_CHARS`,
:data:`AUTHOR_FIELD_MAX_NAMES`): a cap warns whenever the value read is
used, a read whose value is discarded (*quiet*) warns about nothing. A
structured entry -- one display name in ``"`` or typographic quotes, one
``[project].authors`` table, one Poetry ``authors`` string -- is one
author and is never split.

See also: :mod:`pitloom.extract._author_warnings` (the warnings),
:mod:`pitloom.extract.dependency_authors` (a dependency's originators) and
:mod:`pitloom.extract._core_metadata`
(:func:`~pitloom.extract._core_metadata.parse_core_metadata_authors`).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from email.utils import getaddresses, unquote
from typing import TYPE_CHECKING, NamedTuple

from pitloom.extract._author_warnings import (
    CORE_METADATA_HINT,
    AuthorSplit,
    counted,
    dependency_author_splits,
    warn_author_splits,
    warn_field_cap,
    warn_not_addresses,
    warn_project_authors_unread,
)
from pitloom.logging_config import Cap

if TYPE_CHECKING:
    #: A name/address pair; either part may be None.
    NameEmail = tuple[str | None, str | None]

__all__ = [
    "AUTHOR_FIELD_MAX_CHARS",
    "AUTHOR_FIELD_MAX_NAMES",
    "AUTHOR_KEYS",
    "CORE_METADATA_HINT",
    "AuthorSplit",
    "author_pairs",
    "collapse_whitespace",
    "dependency_author_splits",
    "is_contributor_group",
    "is_unset_placeholder",
    "read_author_fields",
    "stated_text",
    "warn_author_splits",
    "warn_project_authors_unread",
]

#: A name standing for a group of further contributors: ``Others``, ``and
#: others (see AUTHORS)``, ``et al.`` -- whole words, so ``Jan Brothers`` is
#: a person.
_CONTRIBUTOR_GROUP_RE = re.compile(r"\b(?:others|et\s+al)\b", re.IGNORECASE)
#: A ``,`` or ``;`` between two author-field entries, outside a quoted
#: display name and an address (:func:`_outside_entries`).
_ENTRY_SEPARATOR_RE = re.compile(r"[,;]")
#: What may join several names in one name field: ``,``, ``;``, ``and``.
_JOINER_RE = re.compile(r"[,;]|(?<=\s)and(?=\s)", re.IGNORECASE)
#: An angle bracket, opening or closing an address.
_ANGLE_RE = re.compile(r"[<>]")
#: What makes a part an address entry rather than a name.
_ADDRESS_MARK_RE = re.compile(r"[<>@]")
#: A typographic opening quote and its closing quote.
_TYPOGRAPHIC_QUOTES = {"“": "”", "‘": "’"}
#: A ``"`` or typographic quote, opening or closing a quoted display name.
_QUOTE_RE = re.compile('["“”‘’]')

#: The most characters of one free-text author or address field read; the
#: rest is not read (its last, possibly cut, name neither).
AUTHOR_FIELD_MAX_CHARS = 64 * 1024
#: The most entries read from one author field.
AUTHOR_FIELD_MAX_NAMES = 1000


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
class _Quoting:
    """Whether a position of a text is inside a quoted display name, asked
    in increasing order: where an odd number of ``"`` follow, or between a
    typographic opening quote (U+201C, U+2018) and its closing quote later
    in the text (a closing quote alone, an apostrophe, quotes nothing).
    Each quote is looked at once."""

    def __init__(self, text: str) -> None:
        self._quotes = [(m.start(), m.group()) for m in _QUOTE_RE.finditer(text)]
        self._last = {c: text.rfind(c) for c in _TYPOGRAPHIC_QUOTES.values()}
        self._next = 0
        self._after = text.count('"')
        self._awaited = ""  # the closing quote of an open typographic quote

    def inside(self, position: int) -> bool:
        """Whether *position* is inside a quoted display name."""
        quotes = self._quotes
        while self._next < len(quotes) and quotes[self._next][0] < position:
            start, mark = quotes[self._next]
            self._next += 1
            close = _TYPOGRAPHIC_QUOTES.get(mark, "")
            if mark == '"':
                self._after -= 1
            elif close and not self._awaited and self._last[close] > start:
                self._awaited = close
            elif mark == self._awaited:
                self._awaited = ""
        return bool(self._awaited) or self._after % 2 == 1


#: An address Pitloom records: one ``@``, text on both sides, no space.
_ADDRESS_RE = re.compile(r"[^@\s]+@[^@\s]+")
#: An RFC 5322 comment ending an address entry: ``ann@example.com (Ann)``.
_TRAILING_COMMENT_RE = re.compile(r"\([^()]*\)\s*$")


def _ends_mailbox(segment: str) -> bool:
    """Whether *segment*, the text between two separators, ends a mailbox,
    less a trailing comment: a closed ``<address>`` (``Ann <a@x.org>``) or
    a bare address (``a@x.org``). Where a name field may be cut."""
    text = _TRAILING_COMMENT_RE.sub("", segment).strip()
    return (text.endswith(">") and "<" in text) or bool(_ADDRESS_RE.fullmatch(text))


def _separators(
    text: str, pattern: re.Pattern[str] = _ENTRY_SEPARATOR_RE
) -> Iterator[tuple[int, int]]:
    """The spans of the ``,`` and ``;`` (*pattern*) in *text* neither
    inside a quoted display name (:class:`_Quoting`) nor inside a
    ``<...>`` address: where the next angle bracket after it is not ``>``.
    One pass, each bracket and quote looked at once."""
    angles = [(m.start(), m.group()) for m in _ANGLE_RE.finditer(text)]
    quoting = _Quoting(text)
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
    segment (the text since the last separator) that ends a mailbox
    (:func:`_ends_mailbox`), or a blank one right after a cut (``;;``).
    Each segment looked at once."""
    last = cut = 0  # where the last separator, and the last cut, ended
    for begin, end in spans:
        segment = text[last:begin]
        fresh, last = last == cut, end
        if _ends_mailbox(segment) or (fresh and not segment.strip()):
            cut = end
            yield begin, end


def _outside_entries(text: str, named: bool = False) -> list[str]:
    """*text* split on its separators (:func:`_separators`); a *named*
    field (a name field) only on those after a mailbox
    (:func:`_mailbox_cuts`)."""
    spans = _separators(text)
    return _split_at(text, _mailbox_cuts(text, spans) if named else spans)


def _group_split(part: str) -> list[str]:
    """One comma-separated *part* of an author field as entries: a
    contributor group after an ``<address>`` (``Jane <j@x.org> et al.``)
    is an entry of its own, the address ending the one before it."""
    closed = part.rfind(">") + 1
    if closed and is_contributor_group(part[closed:]):
        return [part[:closed], part[closed:]]
    return [part]


def _parts(field: str, named: bool = False) -> tuple[list[str], bool]:
    """An author *field* as stripped parts (:func:`_outside_entries`,
    :func:`_group_split`), and whether a cut is warned about: in a *named*
    field, any cut on a separator; in an address field, a cut after a name
    (a part with no ``<``, ``>`` or ``@``; an address entry ends an
    author), which could be inside one name."""
    pieces = _outside_entries(field, named)
    raw = [name for part in pieces for name in _group_split(part)]
    parts = [part.strip() for part in raw if part.strip()]
    if named:
        return parts, len(pieces) > 1
    return parts, any(not _ADDRESS_MARK_RE.search(left) for left in parts[:-1])


class _Field(NamedTuple):
    """A field's key (``AUTHOR``, ``MAINTAINER_EMAIL``) and whether it is a
    name field, cut only after a mailbox (:func:`_parts`)."""

    key: str
    named: bool


#: The keys of the author name and address fields.
AUTHOR_KEYS = ("AUTHOR", "AUTHOR_EMAIL")


class _Report(NamedTuple):
    """Which ``WARNING:`` lines one read of an author field gives."""

    #: A field over a cap (:func:`_capped`).
    caps: bool
    #: Where the ``(key, entry)`` of an address entry holding no address
    #: is noted (:func:`_read_entry`); ``None``: not warned about.
    addresses: list[tuple[str, str]] | None


def _capped(field: str, parts: list[str], what: _Field, warn: bool) -> list[str]:
    """*parts* of *field* within :data:`AUTHOR_FIELD_MAX_CHARS` and
    :data:`AUTHOR_FIELD_MAX_NAMES`: past the first, the last part (maybe
    cut; a name field's one part when it holds no mailbox) is dropped too.
    With *warn*, one ``WARNING:`` once per field and process naming the
    cap hit (the character cap when both are) and what was read
    (:func:`~pitloom.extract._author_warnings.warn_field_cap`)."""
    cut = len(field) > AUTHOR_FIELD_MAX_CHARS
    if not cut and len(parts) <= AUTHOR_FIELD_MAX_NAMES:
        return parts
    kept = parts[: -1 if cut else None][:AUTHOR_FIELD_MAX_NAMES]
    if warn:
        cap = (
            Cap(AUTHOR_FIELD_MAX_CHARS, "character", "author-field", "FIELD")
            if cut
            else Cap(AUTHOR_FIELD_MAX_NAMES, "entry", "author-field", "FIELD")
        )
        read = counted(len(kept), "entry", "entries") if kept else None
        warn_field_cap(field, what.key, cap, read)
    return kept


def is_unset_placeholder(value: object) -> bool:
    """Whether *value* is the ``UNKNOWN`` placeholder older setuptools
    writes for an unset author field."""
    return isinstance(value, str) and value.strip() == "UNKNOWN"


def stated_text(value: str | None) -> str:
    """*value* stripped, ``""`` when absent, blank or
    :func:`is_unset_placeholder`."""
    return "" if is_unset_placeholder(value) else (value or "").strip()


def _display_name(name: str, addr: str) -> str | None:
    """An entry's display name, ``None`` when blank or the ``Unknown``
    pdm-backend and ``pyproject-metadata`` write for an author declaring
    only an address."""
    name = name.strip()
    return None if not name or (name == "Unknown" and addr.strip()) else name


def _quoted(name: str) -> str | None:
    """*name*'s text when it is all one quoted display name, in ``"`` or
    typographic quotes; else ``None``."""
    if len(name) > 1 and (
        name[0] == name[-1] == '"' or _TYPOGRAPHIC_QUOTES.get(name[0]) == name[-1]
    ):
        return unquote(name) if name[0] == '"' else name[1:-1]
    return None


def collapse_whitespace(name: str) -> str:
    """*name* with each run of white space one space and none at its ends:
    a folded ``Author`` (``Ann\\n        Bob``) reads as the ``Ann\\nBob``
    and ``Ann Bob`` other surfaces write."""
    return " ".join(name.split())


def _mailbox_name(head: str) -> str:
    """The display name *head*, before an ``<address>`` or a whole name
    entry: its text when all one quoted display name (:func:`_quoted`),
    else *head*, white space collapsed (:func:`collapse_whitespace`)."""
    quoted = _quoted(head.strip())
    return collapse_whitespace(head if quoted is None else quoted)


def _sole_address(head: str) -> bool:
    """Whether *head*, the text before an entry's last ``<``, holds no
    other angle bracket outside a quoted display name: it is all one
    (:func:`_quoted`, escaped quotes too) or each of its brackets is inside
    one (:class:`_Quoting`), as in ``"A <b>" <a@x.org>``."""
    if _quoted(head.strip()) is not None:
        return True
    quoting = _Quoting(head)
    return all(quoting.inside(found.start()) for found in _ANGLE_RE.finditer(head))


def _read_entry(
    entry: str, key: str, noted: list[tuple[str, str]] | None
) -> list[tuple[str, str]]:
    """``(raw display name, address)`` of one entry, a part of an author
    field (:func:`_parts`). An entry holding no ``<``, ``>`` or ``@`` is a
    name (:func:`_mailbox_name`). Any other is one mailbox, its address
    checked as written -- after the last ``<`` and closed by ``>``, less a
    trailing comment: :func:`email.utils.getaddresses` drops a space or an
    extra ``@`` (``a@b c`` reads ``a@bc``), and that address is no one's.
    Its display name is all the text before a sole ``<``
    (:func:`_mailbox_name`), a comma in it included (``Doe, Jane
    <j@x.org>``), as are brackets inside quotes (:func:`_sole_address`); a
    bare address may give one in a comment (``a@x.org (Ann)``). With no
    valid address, or a second ``<`` (two addresses are no one mailbox),
    nothing before the last ``<`` is kept, and a display name stated before
    a sole ``<`` is kept alone (``("Ann", "")``); the address, unless an
    empty ``<>``, is not recorded, its ``(key, entry)`` appended to *noted*
    (when given) for
    :func:`~pitloom.extract._author_warnings.warn_not_addresses`, as is an
    entry left with nothing."""
    if not _ADDRESS_MARK_RE.search(entry):
        name = _mailbox_name(entry)
        return [(name, "")] if name else []
    head, angle, tail = _TRAILING_COMMENT_RE.sub("", entry).rpartition("<")
    tail = tail.strip()
    written = tail.removesuffix(">").strip()
    sole = _sole_address(head)
    stated = _mailbox_name(head) if angle and sole else ""
    if sole and (not angle or tail.endswith(">")) and _ADDRESS_RE.fullmatch(written):
        if angle:
            return [(stated, written)]
        found = [
            (name, addr.strip())
            for name, addr in getaddresses([entry])
            if addr.strip() == written
        ]
        if found:
            return found
    name = _display_name(stated, written) or ""
    if noted is not None and (written or not name):
        noted.append((key, entry.strip()))
    return [(name, "")] if name else []


def _field_entries(
    text: str, what: _Field, splits: list[AuthorSplit], report: _Report
) -> list[tuple[str, str]]:
    """``(raw display name, address)`` per part of the field *text*
    (:func:`_parts`, :func:`_read_entry`), capped (:func:`_capped`); a
    warned split is appended to *splits*, as is a name field read as one
    part that holds a :data:`_JOINER_RE` outside quotes and ``<...>``."""
    read = text[:AUTHOR_FIELD_MAX_CHARS]
    parts, warned = _parts(read, what.named)
    parts = _capped(text, parts, what, report.caps)
    one = len(parts) == 1 and what.named
    if (warned and len(parts) > 1) or (one and any(_separators(parts[0], _JOINER_RE))):
        splits.append(AuthorSplit(text, len(parts), what.key, what.named))
    return [
        pair for part in parts for pair in _read_entry(part, what.key, report.addresses)
    ]


def _pairs(entries: list[tuple[str, str]]) -> list[NameEmail]:
    return [(_display_name(name, addr), addr or None) for name, addr in entries]


def author_pairs(
    names: str | None,
    addresses: str | None,
    *,
    splits: list[AuthorSplit],
    quiet: bool,
    address_warnings: bool = True,
    keys: tuple[str, str] = AUTHOR_KEYS,
) -> list[NameEmail]:
    """``(name, email)`` pairs from a free-text name field and its address
        field (``Author``/``Author-email``, ``author``/``author_email``).

        Both are cut on ``,`` and ``;`` outside a quoted display name and an
        ``<address>``, never on ``and``, a contributor group after an
        ``<address>`` an entry of its own (:func:`_field_entries`): the address
        field after any separator, the name field only after a closed
        ``<address>`` or a bare address (``Author: Doe, Jane`` and ``Author:
        Ann and Bob`` are one author each; ``Author: Ann <a@x.org>; Bob
        <b@x.org>`` is two, as in ``Author-email``). Each entry is read alike
        (:func:`_read_entry`): one with no ``<``, ``>`` or ``@`` a name, any
        other one mailbox. So ``Author-email: Doe, Jane <j@x.org>`` is ``Doe``,
        and ``Jane`` with the address; ``Author: Doe, Jane <j@x.org>`` is
        ``Doe, Jane`` with it. The legacy pair -- a name and one bare address
        -- is one author with both, or, when the name holds an address, the
        two on their own. A name is never paired with an
        address by position: one name and two addresses are three authors.
        Repeats are dropped, and a name already read from the address field;
        ``UNKNOWN`` and blank fields count as absent, and so does an
        ``Unknown`` display name beside an address.

        Order: the address field's authors first, then the name field's, each
        in field order. Hatchling and
        setuptools write the authors that have an address to ``Author-email``
        and the rest to ``Author``, each in declared order, so the interleaving
        declared in ``pyproject.toml`` cannot be recovered from these headers;
        the one fixed rule keeps the result stable.

        An address entry holding no address of the form ``local@domain`` is not
        recorded, its stated display name kept, with one ``WARNING:`` per field
        (unless *quiet* or not *address_warnings*). An address field cut where
        a separator could be inside a name, and a name field cut at all, are
        appended to *splits*, for the caller's warning, as is a name field read
    as one author though it holds ``,``, ``;`` or ``and`` (one entry). A field over
        :data:`AUTHOR_FIELD_MAX_CHARS` or :data:`AUTHOR_FIELD_MAX_NAMES` is read
        up to the cap, with one
        ``WARNING:`` once per field and process: a cap warns whenever the value
        read is used, and *quiet* marks a read whose value is discarded (or
        re-reads a field already reported), which warns about nothing. A
        ``WARNING:`` names a field by its key in *keys* (name field, address
        field).
    """
    noted: list[tuple[str, str]] | None = [] if address_warnings and not quiet else None
    report = _Report(caps=not quiet, addresses=noted)
    names_text = stated_text(names)
    address_field = _Field(keys[1], named=False)
    parsed = _field_entries(stated_text(addresses), address_field, splits, report)
    named = _field_entries(names_text, _Field(keys[0], named=True), splits, report)
    warn_not_addresses(noted or [])
    if named and len(parsed) == 1 and not parsed[0][0].strip() and parsed[0][1]:
        # The legacy pair: the address cannot be fairly attributed to a
        # name that wrote its own, so it stands on its own.
        if not _ADDRESS_MARK_RE.search(names_text):
            parsed = [(named[0][0], parsed[0][1])]
        else:
            parsed = [*named, *parsed]
        named = []
    pairs = _pairs(parsed)
    known = {name for name, _ in pairs}
    pairs.extend(pair for pair in _pairs(named) if pair[1] or pair[0] not in known)
    return list(dict.fromkeys(pairs))  # every pair names a name or address


def read_author_fields(
    names: str | None,
    addresses: str | None,
    *,
    quiet: bool = False,
    splits: list[AuthorSplit] | None = None,
    hint: str = "",
) -> list[dict[str, str]]:
    """:func:`author_pairs` as ``{name?, email?}`` dicts (the shape of
    :attr:`pitloom.core.project.ProjectMetadata.authors`).

    A split field gets one ``WARNING:`` per key and call ending with *hint*
    (unless *quiet*: a read whose value is discarded, which warns about
    nothing); with *splits* given, the splits are appended to it
    instead, for a caller that warns only once it knows these authors are
    the ones used (:func:`warn_author_splits`).
    """
    noted: list[AuthorSplit] = [] if splits is None else splits
    authors: list[dict[str, str]] = []
    for name, addr in author_pairs(names, addresses, splits=noted, quiet=quiet):
        author = {"name": name} if name else {}
        if addr:
            author["email"] = addr
        authors.append(author)
    if splits is None:
        warn_author_splits(noted, quiet=quiet, hint=hint)
    return authors
