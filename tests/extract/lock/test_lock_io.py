# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the lock-file loaders of :mod:`pitloom.extract.lock._lock_io`
(``load_lock_toml``/``load_lock_json``): parse failures, the size cap and
the memo.

See also: tests/extract/lock/test_common.py (the other shared helpers).
"""

# pylint: disable=protected-access

import logging
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

import pitloom.extract.lock._lock_io as lock_io
import pitloom.extract.lock.common as lock_common
from pitloom.extract._extract_utils import FETCH_MAX_BYTES, quote_source
from pitloom.extract.lock.common import load_lock_json, load_lock_toml
from tests._bounded import run_bounded


def test_load_lock_toml_missing_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert load_lock_toml(Path(tmp) / "does-not-exist.lock") is None


def test_load_lock_toml_malformed_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_text("this is not [ valid toml", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = load_lock_toml(lock_path)

        assert result is None
        assert "Failed to parse" in caplog.text


def test_load_lock_toml_valid_file_returns_data() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_text('key = "value"\n', encoding="utf-8")

        assert load_lock_toml(lock_path) == {"key": "value"}


def test_load_lock_toml_invalid_utf8_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """tomllib/tomli raise a bare ``UnicodeDecodeError`` (not
    ``TOMLDecodeError``) for invalid UTF-8: the result degrades to ``None``
    with a ``WARNING:`` and the cascade continues."""
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_bytes(b'name = "\xff\xfebad"\n')

        with caplog.at_level(logging.WARNING):
            result = load_lock_toml(lock_path)

        assert result is None
        assert "Failed to parse" in caplog.text


def test_load_lock_toml_second_read_of_same_file_is_cached() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_text('key = "value"\n', encoding="utf-8")

        first = load_lock_toml(lock_path)
        second = load_lock_toml(lock_path)

        assert first == {"key": "value"}
        assert second is first  # the cached dict, not a freshly-parsed one


def test_load_lock_toml_no_cache_key_skips_caching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the file's identity cannot be determined (e.g. a stat() race), the
    parse succeeds and is not cached."""
    monkeypatch.setattr(lock_io, "_lock_file_cache_key", lambda _path: None)
    cache_size_before = len(lock_io._LOCK_FILE_CACHE)
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_text('key = "value"\n', encoding="utf-8")

        assert load_lock_toml(lock_path) == {"key": "value"}
        assert len(lock_io._LOCK_FILE_CACHE) == cache_size_before


def test_load_lock_json_second_read_of_same_file_is_cached() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.json"
        lock_path.write_text('{"key": "value"}', encoding="utf-8")

        first = load_lock_json(lock_path)
        second = load_lock_json(lock_path)

        assert first == {"key": "value"}
        assert second is first


def test_load_lock_json_no_cache_key_skips_caching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lock_io, "_lock_file_cache_key", lambda _path: None)
    cache_size_before = len(lock_io._LOCK_FILE_CACHE)
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.json"
        lock_path.write_text('{"key": "value"}', encoding="utf-8")

        assert load_lock_json(lock_path) == {"key": "value"}
        assert len(lock_io._LOCK_FILE_CACHE) == cache_size_before


def test_load_lock_json_invalid_utf8_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid UTF-8 in text mode raises a bare ``UnicodeDecodeError`` (not
    ``json.JSONDecodeError``): the result degrades to ``None`` with a
    ``WARNING:`` and the cascade continues."""
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.json"
        lock_path.write_bytes(b'{"name": "\xff\xfebad"}')

        with caplog.at_level(logging.WARNING):
            result = load_lock_json(lock_path)

        assert result is None
        assert "Failed to parse" in caplog.text


_LOADERS = pytest.mark.parametrize(
    "loader", [load_lock_toml, load_lock_json], ids=["toml", "json"]
)


@pytest.mark.parametrize(
    ("loader", "make"),
    [
        (load_lock_toml, lambda n: b"a=" + b"[" * n + b"]" * n),
        (load_lock_toml, lambda n: b"a=" + b"{a=" * n + b"1" + b"}" * n),
        (load_lock_json, lambda n: b"[" * n + b"]" * n),
        (load_lock_json, lambda n: b'{"a":' * n + b"1" + b"}" * n),
    ],
    ids=["toml-array", "toml-inline-table", "json-array", "json-object"],
)
def test_deeply_nested_lock_file_never_aborts(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    loader: Callable[[Path], object],
    make: Callable[[int], bytes],
) -> None:
    """Whatever the interpreter does with nesting past its recursion limit
    (the C JSON scanner's limit differs by Python version), the loader
    returns: ``None`` after at most one warning, or the parsed object. The
    ``RecursionError`` path itself is pinned by the next test."""
    lock_path = tmp_path / "some.lock"
    lock_path.write_bytes(make(max(2 * sys.getrecursionlimit(), 100_000)))
    with caplog.at_level(logging.WARNING):
        result = loader(lock_path)
    assert len(caplog.messages) == (result is None)


@_LOADERS
@pytest.mark.parametrize("error", [MemoryError, RecursionError])
def test_a_parser_resource_error_is_a_bad_file(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    loader: Callable[[Path], object],
    error: type[BaseException],
) -> None:
    """Raised by the parser itself (so the same on every Python version)."""

    def _fails(_raw: bytes) -> object:
        raise error

    monkeypatch.setattr(lock_io, "load_toml_bytes", _fails)
    monkeypatch.setattr(lock_io, "json", SimpleNamespace(loads=_fails))
    lock_path = tmp_path / "some.lock"
    lock_path.write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert loader(lock_path) is None
    assert caplog.messages == [
        f"Failed to parse {quote_source(lock_path)}: {error.__name__}"
    ]


@_LOADERS
def test_lock_file_over_the_size_cap_is_not_parsed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, loader: Callable[[Path], object]
) -> None:
    """One byte over the cap (a sparse file): one ``WARNING:``, no parse."""
    lock_path = tmp_path / "some.lock"
    with lock_path.open("wb") as handle:
        handle.truncate(FETCH_MAX_BYTES + 1)
    with caplog.at_level(logging.WARNING):
        assert loader(lock_path) is None
    assert caplog.messages == [
        f"Cannot read {quote_source(lock_path)}: over {FETCH_MAX_BYTES} bytes"
    ]


@_LOADERS
def test_directory_is_not_a_lock_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, loader: Callable[[Path], object]
) -> None:
    with caplog.at_level(logging.WARNING):
        assert loader(tmp_path) is None
    assert caplog.messages == [
        f"Cannot read {quote_source(tmp_path)}: not a regular file"
    ]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs POSIX FIFOs")
@_LOADERS
def test_fifo_is_refused_without_blocking(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, loader: Callable[[Path], object]
) -> None:
    """A FIFO reports size 0 and would block the open forever."""
    fifo = tmp_path / "pylock.toml"
    os.mkfifo(fifo)
    with caplog.at_level(logging.WARNING):
        result = run_bounded(lambda: loader(fifo))
    assert result is None
    assert "not a regular file" in caplog.text


def test_lock_file_cache_keeps_the_two_most_recent_files(tmp_path: Path) -> None:
    """The memo is bounded (the pin pass, then the hash pass): the least
    recently used file is dropped first."""
    lock_io._LOCK_FILE_CACHE.clear()
    paths = [tmp_path / f"{i}.toml" for i in range(3)]
    for path in paths:
        path.write_text("a = 1\n", encoding="utf-8")
    first, second, third = paths
    load_lock_toml(first)
    load_lock_toml(second)
    load_lock_toml(first)  # first is now the most recent
    load_lock_toml(third)
    assert [key[0] for key in lock_io._LOCK_FILE_CACHE] == [first, third]
    lock_io._LOCK_FILE_CACHE.clear()


@_LOADERS
def test_a_directory_is_refused_before_it_is_opened(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    loader: Callable[[Path], object],
) -> None:
    """Windows cannot ``os.open`` a directory (``EACCES``): the type is
    checked first, so the message is the same everywhere."""

    def _cannot_open(*_args: object, **_kwargs: object) -> int:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "open", _cannot_open)
    with caplog.at_level(logging.WARNING):
        assert loader(tmp_path) is None
    assert caplog.messages == [
        f"Cannot read {quote_source(tmp_path)}: not a regular file"
    ]


def test_the_lock_file_is_opened_binary_and_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``O_BINARY`` (Windows: no CRLF or Ctrl-Z handling) and ``O_NONBLOCK``
    are in the open flags where the platform has them."""
    monkeypatch.setattr(os, "O_BINARY", 0x8000, raising=False)
    monkeypatch.setattr(os, "O_NONBLOCK", 0x800, raising=False)
    seen: list[int] = []
    real_open = os.open

    def _spy(path: object, flags: int, *args: object) -> int:
        seen.append(flags)
        return real_open(path, flags & ~0x8000, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", _spy)
    lock_path = tmp_path / "a.toml"
    lock_path.write_bytes(b"a = 1\r\n")
    assert lock_common.read_lock_bytes(lock_path) == b"a = 1\r\n"
    assert seen and seen[0] & 0x8000 and seen[0] & 0x800


@pytest.mark.skipif(sys.platform == "win32", reason="Windows cannot open a directory")
def test_a_file_swapped_for_a_directory_after_the_check_is_refused_and_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The descriptor's own type is checked after the open (the path may have
    changed since the first ``stat``); a refusal closes the descriptor."""
    regular = tmp_path / "a.toml"
    regular.write_text("a = 1\n", encoding="utf-8")
    swapped = tmp_path / "swapped"
    swapped.mkdir()
    real_stat, real_open, real_close = os.stat, os.open, os.close
    opened: list[int] = []
    closed: list[int] = []

    def _stat(path: object, *args: object, **kwargs: object) -> os.stat_result:
        target = regular if path == swapped else path
        return real_stat(target, *args, **kwargs)  # type: ignore[arg-type]

    def _open(path: object, flags: int, *args: object) -> int:
        descriptor = real_open(path, flags, *args)  # type: ignore[arg-type]
        opened.append(descriptor)
        return descriptor

    def _close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(os, "stat", _stat)
    monkeypatch.setattr(os, "open", _open)
    monkeypatch.setattr(os, "close", _close)
    with pytest.raises(ValueError, match="not a regular file"):
        lock_common.read_lock_bytes(swapped)
    assert opened and closed == opened
