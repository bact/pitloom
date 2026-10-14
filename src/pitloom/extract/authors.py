# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one reading of a free-text author field and its address field, on
every surface: core-metadata ``Author``/``Author-email`` (wheel, sdist
``PKG-INFO``, a dependency's installed or PyPI record), ``setup.cfg``
``author``/``author_email`` and ``setup.py`` ``setup(author=...)``.

A free-text name field is split on ``,`` and ``and``: it cannot tell a list
from one name containing a comma, so a split is warned about. Each
comma-separated part is tested on its own for a contributor group
(``Jane and others``, ``J. et al.``), which is not split on ``and``; a
name part ending in ``<address>`` is read as an address entry, and a group
after it (``Jane <j@x.org> et al.``) is a part of its own; an address that
is no address is not recorded, the name stated before it kept, with one
``WARNING:`` per field naming the count and the first few. One pass
reads each field, capped (:data:`AUTHOR_FIELD_MAX_CHARS`,
:data:`AUTHOR_FIELD_MAX_NAMES`): a cap warns whenever the value read is
used, a read whose value is discarded (*quiet*) warns about nothing. A
structured entry -- one ``Author-email`` display name in ``"`` or
typographic quotes, one ``[project].authors`` table, one Poetry ``authors``
string -- is one author and is never split.

See also: :mod:`pitloom.extract._core_metadata`
(:func:`~pitloom.extract._core_metadata.parse_core_metadata_authors`).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import re
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from email.utils import getaddresses, quote, unquote
from typing import TYPE_CHECKING, NamedTuple

from pitloom.logging_config import Cap, loggable, one_line, warn_over_cap

if TYPE_CHECKING:
    #: A name/address pair; either part may be None.
    NameEmail = tuple[str | None, str | None]

_logger = logging.getLogger(__name__)


#: A name standing for a group of further contributors: ``Others``, ``and
#: others (see AUTHORS)``, ``et al.`` -- whole words, so ``Jan Brothers`` is
#: a person.
_CONTRIBUTOR_GROUP_RE = re.compile(r"\b(?:others|et\s+al)\b", re.IGNORECASE)
#: A comma, then a whole-word ``and``: between two names, outside an
#: address (:func:`_outside_addresses`).
_COMMA_RE = re.compile(r",")
_AND_RE = re.compile(r"\band\b")
#: A ``;`` between two address entries of one name part.
_SEMICOLON_RE = re.compile(r";")
#: An angle bracket, opening or closing an address.
_ANGLE_RE = re.compile(r"[<>]")
#: An ``<address>``, left out when testing a name for a contributor group.
_ADDRESS_PART_RE = re.compile(r"<[^<>]*>")

#: The most characters of one free-text author or address field read; the
#: rest is not read (its last, possibly cut, name neither).
AUTHOR_FIELD_MAX_CHARS = 64 * 1024
#: The most names (or address entries) read from one author field.
AUTHOR_FIELD_MAX_NAMES = 1000
#: Characters of a field shown in a warning.
_SHOWN_CHARS = 120
#: Fields (or entries) shown in a warning naming several.
_SHOWN_FIELDS = 3


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


def _outside_addresses(text: str, separator: re.Pattern[str]) -> list[str]:
    """*text* split on *separator* where it is not inside a ``<...>``
    address: where the next angle bracket after it is not ``>``. One pass,
    each bracket looked at once."""
    angles = [(m.start(), m.group()) for m in _ANGLE_RE.finditer(text)]

    def spans() -> Iterator[tuple[int, int]]:
        index = 0
        for found in separator.finditer(text):
            while index < len(angles) and angles[index][0] < found.end():
                index += 1
            if index == len(angles) or angles[index][1] == "<":
                yield found.span()

    return _split_at(text, spans())


def _outside_quotes(text: str) -> list[str]:
    """*text* split on ``,`` and ``;`` outside a quoted display name: where
    an even number of ``"`` follow, and not between a typographic opening
    quote (U+201C, U+2018) and its closing quote later in *text* (a closing
    quote alone, an apostrophe, quotes nothing). One pass."""
    quotes_after = text.count('"')
    last = {close: text.rfind(close) for close in _TYPOGRAPHIC_QUOTES.values()}

    def spans() -> Iterator[tuple[int, int]]:
        nonlocal quotes_after
        awaited = ""  # the closing quote of an open typographic quote
        for found in _ENTRY_TOKEN_RE.finditer(text):
            mark = found.group()
            close = _TYPOGRAPHIC_QUOTES.get(mark, "")
            if mark == '"':
                quotes_after -= 1
            elif close and not awaited and last[close] > found.start():
                awaited = close
            elif mark == awaited:
                awaited = ""
            elif mark in ",;" and not awaited and quotes_after % 2 == 0:
                yield found.span()

    return _split_at(text, spans())


def _group_split(part: str) -> list[str]:
    """One comma-separated *part* of a name field as names: a contributor
    group stays whole, as a ``[project].authors`` entry does, unless it
    follows an ``<address>`` (``Jane <j@x.org> et al.``), which ends the
    entry before it; any other part is split on ``and``."""
    bare = _ADDRESS_PART_RE.sub(" ", part)
    if not is_contributor_group(bare):
        return _outside_addresses(part, _AND_RE)
    closed = part.rfind(">") + 1
    if closed and is_contributor_group(part[closed:]):
        return [*_outside_addresses(part[:closed], _AND_RE), part[closed:]]
    return [part]


class AuthorSplit(NamedTuple):
    """A free-text name field split into several names, and how many."""

    field: str
    names: int


def _names(name: str) -> tuple[list[str], bool]:
    """A comma-/``and``-separated name list as stripped names, and whether
    a split was a guess: a separator not right after an ``<address>``
    (which ends an author) could be inside one name. Each comma-separated
    part is tested for a contributor group on its own (:func:`_group_split`)."""
    raw = [
        name
        for part in _outside_addresses(name, _COMMA_RE)
        for name in _group_split(part)
    ]
    parts = [part.strip() for part in raw if part.strip()]
    guessed = any(not left.endswith(">") for left in parts[:-1])
    return parts, guessed


class _Report(NamedTuple):
    """Which ``WARNING:`` lines one read of an author field gives."""

    #: A field over a cap (:func:`_capped`).
    caps: bool
    #: Where the ``(key, entry)`` of an address entry holding no address
    #: is noted (:func:`_read_entry`); ``None``: not warned about.
    addresses: list[tuple[str, str]] | None


def _split_names(
    name: str, splits: list[AuthorSplit] | None, report: _Report
) -> list[str]:
    """:func:`_names`, capped (:func:`_capped`); a guessed split is
    appended to *splits* (when given)."""
    parts, guessed = _names(name[:AUTHOR_FIELD_MAX_CHARS])
    parts = _capped(name, parts, ("AUTHOR", "name", "names"), report.caps)
    if splits is not None and guessed and len(parts) > 1:
        splits.append(AuthorSplit(name, len(parts)))
    return parts


def _capped(
    field: str, parts: list[str], what: tuple[str, str, str], warn: bool
) -> list[str]:
    """*parts* of *field* within :data:`AUTHOR_FIELD_MAX_CHARS` and
    :data:`AUTHOR_FIELD_MAX_NAMES`: past the first, the last part (maybe
    cut) is dropped too. *what* is the field's key and the singular and
    plural of a part. With *warn*, one ``WARNING:`` once per field (its
    whole text) and process (:func:`~pitloom.logging_config.warn_over_cap`),
    naming the cap hit (the character cap when both are) and what was read."""
    cut = len(field) > AUTHOR_FIELD_MAX_CHARS
    if not cut and len(parts) <= AUTHOR_FIELD_MAX_NAMES:
        return parts
    kept = parts[: -1 if cut else None][:AUTHOR_FIELD_MAX_NAMES]
    key, unit, units = what
    if warn:
        cap = (
            Cap(AUTHOR_FIELD_MAX_CHARS, "character", "author-field", "FIELD")
            if cut
            else Cap(AUTHOR_FIELD_MAX_NAMES, unit, "author-field", "FIELD")
        )
        read = _counted(len(kept), unit, units)
        digest = hashlib.sha256(field.encode("utf-8", "surrogatepass")).hexdigest()
        outcome = f"only the first {read} read of {_shown(field)}"
        warn_over_cap(_logger, cap, key, outcome, once=True, key=f"{key}:{digest}")
    return kept


def _counted(count: int, unit: str, units: str) -> str:
    """*count* and *unit*, or *units* unless one: ``1 name``, ``2 names``."""
    return f"{count} {unit if count == 1 else units}"


def _shown(field: str) -> str:
    """*field* for a warning as one quoted literal, escaped once: on one
    line, at most :data:`_SHOWN_CHARS` characters, its ``repr`` when
    printable, else its ASCII-escaped literal
    (:func:`~pitloom.logging_config.loggable`); ``...`` after it when cut."""
    text = " ".join(field.split())
    shown = text[:_SHOWN_CHARS]
    escaped = loggable(shown)
    literal = repr(shown) if escaped == shown else escaped
    return literal + ("..." if len(text) > _SHOWN_CHARS else "")


def _shown_list(fields: list[str]) -> str:
    """One field :func:`_shown`, or several as ``[a, b, c, ...]``: the first
    :data:`_SHOWN_FIELDS`, ``...`` when there are more."""
    if len(fields) == 1:
        return _shown(fields[0])
    shown = [_shown(field) for field in fields[:_SHOWN_FIELDS]]
    if len(fields) > _SHOWN_FIELDS:
        shown.append("...")
    return f"[{', '.join(shown)}]"


#: One line per document whose free-text author names were split; the
#: first ``%s`` is the string, or the strings when several were split
#: (:func:`_shown_list`); the last ``%s`` is the caller's hint.
_NAMES_SPLIT_MESSAGE = (
    "AUTHOR=%s: split into %s on ',' / 'and'; a free-text author field"
    " cannot tell a list from one name containing a comma%s"
)
#: The hint for a split read from core metadata.
CORE_METADATA_HINT = (
    " -- use --project-dir or an sdist with pyproject.toml for declared"
    " [project].authors"
)
#: One line per document whose dependencies' free-text authors were split.
_DEPENDENCY_SPLIT_MESSAGE = (
    "AUTHOR=%s: split into %s on ',' / 'and' (PACKAGE=%s; %s split in all); a"
    " free-text author field cannot tell a list from one name containing a"
    " comma"
)


def warn_author_splits(
    splits: list[AuthorSplit], *, quiet: bool = False, hint: str
) -> None:
    """One ``WARNING:`` for all the names in *splits* (unless *quiet*),
    ending with *hint*."""
    if splits and not quiet:
        total = sum(split.names for split in splits)
        _logger.warning(
            _NAMES_SPLIT_MESSAGE,
            _shown_list([split.field for split in splits]),
            _counted(total, "name", "names"),
            hint,
        )


def is_unset_placeholder(value: object) -> bool:
    """Whether *value* is the ``UNKNOWN`` placeholder older setuptools
    writes for an unset author field."""
    return isinstance(value, str) and value.strip() == "UNKNOWN"


def _stated_text(value: str | None) -> str:
    """*value* stripped, ``""`` when absent, blank or
    :func:`is_unset_placeholder`."""
    return "" if is_unset_placeholder(value) else (value or "").strip()


def _display_name(name: str, addr: str) -> str | None:
    """An address entry's display name, ``None`` when blank or the
    ``Unknown`` pdm-backend and ``pyproject-metadata`` write for an author
    declaring only an address."""
    name = name.strip()
    return None if not name or (name == "Unknown" and addr.strip()) else name


#: An address Pitloom records: one ``@``, text on both sides, no space.
_ADDRESS_RE = re.compile(r"[^@\s]+@[^@\s]+")
#: A typographic opening quote and its closing quote.
_TYPOGRAPHIC_QUOTES = {"\u201c": "\u201d", "\u2018": "\u2019"}
#: A ``"`` or typographic quote (opening or closing a quoted display
#: name), or a ``,`` or ``;`` between two entries when outside one.
_ENTRY_TOKEN_RE = re.compile('[",;\u201c\u201d\u2018\u2019]')
#: An RFC 5322 comment ending an address entry: ``ann@example.com (Ann)``.
_TRAILING_COMMENT_RE = re.compile(r"\([^()]*\)\s*$")
#: One line per field holding address entries that hold no address: the
#: field's key (``AUTHOR_EMAIL``, or ``AUTHOR`` for an entry in the name
#: field), the entries (:func:`_shown_list`) and, when several, how many.
_NOT_AN_ADDRESS_MESSAGE = "%s=%s: not an email address; %snot recorded"


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
    """``(raw display name, address)`` of one address entry. The address is
    checked as written -- after the last ``<`` and closed by ``>``, less a
    trailing comment: :func:`email.utils.getaddresses` drops a space or an
    extra ``@`` (``a@b c`` reads ``a@bc``), and that address is no one's.
    With no valid address, a display name stated before the ``<`` is kept
    alone (``("Ann", "")``); the address, unless an empty ``<>``, is not
    recorded, its ``(key, entry)`` appended to *noted* (when given) for
    :func:`_warn_not_addresses`, as is an entry left with nothing."""
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


def _warn_not_addresses(noted: list[tuple[str, str]]) -> None:
    """One ``WARNING:`` per key of *noted*, in order: its entries holding
    no address, the first few shown, and how many when several."""
    for key in dict.fromkeys(key for key, _ in noted):
        entries = [entry for at, entry in noted if at == key]
        count = f"{len(entries)} entries " if len(entries) > 1 else ""
        _logger.warning(_NOT_AN_ADDRESS_MESSAGE, key, _shown_list(entries), count)


def _address_entries(
    addresses: str,
    report: _Report,
    key: str = "AUTHOR_EMAIL",
    split: Callable[[str], list[str]] = _outside_quotes,
) -> list[tuple[str, str]]:
    """``(raw display name, address)`` per entry of an address field
    (:func:`_read_entry`), entries split by *split* (on ``,`` and ``;``
    outside quotes) and capped (:func:`_capped`)."""
    entries = [
        entry for entry in split(addresses[:AUTHOR_FIELD_MAX_CHARS]) if entry.strip()
    ]
    capped = _capped(addresses, entries, (key, "entry", "entries"), report.caps)
    return [
        pair for entry in capped for pair in _read_entry(entry, key, report.addresses)
    ]


def _name_part_entries(part: str) -> list[str]:
    """A name part's address entries: split on ``;`` outside its
    ``<address>``es, as the name field is on ``,``."""
    return _outside_addresses(part, _SEMICOLON_RE)


def _name_entries(
    names: str, splits: list[AuthorSplit], report: _Report
) -> list[NameEmail]:
    """``(name, email)`` per name of a free-text name field split by
    :func:`_split_names`; a part holding a ``<address>`` (the
    core-metadata ``Author`` example ends with one) is read as address
    entries (:func:`_address_entries`), the ``<...>`` whole."""
    pairs: list[NameEmail] = []
    for part in _split_names(names, splits, report):
        if "<" not in part:
            pairs.append((part, None))
            continue
        pairs.extend(
            (_display_name(name, addr), addr or None)
            for name, addr in _address_entries(
                part, report, "AUTHOR", _name_part_entries
            )
        )
    return pairs


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

    The address field first, one author per address in field order, its
    display name kept whole (a backend writes one address per declared
    author, so a comma inside a quoted name is part of that name); then
    each name not already read, split on commas and ``and`` -- a
    comma-separated part that is a contributor group stays whole, one
    after an ``<address>`` is its own -- a part ending in ``<address>`` read
    as one address entry. The legacy pair -- names and one bare address -- is one author
    with both, or, when the names split, name-only authors plus the address
    on its own.
    Repeats are dropped; ``UNKNOWN`` and blank fields count as absent, and
    so does an ``Unknown`` display name beside an address.

    Order: the address field's authors first, then the name field's, each
    in field order. Hatchling and
    setuptools write the authors that have an address to ``Author-email``
    and the rest to ``Author``, each in declared order, so the interleaving
    declared in ``pyproject.toml`` cannot be recovered from these headers;
    the one fixed rule keeps the result stable.

    An address entry holding no address of the form ``local@domain`` is not
    recorded, its stated display name kept, with one ``WARNING:`` per field
    (unless *quiet* or not *address_warnings*). Each name string that was split
    where a separator could be inside a name is appended to *splits*, for
    the caller's one warning. A field over :data:`AUTHOR_FIELD_MAX_CHARS` or
    :data:`AUTHOR_FIELD_MAX_NAMES` is read up to the cap, with one
    ``WARNING:`` once per field and process: a cap warns whenever the value
    read is used, and *quiet* marks a read whose value is discarded (or
    re-reads a field already reported), which warns about nothing.
    """
    noted: list[tuple[str, str]] | None = [] if address_warnings and not quiet else None
    report = _Report(caps=not quiet, addresses=noted)
    names_text = _stated_text(names)
    parsed = _address_entries(_stated_text(addresses), report)
    named = _name_entries(names_text, splits, report)
    _warn_not_addresses(noted or [])
    pairs: list[NameEmail] = [
        (_display_name(name, addr), addr or None) for name, addr in parsed
    ]
    if named and len(parsed) == 1 and not parsed[0][0].strip() and parsed[0][1]:
        # The legacy pair: the address cannot be fairly attributed to any
        # one of several names, nor to one that wrote its own, so it stands
        # on its own.
        pairs = (
            [(named[0][0], parsed[0][1])]
            if len(named) == 1 and "<" not in names_text
            else [*named, *pairs]
        )
        named = []
    known = {name for name, _ in pairs}
    pairs.extend(pair for pair in named if pair[1] or pair[0] not in known)
    return list(dict.fromkeys(pairs))  # every pair names a name or address


#: One line when the project metadata read for the declared authors cannot
#: be read: their declared order and unsplit names are lost.
_PROJECT_UNREAD_MESSAGE = "%s: project metadata not read (%s); authors from the %s"


def warn_project_authors_unread(where: str, reason: object, fallback: str) -> None:
    """One ``WARNING:``: *where*, read for the declared authors, could not
    be read (*reason*), so the authors come from *fallback*."""
    _logger.warning(
        _PROJECT_UNREAD_MESSAGE, loggable(where), one_line(reason), fallback
    )


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


class _DependencySplit(NamedTuple):
    package: str
    split: AuthorSplit


#: The splits of the dependency authors read for the document being built.
_DEPENDENCY_SPLITS: ContextVar[list[_DependencySplit] | None] = ContextVar(
    "pitloom_dependency_author_splits", default=None
)


def _warn_dependency_splits(found: list[_DependencySplit]) -> None:
    if found:
        first = found[0]
        packages = {split.package for split in found}
        _logger.warning(
            _DEPENDENCY_SPLIT_MESSAGE,
            _shown(first.split.field),
            _counted(first.split.names, "name", "names"),
            loggable(first.package),
            _counted(len(packages), "dependency", "dependencies"),
        )


@contextlib.contextmanager
def dependency_author_splits() -> Iterator[None]:
    """Collect the dependency author splits of one document and warn once,
    naming the first and the count, when the block ends without error."""
    found: list[_DependencySplit] = []
    token = _DEPENDENCY_SPLITS.set(found)
    try:
        yield
    finally:
        _DEPENDENCY_SPLITS.reset(token)
    _warn_dependency_splits(found)


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
    found = [_DependencySplit(package, split) for split in splits]
    collector = _DEPENDENCY_SPLITS.get()
    if collector is None:
        _warn_dependency_splits(found)
    else:
        collector.extend(found)
    return pairs
