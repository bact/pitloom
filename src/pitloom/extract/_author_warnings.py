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
from pathlib import Path
from typing import NamedTuple

from pitloom.logging_config import excerpt
from pitloom.messages.authors import (
    note_one_author,
    warn_author_split,
    warn_dependency_split,
    warn_project_unreadable,
)
from pitloom.messages.authors import (
    warn_not_addresses as say_not_addresses,
)
from pitloom.messages.files import (
    Cap,
    warn_over_cap,
)

_logger = logging.getLogger(__name__)


class AuthorSplit(NamedTuple):
    """A free-text author field split, into how many entries, its key, and
    whether it is a name field (``Author``, cut only next to an address)
    rather than an address field (``Author-email``, cut on ``,`` or ``;``
    after a name). One entry: a name field recorded as one author though it
    holds ``,``, ``;`` or ``and`` (:func:`warn_author_splits`)."""

    field: str
    entries: int
    key: str = "AUTHOR_EMAIL"
    named: bool = False


def warn_field_cap(
    field: str, key: str, cap: Cap, read: str | None, package: str | None = None
) -> None:
    """One ``WARNING:`` once per *package*, *key* and *field* (its whole
    text) and process (:func:`~pitloom.messages.files.warn_over_cap`) that
    it is over *cap*: *key* names the field, *read* what was read
    (``3 entries``; ``None``: nothing), *package* the dependency whose
    record holds it (``None``: the project's own)."""
    digest = hashlib.sha256(field.encode("utf-8", "surrogatepass")).hexdigest()
    shown = excerpt(field)
    outcome = f"only the first {read} read of {shown}" if read else f"{shown} not read"
    warn_over_cap(
        _logger,
        cap,
        key,
        outcome,
        once=True,
        key=repr((package, key, digest)),
        package=package,
    )


def warn_author_splits(splits: list[AuthorSplit], *, quiet: bool = False) -> None:
    """One ``WARNING:`` (``author-ambiguous``) per key of *splits* cut, in
    order, for all its entries, and one ``INFO:`` for the name fields read
    as one author (one entry), each field once; nothing when *quiet*."""
    if quiet:
        return
    cut = [split for split in splits if split.entries > 1]
    for key in dict.fromkeys(split.key for split in cut):
        same = [split for split in cut if split.key == key]
        warn_author_split(
            _logger,
            [split.field for split in same],
            sum(split.entries for split in same),
            named=same[0].named,
        )
    one = [split for split in splits if split.entries == 1]
    if one:
        note_one_author(_logger, list(dict.fromkeys(split.field for split in one)))


def warn_not_addresses(noted: list[tuple[str, str]]) -> None:
    """One ``WARNING:`` (``author-invalid``) per key of *noted* (``(key,
    entry)``), in order: its entries holding no address, the first few
    shown, and how many when several."""
    for key in dict.fromkeys(key for key, _ in noted):
        say_not_addresses(_logger, key, [entry for at, entry in noted if at == key])


def warn_project_authors_unread(project_dir: str | Path, reason: BaseException) -> None:
    """One ``WARNING:`` (``project-unreadable``): *project_dir*, read by an
    embed for its declared authors, could not be read (*reason*), so the
    authors come from the wheel's ``METADATA``."""
    warn_project_unreadable(_logger, project_dir, reason)


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
        warn_dependency_split(
            _logger,
            first.package,
            first.split.key,
            first.split.field,
            first.split.entries,
            named=first.split.named,
            dependencies=len({split.package for split in found}),
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
