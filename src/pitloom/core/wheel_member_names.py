# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Wheel member names -> install-location names, identical on every OS.

Every reader that turns a wheel's ZIP member names into
``ProjectFile``/``IncludedFile`` distribution paths goes through
:func:`wheel_file_members`, so ``software_File.name`` and every lookup keyed
by it (``contains``, ``hasDataFile``, registry, phantom dependencies) agree.

See also: ``working-docs/implementation/wheel-member-names.md``.
"""

from __future__ import annotations

import logging
import re
import zipfile
from typing import Literal, NamedTuple

from pitloom.core._models_wheel_types import to_posix_distribution_path

MemberNameStatus = Literal["ok", "normalized", "unsafe"]

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


class WheelMemberName(NamedTuple):
    """A classified wheel member name.

    ``name`` is the install location (``/``-separated, no empty or ``.``
    segments) when ``status`` is ``"ok"`` or ``"normalized"``. For
    ``"unsafe"`` it is the ``/``-separated raw name, for messages only --
    never use it as a path.
    """

    name: str
    status: MemberNameStatus


def normalize_wheel_member_name(raw: str) -> WheelMemberName:
    """Classify and normalise one raw ZIP member name.

    Separators become ``/``; empty and ``.`` segments are dropped. A name
    that is absolute (leading ``/``, a drive letter on its first remaining
    segment), has a ``..`` segment, contains NUL or is empty after
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
        return WheelMemberName(posix, "unsafe")
    name = "/".join(segments)
    return WheelMemberName(name, "ok" if name == raw else "normalized")


def is_directory_member(info: zipfile.ZipInfo) -> bool:
    """Whether *info* is a directory entry, judged by its raw name.

    ``ZipInfo.is_dir()`` reads ``filename``, which CPython converts from
    ``os.sep`` only on Windows; ``orig_filename`` is the raw name. A name
    ending in a ``.`` segment (``pkg/.``) names a directory too.
    """
    posix = to_posix_distribution_path(info.orig_filename)
    return posix.endswith(("/", "/.")) or posix == "."


class WheelFileMember(NamedTuple):
    """One file member of a wheel and its install-location name."""

    info: zipfile.ZipInfo
    name: str


_UNSAFE = "%s%s: wheel entry %r has no safe install location -- skipped"
_OVERWRITTEN = "%s%s: wheel entry %r is overwritten by later entry %r -- skipped"
_NORMALIZED = "%s%s: wheel entry %r is non-conforming -- recorded as %r"


def wheel_file_members(
    zf: zipfile.ZipFile,
    wheel_name: str,
    logger: logging.Logger,
    log_prefix: str = "",
) -> list[WheelFileMember]:
    """File members of *zf* under their install-location names.

    Archive order; directory entries are skipped. Names come from
    ``orig_filename``, so the result does not depend on the OS. Exactly one
    ``WARNING:`` per member that is skipped as unsafe, skipped because a
    later member has the same name (an installer extracts in archive order,
    so the later one is what gets installed), or kept under its normalised
    name. Each quotes the raw name.
    """
    classified = [
        (info, normalize_wheel_member_name(info.orig_filename))
        for info in zf.infolist()
        if not is_directory_member(info)
    ]
    last = {m.name: i for i, (_, m) in enumerate(classified) if m.status != "unsafe"}
    members: list[WheelFileMember] = []
    for index, (info, member) in enumerate(classified):
        raw = info.orig_filename
        if member.status == "unsafe":
            logger.warning(_UNSAFE, log_prefix, wheel_name, raw)
        elif last[member.name] != index:
            later = classified[last[member.name]][0].orig_filename
            logger.warning(_OVERWRITTEN, log_prefix, wheel_name, raw, later)
        else:
            if member.status == "normalized":
                logger.warning(_NORMALIZED, log_prefix, wheel_name, raw, member.name)
            members.append(WheelFileMember(info, member.name))
    return members
