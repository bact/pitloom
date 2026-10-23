# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The edges of Git fetching: a ``git`` that hangs, floods or fails, hostile
ref listings, the monorepo hint's limits, and what a URL's text may be.

A stand-in ``git`` program (a script first on ``PATH``) plays the server's
side, so no network and no real repository is involved.
"""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest import mock

import pytest

from pitloom.extract.remote import RemoteSourceError, _git_run, git, git_url
from pitloom.extract.remote._git_folder import subproject_hint
from pitloom.extract.remote._git_run import GitRunner, _kill, _taskkill
from pitloom.extract.remote.git import (
    GitCheckout,
    _checkout,
    _folder,
    _resolve,
    _target,
)
from pitloom.extract.remote.git_url import (
    GitPage,
    GitTarget,
    is_unsupported_remote_url,
    parse_git_page,
    scheme_allowed,
)

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="a shell script stands in for git"
)


def _fake_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    """Put a ``git`` that runs the shell *body* first on ``PATH``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "git"
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")


@posix_only
def test_a_git_that_outlives_the_deadline_is_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``git.timeout``, and the call returns when the deadline does."""
    _fake_git(tmp_path, monkeypatch, "sleep 30")
    with pytest.raises(RemoteSourceError) as excinfo:
        GitRunner(seconds=0.5).run(["ls-remote"], "ls-remote")
    assert excinfo.value.code == "git.timeout"


@posix_only
def test_a_git_that_floods_its_output_is_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """More output than the cap: ``git.output-too-large``."""
    _fake_git(tmp_path, monkeypatch, "yes | head -c 20000000")
    with pytest.raises(RemoteSourceError) as excinfo:
        GitRunner().run(["ls-remote"], "ls-remote")
    assert excinfo.value.code == "git.output-too-large"


@posix_only
def test_a_failing_git_reports_its_message_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``git.clone-failed`` carries git's own stderr; a password in it is
    masked; an empty stderr says the exit status."""
    _fake_git(
        tmp_path,
        monkeypatch,
        "echo 'fatal: unable to access https://u:secret@h/r' >&2; exit 128",
    )
    with pytest.raises(RemoteSourceError) as excinfo:
        GitRunner().run(["clone"], "clone", echo=False)
    assert "secret" not in str(excinfo.value) and "***:***@h/r" in str(excinfo.value)
    _fake_git(tmp_path / "again", monkeypatch, "exit 3")
    with pytest.raises(RemoteSourceError, match="git exited 3"):
        GitRunner().run(["clone"], "clone")


@posix_only
def test_the_command_is_echoed_in_an_info_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Each call is one ``INFO:``; a ``user:password@`` is masked; a call made
    quietly says nothing."""
    _fake_git(tmp_path, monkeypatch, "exit 0")
    with caplog.at_level(logging.INFO):
        GitRunner().run(["ls-remote", "--", "https://u:pw@h/r"], "ls-remote")
        GitRunner().run(["rev-parse"], "rev-parse", echo=False)
    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 1 and "***:***@h/r" in lines[0] and "pw@" not in lines[0]


# pylint: disable-next=too-few-public-methods
class _Listing:
    """A stand-in runner answering ``ls-remote`` with fixed text."""

    def __init__(self, text: str) -> None:
        self.text = text

    def run(self, _args: list[str], _what: str, *, echo: bool = True) -> str:
        """Return the listing."""
        assert echo
        return self.text


def test_a_hostile_ref_listing_cannot_make_a_ref_or_folder_up() -> None:
    """Lines that are no ``branch`` or ``tag`` ref (no tab, other namespaces,
    blank, odd names) add nothing; the longest real ref still wins."""
    lines = [
        "",
        "no-tab-here",
        "abc\trefs/pull/1/head",
        "abc\trefs/heads/",
        "abc\trefs/heads/main",
        "abc\trefs/heads/main/x",
        "abc\trefs/tags/v1",
        "abc\trefs/heads/dup",
        "abc\trefs/tags/dup",
    ]
    listing = "\n".join(lines)
    page = GitPage("https://h/o/r", ("main", "x", "dir"), kind=None)
    target = _target(_Listing(listing), "https://h/o/r", page)  # type: ignore[arg-type]
    assert (target.ref, target.subdir) == ("main/x", "dir")


def test_a_page_that_is_not_a_repository_with_the_same_url_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the whole URL is the repository already (nothing to fall back to),
    or the failure is not "not a repository", the error stands."""

    # pylint: disable-next=too-few-public-methods
    class Failing:
        """A runner whose ``ls-remote`` fails with a chosen code."""

        def __init__(self, code: str) -> None:
            self.code = code

        def run(self, *_args: object, **_kwargs: object) -> str:
            """Raise."""
            raise RemoteSourceError(self.code, "boom")

    monkeypatch.setattr(git, "resolve_git_url", lambda url, _check: url)
    same = GitPage("https://h/o/r", ("main",), plain_url="https://h/o/r")
    with pytest.raises(RemoteSourceError, match="boom"):
        _resolve(Failing("git.clone-failed"), same, None)  # type: ignore[arg-type]
    other = GitPage("https://h/o", ("main",), plain_url="https://h/o/src/r")
    with pytest.raises(RemoteSourceError) as excinfo:
        _resolve(Failing("git.timeout"), other, None)  # type: ignore[arg-type]
    assert excinfo.value.code == "git.timeout"


def test_a_failure_of_the_project_is_explained_only_when_there_is_a_hint(
    tmp_path: Path,
) -> None:
    """A folder with no project but projects below it turns a failure into
    ``git.no-project``; a failure that is already a ``RemoteSourceError`` or
    has no hint passes untouched."""
    plain = GitCheckout(str(tmp_path), "u", None, "c", "", True)
    with pytest.raises(ValueError, match="plain"), plain.explaining_failures():
        raise ValueError("plain")
    with pytest.raises(RemoteSourceError) as excinfo, plain.explaining_failures():
        raise RemoteSourceError("git.clone-failed", "kept")
    assert excinfo.value.code == "git.clone-failed"
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "setup.py").write_text("", encoding="utf-8")
    with pytest.raises(RemoteSourceError) as excinfo, plain.explaining_failures():
        raise ValueError("no project")
    assert excinfo.value.code == "git.no-project"
    assert "no project" in str(excinfo.value) and "sub" in str(excinfo.value)


def test_the_hint_looks_a_few_folders_deep_only(tmp_path: Path) -> None:
    """A project five folders down is not listed; a checkout with no project
    anywhere has no hint."""
    deep = tmp_path / "a" / "b" / "c" / "d" / "e"
    deep.mkdir(parents=True)
    (deep / "setup.py").write_text("", encoding="utf-8")
    assert subproject_hint(str(tmp_path), True) == ""
    (tmp_path / "a" / "b" / "c" / "setup.py").write_text("", encoding="utf-8")
    assert "a/b/c" in subproject_hint(str(tmp_path), True)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("ssh://git@host/o/r.git", True),
        ("git://host/o/r.git", True),
        ("file:///tmp/r", True),
        ("ftp://h/x", True),
        ("git@github.com:o/r.git", True),
        ("user@host:path/r", True),
        (" ssh://h/r ", True),
        ("https://github.com/o/r", False),
        ("https://huggingface.co/o/m", False),
        ("C:\\\\work\\\\proj", False),
        ("C:/work/proj", False),
        ("./proj", False),
        ("a@b:/abs", False),
        ("plain", False),
        ("", False),
    ],
)
def test_which_addresses_are_remote_but_not_fetched(
    source: str, expected: bool
) -> None:
    """An ssh, git, file or scp-style address is told apart from a path, a
    Windows drive and a supported URL."""
    assert is_unsupported_remote_url(source) is expected


def test_a_broken_url_is_not_an_allowed_scheme() -> None:
    """``urlsplit`` raising (a bracket without its pair) is a refusal."""
    assert not scheme_allowed("http://[::1")
    assert parse_git_page("https://").repo_name == ""


def test_the_allowed_schemes_can_be_widened_for_a_test_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The set is read when asked, so a test can allow ``file:``."""
    monkeypatch.setattr(git_url, "ALLOWED_SCHEMES", frozenset({"file"}))
    assert scheme_allowed("file:///x") and not scheme_allowed("https://h/x")


@posix_only
def test_killing_a_process_that_is_already_gone_is_harmless() -> None:
    """A deadline that fires as git exits finds no process group: no error."""
    with subprocess.Popen(  # nosec B603: fixed argv
        [sys.executable, "-c", "pass"], start_new_session=True
    ) as proc:
        proc.wait()
        _kill(proc)


@posix_only
@pytest.mark.parametrize("error", [ProcessLookupError, PermissionError])
def test_a_process_group_that_cannot_be_signalled_is_gone(
    error: type[OSError], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Killing the group of a process that has just exited is no failure
    (macOS says EPERM, Linux ESRCH)."""

    def refuse(_pid: int, _signal: int) -> None:
        raise error

    monkeypatch.setattr(os, "killpg", refuse)
    with subprocess.Popen(  # nosec B603: fixed argv
        [sys.executable, "-c", "pass"]
    ) as proc:
        _kill(proc)


def _gone(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(argv, 128)


def _hangs(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    raise subprocess.TimeoutExpired(argv, kwargs["timeout"])


def _missing(_argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    raise FileNotFoundError("taskkill")


@pytest.mark.parametrize(
    ("taskkill", "answer"),
    [
        ("taskkill.exe", lambda argv, **_: subprocess.CompletedProcess(argv, 0)),
        ("taskkill.exe", _gone),
        ("taskkill.exe", _hangs),
        ("taskkill.exe", _missing),
        (None, _gone),
    ],
    ids=["killed", "already-gone", "hangs", "fails-to-start", "no-taskkill"],
)
def test_off_posix_the_process_tree_is_killed_then_the_process(
    taskkill: str | None,
    answer: Callable[..., subprocess.CompletedProcess[bytes]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``taskkill /F /T`` ends git and git-remote-https, within a bounded
    time; ``proc.kill()`` follows whatever taskkill did, or without it."""
    calls: list[object] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append((argv, kwargs["timeout"], kwargs["check"]))
        return answer(argv, **kwargs)

    proc = mock.create_autospec(subprocess.Popen, instance=True)
    proc.pid = 4321
    proc.kill.side_effect = lambda: calls.append("kill")
    monkeypatch.setattr(_git_run, "_POSIX", False)
    monkeypatch.setattr(_git_run, "_taskkill", lambda: taskkill)
    monkeypatch.setattr(_git_run, "_run_command", run)
    _kill(proc)
    tree = [(["taskkill.exe", "/F", "/T", "/PID", "4321"], 10.0, False)]
    assert calls == (tree if taskkill else []) + ["kill"]


def test_taskkill_is_found_below_the_system_root_or_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``%SystemRoot%\\System32`` first, then ``PATH``; ``None`` without
    either."""
    name = "taskkill.exe" if sys.platform == "win32" else "taskkill"
    on_path, root = tmp_path / "bin", tmp_path / "root"
    on_path.mkdir()
    (root / "System32").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)  # Windows looks in the current folder first
    monkeypatch.setenv("PATH", str(on_path))
    monkeypatch.delenv("SystemRoot", raising=False)
    assert _taskkill() is None
    found = on_path / name
    found.write_bytes(b"")
    found.chmod(found.stat().st_mode | stat.S_IEXEC)
    assert Path(_taskkill() or "") == found
    monkeypatch.setenv("SystemRoot", str(root))
    assert Path(_taskkill() or "") == found
    below_root = root / "System32" / "taskkill.exe"
    below_root.write_bytes(b"")
    assert _taskkill() == str(below_root)


@pytest.mark.parametrize(
    ("target", "folder"),
    [
        (GitTarget(ref="main", subdir="dir/app.toml"), "dir"),
        (GitTarget(ref="main", subdir="app.toml"), ""),
    ],
    ids=["file-in-folder", "file-at-root"],
)
def test_a_folder_page_that_names_a_file_reads_the_folder_holding_it(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    target: GitTarget,
    folder: str,
) -> None:
    """Bitbucket and SourceHut write a file page like a folder page."""
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "app.toml").write_bytes(b"")
    (tmp_path / "app.toml").write_bytes(b"")
    with caplog.at_level(logging.INFO):
        result = _folder(str(tmp_path), target)
    assert os.path.realpath(result) == os.path.realpath(tmp_path / folder)
    assert "is a file, not a folder" in caplog.text


@pytest.mark.parametrize(
    "target",
    [
        GitTarget(ref="main", subdir="nothing"),
        GitTarget(ref="main", subdir="dir", file="app.toml"),
    ],
    ids=["missing", "file-page-with-a-folder-that-is-missing"],
)
def test_a_missing_folder_is_still_refused(tmp_path: Path, target: GitTarget) -> None:
    """Only a path that is a file of the checkout is read as its folder."""
    with pytest.raises(RemoteSourceError) as excinfo:
        _folder(str(tmp_path), target)
    assert excinfo.value.code == "git.path-not-found"


def test_a_file_reached_through_a_link_out_of_the_checkout_is_refused(
    tmp_path: Path,
) -> None:
    """A link to a file outside the checkout does not make a folder page a
    file page."""
    outside = tmp_path / "outside.toml"
    outside.write_bytes(b"")
    work = tmp_path / "work"
    work.mkdir()
    try:
        (work / "link.toml").symlink_to(outside)
    except OSError:  # pragma: no cover - Windows without symlink privilege
        pytest.skip("symbolic links are not available")
    with pytest.raises(RemoteSourceError):
        _folder(str(work), GitTarget(ref="main", subdir="link.toml"))


# pylint: disable-next=too-few-public-methods
class _FilterRejectingRunner:
    """A runner whose calls with a ``--filter`` option fail with *message*, and
    which, like git, refuses a second ``init`` or ``remote add`` in one work
    folder."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.calls: list[list[str]] = []
        self.saved = False

    def run(self, args: list[str], _what: str, **_kwargs: Any) -> str:
        if args[0] == "init" or "remote" in args:
            assert not any(
                c[0] == args[0] and ("remote" in c) == ("remote" in args)
                for c in self.calls
            ), "second init or remote add in one work folder"
        self.calls.append(args)
        # git keeps the filter of a fetch in the repository's config, even
        # when the fetch failed, and a later plain fetch sends it again.
        filtered = any(a.startswith("--filter") for a in args)
        if "fetch" in args:
            filtered = filtered or (self.saved and "--no-filter" not in args)
            self.saved = self.saved or filtered
        if filtered:
            raise RemoteSourceError("git.clone-failed", self.message)
        return ""


_REJECTED = "error: RPC failed; HTTP 400 curl 22 The requested URL returned error: 400"


@pytest.mark.parametrize(
    "target",
    [GitTarget(), GitTarget(ref="v1", tag=True), GitTarget(commit="a" * 40)],
    ids=["clone", "tag", "commit"],
)
def test_a_server_that_rejects_the_blob_filter_is_asked_again_without_it(
    caplog: pytest.LogCaptureFixture, target: GitTarget
) -> None:
    """Azure DevOps answers ``--filter=blob:limit`` with HTTP 400 but serves a
    plain shallow fetch."""
    runner = _FilterRejectingRunner(_REJECTED)
    with caplog.at_level(logging.INFO):
        _checkout(cast(GitRunner, runner), "https://h/o/r", "/work", target)
    wanted = "fetch" if target.tag or target.commit else "clone"
    shallow = [c for c in runner.calls if wanted in c and "--depth" in c]
    assert len(shallow) == 2
    assert any(a.startswith("--filter") for a in shallow[0])
    assert not any(a.startswith("--filter") for a in shallow[1])
    assert "rejected the blob filter" in caplog.text


@pytest.mark.parametrize(
    "message",
    ["fatal: repository not found", "fatal: unable to access: HTTP 500"],
    ids=["not-found", "server-error"],
)
def test_any_other_clone_failure_is_not_retried(message: str) -> None:
    """Only the answer a filter earns is retried: any other error stands."""
    runner = _FilterRejectingRunner(message)
    with pytest.raises(RemoteSourceError, match="fatal"):
        _checkout(cast(GitRunner, runner), "https://h/o/r", "/work", GitTarget())
    assert len(runner.calls) == 1
