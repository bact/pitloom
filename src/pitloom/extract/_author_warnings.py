# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``WARNING:`` lines of the free-text author reading: a guessed split,
an address entry holding no address, a field over a cap, a project whose
declared authors cannot be read, and the one line per document for its
dependencies' splits. Each shows a field as one bounded, escaped literal.

See also: :mod:`pitloom.extract.authors` (the reading, which re-exports
the public names).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from collections.abc import Iterator
from contextvars import ContextVar
from typing import NamedTuple

from pitloom.logging_config import Cap, loggable, one_line, warn_over_cap

_logger = logging.getLogger(__name__)

#: Characters of a field shown in a warning.
_SHOWN_CHARS = 120
#: Fields (or entries) shown in a warning naming several.
_SHOWN_FIELDS = 3


#: What a name field (``Author``) is split on, as a split warning names it.
NAME_SEPARATORS = ("','", "';'", "'and'")
#: What an address field (``Author-email``) is split on: never ``and``.
ADDRESS_SEPARATORS = ("','", "';'")


class AuthorSplit(NamedTuple):
    """A free-text author field split into several names, how many, and on
    what (:data:`NAME_SEPARATORS` or :data:`ADDRESS_SEPARATORS`)."""

    field: str
    names: int
    separators: tuple[str, ...] = NAME_SEPARATORS


def _separators(splits: list[AuthorSplit]) -> str:
    """The separators of every split in *splits*, once each, in order."""
    found = dict.fromkeys(sep for split in splits for sep in split.separators)
    return " / ".join(found)


def counted(count: int, unit: str, units: str) -> str:
    """*count* and *unit*, or *units* unless one: ``1 name``, ``2 names``."""
    return f"{count} {unit if count == 1 else units}"


def shown(field: str) -> str:
    """*field* for a warning as one quoted literal, escaped once: on one
    line, at most :data:`_SHOWN_CHARS` characters, its ``repr`` when
    printable, else its ASCII-escaped literal
    (:func:`~pitloom.logging_config.loggable`); ``...`` after it when cut."""
    text = " ".join(field.split())
    cut = text[:_SHOWN_CHARS]
    escaped = loggable(cut)
    literal = repr(cut) if escaped == cut else escaped
    return literal + ("..." if len(text) > _SHOWN_CHARS else "")


def shown_list(fields: list[str]) -> str:
    """One field :func:`shown`, or several as ``[a, b, c, ...]``: the first
    :data:`_SHOWN_FIELDS`, ``...`` when there are more."""
    if len(fields) == 1:
        return shown(fields[0])
    listed = [shown(field) for field in fields[:_SHOWN_FIELDS]]
    if len(fields) > _SHOWN_FIELDS:
        listed.append("...")
    return f"[{', '.join(listed)}]"


def warn_field_cap(field: str, key: str, cap: Cap, read: str) -> None:
    """One ``WARNING:`` once per *field* (its whole text) and process
    (:func:`~pitloom.logging_config.warn_over_cap`) that it is over *cap*:
    *key* names the field, *read* what was read (``3 names``)."""
    digest = hashlib.sha256(field.encode("utf-8", "surrogatepass")).hexdigest()
    outcome = f"only the first {read} read of {shown(field)}"
    warn_over_cap(_logger, cap, key, outcome, once=True, key=f"{key}:{digest}")


#: One line per document whose free-text author names were split; the
#: first ``%s`` is the string, or the strings when several were split
#: (:func:`shown_list`); the third the separators (:func:`_separators`);
#: the last the caller's hint.
_NAMES_SPLIT_MESSAGE = (
    "AUTHOR=%s: split into %s on %s; a free-text author field"
    " cannot tell a list from one name containing a comma%s"
)
#: The hint for a split read from core metadata.
CORE_METADATA_HINT = (
    " -- use --project-dir or an sdist with pyproject.toml for declared"
    " [project].authors"
)
#: One line per document whose dependencies' free-text authors were split.
_DEPENDENCY_SPLIT_MESSAGE = (
    "AUTHOR=%s: split into %s on %s (PACKAGE=%s; %s split in"
    " all); a free-text author field cannot tell a list from one name"
    " containing a comma"
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
            shown_list([split.field for split in splits]),
            counted(total, "name", "names"),
            _separators(splits),
            hint,
        )


#: One line per field holding address entries that hold no address: the
#: field's key (``AUTHOR_EMAIL`` or ``AUTHOR``), the entries
#: (:func:`shown_list`) and, when several, how many.
_NOT_AN_ADDRESS_MESSAGE = "%s=%s: not an email address; %snot recorded"


def warn_not_addresses(noted: list[tuple[str, str]]) -> None:
    """One ``WARNING:`` per key of *noted* (``(key, entry)``), in order: its
    entries holding no address, the first few shown, and how many when
    several."""
    for key in dict.fromkeys(key for key, _ in noted):
        entries = [entry for at, entry in noted if at == key]
        count = f"{len(entries)} entries " if len(entries) > 1 else ""
        _logger.warning(_NOT_AN_ADDRESS_MESSAGE, key, shown_list(entries), count)


#: One line when the project metadata read for the declared authors cannot
#: be read: their declared order and unsplit names are lost.
_PROJECT_UNREAD_MESSAGE = "%s: project metadata not read (%s); authors from the %s"


def warn_project_authors_unread(where: str, reason: object, fallback: str) -> None:
    """One ``WARNING:``: *where*, read for the declared authors, could not
    be read (*reason*), so the authors come from *fallback*."""
    _logger.warning(
        _PROJECT_UNREAD_MESSAGE, loggable(where), one_line(reason), fallback
    )


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
            shown(first.split.field),
            counted(first.split.names, "name", "names"),
            _separators([first.split]),
            loggable(first.package),
            counted(len(packages), "dependency", "dependencies"),
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


def report_dependency_splits(package: str, splits: list[AuthorSplit]) -> None:
    """*package*'s author *splits*, for the enclosing
    :func:`dependency_author_splits` block, or warned about at once outside
    one."""
    found = [_DependencySplit(package, split) for split in splits]
    collector = _DEPENDENCY_SPLITS.get()
    if collector is None:
        _warn_dependency_splits(found)
    else:
        collector.extend(found)
