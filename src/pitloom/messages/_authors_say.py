# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The helpers that say the author lines: ``author-ambiguous``,
``author-invalid`` and ``project-unreadable``. Each takes the fields as
read; the ``authors`` field masks, cuts and escapes them.

See also: :mod:`pitloom.messages._authors` (the entries) and
:mod:`pitloom.extract._author_warnings` (the callers).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence

from pitloom.core.internal_error import InternalError
from pitloom.messages._authors import (
    ADDRESS_SPLIT_LINE,
    AUTHOR_AMBIGUOUS,
    AUTHOR_INVALID,
    DEPENDENCY_ADDRESS_SPLIT_LINE,
    DEPENDENCY_NAME_SPLIT_LINE,
    EMAIL_INVALID_COUNT_LINE,
    EMAIL_INVALID_LINE,
    NAME_INVALID_COUNT_LINE,
    NAME_INVALID_LINE,
    NAME_SPLIT_LINE,
    PROJECT_UNREADABLE,
)
from pitloom.messages._emit import emit

#: The ``author-invalid`` lines by the key of the field and whether several
#: entries are named.
_INVALID_LINES = {
    ("AUTHOR_EMAIL", False): EMAIL_INVALID_LINE,
    ("AUTHOR_EMAIL", True): EMAIL_INVALID_COUNT_LINE,
    ("AUTHOR", False): NAME_INVALID_LINE,
    ("AUTHOR", True): NAME_INVALID_COUNT_LINE,
}


#: The ``author-ambiguous`` split lines by whether the field is a
#: dependency's and whether it is a name field.
_SPLIT_LINES = {
    (False, True): NAME_SPLIT_LINE,
    (False, False): ADDRESS_SPLIT_LINE,
    (True, True): DEPENDENCY_NAME_SPLIT_LINE,
    (True, False): DEPENDENCY_ADDRESS_SPLIT_LINE,
}


def warn_author_split(
    log: logging.Logger, fields: Sequence[str], entries: int, *, named: bool
) -> None:
    """The ``WARNING:`` that a project's author *fields* (all of one key)
    were split into *entries* in all: a name field (``AUTHOR``) when
    *named*, cut next to an address, else an address field
    (``AUTHOR_EMAIL``), cut on ``,`` or ``;``."""
    emit(
        log,
        AUTHOR_AMBIGUOUS,
        logging.WARNING,
        line=_SPLIT_LINES[(False, named)],
        authors=list(fields),
        entry_count=entries,
    )


def note_one_author(log: logging.Logger, fields: Sequence[str]) -> None:
    """The ``INFO:`` that a project's name *fields* (``AUTHOR``) were each
    read as one author, though each may list several."""
    emit(log, AUTHOR_AMBIGUOUS, logging.INFO, authors=list(fields))


# One value per part of the line.
# pylint: disable-next=too-many-arguments
def warn_dependency_split(
    log: logging.Logger,
    package: str,
    key: str,
    field: str,
    entries: int,
    *,
    named: bool,
    dependencies: int,
) -> None:
    """The one ``WARNING:`` of a document whose dependencies' author fields
    were split: the first, *package*'s *field* under *key*
    (``AUTHOR_EMAIL``), split into *entries*, a name field when *named*,
    and how many *dependencies* were split in all."""
    emit(
        log,
        AUTHOR_AMBIGUOUS,
        logging.WARNING,
        line=_SPLIT_LINES[(True, named)],
        package=package,
        author_key=key,
        authors=field,
        entry_count=entries,
        dependency_count=dependencies,
    )


def warn_not_addresses(log: logging.Logger, key: str, entries: Sequence[str]) -> None:
    """The ``WARNING:`` that *entries* of a project's author field *key*
    (``AUTHOR`` or ``AUTHOR_EMAIL``) are not one valid email address each,
    with how many when several.

    Raises:
        pitloom.core.internal_error.InternalError: *key* is neither, or
            *entries* is empty.
    """
    several = len(entries) > 1
    line = _INVALID_LINES.get((key, several))
    if line is None or not entries:
        raise InternalError(f"not an author address warning: {key!r}, {entries!r}")
    if several:
        emit(
            log,
            AUTHOR_INVALID,
            logging.WARNING,
            line=line,
            authors=list(entries),
            entry_count=len(entries),
        )
    else:
        emit(log, AUTHOR_INVALID, logging.WARNING, line=line, authors=list(entries))


def warn_project_unreadable(
    log: logging.Logger, project_dir: str | os.PathLike[str], exc: BaseException
) -> None:
    """The ``WARNING:`` that the metadata of *project_dir*, read by an embed
    for its declared authors, could not be read (*exc*): the authors come
    from the wheel's ``METADATA``."""
    emit(log, PROJECT_UNREADABLE, logging.WARNING, dir=project_dir, failure=exc)
