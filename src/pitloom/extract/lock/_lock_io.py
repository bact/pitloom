# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reading lock files for the extractors in this package: a bounded read,
a refusal for a file that is not a regular file or is over the size cap, and
a small cache of parsed TOML/JSON.

See also: :mod:`pitloom.extract.lock.common`, which re-exports these names.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitloom._toml_io import load_toml_bytes
from pitloom.core.quote_source import quote_source
from pitloom.extract._extract_utils import FETCH_MAX_BYTES
from pitloom.logging_config import one_line

log = logging.getLogger(__name__)

#: (path, mtime_ns, size) -> parsed lock data. A pin extractor and its hash
#: companion parse the same file back to back; a changed or vanished file
#: has a different key, so it is never served stale. Callers only read the
#: dict. Only the most recent ``_LOCK_FILE_CACHE_SIZE`` files are kept.
_LockFileCacheKey = tuple[Path, int, int]
_LOCK_FILE_CACHE: dict[_LockFileCacheKey, dict[str, Any]] = {}
_LOCK_FILE_CACHE_SIZE = 2


def _lock_file_cache_key(lock_path: Path) -> _LockFileCacheKey | None:
    """*lock_path*'s ``(path, mtime_ns, size)`` cache key, or ``None`` when it
    cannot be ``stat()``-ed."""
    try:
        stat_result = lock_path.stat()
    except OSError:
        return None
    return (lock_path, stat_result.st_mtime_ns, stat_result.st_size)


class LockFileRefusedError(ValueError):
    """A lock/pin file that is not read at all: not a regular file, or over
    :data:`~pitloom.extract._extract_utils.FETCH_MAX_BYTES`."""


def read_lock_bytes(lock_path: Path) -> bytes:
    """*lock_path*'s bytes, reading at most ``FETCH_MAX_BYTES`` + 1.

    The type is checked before the open and again on the open descriptor,
    which is binary and non-blocking; ``st_size`` is not trusted.

    Raises:
        LockFileRefusedError: Not a regular file, or over the cap.
        OSError: Any other failure (``FileNotFoundError`` included); the
            caller logs its own ``WARNING:``.
    """
    # Pre-stat: Windows cannot open a directory. Non-blocking open plus the
    # fstat below: a FIFO swapped in after the stat cannot hang the read.
    if not stat.S_ISREG(os.stat(lock_path).st_mode):
        raise LockFileRefusedError("not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(lock_path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise LockFileRefusedError("not a regular file")
        handle = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with handle:
        raw = handle.read(FETCH_MAX_BYTES + 1)
    if len(raw) > FETCH_MAX_BYTES:
        raise LockFileRefusedError(f"over {FETCH_MAX_BYTES} bytes")
    return raw


def warn_unreadable_lock_file(lock_path: Path, exc: BaseException) -> None:
    """The one ``WARNING:`` for a lock/pin file that can't be read or
    parsed (*exc*: why): ``Cannot read`` for a file refused before parsing,
    ``Failed to parse`` otherwise."""
    verb = "Cannot read" if isinstance(exc, LockFileRefusedError) else "Failed to parse"
    log.warning("%s %s: %s", verb, quote_source(lock_path), one_line(exc))


def _load_lock(
    lock_path: Path, parse: Callable[[bytes], Any], kind: str
) -> dict[str, Any] | None:
    """Parse *lock_path* with *parse* (a *kind* reader), through the cache.

    Returns ``None`` silently for an absent file, and after one ``WARNING:``
    for one that is refused, unreadable, unparseable or not a table/object.
    """
    cache_key = _lock_file_cache_key(lock_path)
    if cache_key is not None and cache_key in _LOCK_FILE_CACHE:
        data = _LOCK_FILE_CACHE.pop(cache_key)
        _LOCK_FILE_CACHE[cache_key] = data  # most recent last
        return data
    try:
        data = parse(read_lock_bytes(lock_path))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError, MemoryError) as exc:
        # ValueError covers the format's decode errors, a bare
        # UnicodeDecodeError and LockFileRefusedError.
        warn_unreadable_lock_file(lock_path, exc)
        return None
    if not isinstance(data, dict):
        log.warning(
            "%s: top-level %s value is %s, expected an object",
            quote_source(lock_path),
            kind,
            type(data).__name__,
        )
        return None
    if cache_key is not None:
        if len(_LOCK_FILE_CACHE) >= _LOCK_FILE_CACHE_SIZE:
            del _LOCK_FILE_CACHE[next(iter(_LOCK_FILE_CACHE))]
        _LOCK_FILE_CACHE[cache_key] = data
    return data


def load_lock_toml(lock_path: Path) -> dict[str, Any] | None:
    """Load *lock_path* as TOML; ``None`` (silently if absent, else after
    a ``WARNING:``) instead of raising."""
    return _load_lock(lock_path, load_toml_bytes, "TOML")


def load_lock_json(lock_path: Path) -> dict[str, Any] | None:
    """:func:`load_lock_toml` for JSON (``Pipfile.lock``); a top level that
    is not an object is rejected with a ``WARNING:``."""
    return _load_lock(lock_path, json.loads, "JSON")
