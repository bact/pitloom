# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the lock-file loaders of :mod:`pitloom.extract.lock.common`
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
    monkeypatch.setattr(lock_common, "_lock_file_cache_key", lambda _path: None)
    cache_size_before = len(lock_common._LOCK_FILE_CACHE)
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_text('key = "value"\n', encoding="utf-8")

        assert load_lock_toml(lock_path) == {"key": "value"}
        assert len(lock_common._LOCK_FILE_CACHE) == cache_size_before


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
    monkeypatch.setattr(lock_common, "_lock_file_cache_key", lambda _path: None)
    cache_size_before = len(lock_common._LOCK_FILE_CACHE)
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.json"
        lock_path.write_text('{"key": "value"}', encoding="utf-8")

        assert load_lock_json(lock_path) == {"key": "value"}
        assert len(lock_common._LOCK_FILE_CACHE) == cache_size_before


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
def test_deeply_nested_lock_file_warns_once_instead_of_aborting(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    loader: Callable[[Path], object],
    make: Callable[[int], bytes],
) -> None:
    """Nesting past the interpreter's recursion limit (the C JSON scanner's
    own limit is higher on newer Pythons) is a bad file like any other,
    whatever the parser raises for it."""
    lock_path = tmp_path / "some.lock"
    lock_path.write_bytes(make(max(2 * sys.getrecursionlimit(), 100_000)))
    with caplog.at_level(logging.WARNING):
        assert loader(lock_path) is None
    (message,) = caplog.messages
    assert message.startswith(f"Failed to parse {quote_source(lock_path)}: ")


@_LOADERS
def test_memory_error_is_a_bad_file(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    loader: Callable[[Path], object],
) -> None:
    def _no_memory(_raw: bytes) -> object:
        raise MemoryError

    monkeypatch.setattr(lock_common, "load_toml_bytes", _no_memory)
    monkeypatch.setattr(lock_common, "json", SimpleNamespace(loads=_no_memory))
    lock_path = tmp_path / "some.lock"
    lock_path.write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert loader(lock_path) is None
    assert caplog.messages == [
        f"Failed to parse {quote_source(lock_path)}: MemoryError"
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
        f"Failed to parse {quote_source(lock_path)}: over {FETCH_MAX_BYTES} bytes"
    ]


@_LOADERS
def test_directory_is_not_a_lock_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, loader: Callable[[Path], object]
) -> None:
    with caplog.at_level(logging.WARNING):
        assert loader(tmp_path) is None
    assert caplog.messages == [
        f"Failed to parse {quote_source(tmp_path)}: not a regular file"
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
    lock_common._LOCK_FILE_CACHE.clear()
    paths = [tmp_path / f"{i}.toml" for i in range(3)]
    for path in paths:
        path.write_text("a = 1\n", encoding="utf-8")
    first, second, third = paths
    load_lock_toml(first)
    load_lock_toml(second)
    load_lock_toml(first)  # first is now the most recent
    load_lock_toml(third)
    assert [key[0] for key in lock_common._LOCK_FILE_CACHE] == [first, third]
    lock_common._LOCK_FILE_CACHE.clear()
