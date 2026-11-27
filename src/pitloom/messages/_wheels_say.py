# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying the wheel lines: :class:`WheelRefused` and one constructor per
refusal line (``refuse_*``), each naming its entry and line itself, and
the ``.dist-info`` lines by the problem
:func:`pitloom.core.wheel_dist_info.resolve_own_dist_info` found
(:data:`DIST_INFO_PROBLEMS`).

An *archive* is a ``str`` (the file name; a caller passes ``path.name``) or
a path, named by its last component; a *member* is the raw member name as
the archive stores it (``ZipInfo.orig_filename``). The field writers quote,
mask and escape both.

See also: :mod:`pitloom.messages._wheels` (the entries),
:mod:`pitloom.messages._archive_members_say` (a member left out).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from pitloom.core.internal_error import InternalError
from pitloom.messages._emit import CodedValueError, emit
from pitloom.messages._surface import (
    SURFACE_HOOK,
    SURFACE_LIBRARY,
    current_surface,
    unreachable_on_hook,
)
from pitloom.messages._types import Line, Message
from pitloom.messages._wheels import (
    ALLOW_SIGNED_NAMES,
    DIST_INFO_AMBIGUOUS,
    DIST_INFO_CONFLICT,
    DIST_INFO_MISSING,
    DUPLICATE_NAME_LINE,
    MEMBER_UNREADABLE_LINE,
    METADATA_MISSING_LINE,
    NO_DIST_INFO_LINE,
    NO_DIST_INFO_WARNING_LINE,
    NON_CONFORMING_LINE,
    NOT_A_WHEEL_NAME_LINE,
    NOT_A_WHEEL_NAME_WARNING_LINE,
    NUL_NAME_LINE,
    OTHER_DIST_INFO_LINE,
    SEVERAL_MATCH_LINE,
    SEVERAL_MATCH_WARNING_LINE,
    SEVERAL_NONE_MATCH_LINE,
    SEVERAL_NONE_MATCH_WARNING_LINE,
    SIGNATURE_REMOVED_LINE,
    SIGNED_LINE,
    UNOPENABLE_LINE,
    WHEEL_INVALID,
    WHEEL_UNREADABLE,
    WHEEL_UNUSABLE,
    WHEEL_UNUSABLE_SIGNED,
)

if TYPE_CHECKING:
    import os
    from typing import TypeAlias

    #: An archive as a caller passes it: its file name, or a path.
    Archive: TypeAlias = str | os.PathLike[str]


class WheelRefused(CodedValueError):
    """A wheel Pitloom refuses as a whole, with one coded line: a
    :class:`ValueError`, so every caller that catches ``(ValueError,
    OSError)`` catches it. Make one with a ``refuse_*`` constructor of
    this module (or, for a file not named ``.whl``,
    :class:`pitloom.core.wheel_dist_info.NotAWheelError`).

    Raises:
        ValueError: (a plain one) No ``ERROR`` line of the message names
            the values, or a value does not have its field's shape.
    """


def refuse_unopenable(archive: Archive, exc: BaseException) -> WheelRefused:
    """*archive* could not be opened as a ZIP archive: *exc* is what
    :class:`zipfile.ZipFile` raised, named by its type only
    (``wheel-unreadable``)."""
    return WheelRefused(
        WHEEL_UNREADABLE, line=UNOPENABLE_LINE, archive=archive, exception_type=exc
    )


def refuse_unreadable_member(
    archive: Archive, member: str, exc: BaseException
) -> WheelRefused:
    """*member* of *archive* could not be read (damaged, encrypted, not
    UTF-8 where text is needed): *exc*, named by its type only
    (``wheel-unreadable``)."""
    return WheelRefused(
        WHEEL_UNREADABLE,
        line=MEMBER_UNREADABLE_LINE,
        archive=archive,
        member=member,
        exception_type=exc,
    )


def refuse_nul_name(archive: Archive, member: str) -> WheelRefused:
    """*member*'s name holds a NUL (``wheel-invalid``)."""
    return WheelRefused(
        WHEEL_INVALID, line=NUL_NAME_LINE, archive=archive, member=member
    )


def refuse_duplicate_name(archive: Archive, member: str) -> WheelRefused:
    """*member* has the install name of a later member (``wheel-invalid``)."""
    return WheelRefused(
        WHEEL_INVALID, line=DUPLICATE_NAME_LINE, archive=archive, member=member
    )


def refuse_non_conforming(archive: Archive, member: str) -> WheelRefused:
    """*member*, of the wheel's own ``.dist-info``, is stored under a name
    that is not its install name, so an embed cannot rewrite ``RECORD``
    (``wheel-unusable``)."""
    return WheelRefused(
        WHEEL_UNUSABLE, line=NON_CONFORMING_LINE, archive=archive, member=member
    )


def refuse_signed(archive: Archive, member: str) -> WheelRefused:
    """*member* (``RECORD.jws``, ``RECORD.p7s``) signs the ``RECORD`` an
    embed rewrites (``wheel-unusable/signed``), named with the option of
    the surface that runs (:data:`ALLOW_SIGNED_NAMES`)."""
    surface = current_surface()
    if surface == SURFACE_HOOK:
        # The hook never embeds into a wheel.
        unreachable_on_hook("the signed-wheel refusal")
        surface = SURFACE_LIBRARY
    return WheelRefused(
        WHEEL_UNUSABLE_SIGNED,
        line=SIGNED_LINE,
        archive=archive,
        member=member,
        option=ALLOW_SIGNED_NAMES[surface],
    )


def say_signature_removed(log: logging.Logger, archive: Archive, member: str) -> None:
    """The one ``INFO:`` on *log*: ``--allow-signed-wheel`` removed the
    signature *member* from *archive* (``wheel-unusable/signed``)."""
    emit(
        log,
        WHEEL_UNUSABLE_SIGNED,
        logging.INFO,
        line=SIGNATURE_REMOVED_LINE,
        archive=archive,
        member=member,
    )


#: No top-level ``.dist-info``.
DIST_INFO_NONE: Final = "none"
#: Several top-level ``.dist-info`` match the file name.
DIST_INFO_SEVERAL_MATCH: Final = "several-match"
#: The file name is not a wheel name and several exist.
DIST_INFO_NOT_A_WHEEL_NAME: Final = "not-a-wheel-name"
#: Several exist, none the one the file name names.
DIST_INFO_SEVERAL_NONE_MATCH: Final = "several-none-match"
#: Exactly one exists, not the one the file name names: it is used.
DIST_INFO_OTHER: Final = "other"

#: Each problem that leaves no ``.dist-info`` chosen: its entry, its
#: ``ERROR`` line and its ``WARNING`` line.
_UNCHOSEN: Final[Mapping[str, tuple[Message, Line, Line]]] = MappingProxyType(
    {
        DIST_INFO_NONE: (
            DIST_INFO_MISSING,
            NO_DIST_INFO_LINE,
            NO_DIST_INFO_WARNING_LINE,
        ),
        DIST_INFO_SEVERAL_MATCH: (
            DIST_INFO_AMBIGUOUS,
            SEVERAL_MATCH_LINE,
            SEVERAL_MATCH_WARNING_LINE,
        ),
        DIST_INFO_NOT_A_WHEEL_NAME: (
            DIST_INFO_AMBIGUOUS,
            NOT_A_WHEEL_NAME_LINE,
            NOT_A_WHEEL_NAME_WARNING_LINE,
        ),
        DIST_INFO_SEVERAL_NONE_MATCH: (
            DIST_INFO_AMBIGUOUS,
            SEVERAL_NONE_MATCH_LINE,
            SEVERAL_NONE_MATCH_WARNING_LINE,
        ),
    }
)

#: Every problem :func:`~pitloom.core.wheel_dist_info.resolve_own_dist_info`
#: can find.
DIST_INFO_PROBLEMS: Final = (*_UNCHOSEN, DIST_INFO_OTHER)


def _unchosen(problem: str) -> tuple[Message, Line, Line]:
    """The entry and lines of *problem*, one that leaves no ``.dist-info``.

    Raises:
        pitloom.core.internal_error.InternalError: It is not one.
    """
    try:
        return _UNCHOSEN[problem]
    except KeyError:
        raise InternalError(f"no .dist-info refusal for {problem!r}") from None


def refuse_dist_info(archive: Archive, problem: str) -> WheelRefused:
    """*archive*'s own ``.dist-info`` cannot be told: *problem* is one of
    :data:`DIST_INFO_PROBLEMS` but :data:`DIST_INFO_OTHER`
    (``dist-info-missing``, ``dist-info-ambiguous``).

    Raises:
        pitloom.core.internal_error.InternalError: *problem* is not one of
            them.
    """
    message, line, _ = _unchosen(problem)
    # Each entry named, not *message*: the message inventory reads a
    # constructor as coded by the entry it names.
    if message is DIST_INFO_MISSING:
        return WheelRefused(DIST_INFO_MISSING, line=line, archive=archive)
    return WheelRefused(DIST_INFO_AMBIGUOUS, line=line, archive=archive)


def warn_dist_info(
    log: logging.Logger, archive: Archive, problem: str, *, chosen: str | None = None
) -> None:
    """The one ``WARNING:`` on *log* for *archive*'s *problem*: with
    :data:`DIST_INFO_OTHER`, the ``.dist-info`` *chosen* (``"<dir>/"``, as
    the archive names it) is read though the file name names another
    (``dist-info-conflict``); with any other, none is, so the wheel's
    identity is unknown (``dist-info-missing``, ``dist-info-ambiguous``).

    Raises:
        pitloom.core.internal_error.InternalError: *problem* is not one of
            :data:`DIST_INFO_PROBLEMS`, or *chosen* is given with any but
            :data:`DIST_INFO_OTHER` or missing with it.
    """
    if problem == DIST_INFO_OTHER:
        if chosen is None:
            raise InternalError("the .dist-info used is not named")
        emit(
            log,
            DIST_INFO_CONFLICT,
            logging.WARNING,
            line=OTHER_DIST_INFO_LINE,
            archive=archive,
            member=chosen,
        )
        return
    if chosen is not None:
        raise InternalError(f"a .dist-info chosen for {problem!r}")
    message, _, line = _unchosen(problem)
    emit(log, message, logging.WARNING, line=line, archive=archive)


def warn_metadata_missing(log: logging.Logger, archive: Archive, member: str) -> None:
    """The one ``WARNING:`` on *log*: *archive* has no *member*, the
    ``METADATA`` of its own ``.dist-info`` (``dist-info-missing``)."""
    emit(
        log,
        DIST_INFO_MISSING,
        logging.WARNING,
        line=METADATA_MISSING_LINE,
        archive=archive,
        member=member,
    )
