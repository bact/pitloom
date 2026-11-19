# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What stops a Git URL fetch, each as an error of the same class and
``.code`` as before with the catalogue's ``pitloom_code`` and line: no git,
an empty repository, a ref the repository lacks, a deadline, git's own
failure (the network, or any other cause; a server's text on one line), the
monorepo hint after ``project-not-found`` and ``project-or-model-not-found``,
and the git command echo.

The server is a local smart-HTTP one (`loopback`).

See also: tests/extract/remote/test_git_say.py (what a fetch decides),
tests/messages/test_git_surfaces.py (the command line and the library) and
tests/messages/test_git.py (the lines themselves).
"""

from __future__ import annotations

import http.server
import logging
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.extract import model_target
from pitloom.extract.remote import _git_run, git_target
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote._git_say import project_hint_error
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout, fetch_git_project
from pitloom.extract.remote.git_target import resolve_git_target
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    GIT_PREFIX,
    CodedFileNotFoundError,
    CodedValueError,
    code_of,
    trusted_message,
)
from pitloom.messages.git import (
    GIT_EMPTY_LINE,
    GIT_MISSING_LINE,
    GIT_REF_NOT_FOUND,
    GIT_REF_NOT_FOUND_LINE,
)
from pitloom.messages.network import GIT_TIMEOUT_LINE
from pitloom.messages.targets import (
    NO_SBOM_TARGET,
    NO_TARGET_FOLDER_HINT_LINE,
    NO_TARGET_HINT_LINE,
    PROJECT_FOLDER_HINT_LINE,
    PROJECT_HINT_LINE,
    PROJECT_NOT_FOUND,
    input_not_found,
)
from tests._git_http_server import serve_git
from tests._git_say_repos import SERVER_MARKS, build_repos
from tests._loopback_server import ThreadingLoopbackHTTPServer

pytestmark = [*SERVER_MARKS, pytest.mark.platform]


@pytest.fixture(name="served", scope="module")
def _served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("srv")
    build_repos(root)
    with serve_git(root, gitlab_style=True) as base:
        yield base


def _closed_port() -> int:
    """A port on 127.0.0.1 nothing listens on."""
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        return int(closed.getsockname()[1])


def _error_line(exc: RemoteSourceError, frame: str = "") -> str:
    """The ``ERROR:`` line the command line prints for *exc*."""
    return f"ERROR: {frame}{exc} [{code_of(exc)}]"


def _trusted(exc: RemoteSourceError) -> None:
    """*exc*'s printed line is trusted, framed by a command or not."""
    expected = code_of(exc)
    assert expected is not None
    for frame in ("", "loom project: "):
        found = trusted_message(_error_line(exc, frame))
        assert found is not None and found.code == expected, _error_line(exc, frame)


# -- an empty repository (row 16) and a ref the repository lacks (rows 21, 22) --


def test_an_empty_repository_is_unusable_not_a_failed_clone(served: str) -> None:
    url = served + "/g/empty.git"
    with pytest.raises(RemoteSourceError) as raised:
        with fetch_git_project(url):
            pass
    assert raised.value.code == "git.clone-failed"
    assert code_of(raised.value) == "git-repository-unusable/empty"
    assert str(raised.value) == GIT_EMPTY_LINE.render({"url": url})
    _trusted(raised.value)


@pytest.mark.parametrize(
    ("page", "repo", "ref"),
    [
        ("/g/p.git/-/tree/nope/x", "/g/p.git", "nope"),
        ("/g/_git/p?path=/x&version=GBnope", "/g/_git/p", "nope"),
        ("/g/p.git/-/tree/a%0Ab%1B/x", "/g/p.git", "a\nb\x1b"),
    ],
    ids=["path-style", "query-style", "hostile-ref"],
)
def test_a_ref_the_repository_lacks_is_one_line_in_either_page_style(
    served: str, page: str, repo: str, ref: str
) -> None:
    """The two sites say one line; a ref with a line break and an escape,
    decoded from the URL, is escaped."""
    with pytest.raises(RemoteSourceError) as raised:
        with fetch_git_project(served + page):
            pass
    assert raised.value.code == "git.ref-not-found"
    assert code_of(raised.value) == GIT_REF_NOT_FOUND.code
    text = str(raised.value)
    assert text == GIT_REF_NOT_FOUND_LINE.render({"url": served + repo, "ref": ref})
    assert text.count("\n") == 0 and "\x1b" not in text
    assert "not found" not in text  # a retry reads that word in git's text
    _trusted(raised.value)


# -- git is missing (row 6) ------------------------------------------------------


def test_a_missing_git_is_git_missing_whichever_way_it_is_reached(
    served: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The imported name is patched, never ``shutil.which``."""
    monkeypatch.setattr(_git_run, "_which", lambda name: None)
    with pytest.raises(RemoteSourceError) as direct:
        GitRunner().run(["--version"], "version")
    with pytest.raises(RemoteSourceError) as fetched:
        with fetch_git_project(served + "/g/p.git"):
            pass
    for raised in (direct, fetched):
        assert raised.value.code == "git.not-found"
        assert code_of(raised.value) == "git-missing"
        assert str(raised.value) == GIT_MISSING_LINE.template
        _trusted(raised.value)


# -- a deadline (rows 8, 9) -------------------------------------------------------


def test_a_deadline_gone_before_the_call_is_a_timeout() -> None:
    with pytest.raises(RemoteSourceError) as raised:
        GitRunner(seconds=0).run(["--version"], "version")
    assert raised.value.code == "git.timeout"
    assert code_of(raised.value) == "download-timeout"
    values = {"command": "version", "seconds": 1}
    assert str(raised.value) == GIT_TIMEOUT_LINE.render(values)
    _trusted(raised.value)


def test_a_deadline_that_passes_during_the_call_is_the_same_timeout() -> None:
    """A server that takes the connection and never answers."""
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen(1)
        url = f"http://127.0.0.1:{silent.getsockname()[1]}/x.git"
        with pytest.raises(RemoteSourceError) as raised:
            GitRunner(seconds=0.5).run(["ls-remote", "--", url], "ls-remote")
    assert raised.value.code == "git.timeout"
    assert code_of(raised.value) == "download-timeout"
    values = {"command": "ls-remote", "seconds": 1}
    assert str(raised.value) == GIT_TIMEOUT_LINE.render(values)
    _trusted(raised.value)


# -- git's own failure (`_failed`) --------------------------------------------------


def test_a_network_failure_is_download_network_failed() -> None:
    url = f"http://127.0.0.1:{_closed_port()}/x.git"
    with pytest.raises(RemoteSourceError) as raised:
        GitRunner().run(["ls-remote", "--", url], "ls-remote")
    assert raised.value.code == "git.clone-failed"
    assert code_of(raised.value) == "download-network-failed"
    assert str(raised.value).startswith("git ls-remote failed: ")
    _trusted(raised.value)


def test_any_other_failure_is_git_repository_unusable(served: str) -> None:
    with pytest.raises(RemoteSourceError) as raised:
        GitRunner().run(["ls-remote", "--", served + "/g/missing.git"], "ls-remote")
    assert raised.value.code == "git.clone-failed"
    assert code_of(raised.value) == "git-repository-unusable"
    text = str(raised.value)
    assert text.startswith("git ls-remote: fatal: ") and "failed:" not in text
    assert text.endswith("; nothing fetched")
    _trusted(raised.value)


def _pkt(payload: bytes) -> bytes:
    """A git pkt-line holding *payload*."""
    return b"%04x" % (len(payload) + 4) + payload


@pytest.fixture(name="hostile")
def _hostile() -> Iterator[str]:
    """A server whose answer to the ref advertisement is an ``ERR`` packet
    holding a carriage return, a line break, an escape, a fake code and a
    URL with a credential: git prints it as its own ``fatal:`` line."""
    text = "see https://u:tok@h/r\r\nremote: \x1b[2Jgone [over-cap]\nerror: x"
    body = (
        _pkt(b"# service=git-upload-pack\n") + b"0000" + _pkt(b"ERR " + text.encode())
    )

    class Handler(http.server.BaseHTTPRequestHandler):
        """Answer every request with the ``ERR`` packet."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            """Send the packet."""
            self.send_response(200)
            kind = "application/x-git-upload-pack-advertisement"
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # pylint: disable-next=redefined-builtin
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Keep the test output quiet."""

    server = ThreadingLoopbackHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/x.git"
    finally:
        server.shutdown()
        server.server_close()


def test_a_servers_text_is_one_masked_line_with_the_code(hostile: str) -> None:
    with pytest.raises(RemoteSourceError) as raised:
        GitRunner().run(["ls-remote", "--", hostile], "ls-remote")
    text = str(raised.value)
    assert code_of(raised.value) == "git-repository-unusable"
    assert "tok@" not in text and "\x1b" not in text and "\n" not in text
    assert "\r" not in text and "https://***:***@h/r" in text
    assert text.count("nothing fetched") == 1 and text.endswith("; nothing fetched")
    _trusted(raised.value)


# -- the monorepo hint (row 10, git_target.py:188) -----------------------------------


def _checkout(folder: Path, *, whole: bool) -> GitCheckout:
    return GitCheckout(
        folder=str(folder),
        repo_url="https://h.example/r.git",
        ref=None,
        commit="0" * 40,
        subdir="" if whole else "apps",
        whole_repository=whole,
    )


def _monorepo(root: Path, count: int = 2) -> Path:
    for name in "abcdefg"[:count]:
        (root / name).mkdir()
        (root / name / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return root


@pytest.mark.parametrize(
    ("whole", "line", "count", "folders"),
    [
        (True, PROJECT_HINT_LINE, 2, "a, b"),
        (False, PROJECT_FOLDER_HINT_LINE, 2, "a, b"),
        (True, PROJECT_HINT_LINE, 6, "a, b, c, d, e and 1 more"),
    ],
    ids=["whole", "folder", "more"],
)
def test_a_project_not_found_names_the_subprojects_and_keeps_its_code(
    tmp_path: Path, whole: bool, line: object, count: int, folders: str
) -> None:
    folder = _monorepo(tmp_path, count)
    checkout = _checkout(folder, whole=whole)
    inner = CodedFileNotFoundError(PROJECT_NOT_FOUND, path=str(folder))
    with pytest.raises(RemoteSourceError) as raised:
        with checkout.explaining_failures():
            raise inner
    assert raised.value.code == "git.no-project"
    assert code_of(raised.value) == "project-not-found"
    assert raised.value.__cause__ is inner
    assert str(raised.value) == line.render(  # type: ignore[attr-defined]
        {"path": str(folder), "folders": folders}
    )
    _trusted(raised.value)


def _untouched(checkout: GitCheckout, inner: BaseException) -> None:
    """*inner* leaves :meth:`GitCheckout.explaining_failures` as it is."""
    with pytest.raises(type(inner)) as raised:
        with checkout.explaining_failures():
            raise inner
    assert raised.value is inner


def test_any_other_failure_is_left_as_it_is(tmp_path: Path) -> None:
    """An inner error of another code, one with no code, and a
    ``project-not-found`` with no subprojects to name."""
    folder = _monorepo(tmp_path)
    checkout = _checkout(folder, whole=True)
    _untouched(checkout, input_not_found("fragments directory", "x"))
    _untouched(checkout, FileNotFoundError("no project"))
    empty = tmp_path / "empty"
    empty.mkdir()
    lone = CodedFileNotFoundError(PROJECT_NOT_FOUND, path=str(empty))
    _untouched(_checkout(empty, whole=True), lone)


def test_a_hint_already_given_is_not_explained_again(tmp_path: Path) -> None:
    """A ``git.no-project`` error (a fetch error carrying
    ``project-not-found``) crossing a second ``explaining_failures`` leaves
    as it is, not wrapped in a second hint."""
    folder = _monorepo(tmp_path)
    hint = project_hint_error(str(folder), ["a", "b"], 0, True)
    _untouched(_checkout(folder, whole=True), hint)


@pytest.mark.parametrize(
    ("whole", "line"),
    [(True, NO_TARGET_HINT_LINE), (False, NO_TARGET_FOLDER_HINT_LINE)],
    ids=["whole", "folder"],
)
def test_a_neither_project_nor_model_names_the_subprojects_too(
    tmp_path: Path, whole: bool, line: object
) -> None:
    folder = _monorepo(tmp_path)
    subject = "https://h.example/r.git"
    with pytest.raises(RemoteSourceError) as raised:
        resolve_git_target(_checkout(folder, whole=whole), model_target.AUTO, subject)
    assert raised.value.code == "git.no-project"
    assert code_of(raised.value) == NO_SBOM_TARGET.code
    assert str(raised.value) == line.render(  # type: ignore[attr-defined]
        {"path": subject, "folders": "a, b"}
    )
    _trusted(raised.value)


def test_a_neither_project_nor_model_without_subprojects_is_untouched(
    tmp_path: Path,
) -> None:
    with pytest.raises(CodedValueError) as raised:
        resolve_git_target(
            _checkout(tmp_path, whole=True), model_target.AUTO, "https://h/r.git"
        )
    assert code_of(raised.value) == NO_SBOM_TARGET.code
    assert raised.type is CodedValueError  # not the remote class


@pytest.mark.parametrize(
    "inner",
    [input_not_found("fragments directory", "x"), ValueError("not coded")],
    ids=["other-code", "uncoded"],
)
def test_another_target_failure_is_not_given_the_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inner: BaseException
) -> None:
    """Subprojects exist, but the inner error is not ``project-or-model-not-found``."""
    folder = _monorepo(tmp_path)

    def refuse(*args: object, **kw: object) -> None:
        raise inner

    monkeypatch.setattr(git_target, "resolve_sbom_target", refuse)
    with pytest.raises(type(inner)) as raised:
        resolve_git_target(
            _checkout(folder, whole=True), model_target.AUTO, "https://h/r.git"
        )
    assert raised.value is inner


# -- the git command echo (row 7) ------------------------------------------------------


def test_each_git_call_is_echoed_without_a_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="pitloom"):
        GitRunner().run(["--version"], "version")
        GitRunner().run(["--version"], "version", echo=False)
    (record,) = caplog.records
    assert record.getMessage().startswith(f"{GIT_PREFIX}$ ")
    assert record.getMessage().endswith(" --version")
    assert getattr(record, CODE_ATTR, None) is None
    assert trusted_message(f"INFO: {record.getMessage()}") is None


def test_the_echo_holds_no_credential_of_the_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    url = f"http://user:tok3n@127.0.0.1:{_closed_port()}/x.git"
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            GitRunner().run(["ls-remote", "--", url], "ls-remote")
    echoed = [r.getMessage() for r in caplog.records]
    assert any("ls-remote" in line for line in echoed)
    assert "tok3n" not in " ".join(echoed) and "tok3n" not in str(raised.value)
