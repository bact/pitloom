# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A local Git server over smart HTTP, for tests that need the real protocol.

``git http-backend`` (shipped with ``git``) serves bare repositories under a
root; :func:`serve_git` puts it behind a loopback HTTP server. With
``gitlab_style`` the server answers ``<project>/info/refs`` with the redirect
to ``<project>.git/info/refs`` that GitLab sends, so the tests run the same
URL walk as against ``gitlab.com`` without the network.

The tests that use it opt out of the socket block (``network`` marker): the
server is on ``127.0.0.1``.
"""

from __future__ import annotations

import http.server
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

__all__ = ["backend_available", "git", "make_repo", "serve_git"]

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def backend_available() -> bool:
    """Whether ``git`` and its ``http-backend`` are installed."""
    if shutil.which("git") is None:
        return False
    return _backend() is not None


def _backend() -> str | None:
    done = subprocess.run(
        ["git", "--exec-path"], capture_output=True, text=True, check=False
    )
    path = Path(done.stdout.strip()) / "git-http-backend"
    return str(path) if path.is_file() else None


def git(cwd: Path, *args: str) -> str:
    """Run ``git`` in *cwd* with a fixed identity and no user config."""
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_ENV},
    )
    return done.stdout.strip()


def make_repo(
    root: Path, name: str, files: dict[str, dict[str, str]], default: str = "main"
) -> Path:
    """The bare repository ``<root>/<name>.git`` holding one commit per branch
    of *files* (branch -> path -> content), with *default* as its HEAD."""
    bare = root / f"{name}.git"
    bare.parent.mkdir(parents=True, exist_ok=True)
    work = root / f".work-{name.replace('/', '-')}"
    work.mkdir(parents=True)
    git(work, "init", "-q")
    for branch, tree in files.items():
        git(work, "checkout", "-q", "--orphan", branch)
        git(work, "rm", "-rfq", "--ignore-unmatch", ".")
        for rel, content in tree.items():
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", f"{branch}")
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(work), str(bare)],
        check=True,
        capture_output=True,
        env={**os.environ, **_ENV},
    )
    git(bare, "symbolic-ref", "HEAD", f"refs/heads/{default}")
    shutil.rmtree(work)
    return bare


@contextmanager
def serve_git(root: Path, *, gitlab_style: bool = False) -> Iterator[str]:
    """Serve the bare repositories under *root* at ``http://127.0.0.1:<port>``.

    With *gitlab_style*, ``/<path>/info/refs`` of a path not ending in
    ``.git`` is answered with a 301 to ``/<path>.git/info/refs``.
    """
    backend = _backend()
    if backend is None:  # pragma: no cover
        raise RuntimeError("git http-backend is not installed")

    class Handler(http.server.BaseHTTPRequestHandler):
        """Run ``git http-backend`` for each request."""

        protocol_version = "HTTP/1.0"

        def _serve(self) -> None:
            path, _, query = self.path.partition("?")
            if gitlab_style and path.endswith("/info/refs"):
                repo = path.removesuffix("/info/refs")
                if not repo.endswith(".git"):
                    self.send_response(301)
                    self.send_header(
                        "Location",
                        f"{repo}.git/info/refs" + (f"?{query}" if query else ""),
                    )
                    self.end_headers()
                    return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            env = {
                **os.environ,
                "GIT_HTTP_EXPORT_ALL": "1",
                "GIT_PROJECT_ROOT": str(root),
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": self.command,
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": str(len(body)),
                "REMOTE_ADDR": "127.0.0.1",
            }
            for key, value in self.headers.items():
                env["HTTP_" + key.upper().replace("-", "_")] = value
            done = subprocess.run(
                [backend], input=body, capture_output=True, env=env, check=False
            )
            head, _, payload = done.stdout.partition(b"\r\n\r\n")
            status = 200
            headers: list[tuple[str, str]] = []
            for line in head.decode("latin-1").split("\r\n"):
                name, _, value = line.partition(":")
                if name.lower() == "status":
                    status = int(value.split()[0])
                elif name:
                    headers.append((name, value.strip()))
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        do_GET = _serve  # noqa: N815
        do_POST = _serve  # noqa: N815

        def log_message(self, *_args: object) -> None:
            """Keep the test output quiet."""

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{cast(tuple[str, int], server.server_address)[1]}"
    finally:
        server.shutdown()
        server.server_close()
