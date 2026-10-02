# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Archive member names -> install-location names, identical on every OS.

Every reader that turns wheel or sdist archive members into
``ProjectFile``/``IncludedFile`` distribution paths goes through
:func:`file_members` (:func:`zip_file_members` for a ZIP), so
``software_File.name`` and every lookup keyed by it (``contains``,
``hasDataFile``, registry, phantom dependencies) agree.

See also: ``working-docs/implementation/archive-member-names.md``.
"""

from __future__ import annotations

import logging
import re
import zipfile
from collections.abc import Callable, Iterable
from typing import Literal, NamedTuple, TypeVar

from pitloom.core._models_wheel_types import to_posix_distribution_path

MemberNameStatus = Literal["ok", "normalized", "unsafe"]

T = TypeVar("T")

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")

_MSG = "%sARCHIVE=%r ENTRY=%r: "
_UNSAFE = _MSG + "no safe install location -- skipped"
_OVERWRITTEN = _MSG + "overwritten by later entry %r -- skipped"
_SHADOWED = _MSG + "also a directory of other entries -- skipped"
_NORMALIZED = _MSG + "non-conforming name -- recorded as %r"
_DIRECTORY_DATA = _MSG + "directory entry carries data -- skipped"


class MemberName(NamedTuple):
    """A classified archive member name.

    ``name`` is the install location (``/``-separated, no empty or ``.``
    segments) when ``status`` is ``"ok"`` or ``"normalized"``. For
    ``"unsafe"`` it is the ``/``-separated raw name, for messages only --
    never use it as a path.
    """

    name: str
    status: MemberNameStatus


def normalize_member_name(raw: str) -> MemberName:
    """Classify and normalise one raw archive member name.

    Separators become ``/`` (the Windows reading, so one archive gives one
    name on every OS); empty and ``.`` segments are dropped. A name that is
    absolute (leading ``/``, or a first remaining segment starting with a
    drive such as ``C:`` -- ``a:b.py`` included, drive-relative on
    Windows), has a ``..`` segment, contains NUL or is empty after
    normalisation has no install location and is ``"unsafe"`` -- it is not
    rewritten into a legal-looking path.
    """
    posix = to_posix_distribution_path(raw)
    segments = [s for s in posix.split("/") if s not in ("", ".")]
    if (
        not segments
        or posix.startswith("/")
        or _DRIVE_PREFIX.match(segments[0])
        or "\0" in posix
        or ".." in segments
    ):
        return MemberName(posix, "unsafe")
    name = "/".join(segments)
    return MemberName(name, "ok" if name == raw else "normalized")


def _classify(raw: str, dot_prefix_ok: bool) -> MemberName:
    member = normalize_member_name(raw)
    if dot_prefix_ok and raw.startswith("./") and member.name == raw[2:]:
        return MemberName(member.name, "ok")
    return member


def _ancestors(names: Iterable[str]) -> set[str]:
    """Every proper ``/``-prefix directory of *names*.

    Walks up from each name and stops at a prefix already found, whose own
    ancestors are then found too: linear in the names, not in their depth
    squared.
    """
    found: set[str] = set()
    for name in names:
        end = name.rfind("/")
        while end >= 0 and name[:end] not in found:
            found.add(name[:end])
            end = name.rfind("/", 0, end)
    return found


def archive_members(
    entries: Iterable[tuple[str, T]],
    archive_name: str,
    logger: logging.Logger | None,
    log_prefix: str = "",
    *,
    dot_prefix_ok: bool = False,
    on_duplicate: Callable[[str], Exception] | None = None,
) -> list[tuple[str, T]]:
    """*entries* (raw member name, payload) as (install-location name,
    payload), in archive order.

    Exactly one ``WARNING:`` per member, quoting its raw name, that is:

    - skipped as unsafe (see :func:`normalize_member_name`);
    - skipped because a later member has the same normalised name: read
      with ``\\`` as a separator, as on Windows, an installer extracting
      in archive order leaves the later one behind (on POSIX, pip keeps a
      backslash name as a separate literal file; exact and ``./``
      duplicates overwrite there too);
    - skipped because it is a file whose name is also a directory of other
      members (no installer can write both);
    - kept under its normalised name.

    *logger* ``None`` logs nothing, for a second read of an archive
    another call already reported on. *dot_prefix_ok* treats one leading
    ``./`` as conforming (ordinary for tar, not for a wheel's ZIP), so it
    alone does not warn. *on_duplicate* turns the second case into a refusal:
    called with the raw name of the first member whose normalised name a
    later one repeats, it returns the exception to raise, before anything
    is logged.
    """
    classified = [
        (raw, _classify(raw, dot_prefix_ok), payload) for raw, payload in entries
    ]
    last = {m.name: i for i, (_, m, _) in enumerate(classified) if m.status != "unsafe"}
    if on_duplicate is not None:
        for index, (raw, member, _) in enumerate(classified):
            if member.status != "unsafe" and last[member.name] != index:
                raise on_duplicate(raw)
    directories = _ancestors(last)
    members: list[tuple[str, T]] = []
    for index, (raw, member, payload) in enumerate(classified):
        if member.status == "unsafe":
            args: tuple[object, ...] = (_UNSAFE, raw)
        elif last[member.name] != index:
            args = (_OVERWRITTEN, raw, classified[last[member.name]][0])
        elif member.name in directories:
            args = (_SHADOWED, raw)
        else:
            members.append((member.name, payload))
            if member.status == "ok":
                continue
            args = (_NORMALIZED, raw, member.name)
        if logger is not None:
            logger.warning(args[0], log_prefix, archive_name, *args[1:])
    return members


def is_directory_name(raw: str) -> bool:
    """Whether the raw member name *raw* names a directory: it ends in
    ``/``, ``\\`` or a ``.`` segment (``pkg/.``). Judged from the raw name,
    not ``ZipInfo.is_dir()`` (reads ``filename``, converted from ``os.sep``
    only on Windows) or ``TarInfo.isdir()`` (a regular file named ``pkg\\``
    stays a file), so a ZIP and a tar agree on every OS.
    """
    posix = to_posix_distribution_path(raw)
    return posix.endswith(("/", "/.")) or posix == "."


def file_members(
    entries: Iterable[tuple[str, int, T]],
    archive_name: str,
    logger: logging.Logger | None,
    log_prefix: str = "",
    *,
    dot_prefix_ok: bool = False,
    on_duplicate: Callable[[str], Exception] | None = None,
) -> list[tuple[str, T]]:
    """:func:`archive_members` over an archive's file-typed entries
    (raw name, size, payload), after dropping the ones whose name is a
    directory (:func:`is_directory_name`); one that carries data gets a
    ``WARNING:`` too, since its bytes are dropped."""
    files: list[tuple[str, T]] = []
    for raw, size, payload in entries:
        if not is_directory_name(raw):
            files.append((raw, payload))
        elif size and logger is not None:
            logger.warning(_DIRECTORY_DATA, log_prefix, archive_name, raw)
    return archive_members(
        files,
        archive_name,
        logger,
        log_prefix,
        dot_prefix_ok=dot_prefix_ok,
        on_duplicate=on_duplicate,
    )


def zip_file_members(
    zf: zipfile.ZipFile,
    archive_name: str,
    logger: logging.Logger | None,
    log_prefix: str = "",
    *,
    on_duplicate: Callable[[str], Exception] | None = None,
) -> list[tuple[str, zipfile.ZipInfo]]:
    """:func:`file_members` for a ZIP (wheel or ``.zip`` sdist). Names come
    from ``orig_filename``, so the result does not depend on the OS."""
    entries = ((info.orig_filename, info.file_size, info) for info in zf.infolist())
    return file_members(
        entries, archive_name, logger, log_prefix, on_duplicate=on_duplicate
    )
