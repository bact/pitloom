# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying the archive member lines: :func:`warn_archive_member` for one
member a read leaves out or lists under another name, by its kind
(:data:`MEMBER_KINDS`), and :func:`warn_shared_paths` for members of an
sdist that share a project path.

The route is the frame: no frame is a read of a wheel or an sdist (``;
not listed``), :data:`~pitloom.messages._frames.BUILD_FRAME` the
``--allow-build`` route (``Build: `` before the line, ``; not copied``).

See also: :mod:`pitloom.messages._archive_members` (the entries),
:mod:`pitloom.core.archive_member_names` (the reader).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from pitloom.core.internal_error import InternalError
from pitloom.messages._archive_members import (
    ARCHIVE_MEMBER_CONFLICT,
    ARCHIVE_MEMBER_INVALID,
    ARCHIVE_MEMBER_UNSAFE,
    DIRECTORY_DATA_COPY_LINE,
    DIRECTORY_DATA_LINE,
    NORMALISED_COPY_LINE,
    NORMALISED_LINE,
    OUTSIDE_LINE,
    OVERWRITTEN_COPY_LINE,
    OVERWRITTEN_LINE,
    SHADOWED_COPY_LINE,
    SHADOWED_LINE,
    SHARED_PATHS_LINE,
    UNSAFE_COPY_LINE,
    UNSAFE_LINE,
)
from pitloom.messages._emit import emit
from pitloom.messages._frames import BUILD_FRAME, Frame
from pitloom.messages._types import Line, Message

if TYPE_CHECKING:
    from pitloom.messages._wheels_say import Archive

#: A name with no install location.
MEMBER_UNSAFE: Final = "unsafe"
#: A member a later one of the same install name overwrites.
MEMBER_OVERWRITTEN: Final = "overwritten"
#: A file member whose name is also a directory of other members.
MEMBER_SHADOWED: Final = "shadowed"
#: A member listed under its install name, not as stored.
MEMBER_NORMALISED: Final = "normalised"
#: A directory entry that carries bytes.
MEMBER_DIRECTORY_DATA: Final = "directory-data"
#: A member that resolves outside the extraction directory (the build
#: route only).
MEMBER_OUTSIDE: Final = "outside"

#: Each kind's entry and its lines: on a read, on the build route.
_KINDS: Final[Mapping[str, tuple[Message, Line | None, Line]]] = MappingProxyType(
    {
        MEMBER_UNSAFE: (ARCHIVE_MEMBER_UNSAFE, UNSAFE_LINE, UNSAFE_COPY_LINE),
        MEMBER_OVERWRITTEN: (
            ARCHIVE_MEMBER_CONFLICT,
            OVERWRITTEN_LINE,
            OVERWRITTEN_COPY_LINE,
        ),
        MEMBER_SHADOWED: (ARCHIVE_MEMBER_CONFLICT, SHADOWED_LINE, SHADOWED_COPY_LINE),
        MEMBER_NORMALISED: (
            ARCHIVE_MEMBER_INVALID,
            NORMALISED_LINE,
            NORMALISED_COPY_LINE,
        ),
        MEMBER_DIRECTORY_DATA: (
            ARCHIVE_MEMBER_INVALID,
            DIRECTORY_DATA_LINE,
            DIRECTORY_DATA_COPY_LINE,
        ),
        MEMBER_OUTSIDE: (ARCHIVE_MEMBER_UNSAFE, None, OUTSIDE_LINE),
    }
)

#: Every kind :func:`warn_archive_member` takes.
MEMBER_KINDS: Final = tuple(_KINDS)


# One keyword per field a kind may take.
# pylint: disable-next=too-many-arguments
def warn_archive_member(
    log: logging.Logger,
    kind: str,
    archive: Archive,
    raw: str,
    *,
    frame: Frame | None = None,
    later: str | None = None,
    listed_as: str | None = None,
) -> None:
    """The one ``WARNING:`` on *log* for the member *raw* (its name as
    *archive* stores it) of *kind* (:data:`MEMBER_KINDS`): with *frame*
    ``None``, a read leaves it out of the SBOM or lists it as *listed_as*;
    with :data:`~pitloom.messages._frames.BUILD_FRAME`, the
    ``--allow-build`` route does not copy it, or copies it as *listed_as*.
    *later* is the raw name of the member that overwrites it
    (:data:`MEMBER_OVERWRITTEN` only); *listed_as* its install name
    (:data:`MEMBER_NORMALISED` only).

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not one,
            *frame* is another frame, :data:`MEMBER_OUTSIDE` comes without
            the build frame, or *later* or *listed_as* is given with another
            kind or missing with its own.
    """
    try:
        message, read_line, build_line = _KINDS[kind]
    except KeyError:
        raise InternalError(f"no archive member kind {kind!r}") from None
    if frame is not None and frame is not BUILD_FRAME:
        raise InternalError(f"archive member lines take no frame {frame.template!r}")
    line = read_line if frame is None else build_line
    if line is None:
        raise InternalError(f"archive member kind {kind!r} is the build route's")
    if (later is not None) != (kind == MEMBER_OVERWRITTEN) or (
        listed_as is not None
    ) != (kind == MEMBER_NORMALISED):
        raise InternalError(f"archive member kind {kind!r}: wrong values")
    # Any: the values go to emit()'s **values, whose other keywords are typed.
    values: dict[str, Any] = {"archive": archive, "member": raw}
    if later is not None:
        values["later_member"] = later
    if listed_as is not None:
        values["install_name"] = listed_as
    emit(log, message, logging.WARNING, line=line, frame=frame, **values)


def warn_shared_paths(
    log: logging.Logger, archive: Archive, paths: Sequence[str]
) -> None:
    """The one ``WARNING:`` on *log* for members of *archive* that share
    the project *paths* (each once, in the order found;
    ``archive-member-conflict``).

    Raises:
        pitloom.core.internal_error.InternalError: *paths* is empty.
    """
    if not paths:
        raise InternalError("no shared project path to say")
    emit(
        log,
        ARCHIVE_MEMBER_CONFLICT,
        logging.WARNING,
        line=SHARED_PATHS_LINE,
        archive=archive,
        project_paths=tuple(paths),
    )
