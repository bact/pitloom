# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""What an untrusted Git server or repository cannot do: reach another host
through git-lfs, forge a log line, leak a credential, outlive Ctrl-C, fill the
disk, or point Pitloom at a host file; and that every refusal is said.

A stand-in ``git`` script plays the server's side where a real one cannot, and
local repositories (``file://``, allowed for these tests only) elsewhere.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from pitloom.extract.remote import (
    RemoteSourceError,
    _git_run,
    fetch_git_project,
    git,
    git_url,
)
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote.git import _head, _resolve
from pitloom.extract.remote.git_url import (
    GitPage,
    is_git_url,
    parse_git_page,
    split_ref,
)

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="a shell script stands in for git"
)
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _fake_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    """Put a ``git`` that runs the shell *body* first on ``PATH``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "git"
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")


@posix_only
def test_git_runs_without_lfs_and_with_a_clean_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git-lfs would fetch from the address a repository's ``.lfsconfig``
    names, past the URL check; a ``GIT_DIR`` of the caller (a git hook) would
    point git at another repository."""
    seen = tmp_path / "seen.txt"
    _fake_git(tmp_path, monkeypatch, f'echo "$@" > {seen}; env >> {seen}')
    monkeypatch.setenv("GIT_DIR", "/elsewhere/.git")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "kept")
    GitRunner().run(["ls-remote"], "ls-remote", echo=False)
    lines = seen.read_text(encoding="utf-8").splitlines()
    for setting in (
        "filter.lfs.smudge=",
        "filter.lfs.process=",
        "http.followRedirects=false",
    ):
        assert f"-c {setting}" in lines[0]
    assert "filter.lfs.required=false" in lines[0]
    env = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
    assert env["GIT_LFS_SKIP_SMUDGE"] == "1" and env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_ALLOW_PROTOCOL"] == "http:https"
    assert "GIT_DIR" not in env and "GIT_CONFIG_COUNT" not in env
    assert env["GIT_AUTHOR_NAME"] == "kept"  # only what repoints git is removed


@posix_only
@pytest.mark.parametrize(
    "stderr",
    [
        "remote: boom\nERROR: forged line\n::error::x \x1b[31mred",
        "Cloning into '/tmp/pitloom-git-ab12'...\nfatal: boom\n",
        "\x1b[31m::error::x\nERROR: forged",
    ],
    ids=["server-lines", "checkout-path-and-progress", "no-error-line"],
)
def test_git_stderr_becomes_one_plain_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    """A message from the server cannot forge a tagged line, a workflow
    command or a terminal escape; it is one line, without the temporary path."""
    script = tmp_path / "err.txt"
    script.write_text(stderr, encoding="utf-8")
    _fake_git(tmp_path, monkeypatch, f"cat {script} >&2; exit 128")
    with pytest.raises(RemoteSourceError) as excinfo:
        GitRunner().run(["clone"], "clone", echo=False)
    message = str(excinfo.value)
    assert "\n" not in message and "\x1b" not in message
    assert not message.startswith(("ERROR", "::"))
    assert "pitloom-git-" not in message
    assert ("boom" in message) == ("boom" in stderr)


@posix_only
def test_git_stderr_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A server that talks without end fills neither disk nor memory."""
    monkeypatch.setattr(_git_run, "MAX_OUTPUT_BYTES", 1000)
    _fake_git(tmp_path, monkeypatch, "yes remote | head -c 2000000 >&2; exit 1")
    with pytest.raises(RemoteSourceError) as excinfo:
        GitRunner().run(["clone"], "clone", echo=False)
    assert len(str(excinfo.value)) <= 1100


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@posix_only
def test_ctrl_c_kills_what_git_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupt of the caller does not leave git (or its helpers) running."""
    pid_file = tmp_path / "pid.txt"
    _fake_git(tmp_path, monkeypatch, f"sleep 37 & echo $! > {pid_file}; wait")

    def interrupt(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    def press_ctrl_c() -> None:
        """Interrupt the caller once git has started what must be killed."""
        deadline = time.monotonic() + 60
        while not pid_file.exists() or not pid_file.read_text(encoding="utf-8"):
            if time.monotonic() > deadline:  # pragma: no cover
                break
            time.sleep(0.02)
        os.kill(os.getpid(), signal.SIGUSR1)

    previous = signal.signal(signal.SIGUSR1, interrupt)
    presser = threading.Thread(target=press_ctrl_c, daemon=True)
    presser.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            GitRunner().run(["clone"], "clone", echo=False)
    finally:
        signal.signal(signal.SIGUSR1, previous)
        presser.join()
    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 30
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(pid)


def test_a_message_never_carries_the_credentials_of_the_url() -> None:
    """Both the path check and the ref check quote the URL without them."""
    with pytest.raises(RemoteSourceError) as excinfo:
        parse_git_page("https://user:SECRET@h/o/r/-/tree/main/../x")
    assert "SECRET" not in str(excinfo.value) and "***" in str(excinfo.value)
    page = GitPage("https://user:SECRET@h/o/r", ("nothere", "x"))
    with pytest.raises(RemoteSourceError) as excinfo:
        split_ref(page, {})
    assert "SECRET" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("url", "repo", "rest", "is_file"),
    [
        (
            "https://g.example/g/sub/src/proj/-/tree/main/x",
            "g/sub/src/proj",
            ("main", "x"),
            False,
        ),
        (
            "https://g.example/g/sub/tree/proj/-/blob/main/x.py",
            "g/sub/tree/proj",
            ("main", "x.py"),
            True,
        ),
        (
            "https://g.example/o/r/tree/main/src/branch/x",
            "o/r",
            ("main", "src", "branch", "x"),
            False,
        ),
    ],
    ids=["group-called-src", "group-called-tree", "folder-called-like-a-marker"],
)
def test_the_gitlab_marker_wins_over_a_group_named_like_another(
    url: str, repo: str, rest: tuple[str, ...], is_file: bool
) -> None:
    """``/-/`` is unambiguous; any other marker is the first one by position."""
    page = parse_git_page(url)
    assert page.repo_url == f"https://g.example/{repo}"
    assert page.rest == rest and page.is_file is is_file


@pytest.mark.parametrize(
    "url",
    ["https://hf.co/o/m", "https://www.huggingface.co/o/m", "https://HF.CO/o/m"],
)
def test_other_spellings_of_hugging_face_are_not_git_repositories(url: str) -> None:
    """A clone of a model repository would fetch its weights."""
    assert not is_git_url(url)


def _page(url: str = "https://h/o/r/tree/main/x") -> GitPage:
    return parse_git_page(url)


@pytest.mark.parametrize(
    ("message", "retried"),
    [
        ("fatal: repository 'https://h/o/r/' not found", True),
        ("fatal: unable to access: SSL certificate problem", False),
        ("fatal: Authentication failed", False),
    ],
    ids=["not-found", "tls", "sign-in"],
)
def test_only_a_missing_repository_is_tried_as_the_whole_url(
    monkeypatch: pytest.MonkeyPatch, message: str, retried: bool
) -> None:
    """A failure to reach the server is the failure, not a reason to ask again."""
    monkeypatch.setattr(git, "resolve_git_url", lambda url, _check: url)

    def refuse(*_args: object) -> None:
        raise RemoteSourceError("git.clone-failed", message)

    monkeypatch.setattr(git, "_target", refuse)
    if retried:
        _url, page, target = _resolve(GitRunner(), _page(), None)
        assert page.repo_url == "https://h/o/r/tree/main/x" and not target.ref
    else:
        with pytest.raises(RemoteSourceError, match="fatal"):
            _resolve(GitRunner(), _page(), None)


@pytest.mark.parametrize(
    "refusal",
    [
        RemoteSourceError("git.too-many-redirects", "too many"),
        RemoteSourceError("git.url-invalid", "bad port"),
        RemoteSourceError("git.ref-not-found", "no such ref"),
        ValueError("blocked by the caller's check"),
    ],
    ids=["redirects", "url", "ref", "caller-check"],
)
def test_every_refusal_is_a_warning_and_raised(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    refusal: Exception,
) -> None:
    """A caller that only logs still shows why nothing was fetched."""

    def refuse(*_args: object) -> None:
        raise refusal

    monkeypatch.setattr(git, "resolve_git_url", refuse)
    with caplog.at_level(logging.WARNING), pytest.raises(type(refusal)):
        with fetch_git_project("https://h/o/r"):
            pytest.fail("not fetched")
    assert [r.getMessage() for r in caplog.records] == [f"Git source: {refusal}"]


def test_a_failure_of_the_caller_inside_the_block_is_not_a_fetch_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Only what happens before the checkout is handed over is said."""
    work = Path(os.devnull)
    del work
    monkeypatch.setattr(
        git,
        "_prepare",
        lambda *_a: git.GitCheckout("f", "u", None, "c", "", True),
    )
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match="mine"):
        with fetch_git_project("https://h/o/r"):
            raise ValueError("mine")
    assert not caplog.records


def test_offline_is_a_warning_as_well(caplog: pytest.LogCaptureFixture) -> None:
    """The same as a refused scheme: logged and raised."""
    with caplog.at_level(logging.WARNING), pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project("https://h/o/r", offline=True):
            pytest.fail("not fetched")
    assert excinfo.value.code == "git.offline"
    assert "network access is forbidden" in caplog.text


@pytest.fixture(name="local")
def _local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow ``file:`` URLs and isolate ``git`` from the user's own config."""
    monkeypatch.setattr(git_url, "ALLOWED_SCHEMES", frozenset({"file"}))
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)


def _run(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={**os.environ, **_ENV},
    )


@needs_git
@posix_only
@pytest.mark.usefixtures("local")
def test_a_link_to_a_host_file_is_dropped_with_an_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A tracked symbolic link that leaves the checkout is never read or
    hashed; one that stays inside is kept."""
    secret = tmp_path / "secret.txt"
    secret.write_text("host file", encoding="utf-8")
    root = tmp_path / "origin"
    root.mkdir()
    _run(root, "init", "-q", "-b", "main")
    (root / "real.py").write_text("x = 1\n", encoding="utf-8")
    (root / "inside.py").symlink_to("real.py")
    (root / "outside.py").symlink_to(secret)
    (root / "dir").symlink_to(tmp_path)
    _run(root, "add", ".")
    _run(root, "commit", "-q", "-m", "one")
    with caplog.at_level(logging.INFO):
        with fetch_git_project(f"file://{root}") as checkout:
            names = sorted(p.name for p in Path(checkout.folder).iterdir())
    assert names == [".git", "inside.py", "real.py"]
    assert "2 symbolic link(s) leading out of the repository" in caplog.text


@needs_git
@posix_only
@pytest.mark.usefixtures("local")
def test_an_empty_repository_is_said_to_be_empty(tmp_path: Path) -> None:
    """Not git's ``ambiguous argument 'HEAD'``."""
    root = tmp_path / "empty.git"
    root.mkdir()
    _run(root, "init", "-q", "--bare")
    with pytest.raises(RemoteSourceError, match="empty repository"):
        with fetch_git_project(f"file://{root}"):
            pytest.fail("nothing to read")


@needs_git
@posix_only
@pytest.mark.usefixtures("local")
def test_the_folder_is_named_below_a_symlinked_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """macOS's ``/var`` is a link to ``/private/var``: ``subdir`` stays the
    folder the URL named."""
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "link"))
    monkeypatch.setattr("tempfile.tempdir", None)
    root = tmp_path / "origin"
    (root / "pkg").mkdir(parents=True)
    _run(root, "init", "-q", "-b", "main")
    (root / "pkg" / "a.txt").write_text("a", encoding="utf-8")
    _run(root, "add", ".")
    _run(root, "commit", "-q", "-m", "one")
    with fetch_git_project(f"file://{root}/tree/main/pkg") as checkout:
        assert checkout.subdir == "pkg" and not checkout.whole_repository
    with fetch_git_project(f"file://{root}") as checkout:
        assert checkout.subdir == "" and checkout.whole_repository


def test_a_timeout_reading_the_commit_is_not_an_empty_repository() -> None:
    """Only git's own failure means there is no commit; a deadline stays one."""

    # pylint: disable-next=too-few-public-methods
    class Late:
        """A runner whose deadline has passed."""

        def run(self, *_args: object, **_kwargs: object) -> str:
            """Fail as a call past the deadline does."""
            raise RemoteSourceError("git.timeout", "late")

    with pytest.raises(RemoteSourceError) as excinfo:
        _head(Late(), "w", "u")  # type: ignore[arg-type]
    assert excinfo.value.code == "git.timeout"


@posix_only
@pytest.mark.parametrize(
    ("body", "stopped"),
    [
        # Writes past the cap, then would run for a minute.
        ('head -c 200000 /dev/zero > "$PITLOOM_TEST_DIR/pack"; sleep 60', True),
        # Past the cap before the first look, and gone.
        ('head -c 200000 /dev/zero > "$PITLOOM_TEST_DIR/pack"', True),
        # Under the cap through several looks at the size.
        ('head -c 100 /dev/zero > "$PITLOOM_TEST_DIR/pack"; sleep 1', False),
    ],
    ids=["running", "finished", "under"],
)
def test_a_call_that_writes_more_than_the_cap_is_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str, stopped: bool
) -> None:
    """``git.too-large``, quickly and not after the sleep; a call under the
    cap is untouched."""
    watched = tmp_path / "checkout"
    watched.mkdir()
    monkeypatch.setattr(_git_run, "_SIZE_POLL_SECONDS", 0.1)
    monkeypatch.setenv("PITLOOM_TEST_DIR", str(watched))
    _fake_git(tmp_path, monkeypatch, body)
    started = time.monotonic()
    runner = GitRunner(max_bytes=100_000)
    if stopped:
        with pytest.raises(
            RemoteSourceError, match="larger than 100000 bytes"
        ) as excinfo:
            runner.run(["clone"], "clone", echo=False, watch=str(watched))
        assert excinfo.value.code == "git.too-large"
        assert time.monotonic() - started < 30
    else:
        assert runner.run(["clone"], "clone", echo=False, watch=str(watched)) == ""


@posix_only
def test_nothing_is_watched_without_a_directory_or_a_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched = tmp_path / "checkout"
    watched.mkdir()
    monkeypatch.setenv("PITLOOM_TEST_DIR", str(watched))
    _fake_git(tmp_path, monkeypatch, 'head -c 200000 /dev/zero > "$PITLOOM_TEST_DIR/p"')
    GitRunner(max_bytes=100).run(["clone"], "clone", echo=False)
    GitRunner().run(["clone"], "clone", echo=False, watch=str(watched))


@pytest.mark.parametrize("limit", [0, -1])
def test_a_cap_that_is_not_positive_is_refused(limit: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        with fetch_git_project("https://h/o/r", max_bytes=limit):
            pytest.fail("not fetched")


@needs_git
@posix_only
@pytest.mark.usefixtures("local")
@pytest.mark.parametrize("limit", [10_000, 10_000_000], ids=["over", "under"])
def test_a_repository_over_the_cap_is_not_read(tmp_path: Path, limit: int) -> None:
    """The real clone of a repository holding a 300 KB file."""
    root = tmp_path / "origin"
    root.mkdir()
    _run(root, "init", "-q", "-b", "main")
    (root / "big.bin").write_bytes(os.urandom(300_000))
    _run(root, "add", ".")
    _run(root, "commit", "-q", "-m", "one")
    if limit < 300_000:
        with pytest.raises(RemoteSourceError) as excinfo:
            with fetch_git_project(f"file://{root}", max_bytes=limit):
                pytest.fail("too large")
        assert excinfo.value.code == "git.too-large"
    else:
        with fetch_git_project(f"file://{root}", max_bytes=limit) as checkout:
            assert (Path(checkout.folder) / "big.bin").is_file()
