# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract._extract_utils`."""

from __future__ import annotations

import io
import os
import threading
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from pitloom.extract._extract_utils import (
    close_http_error,
    fetch_json,
    filename_from_url,
    json_nests_over,
    sanitize_provenance_text,
    sanitize_url_credentials,
)
from pitloom.logging_config import Cap

#: ``os.mkfifo`` exists on POSIX only.
_HAS_MKFIFO = hasattr(os, "mkfifo")


def test_sanitize_url_credentials_redacts_user_and_password() -> None:
    assert (
        sanitize_url_credentials("https://user:password123@example.com/repo.git")
        == "https://***:***@example.com/repo.git"
    )
    assert (
        sanitize_url_credentials("git+ssh://token@gitlab.com/repo.git")
        == "git+ssh://***:***@gitlab.com/repo.git"
    )
    assert (
        sanitize_url_credentials("Error fetching https://token:secret@pypi.org/simple")
        == "Error fetching https://***:***@pypi.org/simple"
    )
    assert (
        sanitize_url_credentials("https://example.com/plain/url")
        == "https://example.com/plain/url"
    )


def test_filename_from_url_extracts_basename() -> None:
    assert (
        filename_from_url("https://example.com/packages/foo-1.0-py3-none-any.whl")
        == "foo-1.0-py3-none-any.whl"
    )
    assert (
        filename_from_url(
            "https://example.com/pkg-1.0.whl?key=val&other=1#sha256=abcdef"
        )
        == "pkg-1.0.whl"
    )
    assert filename_from_url("https://example.com/") is None
    assert filename_from_url("https://example.com") is None


def test_filename_from_url_windows_path() -> None:
    assert (
        filename_from_url("file:///C:/Users/dist/pkg-1.0-py3-none-any.whl")
        == "pkg-1.0-py3-none-any.whl"
    )
    assert filename_from_url("https://example.com/a\\b\\pkg-1.0.whl") == "pkg-1.0.whl"
    assert filename_from_url("https://example.com/dir\\") is None


def test_sanitize_provenance_text() -> None:
    assert sanitize_provenance_text("foo|bar|baz") == "foo/bar/baz"
    assert sanitize_provenance_text("clean text") == "clean text"


def test_fetch_json_local_file(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text('{"project": "pitloom"}', encoding="utf-8")
    assert fetch_json(path) == {"project": "pitloom"}


def test_fetch_json_url_success() -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "ok"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch.object(urllib.request, "urlopen", return_value=mock_resp):
        res = fetch_json("https://example.com/api.json")
    assert res == {"status": "ok"}


def test_fetch_json_url_exceeds_max_bytes() -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"0123456789extra"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch.object(urllib.request, "urlopen", return_value=mock_resp):
        with pytest.raises(ValueError, match="exceeds maximum limit"):
            fetch_json("https://example.com/large.json", max_bytes=10)


@pytest.mark.parametrize(("size", "ok"), [(10, True), (11, False)], ids=["at", "over"])
def test_fetch_json_local_file_cap(tmp_path: Path, size: int, ok: bool) -> None:
    """A local file is read within *max_bytes* too: never more than one
    byte past it."""
    path = tmp_path / "data.json"
    path.write_bytes(b'{"a": "' + b"x" * (size - 9) + b'"}')
    assert path.stat().st_size == size
    if ok:
        assert fetch_json(path, max_bytes=10) == {"a": "x"}
    else:
        with pytest.raises(ValueError, match="exceeds maximum limit"):
            fetch_json(path, max_bytes=10)


def test_fetch_json_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        fetch_json(path)


def test_fetch_json_non_dict(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        fetch_json(path)


def test_fetch_json_read_error(tmp_path: Path) -> None:
    path = tmp_path / "nonexistent.json"
    with pytest.raises(ValueError, match="Cannot read source"):
        fetch_json(path)


def _local_source(tmp_path: Path, kind: str) -> Path:
    """A local source of *kind* that :func:`fetch_json` must refuse."""
    path = tmp_path / "source.json"
    if kind == "fifo":
        os.mkfifo(path)  # pylint: disable=no-member
    elif kind == "directory":
        path.mkdir()
    else:
        path.write_bytes(b'{"name": "\xff"}')
    return path


@pytest.mark.parametrize(
    ("kind", "match"),
    [
        pytest.param(
            "fifo",
            "is not a regular file",
            marks=pytest.mark.skipif(not _HAS_MKFIFO, reason="POSIX only"),
        ),
        ("directory", "is not a regular file"),
        ("not-utf8", "is not valid JSON"),
    ],
)
def test_fetch_json_refuses_a_local_source_naming_it(
    tmp_path: Path, kind: str, match: str
) -> None:
    """A FIFO or directory is refused before the blocking open; bytes that
    are not UTF-8 are invalid JSON. Each error names the source."""
    path = _local_source(tmp_path, kind)
    raised: list[BaseException] = []

    def fetch() -> None:
        try:
            fetch_json(path)
        except ValueError as exc:
            raised.append(exc)

    worker = threading.Thread(target=fetch, daemon=True)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive(), "fetch_json blocked"
    assert len(raised) == 1
    assert match in str(raised[0]) and repr(path) in str(raised[0])


def _http_error() -> HTTPError:
    """An ``HTTPError`` holding an open body, as ``urlopen()`` raises it."""
    return HTTPError("https://example.com/x", 404, "Not Found", Message(), io.BytesIO())


def test_close_http_error_closes_http_error() -> None:
    exc = _http_error()
    close_http_error(exc)
    assert exc.fp.closed


@pytest.mark.parametrize(
    "exc", [URLError("unreachable"), OSError("refused"), ValueError("bad")]
)
def test_close_http_error_ignores_other_exceptions(exc: Exception) -> None:
    close_http_error(exc)


def test_fetch_json_url_http_error_is_closed() -> None:
    """An unclosed ``HTTPError`` warns at garbage collection on 3.14."""
    exc = _http_error()
    assert not exc.fp.closed
    with patch.object(urllib.request, "urlopen", side_effect=exc):
        with pytest.raises(ValueError, match="Cannot read source"):
            fetch_json("https://example.com/missing.json")
    assert exc.fp.closed


@pytest.mark.parametrize(
    ("text", "limit", "over"),
    [
        ('{"a": [[1]]}', 3, False),
        ('{"a": [[1]]}', 2, True),
        ('{"a": "[[[[{{{{"}', 1, False),  # brackets in a string
        ('{"a": "\\"[[[[", "b": 1}', 1, False),  # an escaped quote
        ("[" * 5 + "]" * 5 + "[" * 5, 5, False),  # closed, then reopened
        ("[" * 6, 5, True),  # unbalanced
        ("]]]][[", 2, False),  # closers never go negative
        ('{"a": "\ud800"}[[[', 2, True),  # a lone surrogate is no stop
    ],
    ids=["at", "over", "in-string", "escaped", "reopened", "unbalanced",
         "closers", "surrogate"],
)  # fmt: skip
@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-32-be"])
def test_json_nests_over(text: str, limit: int, over: bool, encoding: str) -> None:
    """Counted on the decoded text, so every encoding the JSON parser
    accepts gives one answer."""
    assert json_nests_over(text.encode(encoding, "surrogatepass"), limit) is over


def test_json_nests_over_leaves_undecodable_bytes_to_the_parser() -> None:
    assert json_nests_over(b"[[[[\xff", 1) is False


def test_fetch_json_over_nesting_cap(tmp_path: Path) -> None:
    path = tmp_path / "deep.json"
    path.write_text('{"a": [[]]}', encoding="utf-8")
    cap = Cap(3, "level", "test-nesting")
    assert fetch_json(path, max_nesting=cap) == {"a": [[]]}
    with pytest.raises(ValueError, match="is larger than the 2-level test-nesting"):
        fetch_json(path, max_nesting=Cap(2, "level", "test-nesting"))
    assert fetch_json(path) == {"a": [[]]}  # no cap by default
