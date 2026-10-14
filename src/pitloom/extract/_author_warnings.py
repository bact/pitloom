# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``WARNING:`` lines of the free-text author reading: a guessed split,
an address entry holding no address, a field over a cap, a project whose
declared authors cannot be read, and the one line per document for its
dependencies' splits; and the ``INFO:`` line for a project's name field
read as one author that may list several. Each shows a field as one
bounded, escaped literal.

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

from pitloom.logging_config import Cap, excerpt, loggable, one_line, warn_over_cap

_logger = logging.getLogger(__name__)

#: Fields (or entries) shown in a warning naming several.
_SHOWN_FIELDS = 3


class AuthorSplit(NamedTuple):
    """A free-text author field split on ``,`` or ``;``, into how many
    entries, its key, and whether it is a name field (``Author``, cut only
    after an address) rather than an address field (``Author-email``, cut
    after a name). One entry: a name field read as one author though it
    holds ``,``, ``;`` or ``and`` (:func:`warn_author_splits`)."""

    field: str
    entries: int
    key: str = "AUTHOR_EMAIL"
    named: bool = False


def counted(count: int, unit: str, units: str) -> str:
    """*count* and *unit*, or *units* unless one: ``1 name``, ``2 names``."""
    return f"{count} {unit if count == 1 else units}"


def shown_list(fields: list[str]) -> str:
    """One field as :func:`~pitloom.logging_config.excerpt` shows it, or
    several as ``[a, b, c, ...]``: the first :data:`_SHOWN_FIELDS`, ``...``
    when there are more."""
    if len(fields) == 1:
        return excerpt(fields[0])
    listed = [excerpt(field) for field in fields[:_SHOWN_FIELDS]]
    if len(fields) > _SHOWN_FIELDS:
        listed.append("...")
    return f"[{', '.join(listed)}]"


def warn_field_cap(field: str, key: str, cap: Cap, read: str | None) -> None:
    """One ``WARNING:`` once per *field* (its whole text) and process
    (:func:`~pitloom.logging_config.warn_over_cap`) that it is over *cap*:
    *key* names the field, *read* what was read (``3 entries``; ``None``:
    nothing)."""
    digest = hashlib.sha256(field.encode("utf-8", "surrogatepass")).hexdigest()
    shown = excerpt(field)
    outcome = f"only the first {read} read of {shown}" if read else f"{shown} not read"
    warn_over_cap(_logger, cap, key, outcome, once=True, key=f"{key}:{digest}")


#: One line per key of the free-text author fields split: the key, the
#: field, or the fields when several were split (:func:`shown_list`), the
#: count, the reason (:func:`_split_reason`), then the caller's hint.
_SPLIT_MESSAGE = "%s=%s: split into %s on ',' / ';'; %s%s"
#: The hint for a split read from core metadata.
CORE_METADATA_HINT = (
    " -- a project directory or an sdist with pyproject.toml keeps the declared authors"
)
#: One line for the name fields read as one author that may list several:
#: the key, the field or fields (:func:`shown_list`), then the caller's hint.
_ONE_AUTHOR_MESSAGE = (
    "%s=%s: read as one author; it may list several"
    " ('Doe, Jane' and 'Ann and Bob' cannot be told from lists)%s"
)
#: One line per document whose dependencies' author fields were split,
#: naming the first and its reason (:func:`_split_reason`).
_DEPENDENCY_SPLIT_MESSAGE = (
    "%s=%s: split into %s on ',' / ';' (PACKAGE=%s; %s split in all); %s"
)


def _split_reason(split: AuthorSplit) -> str:
    """Why *split* is warned about: a name field is cut only after an
    address; an address field cannot tell a list from one name."""
    if split.named:
        return "a name field is cut only after an address"
    return "an address field cannot tell a list from one name containing a comma"


def warn_author_splits(
    splits: list[AuthorSplit], *, quiet: bool = False, hint: str
) -> None:
    """One ``WARNING:`` per key of *splits* cut, in order, for all its
    entries, and one ``INFO:`` for the name fields read as one author (one
    entry), each field once (unless *quiet*), each ending with *hint*."""
    if quiet:
        return
    cut = [split for split in splits if split.entries > 1]
    for key in dict.fromkeys(split.key for split in cut):
        same = [split for split in cut if split.key == key]
        _logger.warning(
            _SPLIT_MESSAGE,
            key,
            shown_list([split.field for split in same]),
            counted(sum(split.entries for split in same), "entry", "entries"),
            _split_reason(same[0]),
            hint,
        )
    one = [split for split in splits if split.entries == 1]
    if one:
        fields = list(dict.fromkeys(split.field for split in one))
        _logger.info(_ONE_AUTHOR_MESSAGE, one[0].key, shown_list(fields), hint)


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
#: be read: their declared order is lost, and name-only authors joined into
#: one ``Author`` field read as one.
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
            first.split.key,
            excerpt(first.split.field),
            counted(first.split.entries, "entry", "entries"),
            loggable(first.package),
            counted(len(packages), "dependency", "dependencies"),
            _split_reason(first.split),
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
    """*package*'s author *splits* cut, for the enclosing
    :func:`dependency_author_splits` block, or warned about at once outside
    one; a one-author reading is not reported (one line per dependency
    would flood a large environment)."""
    found = [_DependencySplit(package, s) for s in splits if s.entries > 1]
    collector = _DEPENDENCY_SPLITS.get()
    if collector is None:
        _warn_dependency_splits(found)
    else:
        collector.extend(found)
