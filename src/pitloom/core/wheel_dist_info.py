# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which ``.dist-info`` directory is a wheel's own, and a bounded read of its
``METADATA``.

The one selector every wheel reader goes through, so that they cannot
disagree on a wheel's identity: only a *top-level* directory can be the
wheel's own, never a ``.dist-info`` vendored under a package. Where the file
name (PEP 427) names the directory, that one; where it does not (a renamed
file, a library caller's arbitrary path), the only top-level ``.dist-info``
when there is exactly one.

See also: :mod:`pitloom.extract.wheel` (``read_wheel``),
:mod:`pitloom._wheel_sbom_location` (verify, embed) and
:mod:`pitloom.extract.scanner_wheel` (the model scan).
"""

from __future__ import annotations

import contextlib
import importlib
import lzma
import zipfile
import zlib
from collections.abc import Iterable, Iterator
from typing import IO, NamedTuple

from packaging.utils import (
    InvalidWheelFilename,
    canonicalize_name,
    parse_wheel_filename,
)
from packaging.version import InvalidVersion, Version

from pitloom.logging_config import loggable

#: Upper bound on the bytes of a ``METADATA`` member read into memory.
MAX_METADATA_BYTES = 16 * 1024 * 1024

_CHUNK_BYTES = 8192
_SUFFIX = ".dist-info"


def _zstd_errors() -> tuple[type[Exception], ...]:
    """``compression.zstd.ZstdError`` where zipfile can read Zstandard members
    (Python 3.14+); detected by importing, not by version."""
    try:
        module = importlib.import_module("compression.zstd")
    except ImportError:
        return ()
    error = getattr(module, "ZstdError", None)
    return (error,) if isinstance(error, type) else ()


#: Everything a damaged, encrypted, unsupported or badly named member raises
#: on opening or reading.
MEMBER_READ_ERRORS: tuple[type[Exception], ...] = (
    RuntimeError,
    NotImplementedError,
    UnicodeDecodeError,
    zlib.error,
    lzma.LZMAError,
    EOFError,
    zipfile.BadZipFile,
    *_zstd_errors(),
)


def unreadable_member_error(archive: str, entry: str, exc: BaseException) -> ValueError:
    """The error that refuses a wheel one of whose members cannot be read.

    Names the archive and the member (``repr``, so a hostile name cannot
    forge a line) and the exception's type, never its text.
    """
    return ValueError(
        f"ARCHIVE={archive!r} ENTRY={entry!r}: could not read "
        f"({type(exc).__name__}) -- wheel refused"
    )


@contextlib.contextmanager
def refuse_unreadable(archive: str, entry: str) -> Iterator[None]:
    """Turn a read failure of *entry* in the block into the wheel-refusing
    error of :func:`unreadable_member_error`."""
    try:
        yield
    except MEMBER_READ_ERRORS as exc:
        raise unreadable_member_error(archive, entry, exc) from exc


# pylint: disable-next=too-few-public-methods
class RefusingReader:
    """A member stream whose ``read()`` raises the error of
    :func:`unreadable_member_error`, so a copy loop reports a failure of the
    source only, never of its destination."""

    def __init__(self, stream: IO[bytes], archive: str, entry: str) -> None:
        self._stream = stream
        self._archive = archive
        self._entry = entry

    def read(self, size: int = -1) -> bytes:
        """Up to *size* bytes of the member."""
        with refuse_unreadable(self._archive, self._entry):
            return self._stream.read(size)


class DistInfoChoice(NamedTuple):
    """The wheel's own ``.dist-info`` directory.

    ``prefix`` is ``"<dir>/"``, or ``None`` when there is none. ``problem``
    is a ``WARNING:`` tail to log when the choice is not the plain match, or
    ``None``.
    """

    prefix: str | None
    problem: str | None


def top_level_dist_infos(member_names: Iterable[str]) -> tuple[str, ...]:
    """``"<dir>/"`` for each top-level ``*.dist-info`` directory, sorted."""
    return tuple(
        sorted(
            {
                f"{parts[0]}/"
                for name in member_names
                if len(parts := name.split("/")) > 1 and parts[0].endswith(_SUFFIX)
            }
        )
    )


def is_dist_info_of(directory: str, name: str, version: Version) -> bool:
    """Whether top-level *directory* is ``<name>-<version>.dist-info`` for the
    canonical *name* and *version*, compared as the ecosystem does (PEP 503
    names, PEP 440 versions): ``My.Pkg-1.0`` is ``my_pkg-1.0.0``."""
    distribution, dash, release = directory[: -len(_SUFFIX)].partition("-")
    if not (directory.endswith(_SUFFIX) and dash):
        return False
    try:
        return canonicalize_name(distribution) == name and Version(release) == version
    except InvalidVersion:
        return False


def matching_dist_infos(
    wheel_name: str, member_names: Iterable[str]
) -> tuple[str, ...]:
    """``"<dir>/"`` for each top-level directory that is the ``.dist-info``
    of the wheel *wheel_name* names (PEP 427), sorted.

    Empty where *wheel_name* is not a wheel file name.
    """
    try:
        name, version, _, _ = parse_wheel_filename(wheel_name)
    except InvalidWheelFilename:
        return ()
    return tuple(
        d
        for d in top_level_dist_infos(member_names)
        if is_dist_info_of(d[:-1], name, version)
    )


def resolve_own_dist_info(
    wheel_name: str, member_names: Iterable[str]
) -> DistInfoChoice:
    """The wheel's own ``.dist-info``, and what to say when it is not the
    plain match.

    - Exactly one top-level directory matches the file name: it.
    - Otherwise exactly one top-level ``.dist-info``: it, with a problem
      when the file name is a wheel file name that names another directory.
    - Otherwise none, with a problem.
    """
    names = list(member_names)
    matching = matching_dist_infos(wheel_name, names)
    if len(matching) == 1:
        return DistInfoChoice(matching[0], None)
    present = top_level_dist_infos(names)
    if len(present) == 1:
        try:
            parse_wheel_filename(wheel_name)
        except InvalidWheelFilename:
            return DistInfoChoice(present[0], None)
        return DistInfoChoice(
            present[0],
            f"the file name names no top-level .dist-info; using "
            f"{loggable(present[0])}",
        )
    if present:
        return DistInfoChoice(
            None,
            "several top-level .dist-info directories, none the one the file "
            "name names; metadata not read",
        )
    return DistInfoChoice(None, "no top-level .dist-info directory; metadata not read")


def own_dist_info(wheel_name: str, member_names: Iterable[str]) -> str | None:
    """``"<dir>/"`` of the wheel's own top-level ``.dist-info``, or ``None``.

    See :func:`resolve_own_dist_info`.
    """
    return resolve_own_dist_info(wheel_name, member_names).prefix


def read_member_bounded(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int
) -> bytes | None:
    """The member's bytes, or ``None`` once it holds more than *limit*.

    Reads in chunks and counts what it gets, never trusting the declared
    size; stops at the first chunk past *limit*.

    Raises:
        MEMBER_READ_ERRORS: The member cannot be read.
    """
    chunks: list[bytes] = []
    total = 0
    with zf.open(info) as member:
        while chunk := member.read(_CHUNK_BYTES):
            total += len(chunk)
            if total > limit:
                return None
            chunks.append(chunk)
    return b"".join(chunks)
