# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""Real ``git`` against a loopback server that asks for Basic credentials:
a plain URL is fetched with the user's own credential helpers, as ``git
clone`` would; a URL with user information never asks or tells them.

See also: tests/extract/remote/test_git_credentials.py (a stand-in ``git``).
"""

from __future__ import annotations

import base64
import http.server
import stat
import subprocess
import sys
import threading
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest

from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote.errors import RemoteSourceError
from tests._git_http_server import (  # pylint: disable=protected-access
    _backend,
    _cgi_env,
    _cgi_response,
    backend_available,
    make_repo,
)
from tests._loopback_server import ThreadingLoopbackHTTPServer

pytestmark = [
    pytest.mark.platform,
    pytest.mark.loopback,
    pytest.mark.skipif(
        sys.platform == "win32" or not backend_available(),
        reason="needs git, its http-backend and a shell helper",
    ),
]

SECRET = "PLANTSECRET"


class _Gate(http.server.BaseHTTPRequestHandler):
    """Asks for Basic credentials, then serves the repositories under
    :attr:`root` (any credential is accepted) and records each one."""

    protocol_version = "HTTP/1.0"
    root: ClassVar[Path]
    seen: ClassVar[list[str]] = []

    def _serve(self) -> None:
        sent = self.headers.get("Authorization")
        if sent is None:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="x"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.seen.append(base64.b64decode(sent.split()[1]).decode())
        path, _, query = self.path.partition("?")
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        done = subprocess.run(
            [cast(str, _backend())],
            input=body,
            capture_output=True,
            env=_cgi_env(self, self.root, path, query, body),
            check=False,
        )
        status, headers, payload = _cgi_response(done.stdout)
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _serve  # noqa: N815
    do_POST = _serve  # noqa: N815

    # pylint: disable-next=redefined-builtin
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Keep the test output quiet."""


@contextmanager
def _serve(root: Path) -> Iterator[int]:
    """The port of a :class:`_Gate` serving *root*."""
    _Gate.root, _Gate.seen = root, []
    server = ThreadingLoopbackHTTPServer(("127.0.0.1", 0), _Gate)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield cast(tuple[str, int], server.server_address)[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def _users_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A user whose global configuration lists a helper that logs each call
    and answers ``mine:minepw``, then git's ``store`` helper; the log."""
    home = tmp_path / "home"
    home.mkdir()
    called = tmp_path / "called.log"
    helper = tmp_path / "helper.sh"
    helper.write_text(
        f'#!/bin/sh\ncat > /dev/null\necho "$1" >> "{called}"\n'
        'if [ "$1" = get ]; then echo username=mine; echo password=minepw; fi\n',
        encoding="utf-8",
    )
    helper.chmod(helper.stat().st_mode | stat.S_IEXEC)
    config = home / ".gitconfig"
    config.write_text(
        f"[credential]\n\thelper = {helper}\n\thelper = store\n", encoding="utf-8"
    )
    for name, value in (
        ("HOME", str(home)),
        ("XDG_CONFIG_HOME", str(home / ".config")),
        ("GIT_CONFIG_GLOBAL", str(config)),
        ("GIT_CONFIG_NOSYSTEM", "1"),
    ):
        monkeypatch.setenv(name, value)
    return called


@pytest.mark.parametrize("userinfo", [False, True], ids=["plain", "userinfo"])
def test_the_users_helpers_serve_a_plain_url_only(
    userinfo: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain URL asks the user's helper and stores what worked, as ``git
    clone`` does; a URL with user information sends its own credential, and
    no helper of the user's is asked or told (nothing stored)."""
    make_repo(tmp_path / "srv", "r", {"main": {"a.txt": "a\n"}})
    called = _users_helpers(tmp_path, monkeypatch)
    with _serve(tmp_path / "srv") as port:
        auth = f"u:{SECRET}@" if userinfo else ""
        url = f"http://{auth}127.0.0.1:{port}/r.git"
        out = GitRunner().run(["ls-remote", "--", url], "ls-remote", echo=False)
        seen = list(_Gate.seen)
    assert "refs/heads/main" in out
    stored = tmp_path / "home" / ".git-credentials"
    if userinfo:
        assert seen and set(seen) == {f"u:{SECRET}"}
        assert not called.exists() and not stored.exists()
    else:
        assert set(seen) == {"mine:minepw"}
        assert called.read_text(encoding="utf-8").split() == ["get", "store"]
        assert "minepw" in stored.read_text(encoding="utf-8")


class _Recorder(http.server.BaseHTTPRequestHandler):
    """A server that asks for Basic credentials and records what it gets."""

    seen: ClassVar[list[str | None]] = []

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        self.seen.append(self.headers.get("Authorization"))
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="x"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    # pylint: disable-next=redefined-builtin,unused-argument
    def log_message(self, format: str, *args: Any) -> None:
        """Keep the test output quiet."""


def test_real_git_receives_the_credential_through_the_helper_unmangled() -> None:
    """Real ``git`` runs the helper: a password with ``\\``, ``$`` and a
    quote reaches the server as typed, and a stored helper is not asked."""
    _Recorder.seen.clear()
    server = http.server.HTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    password = 'p\\a$b"c'
    try:
        url = f"http://us%40er:{urllib.parse.quote(password, safe='')}@127.0.0.1:"
        url += f"{server.server_port}/r.git"
        with pytest.raises(RemoteSourceError):
            GitRunner().run(["ls-remote", "--", url], "ls-remote")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    wanted = "Basic " + base64.b64encode(f"us@er:{password}".encode()).decode()
    assert wanted in _Recorder.seen and _Recorder.seen[0] is None
