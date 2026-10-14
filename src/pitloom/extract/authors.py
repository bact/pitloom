# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one reading of a free-text author field and its address field, on
every surface: core-metadata ``Author``/``Author-email`` (wheel, sdist
``PKG-INFO``, a dependency's installed or PyPI record), ``setup.cfg``
``author``/``author_email`` and ``setup.py`` ``setup(author=...)``.

Both fields are split on ``,`` and ``;`` outside a quoted display name
and an ``<address>``; a name field's parts then on ``and``, never an
address field's (backends write a structured ``{name = "Ann and Bob",
email = ...}`` as ``Ann and Bob <...>``). A field cannot tell a list from
one name containing a comma, so a split is warned about. Each
comma-separated part is tested on its own for a contributor group (``Jane
and others``, ``J. et al.``), which is not split on ``and``; a group after
an ``<address>`` (``Jane <j@x.org> et al.``) is a part of its own. A part
holding no ``<``, ``>`` or ``@`` is a name; any other is read as an address
entry: an address that is no address is not recorded, the
name stated before it kept, with one ``WARNING:`` per field naming the
count and the first few. One pass reads each field, capped
(:data:`AUTHOR_FIELD_MAX_CHARS`, :data:`AUTHOR_FIELD_MAX_NAMES`): a cap
warns whenever the value read is used, a read whose value is discarded
(*quiet*) warns about nothing. A structured entry -- one display name in
``"`` or typographic quotes, one ``[project].authors`` table, one Poetry
``authors`` string -- is one author and is never split.

See also: :mod:`pitloom.extract._author_warnings` (the warnings) and
:mod:`pitloom.extract._core_metadata`
(:func:`~pitloom.extract._core_metadata.parse_core_metadata_authors`).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from email.utils import getaddresses, quote, unquote
from typing import TYPE_CHECKING, NamedTuple

from pitloom.extract._author_warnings import (
    ADDRESS_SEPARATORS,
    CORE_METADATA_HINT,
    NAME_SEPARATORS,
    AuthorSplit,
    counted,
    dependency_author_splits,
    report_dependency_splits,
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
    "CORE_METADATA_HINT",
    "AuthorSplit",
    "author_pairs",
    "dependency_author_pairs",
    "dependency_author_splits",
    "is_contributor_group",
    "is_unset_placeholder",
    "read_author_fields",
    "warn_author_splits",
    "warn_project_authors_unread",
]

#: A name standing for a group of further contributors: ``Others``, ``and
#: others (see AUTHORS)``, ``et al.`` -- whole words, so ``Jan Brothers`` is
#: a person.
_CONTRIBUTOR_GROUP_RE = re.compile(r"\b(?:others|et\s+al)\b", re.IGNORECASE)
#: A ``,`` or ``;`` between two entries, then a whole-word ``and`` between
#: two names: each outside a quoted display name and an address
#: (:func:`_outside_entries`).
_ENTRY_SEPARATOR_RE = re.compile(r"[,;]")
_AND_RE = re.compile(r"\band\b")
#: An angle bracket, opening or closing an address.
_ANGLE_RE = re.compile(r"[<>]")
#: An ``<address>``, left out when testing a name for a contributor group.
_ADDRESS_PART_RE = re.compile(r"<[^<>]*>")
#: What makes a part an address entry rather than a name.
_ADDRESS_MARK_RE = re.compile(r"[<>@]")
#: A typographic opening quote and its closing quote.
_TYPOGRAPHIC_QUOTES = {"“": "”", "‘": "’"}
#: A ``"`` or typographic quote, opening or closing a quoted display name.
_QUOTE_RE = re.compile('["“”‘’]')

#: The most characters of one free-text author or address field read; the
#: rest is not read (its last, possibly cut, name neither).
AUTHOR_FIELD_MAX_CHARS = 64 * 1024
#: The most names (or address entries) read from one author field.
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


def _outside_entries(text: str, separator: re.Pattern[str]) -> list[str]:
    """*text* split on *separator* where it is neither inside a quoted
    display name (:class:`_Quoting`) nor inside a ``<...>`` address: where
    the next angle bracket after it is not ``>``. One pass, each bracket
    and quote looked at once."""
    angles = [(m.start(), m.group()) for m in _ANGLE_RE.finditer(text)]
    quoting = _Quoting(text)

    def spans() -> Iterator[tuple[int, int]]:
        index = 0
        for found in separator.finditer(text):
            while index < len(angles) and angles[index][0] < found.end():
                index += 1
            in_address = index < len(angles) and angles[index][1] == ">"
            if not in_address and not quoting.inside(found.start()):
                yield found.span()

    return _split_at(text, spans())


def _and_split(text: str, splits_and: bool) -> list[str]:
    """*text* split on ``and`` (:func:`_outside_entries`) if *splits_and*."""
    return _outside_entries(text, _AND_RE) if splits_and else [text]


def _group_split(part: str, splits_and: bool) -> list[str]:
    """One comma-separated *part* of a field as entries: a contributor group
    stays whole, as a ``[project].authors`` entry does, unless it follows
    an ``<address>`` (``Jane <j@x.org> et al.``), which ends the entry
    before it; any other part is split on ``and`` if *splits_and*."""
    bare = _ADDRESS_PART_RE.sub(" ", part)
    if not is_contributor_group(bare):
        return _and_split(part, splits_and)
    closed = part.rfind(">") + 1
    if closed and is_contributor_group(part[closed:]):
        return [*_and_split(part[:closed], splits_and), part[closed:]]
    return [part]


#: An address Pitloom records: one ``@``, text on both sides, no space.
_ADDRESS_RE = re.compile(r"[^@\s]+@[^@\s]+")
#: An RFC 5322 comment ending an address entry: ``ann@example.com (Ann)``.
_TRAILING_COMMENT_RE = re.compile(r"\([^()]*\)\s*$")


def _parts(field: str, splits_and: bool) -> tuple[list[str], bool]:
    """*field* as stripped parts (:func:`_outside_entries`,
    :func:`_group_split`), and whether a split was a guess: a separator
    after a name (a part with no ``<``, ``>`` or ``@``; an address entry
    ends an author) could be inside one name."""
    raw = [
        name
        for part in _outside_entries(field, _ENTRY_SEPARATOR_RE)
        for name in _group_split(part, splits_and)
    ]
    parts = [part.strip() for part in raw if part.strip()]
    guessed = any(not _ADDRESS_MARK_RE.search(left) for left in parts[:-1])
    return parts, guessed


class _Field(NamedTuple):
    """A field's key, the singular and plural of one of its parts, and the
    separators it is split on, as a split warning names them: ``and`` only
    in a name field."""

    key: str
    unit: str
    units: str
    separators: tuple[str, ...]


_NAME_FIELD = _Field("AUTHOR", "name", "names", NAME_SEPARATORS)
_ADDRESS_FIELD = _Field("AUTHOR_EMAIL", "entry", "entries", ADDRESS_SEPARATORS)


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
    cut) is dropped too. With *warn*, one ``WARNING:`` once per field and
    process naming the cap hit (the character cap when both are) and what
    was read (:func:`~pitloom.extract._author_warnings.warn_field_cap`)."""
    cut = len(field) > AUTHOR_FIELD_MAX_CHARS
    if not cut and len(parts) <= AUTHOR_FIELD_MAX_NAMES:
        return parts
    kept = parts[: -1 if cut else None][:AUTHOR_FIELD_MAX_NAMES]
    if warn:
        cap = (
            Cap(AUTHOR_FIELD_MAX_CHARS, "character", "author-field", "FIELD")
            if cut
            else Cap(AUTHOR_FIELD_MAX_NAMES, what.unit, "author-field", "FIELD")
        )
        read = counted(len(kept), what.unit, what.units)
        warn_field_cap(field, what.key, cap, read)
    return kept


def is_unset_placeholder(value: object) -> bool:
    """Whether *value* is the ``UNKNOWN`` placeholder older setuptools
    writes for an unset author field."""
    return isinstance(value, str) and value.strip() == "UNKNOWN"


def _stated_text(value: str | None) -> str:
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


def _ascii_quoted(entry: str) -> str:
    """*entry* with a display name in typographic quotes (``“Doe, Jane”
    <j@x.org>``) put in ``"`` quotes, as :func:`email.utils.getaddresses`
    reads them."""
    head, angle, tail = entry.rpartition("<")
    name = head.strip()
    if angle and len(name) > 1 and _TYPOGRAPHIC_QUOTES.get(name[0]) == name[-1]:
        return f'"{quote(name[1:-1])}" <{tail}'
    return entry


def _read_entry(
    entry: str, key: str, noted: list[tuple[str, str]] | None
) -> list[tuple[str, str]]:
    """``(raw display name, address)`` of one part of a field. A part
    holding no ``<``, ``>`` or ``@`` is a name, unquoted
    (:func:`_quoted`). Otherwise the address is checked as written --
    after the last ``<`` and closed by ``>``, less a trailing comment:
    :func:`email.utils.getaddresses` drops a space or an extra ``@`` (``a@b
    c`` reads ``a@bc``), and that address is no one's. With no valid
    address, a display name stated before the ``<`` is kept alone (``("Ann",
    "")``); the address, unless an empty ``<>``, is not recorded, its
    ``(key, entry)`` appended to *noted* (when given) for
    :func:`~pitloom.extract._author_warnings.warn_not_addresses`, as is an
    entry left with nothing."""
    if not _ADDRESS_MARK_RE.search(entry):
        quoted = _quoted(entry)
        name = entry if quoted is None else quoted
        return [(name, "")] if name.strip() else []
    entry = _ascii_quoted(entry)
    head, angle, tail = _TRAILING_COMMENT_RE.sub("", entry).rpartition("<")
    tail = tail.strip()
    written = tail.removesuffix(">").strip()
    if (not angle or tail.endswith(">")) and _ADDRESS_RE.fullmatch(written):
        found = [
            (name, addr.strip())
            for name, addr in getaddresses([entry])
            if addr.strip() == written
        ]
        if found:
            return found
    stated = unquote(head.strip()) if angle and not _ANGLE_RE.search(head) else ""
    name = _display_name(stated, written) or ""
    if noted is not None and (written or not name):
        noted.append((key, entry.strip()))
    return [(name, "")] if name else []


def _field_entries(
    text: str, what: _Field, splits: list[AuthorSplit], report: _Report
) -> list[tuple[str, str]]:
    """``(raw display name, address)`` per part of the field *text*
    (:func:`_parts`, :func:`_read_entry`), capped (:func:`_capped`); a
    guessed split is appended to *splits*."""
    parts, guessed = _parts(text[:AUTHOR_FIELD_MAX_CHARS], what is _NAME_FIELD)
    parts = _capped(text, parts, what, report.caps)
    if guessed and len(parts) > 1:
        splits.append(AuthorSplit(text, len(parts), what.separators))
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
) -> list[NameEmail]:
    """``(name, email)`` pairs from a free-text name field and its address
    field (``Author``/``Author-email``, ``author``/``author_email``).

    Both fields are read alike (:func:`_field_entries`): split on ``,``
    and ``;`` outside a quoted display name and an ``<address>``, the name
    field's parts on ``and`` too -- a comma-separated part that is a
    contributor group stays whole, one after an ``<address>`` is its own --
    a part with no ``<``, ``>`` or ``@`` a name, any other an address
    entry. So ``Author-email: Doe, Jane <j@x.org>`` is ``Doe`` and ``Jane``
    with the address, as in ``Author``; ``Author-email: Ann and Bob
    <t@x.org>`` is one author, ``Author: Ann and Bob <t@x.org>`` two. The
    legacy pair -- names and one bare address -- is one author with both,
    or, when the names split or hold an address,
    name-only authors plus the address on its own. A name is never paired
    with an address by position: two names and two addresses are four
    authors. Repeats are dropped, and a name already read from the address
    field; ``UNKNOWN`` and blank fields count as absent, and so does an
    ``Unknown`` display name beside an address.

    Order: the address field's authors first, then the name field's, each
    in field order. Hatchling and
    setuptools write the authors that have an address to ``Author-email``
    and the rest to ``Author``, each in declared order, so the interleaving
    declared in ``pyproject.toml`` cannot be recovered from these headers;
    the one fixed rule keeps the result stable.

    An address entry holding no address of the form ``local@domain`` is not
    recorded, its stated display name kept, with one ``WARNING:`` per field
    (unless *quiet* or not *address_warnings*). Each field split where a
    separator could be inside a name is appended to *splits*, for the
    caller's one warning. A field over :data:`AUTHOR_FIELD_MAX_CHARS` or
    :data:`AUTHOR_FIELD_MAX_NAMES` is read up to the cap, with one
    ``WARNING:`` once per field and process: a cap warns whenever the value
    read is used, and *quiet* marks a read whose value is discarded (or
    re-reads a field already reported), which warns about nothing.
    """
    noted: list[tuple[str, str]] | None = [] if address_warnings and not quiet else None
    report = _Report(caps=not quiet, addresses=noted)
    names_text = _stated_text(names)
    parsed = _field_entries(_stated_text(addresses), _ADDRESS_FIELD, splits, report)
    named = _field_entries(names_text, _NAME_FIELD, splits, report)
    warn_not_addresses(noted or [])
    if named and len(parsed) == 1 and not parsed[0][0].strip() and parsed[0][1]:
        # The legacy pair: the address cannot be fairly attributed to any
        # one of several names, nor to one that wrote its own, so it stands
        # on its own.
        if len(named) == 1 and not _ADDRESS_MARK_RE.search(names_text):
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

    A split name gets one ``WARNING:`` per call ending with *hint* (unless
    *quiet*: a read whose value is discarded, which warns about nothing);
    with *splits* given, the split names are appended to it
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


def dependency_author_pairs(
    package: str, names: str | None, addresses: str | None
) -> list[NameEmail]:
    """A dependency's originator pairs from one name/address field pair, by
    :func:`author_pairs`. A split is reported once per document by the
    enclosing :func:`dependency_author_splits` block, or at once outside
    one; an address entry that is no address is left out quietly (another
    project's record, one line each would flood a large environment). A
    field over a cap warns: these authors are used."""
    splits: list[AuthorSplit] = []
    pairs = author_pairs(
        names, addresses, splits=splits, quiet=False, address_warnings=False
    )
    report_dependency_splits(package, splits)
    return pairs
