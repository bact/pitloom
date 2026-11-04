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

from pitloom.core.internal_error import InternalError
from pitloom.core.quote_source import quote_source
from pitloom.extract._extract_utils import (
    close_http_error,
    fetch_json,
    filename_from_url,
    json_nests_over,
)
from pitloom.messages import FILE_UNREADABLE, JSON_MALFORMED, OVER_CAP, Cap, code_of
from tests._bounded import run_bounded_in_child
from tests._message_drift import raised_as
from tests._unreadable import deny

#: ``os.mkfifo`` exists on POSIX only.
_HAS_MKFIFO = hasattr(os, "mkfifo")
#: What a local source is read for in these tests.
_USE = "for the Croissant document"


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


def test_fetch_json_local_file(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text('{"project": "pitloom"}', encoding="utf-8")
    assert fetch_json(path, use=_USE) == {"project": "pitloom"}


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
        with pytest.raises(ValueError) as raised:
            fetch_json("https://example.com/large.json", max_bytes=10)
    assert str(raised.value) == (
        "'https://example.com/large.json': larger than the 10-byte JSON-document "
        "cap; not read"
    )
    assert raised_as(raised.value, OVER_CAP)


@pytest.mark.parametrize(("size", "ok"), [(10, True), (11, False)], ids=["at", "over"])
def test_fetch_json_local_file_cap(tmp_path: Path, size: int, ok: bool) -> None:
    """A local file is read within *max_bytes* too: never more than one
    byte past it."""
    path = tmp_path / "data.json"
    path.write_bytes(b'{"a": "' + b"x" * (size - 9) + b'"}')
    assert path.stat().st_size == size
    if ok:
        assert fetch_json(path, max_bytes=10, use=_USE) == {"a": "x"}
    else:
        with pytest.raises(ValueError) as raised:
            fetch_json(path, max_bytes=10, use=_USE)
        reason = "larger than the 10-byte JSON-document cap; not read"
        assert str(raised.value) == f"{quote_source(path)}: {reason}"
        assert raised_as(raised.value, OVER_CAP)


def test_fetch_json_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError) as raised:
        fetch_json(path, use=_USE)
    assert str(raised.value).startswith(f"{quote_source(path)}: not valid JSON; ")
    assert raised_as(raised.value, JSON_MALFORMED)


def test_fetch_json_non_dict(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError) as raised:
        fetch_json(path, use=_USE)
    assert str(raised.value) == f"{quote_source(path)}: not a JSON object"
    assert raised_as(raised.value, JSON_MALFORMED)


def test_fetch_json_read_error(tmp_path: Path) -> None:
    """An absent file is not unreadable: no code yet, its own subject."""
    path = tmp_path / "nonexistent.json"
    with pytest.raises(ValueError, match="Cannot read source") as raised:
        fetch_json(path, use=_USE)
    assert code_of(raised.value) is None
    with pytest.raises(ValueError, match="^Cannot read Croissant source '"):
        fetch_json(path, use=_USE, subject="Croissant source")


def test_fetch_json_names_what_stopped_a_read_never_the_path_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file the system refuses: ``file-unreadable``, what the system
    reported, not the exception's text (which quotes the path again)."""
    path = tmp_path / "denied.json"
    path.write_text("{}", encoding="utf-8")
    with deny(path, "open", monkeypatch), pytest.raises(ValueError) as raised:
        fetch_json(path, use=_USE)
    assert str(raised.value) == (
        f"FILE={path}: could not read for the Croissant document; Permission denied"
    )
    assert raised_as(raised.value, FILE_UNREADABLE)


def test_fetch_json_refuses_a_local_source_without_its_use(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(InternalError, match="needs its use"):
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
            ": could not read for the Croissant document; not a regular file",
            marks=pytest.mark.skipif(not _HAS_MKFIFO, reason="POSIX only"),
        ),
        (
            "directory",
            ": could not read for the Croissant document; not a regular file",
        ),
        ("not-utf8", ": not valid JSON; "),
    ],
    ids=["fifo", "directory", "not-utf8"],
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
            fetch_json(path, use=_USE)
        except ValueError as exc:
            raised.append(exc)

    worker = threading.Thread(target=fetch, daemon=True)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive(), "fetch_json blocked"
    assert len(raised) == 1
    named = f"'{path}'" if kind == "not-utf8" else f"FILE={path}"
    assert str(raised[0]).startswith(named + match)
    entry = JSON_MALFORMED if kind == "not-utf8" else FILE_UNREADABLE
    assert raised_as(raised[0], entry)


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
        ('"[[[[', 1, False),  # a string never closed runs to the end
    ],
    ids=["at", "over", "in-string", "escaped", "reopened", "unbalanced",
         "closers", "surrogate", "unterminated"],
)  # fmt: skip
@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-32-be"])
def test_json_nests_over(text: str, limit: int, over: bool, encoding: str) -> None:
    """Counted on the decoded text, so every encoding the JSON parser
    accepts gives one answer."""
    assert json_nests_over(text.encode(encoding, "surrogatepass"), limit) is over


def test_json_nests_over_an_unterminated_string_takes_linear_time() -> None:
    """One quote then many escaped ones: a scan restarting at each later
    quote is quadratic (80 KB took 33 s)."""
    raw = b'"' + b'\\"' * 40_000 + b"[" * 65
    assert (
        run_bounded_in_child("pitloom.extract._extract_utils:json_nests_over", raw, 64)
        is False
    )


def test_json_nests_over_leaves_undecodable_bytes_to_the_parser() -> None:
    assert json_nests_over(b"[[[[\xff", 1) is False


def test_fetch_json_over_nesting_cap(tmp_path: Path) -> None:
    path = tmp_path / "deep.json"
    path.write_text('{"a": [[]]}', encoding="utf-8")
    cap = Cap(3, "level", "test-nesting")
    assert fetch_json(path, max_nesting=cap, use=_USE) == {"a": [[]]}
    match = "larger than the 2-level test-nesting cap; not read"
    with pytest.raises(ValueError, match=match) as raised:
        fetch_json(path, max_nesting=Cap(2, "level", "test-nesting"), use=_USE)
    assert raised_as(raised.value, OVER_CAP)
    assert fetch_json(path, use=_USE) == {"a": [[]]}  # no cap by default


@pytest.mark.parametrize("name", ["plain.json", "back\\slash.json"])
def test_fetch_json_error_names_the_source_as_the_os_writes_it(
    tmp_path: Path, name: str
) -> None:
    """The message holds ``str(source)`` once, quoted: ``repr`` would double a
    backslash (a ``str``) or turn it into ``/`` (a Windows ``Path``)."""
    source = str(tmp_path / name)
    with pytest.raises(ValueError, match="Cannot read source") as excinfo:
        fetch_json(source, use=_USE)
    assert f"'{source}'" in str(excinfo.value)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a\nb.json", r"'a\nb.json'"),
        ("a\x1b[31m.json", r"'a\x1b[31m.json'"),
        ("a\udc80.json", r"'a\udc80.json'"),
        ("é.json", "'é.json'"),
    ],
)
def test_quote_source_escapes_only_what_would_break_a_line(
    source: str, expected: str
) -> None:
    """Control characters and lone surrogates are escaped; text is not."""
    assert quote_source(source) == expected
