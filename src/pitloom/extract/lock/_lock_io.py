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
from pitloom.extract._extract_utils import FETCH_MAX_BYTES, quote_source
from pitloom.logging_config import one_line

log = logging.getLogger(__name__)

#: (path, mtime_ns, size) -> already-parsed lock data, for
#: :func:`load_lock_toml`/:func:`load_lock_json`. A format's pin extractor
#: and its hash-extraction companion (see
#: :mod:`pitloom.extract.lock.pylock_hash` and its siblings) both read and
#: parse the same winning lock file back-to-back within one cascade
#: lookup -- caching by the file's own current identity (not just its
#: path) means a second read within the same run is a dict lookup instead
#: of a re-parse, while a file that's changed or disappeared since the
#: last read (a different mtime/size, or a failed ``stat()``) is never
#: served stale: its cache key simply won't match, so it falls through to
#: a real re-read. Safe because every caller only reads the returned
#: dict, never mutates it. Holds only the :data:`_LOCK_FILE_CACHE_SIZE` most
#: recently used files (the pin pass, then the hash pass), so a long-lived
#: process does not accumulate every lock file it ever read.
_LockFileCacheKey = tuple[Path, int, int]
_LOCK_FILE_CACHE: dict[_LockFileCacheKey, dict[str, Any]] = {}
_LOCK_FILE_CACHE_SIZE = 2


def _lock_file_cache_key(lock_path: Path) -> _LockFileCacheKey | None:
    """Return *lock_path*'s current ``(path, mtime_ns, size)`` identity
    for :data:`_LOCK_FILE_CACHE`, or ``None`` when it can't be
    ``stat()``-ed (absent, permission error, etc.) -- callers treat
    ``None`` as "don't use the cache for this call" rather than raising,
    since the caller's own subsequent read attempt already handles that
    case.
    """
    try:
        stat_result = lock_path.stat()
    except OSError:
        return None
    return (lock_path, stat_result.st_mtime_ns, stat_result.st_size)


class LockFileRefusedError(ValueError):
    """A lock/pin file that is not read at all: not a regular file, or over
    :data:`~pitloom.extract._extract_utils.FETCH_MAX_BYTES`."""


def read_lock_bytes(lock_path: Path) -> bytes:
    """*lock_path*'s bytes, read through at most :data:`FETCH_MAX_BYTES` + 1.

    The type is checked before the open (Windows cannot open a directory) and
    again on the open descriptor, which is binary and non-blocking, so a FIFO
    swapped in for the file cannot hang the read and ``st_size`` is never
    trusted. Raises ``FileNotFoundError``, any other ``OSError``, or
    :class:`LockFileRefusedError` for a file that is not a regular file or is
    over the cap;
    every lock/pin reader logs its own ``WARNING:``."""
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
    """Parse *lock_path*'s bytes with *parse* (a *kind* -- ``"TOML"`` or
    ``"JSON"`` -- reader), through :data:`_LOCK_FILE_CACHE`, returning
    ``None`` after one ``WARNING:`` for a file that is not a regular file,
    is over the size cap, can't be read or parsed (invalid UTF-8, nesting
    too deep for the parser, too large to hold) or whose top level isn't a
    table/object, and silently for an absent file."""
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
        # ValueError: the format's own decode error, a bare
        # UnicodeDecodeError for invalid UTF-8 and the reader's own
        # refusals alike -- a bad file, not a reason to abort the whole
        # cascade.
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
    """Load *lock_path* as TOML, returning ``None`` (after a
    ``WARNING:`` for an oversized or unparseable file, silently for a
    simply-absent one) instead of raising -- every lock format is optional
    enrichment, never a requirement, so a caller's usual next step is
    ``if data is None: return []``.

    See :data:`_LOCK_FILE_CACHE` for the memoization this and
    :func:`load_lock_json` share.
    """
    return _load_lock(lock_path, load_toml_bytes, "TOML")


def load_lock_json(lock_path: Path) -> dict[str, Any] | None:
    """Read and parse *lock_path* as JSON, returning ``None`` (after a
    ``WARNING:`` for an oversized, unparseable or wrong-shaped file,
    silently for a simply-absent one) instead of raising -- the
    JSON-format counterpart of :func:`load_lock_toml`, for
    ``Pipfile.lock`` (JSON, unlike every other lock/pin format this
    module serves, which are TOML).

    JSON's top level can legally be an array, string, number, or
    ``null`` (TOML's grammar guarantees a table), so a non-object is
    rejected with a ``WARNING:`` and every caller can rely on this
    function's declared ``dict[str, Any] | None`` return type without
    its own defensive `isinstance` check.
    """
    return _load_lock(lock_path, json.loads, "JSON")
