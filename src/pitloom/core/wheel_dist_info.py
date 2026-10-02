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
import email.message
import email.parser
import importlib
import logging
import lzma
import re
import zipfile
import zlib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import IO, NamedTuple

from packaging.utils import NormalizedName, canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom.core.archive_member_names import zip_file_members
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

#: Upper bound on the bytes of a ``METADATA`` header block read into memory.
MAX_METADATA_BYTES = 16 * 1024 * 1024

#: Upper bound on the headers of a ``METADATA`` header block. Parsed, each
#: header costs a few hundred bytes, so the byte cap alone bounds nothing:
#: 16 MiB of ``X-A: b`` lines is 2.4 million of them.
MAX_METADATA_HEADERS = 10_000

#: Longest ``.dist-info`` stem tried: one path component, so no file system
#: installs a longer one. Bounds the per-dash split of :func:`is_dist_info_of`.
MAX_NAME_CHARS = 255
_CHUNK_BYTES = 8192
_SUFFIX = ".dist-info"
_LINE_END = re.compile(rb"\r\n|\r|\n")
_BLANK_LINES = (b"\n", b"\r", b"\r\n")
_PROJECT_NAME = re.compile(r"[\w.]+")


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


class WheelRefused(ValueError):
    """A wheel Pitloom refuses as a whole, with one clean line."""


def refusal(archive: str, entry: str | None, reason: str) -> WheelRefused:
    """The one shape of every wheel refusal:
    ``ARCHIVE='a.whl' ENTRY='m': <reason> -- wheel refused`` (no ``ENTRY=``
    where no member is to blame).

    Archive and member are ``repr``, so a hostile name cannot forge a line.
    """
    where = f"ARCHIVE={archive!r}" + (f" ENTRY={entry!r}" if entry is not None else "")
    return WheelRefused(f"{where}: {reason} -- wheel refused")


def exception_label(exc: BaseException) -> str:
    """The type of *exc* for a message, never its text: bare for a builtin
    (``EOFError``), qualified otherwise (``zlib.error``)."""
    cls = type(exc)
    if cls.__module__ == "builtins":
        return cls.__name__
    return f"{cls.__module__}.{cls.__qualname__}"


def unreadable_member_error(
    archive: str, entry: str | None, exc: BaseException
) -> WheelRefused:
    """The error that refuses a wheel one of whose members cannot be read."""
    return refusal(archive, entry, f"could not read ({exception_label(exc)})")


def wheel_members(
    zf: zipfile.ZipFile, archive: str, logger: logging.Logger | None = None
) -> list[tuple[str, zipfile.ZipInfo]]:
    """The wheel's file members as (install-location name, ``ZipInfo``).

    The one member list every wheel reader selects a ``.dist-info`` from (see
    :func:`pitloom.core.archive_member_names.zip_file_members`: names
    normalised, directory entries dropped). Two members with one name,
    exactly or once normalised (``a/M`` and ``a\\M``), are not an
    installable wheel and no reader can tell which one is meant: the wheel
    is refused. So is a member whose name holds a NUL: ``zipfile`` cuts
    ``ZipInfo.filename`` there, so an installer extracts it under a
    shorter name that may be another member's.

    Raises:
        WheelRefused: Two members have the same name, or a name holds a NUL.
    """
    for info in zf.infolist():
        if "\0" in info.orig_filename:
            raise refusal(archive, info.orig_filename, "NUL in member name")
    return zip_file_members(
        zf,
        archive,
        logger,
        on_duplicate=lambda raw: refusal(archive, raw, "duplicate member name"),
    )


def open_wheel_zip(path: Path) -> zipfile.ZipFile:
    """Open *path* as a ZIP archive.

    Raises:
        WheelRefused: *path* cannot be read as a ZIP archive: not one, a
            member name flagged UTF-8 that is not, a version it cannot
            read. Any exception but ``OSError``, so a ``zipfile`` failure
            mode added later is a refusal too.
        OSError: *path* cannot be opened (missing, permission denied, a
            transient I/O error): left as it is, so a caller can retry it.
    """
    try:
        return zipfile.ZipFile(path, "r")
    except OSError:
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        raise refusal(
            path.name, None, f"could not open ({exception_label(exc)})"
        ) from exc


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


def wheel_name_version(wheel_name: str) -> tuple[NormalizedName, Version] | None:
    """The canonical name and version a wheel file name (PEP 427) carries, or
    ``None`` where it is not a wheel file name.

    The tags are not read: what they must look like changes between
    ``packaging`` releases, and the answer must not depend on which one is
    installed.
    """
    stem = wheel_name.removesuffix(".whl")
    parts = stem.split("-")
    if stem == wheel_name or len(parts) not in (5, 6):
        return None
    name = parts[0]
    if "__" in name or _PROJECT_NAME.fullmatch(name) is None:
        return None
    try:
        return canonicalize_name(name), Version(parts[1])
    except InvalidVersion:
        return None


def is_dist_info_of(directory: str, name: str, version: Version) -> bool:
    """Whether top-level *directory* is ``<name>-<version>.dist-info`` for the
    canonical *name* and *version*, compared as the ecosystem does (PEP 503
    names, PEP 440 versions): ``My.Pkg-1.0`` is ``my_pkg-1.0.0``.

    Every ``-`` is tried as the split, as a name may hold one
    (``foo-bar-1.0``) and so may a version (``1-2`` is ``1.post2``).
    """
    if not directory.endswith(_SUFFIX):
        return False
    stem = directory[: -len(_SUFFIX)]
    if len(stem) > MAX_NAME_CHARS:
        return False
    return any(
        canonicalize_name(stem[:i]) == name and _is_version(stem[i + 1 :], version)
        for i, char in enumerate(stem)
        if char == "-"
    )


def _is_version(text: str, version: Version) -> bool:
    try:
        return Version(text) == version
    except InvalidVersion:
        return False


def matching_dist_infos(
    wheel_name: str, member_names: Iterable[str]
) -> tuple[str, ...]:
    """``"<dir>/"`` for each top-level directory that is the ``.dist-info``
    of the wheel *wheel_name* names (PEP 427), sorted.

    Empty where *wheel_name* is not a wheel file name.
    """
    parsed = wheel_name_version(wheel_name)
    if parsed is None:
        return ()
    name, version = parsed
    return tuple(
        d
        for d in top_level_dist_infos(member_names)
        if is_dist_info_of(d[:-1], name, version)
    )


#: What :func:`resolve_own_dist_info` says where it chooses nothing, or not the
#: plain match. One definition each, shared by every reader's warning/error.
PROBLEM_NONE = "no top-level .dist-info directory"
PROBLEM_SEVERAL_MATCH = "several top-level .dist-info directories match the file name"
PROBLEM_NOT_A_WHEEL_NAME = (
    "the file name is not a wheel name and several top-level .dist-info "
    "directories exist"
)
PROBLEM_SEVERAL_NONE_MATCH = (
    "several top-level .dist-info directories, none the one the file name names"
)
_PROBLEM_OTHER = "the file name names no top-level .dist-info; using %s"


def resolve_own_dist_info(
    wheel_name: str, member_names: Iterable[str]
) -> DistInfoChoice:
    """The wheel's own ``.dist-info``, and what to say when it is not the
    plain match.

    - Exactly one top-level directory matches the file name: it.
    - Otherwise exactly one top-level ``.dist-info``: it, with a problem
      when the file name is a wheel file name that names another directory.
    - Otherwise none, with a problem: ``PROBLEM_NONE``, or one of the three
      reasons several cannot be told apart.
    """
    names = list(member_names)
    matching = matching_dist_infos(wheel_name, names)
    if len(matching) == 1:
        return DistInfoChoice(matching[0], None)
    present = top_level_dist_infos(names)
    is_wheel_name = wheel_name_version(wheel_name) is not None
    if len(present) == 1:
        problem = _PROBLEM_OTHER % loggable(present[0]) if is_wheel_name else None
        return DistInfoChoice(present[0], problem)
    if not present:
        return DistInfoChoice(None, PROBLEM_NONE)
    if matching:
        return DistInfoChoice(None, PROBLEM_SEVERAL_MATCH)
    if not is_wheel_name:
        return DistInfoChoice(None, PROBLEM_NOT_A_WHEEL_NAME)
    return DistInfoChoice(None, PROBLEM_SEVERAL_NONE_MATCH)


class _OverCap(Exception):
    """A header block over a cap: its size and unit."""

    def __init__(self, cap: int, unit: str) -> None:
        super().__init__(cap, unit)
        self.cap = cap
        self.unit = unit


def _lines(stream: IO[bytes]) -> Iterator[bytes]:
    """The lines of *stream* (``\\n``, ``\\r`` or ``\\r\\n`` ends, kept), read
    lazily in chunks.

    Raises:
        _OverCap: One line is longer than :data:`MAX_METADATA_BYTES`.
    """
    pending = bytearray()
    carry = b""  # a trailing CR, which may be half of a CRLF
    while chunk := stream.read(_CHUNK_BYTES):
        chunk = carry + chunk
        carry = b"\r" if chunk.endswith(b"\r") else b""
        chunk = chunk[: len(chunk) - len(carry)]
        start = 0
        for match in _LINE_END.finditer(chunk):
            pending += chunk[start : match.end()]
            yield bytes(pending)
            pending.clear()
            start = match.end()
        pending += chunk[start:]
        if len(pending) > MAX_METADATA_BYTES:
            raise _OverCap(MAX_METADATA_BYTES, "bytes")
    if pending or carry:
        yield bytes(pending) + carry


def _header_block(stream: IO[bytes]) -> bytes:
    """The bytes of *stream* up to the blank line that ends its headers.

    Reading stops there: a ``METADATA`` description follows, and may be any
    size.

    Raises:
        _OverCap: The block is over :data:`MAX_METADATA_BYTES` or
            :data:`MAX_METADATA_HEADERS`.
    """
    kept: list[bytes] = []
    total = headers = 0
    for line in _lines(stream):
        if line in _BLANK_LINES:
            break
        total += len(line)
        if total > MAX_METADATA_BYTES:
            raise _OverCap(MAX_METADATA_BYTES, "bytes")
        if not line.startswith((b" ", b"\t")):
            headers += 1
            if headers > MAX_METADATA_HEADERS:
                raise _OverCap(MAX_METADATA_HEADERS, "headers")
        kept.append(line)
    return b"".join(kept)


def read_metadata_headers(
    zf: zipfile.ZipFile,
    members: Iterable[tuple[str, zipfile.ZipInfo]],
    prefix: str,
    archive: str,
    *,
    report: bool = True,
) -> email.message.Message | None:
    """The headers of the ``METADATA`` in the ``.dist-info`` *prefix*
    (``"<dir>/"``), parsed, or ``None``: the wheel's identity is unknown.

    The one place every reader of a wheel's ``METADATA`` goes through, so
    that none can parse more than the headers or read more than the caps
    allow, and each says why it found nothing in the same words. One
    ``WARNING:`` where the member is absent, or its header block is over
    :data:`MAX_METADATA_BYTES` or :data:`MAX_METADATA_HEADERS`; none with
    *report* false, for a caller whose own message says so.

    Raises:
        WheelRefused: The member cannot be read.
    """
    target = f"{prefix}METADATA"
    info = next((i for name, i in members if name == target), None)
    if info is None:
        if report:
            log.warning("ARCHIVE=%r: no %s -- identity unknown", archive, target)
        return None
    try:
        with refuse_unreadable(archive, info.orig_filename), zf.open(info) as member:
            block = _header_block(member)
    except _OverCap as over:
        if report:
            log.warning(
                "ARCHIVE=%r ENTRY=%r: header block over %d %s -- identity unknown",
                archive,
                info.orig_filename,
                over.cap,
                over.unit,
            )
        return None
    return email.parser.HeaderParser().parsestr(block.decode("utf-8", "replace"))
