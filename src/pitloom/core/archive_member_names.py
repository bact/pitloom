# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Archive member names -> install-location names, identical on every OS.

Every reader that turns wheel or sdist archive members into
``ProjectFile``/``IncludedFile`` distribution paths goes through
:func:`archive_members` (:func:`zip_file_members` for a ZIP), so
``software_File.name`` and every lookup keyed by it (``contains``,
``hasDataFile``, registry, phantom dependencies) agree.

See also: ``working-docs/implementation/archive-member-names.md``.
"""

from __future__ import annotations

import logging
import re
import zipfile
from collections.abc import Iterable
from typing import Literal, NamedTuple, TypeVar

from pitloom.core._models_wheel_types import to_posix_distribution_path

MemberNameStatus = Literal["ok", "normalized", "unsafe"]

T = TypeVar("T")

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")

_MSG = "%sARCHIVE=%s ENTRY=%r: "
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


def _ancestors(names: Iterable[str]) -> set[str]:
    """Every proper ``/``-prefix directory of *names*."""
    found: set[str] = set()
    for name in names:
        segments = name.split("/")
        found.update("/".join(segments[:i]) for i in range(1, len(segments)))
    return found


def archive_members(
    entries: Iterable[tuple[str, T]],
    archive_name: str,
    logger: logging.Logger | None,
    log_prefix: str = "",
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
    another call already reported on.
    """
    classified = [
        (raw, normalize_member_name(raw), payload) for raw, payload in entries
    ]
    last = {m.name: i for i, (_, m, _) in enumerate(classified) if m.status != "unsafe"}
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


def is_directory_member(info: zipfile.ZipInfo) -> bool:
    """Whether *info* is a directory entry, judged by its raw name.

    ``ZipInfo.is_dir()`` reads ``filename``, which CPython converts from
    ``os.sep`` only on Windows; ``orig_filename`` is the raw name. A name
    ending in a ``.`` segment (``pkg/.``) names a directory too.
    """
    posix = to_posix_distribution_path(info.orig_filename)
    return posix.endswith(("/", "/.")) or posix == "."


def zip_file_members(
    zf: zipfile.ZipFile,
    archive_name: str,
    logger: logging.Logger | None,
    log_prefix: str = "",
) -> list[tuple[str, zipfile.ZipInfo]]:
    """:func:`archive_members` for a ZIP (wheel or ``.zip`` sdist).

    Names come from ``orig_filename``, so the result does not depend on the
    OS. Directory entries are skipped; one that carries data gets a
    ``WARNING:`` too.
    """
    files: list[tuple[str, zipfile.ZipInfo]] = []
    for info in zf.infolist():
        if not is_directory_member(info):
            files.append((info.orig_filename, info))
        elif info.file_size and logger is not None:
            logger.warning(
                _DIRECTORY_DATA, log_prefix, archive_name, info.orig_filename
            )
    return archive_members(files, archive_name, logger, log_prefix)
