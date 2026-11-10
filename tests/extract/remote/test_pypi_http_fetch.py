# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The hardened HTTP client of the PyPI route
(:mod:`pitloom.extract.remote._http_fetch`): each URL checked before it is
requested, redirects bounded, the size and time caps holding whatever the
server declares or how slowly it sends.

The server is a local one (``loopback``); plain http is allowed by patching
the scheme set, as only a test does.

See also: tests/_fake_pypi_server.py, tests/extract/remote/test_pypi_fetch.py.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import socket
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.extract.remote import _http_fetch, _http_watch
from pitloom.extract.remote._http_fetch import (
    MAX_REDIRECTS,
    NotFoundError,
    Policy,
    fetch_json,
    fetch_to_file,
    url_refusal,
)
from pitloom.extract.remote._http_watch import Watch
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.messages import (
    DOWNLOAD_FAILED,
    DOWNLOAD_TIMEOUT,
    JSON_MALFORMED,
    OVER_CAP,
    TEMP_DIR_UNUSABLE,
    URL_REFUSED,
)
from tests._fake_pypi_server import FakePypi, Route, redirect, serving, sha256_of

#: Windows ends no ``recv`` on a socket shut for reading.
_WINDOWS = sys.platform == "win32"

pytestmark = pytest.mark.loopback

_HOSTS = frozenset({"files.pythonhosted.org", "127.0.0.1:8080"})


@pytest.mark.parametrize(
    ("url", "refused"),
    [
        ("https://files.pythonhosted.org/p/x.whl", False),
        ("https://FILES.pythonhosted.org:443/p/x.whl", False),
        ("https://127.0.0.1:8080/x", False),
        ("http://files.pythonhosted.org/p/x.whl", True),
        ("file:///etc/passwd", True),
        ("ftp://files.pythonhosted.org/x", True),
        ("https://u:p@files.pythonhosted.org/x", True),
        ("https://@files.pythonhosted.org/x", True),
        ("https://files.pythonhosted.org.evil.example/x", True),
        ("https://files.pythonhosted.org./x", True),
        ("https://files.pythonhosted.org:8443/x", True),
        ("https://files.pythonhosted.org:x/x", True),
        ("https://127.0.0.1/x", True),
        ("https:///x", True),
        ("https:\\\\files.pythonhosted.org\\x", True),
    ],
    ids=[
        "allowed",
        "case-and-port",
        "host-port",
        "http",
        "file",
        "ftp",
        "userinfo",
        "empty-userinfo",
        "suffix",
        "trailing-dot",
        "other-port",
        "bad-port",
        "port-missing",
        "no-host",
        "backslashes",
    ],
)
def test_url_refusal(url: str, refused: bool) -> None:
    assert (url_refusal(url, _HOSTS) is not None) is refused


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePypi]:
    """A fake server, http allowed, small caps and deadlines."""
    monkeypatch.setattr(_http_fetch, "ALLOWED_SCHEMES", frozenset({"http", "https"}))
    monkeypatch.setattr(_http_fetch, "SOCKET_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(_http_fetch, "JSON_MAX_BYTES", 1000)
    with serving() as fake:
        yield fake


def _policy(fake: FakePypi, checked: list[str] | None = None) -> Policy:
    return Policy(frozenset({fake.host}), None if checked is None else checked.append)


def _code(info: pytest.ExceptionInfo[RemoteSourceError]) -> str | None:
    return info.value.pitloom_code


def test_a_redirect_on_the_host_is_followed_and_said(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    """Each URL, the first included, goes to the caller's check before it is
    requested; the request carries no credential or cookie."""
    fake.routes["/a"] = redirect("/b")
    fake.routes["/b"] = Route(body=b'{"ok": true}')
    checked: list[str] = []
    with caplog.at_level(logging.INFO):
        assert fetch_json(fake.url("/a"), _policy(fake, checked)) == {"ok": True}
    assert checked == [fake.url("/a"), fake.url("/b")]
    moved = f"URL={fake.url('/a')}: redirects to {fake.url('/b')}; followed"
    assert moved in caplog.messages
    assert fake.seen == ["/a", "/b"]
    for headers in fake.headers:
        assert headers["user-agent"] == "pitloom-pypi"
        assert "authorization" not in headers and "cookie" not in headers


@pytest.mark.parametrize(
    "location",
    [
        "http://localhost:{port}/other",
        "file:///etc/passwd",
        "http://u:secret@127.0.0.1:{port}/other",
        "//localhost:{port}/other",
    ],
    ids=["other-host", "file", "userinfo", "scheme-relative"],
)
def test_a_redirect_off_the_policy_is_refused_unrequested(
    fake: FakePypi, location: str
) -> None:
    port = fake.host.rpartition(":")[2]
    fake.routes["/a"] = redirect(location.format(port=port))
    fake.routes["/other"] = Route(body=b"{}")
    checked: list[str] = []
    with pytest.raises(RemoteSourceError) as info:
        fetch_json(fake.url("/a"), _policy(fake, checked))
    assert _code(info) == URL_REFUSED.code and info.value.code == "pypi.url-refused"
    assert "not followed" in str(info.value) and "secret" not in str(info.value)
    assert fake.seen == ["/a"] and checked == [fake.url("/a")]


@pytest.mark.parametrize(
    "hops", [MAX_REDIRECTS, MAX_REDIRECTS + 1], ids=["max", "over"]
)
def test_redirects_are_bounded(fake: FakePypi, hops: int) -> None:
    for hop in range(hops):
        fake.routes[f"/r{hop}"] = redirect(f"/r{hop + 1}")
    fake.routes[f"/r{hops}"] = Route(body=b"{}")
    if hops == MAX_REDIRECTS:
        assert fetch_json(fake.url("/r0"), _policy(fake)) == {}
        return
    with pytest.raises(RemoteSourceError) as info:
        fetch_json(fake.url("/r0"), _policy(fake))
    assert info.value.code == "pypi.too-many-redirects"
    assert _code(info) == URL_REFUSED.code
    assert f"more than {MAX_REDIRECTS} redirects" in str(info.value)
    assert f"/r{hops}" not in fake.seen


def test_check_url_runs_before_each_hop_is_requested(fake: FakePypi) -> None:
    """A hop the caller's check refuses is never requested; its error comes
    through unchanged."""
    fake.routes["/a"] = redirect("/b")
    fake.routes["/b"] = redirect("/c")

    def check(url: str) -> None:
        if url.endswith("/c"):
            raise PermissionError("internal address")

    with pytest.raises(PermissionError, match="internal address"):
        fetch_json(fake.url("/a"), Policy(frozenset({fake.host}), check))
    assert fake.seen == ["/a", "/b"]


def test_the_first_url_must_be_on_the_policy(fake: FakePypi) -> None:
    with pytest.raises(InternalError):
        fetch_json(fake.url("/a"), Policy(frozenset({"pypi.org"})))
    assert not fake.seen


@pytest.mark.parametrize(
    ("route", "code"),
    [
        (Route(body=b"x" * 1001, length=-1), OVER_CAP.code),
        (Route(body=b"x" * 1001), OVER_CAP.code),
        (Route(body=b'{"a": 1}', length=1_000_000), DOWNLOAD_FAILED.code),
        (Route(body=b"[" * 70 + b"]" * 70), OVER_CAP.code),
        (Route(body=b"{nope"), JSON_MALFORMED.code),
        (Route(body=b"[1]"), JSON_MALFORMED.code),
        (Route(status=500), DOWNLOAD_FAILED.code),
        (Route(status=301), DOWNLOAD_FAILED.code),
    ],
    ids=[
        "over-no-length",
        "over-with-length",
        "length-lies-high",
        "nesting",
        "not-json",
        "not-object",
        "status-500",
        "redirect-no-location",
    ],
)
def test_a_json_answer_that_cannot_be_read(
    fake: FakePypi, route: Route, code: str
) -> None:
    fake.routes["/a"] = route
    with pytest.raises(RemoteSourceError) as info:
        fetch_json(fake.url("/a"), _policy(fake))
    assert _code(info) == code
    assert "\n" not in str(info.value)


def test_a_declared_length_under_the_body_is_all_that_is_read(fake: FakePypi) -> None:
    """A ``Content-Length`` of 2 for a body over the cap: two bytes read,
    no cap reached (the declared value neither gates nor extends a read)."""
    fake.routes["/a"] = Route(body=b"{}" + b" " * 5000, length=2)
    assert fetch_json(fake.url("/a"), _policy(fake)) == {}


def test_a_json_answer_may_start_with_a_bom(fake: FakePypi) -> None:
    fake.routes["/a"] = Route(body=b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode())
    assert fetch_json(fake.url("/a"), _policy(fake)) == {"a": 1}


@pytest.mark.parametrize("status", [404, 410])
def test_not_found_is_for_the_caller_to_name(fake: FakePypi, status: int) -> None:
    fake.routes["/a"] = Route(status=status)
    with pytest.raises(NotFoundError) as info:
        fetch_json(fake.url("/a"), _policy(fake))
    assert info.value.url == fake.url("/a")
    assert (info.value.code, _code(info)) == (
        "pypi.download-failed",
        DOWNLOAD_FAILED.code,
    )
    assert str(info.value).startswith(f"URL={fake.url('/a')}: HTTP Error {status}")


def test_server_text_is_one_escaped_line(fake: FakePypi) -> None:
    """The reason phrase is the server's: escaped, never a raw control."""
    fake.routes["/a"] = Route(status=503, reason="Busy\x1b[31m ::error::x")
    with pytest.raises(RemoteSourceError) as info:
        fetch_json(fake.url("/a"), _policy(fake))
    assert "Busy" in str(info.value) and "\x1b" not in str(info.value)


@pytest.mark.parametrize("head", [False, True], ids=["body", "head"])
def test_a_slow_drip_stops_at_the_deadline(
    fake: FakePypi, monkeypatch: pytest.MonkeyPatch, head: bool
) -> None:
    """A server sending a byte every 20 ms, each well inside the socket
    timeout, is cut at the overall deadline, not after the whole body."""
    monkeypatch.setattr(_http_fetch, "JSON_DEADLINE_SECONDS", 0.5)
    # The head case is a status line that never ends: the read raises once
    # the socket is shut, which must still read as the deadline.
    body = b"H" * 1000 if head else b" " * 900 + b"{}"
    fake.routes["/a"] = Route(body=body, drip=0.02, drip_head=head)
    started = time.monotonic()
    with pytest.raises(RemoteSourceError) as info:
        fetch_json(fake.url("/a"), _policy(fake))
    assert time.monotonic() - started < 8
    assert _code(info) == DOWNLOAD_TIMEOUT.code
    assert "within 1 seconds" in str(info.value)


def test_a_stalled_socket_times_out(
    fake: FakePypi, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_http_fetch, "SOCKET_TIMEOUT_SECONDS", 0.2)
    fake.routes["/a"] = Route(body=b"{}", drip=5.0)
    with pytest.raises(RemoteSourceError) as info:
        fetch_json(fake.url("/a"), _policy(fake))
    assert _code(info) == DOWNLOAD_TIMEOUT.code


def test_a_refused_connection_fails(fake: FakePypi) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}/a"
    with pytest.raises(RemoteSourceError) as info:
        fetch_json(url, Policy(frozenset({f"127.0.0.1:{port}"})))
    assert (
        _code(info) == DOWNLOAD_FAILED.code
        and info.value.code == "pypi.download-failed"
    )
    assert not fake.seen


@pytest.mark.parametrize("length", [None, -1], ids=["with-length", "no-length"])
def test_a_file_is_streamed_and_hashed(
    fake: FakePypi, tmp_path: Path, length: int | None
) -> None:
    data = bytes(range(256)) * 100
    fake.routes["/f"] = Route(body=data, length=length)
    dest = tmp_path / "x.whl"
    got = fetch_to_file(
        fake.url("/f"),
        _policy(fake),
        dest,
        max_bytes=len(data),
        file="x.whl",
    )
    assert got == (sha256_of(data), len(data))
    assert dest.read_bytes() == data


@pytest.mark.parametrize(
    "length", [None, -1, 10], ids=["with-length", "no-length", "lying"]
)
def test_a_file_over_the_cap_is_stopped(
    fake: FakePypi, tmp_path: Path, length: int | None
) -> None:
    """Over the cap by one byte: ``over-cap``, with or without a declared
    length; a declared length under the cap does not let more in."""
    fake.routes["/f"] = Route(body=b"x" * 20_001, length=length)
    if length == 10:
        got = fetch_to_file(
            fake.url("/f"),
            _policy(fake),
            tmp_path / "x",
            max_bytes=20_000,
            file="x.whl",
        )
        assert got[1] == 10
        return
    with pytest.raises(RemoteSourceError) as info:
        fetch_to_file(
            fake.url("/f"),
            _policy(fake),
            tmp_path / "x",
            max_bytes=20_000,
            file="x.whl",
        )
    assert (info.value.code, _code(info)) == ("pypi.too-large", OVER_CAP.code)
    assert str(info.value) == (
        "FILE=x.whl: larger than the 20000-byte max-download-bytes cap; not downloaded"
    )


def test_a_file_is_never_written_over(fake: FakePypi, tmp_path: Path) -> None:
    """A local failure to save is ``temp-dir-unusable``, never a network
    failure."""
    fake.routes["/f"] = Route(body=b"new")
    dest = tmp_path / "x.whl"
    dest.write_bytes(b"old")
    with pytest.raises(RemoteSourceError) as info:
        fetch_to_file(
            fake.url("/f"),
            _policy(fake),
            dest,
            max_bytes=10,
            file="x.whl",
        )
    assert (info.value.code, _code(info)) == (
        "pypi.save-failed",
        TEMP_DIR_UNUSABLE.code,
    )
    assert str(tmp_path) not in str(info.value)
    assert dest.read_bytes() == b"old"


class _NoSpaceWriter:
    """A file whose writes fail as on a full disk."""

    def __enter__(self) -> _NoSpaceWriter:
        return self

    def __exit__(self, *_exc: object) -> None:
        """Nothing to close."""

    def write(self, _data: bytes) -> int:
        """Refuse, as a full disk does."""
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))


class _FullDisk:  # pylint: disable=too-few-public-methods
    """A destination whose writes fail as on a full disk."""

    def open(self, mode: str) -> _NoSpaceWriter:
        """A writer that fails on its first write."""
        assert mode == "xb"
        return _NoSpaceWriter()


def test_a_full_disk_is_not_a_network_failure(fake: FakePypi) -> None:
    fake.routes["/f"] = Route(body=b"data")
    with pytest.raises(RemoteSourceError) as info:
        fetch_to_file(
            fake.url("/f"),
            _policy(fake),
            cast(Path, _FullDisk()),
            max_bytes=10,
            file="x.whl",
        )
    assert str(info.value) == (
        "FILE=x.whl: could not be saved in the temporary directory "
        f"({os.strerror(errno.ENOSPC)}); not downloaded"
    )


def test_a_file_slow_drip_stops_at_the_deadline(
    fake: FakePypi, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(_http_fetch, "FILE_DEADLINE_SECONDS", 0.5)
    fake.routes["/f"] = Route(body=b"x" * 1000, drip=0.02, length=-1)
    started = time.monotonic()
    with pytest.raises(RemoteSourceError) as info:
        fetch_to_file(
            fake.url("/f"),
            _policy(fake),
            tmp_path / "x",
            max_bytes=10**6,
            file="x.whl",
        )
    assert time.monotonic() - started < 8
    assert _code(info) == DOWNLOAD_TIMEOUT.code


def test_the_deadline_shuts_a_socket_watched_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A socket added after the deadline is shut at once; one never
    connected (``None``, or one the system will not shut) is no error.

    Shut is spied on every system; a read of the shut socket returning end of
    stream is POSIX behaviour only (Windows does not end a ``recv`` on a
    socket shut for reading, so it waits for the timeout).
    """
    shut: list[socket.socket] = []
    real_shut = _http_watch.shut_socket

    def spy(sock: socket.socket) -> None:
        shut.append(sock)
        real_shut(sock)

    monkeypatch.setattr(_http_watch, "shut_socket", spy)
    with Watch(0.0) as watch:
        assert watch.fired.wait(5)
        watch.add(None)
        left, right = socket.socketpair()
        left.settimeout(5)
        with left, right, socket.socket() as unconnected:
            watch.add(left)
            assert shut == [left]
            if not _WINDOWS:
                assert left.recv(1) == b""
            watch.add(unconnected)
            assert shut == [left, unconnected]
    assert watch.remaining() < 0


def test_a_spent_deadline_requests_nothing(
    fake: FakePypi, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_http_fetch, "JSON_DEADLINE_SECONDS", 0.0)
    fake.routes["/a"] = Route(body=b"{}")
    with pytest.raises(RemoteSourceError) as info:
        fetch_json(fake.url("/a"), _policy(fake))
    assert _code(info) == DOWNLOAD_TIMEOUT.code and not fake.seen


def test_a_socket_timeout_is_reported_as_it_was(
    fake: FakePypi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seconds named are the timeout the socket had: less than the
    per-operation timeout when the deadline was nearer."""
    monkeypatch.setattr(_http_fetch, "SOCKET_TIMEOUT_SECONDS", 0.3)
    fake.routes["/a"] = Route(body=b"{}", drip=5.0)
    with pytest.raises(RemoteSourceError, match="within 1 seconds"):
        fetch_json(fake.url("/a"), _policy(fake))
    watch = Watch(100.0)
    watch.socket_seconds = 2.2
    # pylint: disable-next=protected-access
    timeout = _http_fetch._timeout("http://h/x", watch)
    assert "within 3 seconds" in str(timeout)
