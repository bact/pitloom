# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A Git URL's repository, branch, tag, commit and folder against a real
repository: a local one, read through the same ``git`` calls as a remote one
(the URLs are ``file://``, allowed for these tests only).

See also: :mod:`tests.extract.remote.test_git_url` for how a URL is read.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pitloom.extract.remote import (
    RemoteSourceError,
    _git_run,
    fetch_git_project,
    git_url,
)
from pitloom.extract.remote._git_folder import subproject_hint
from pitloom.extract.remote.git import RESOLVED_INFO

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
    pytest.mark.skipif(sys.platform == "win32", reason="file:// URLs of POSIX paths"),
]

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_ENV},
    )
    return done.stdout.strip()


@pytest.fixture(autouse=True)
def _local_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow ``file:`` URLs, and isolate ``git`` from the user's own config."""
    monkeypatch.setattr(git_url, "ALLOWED_SCHEMES", frozenset({"file"}))
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(name="repo")
def _repo(tmp_path: Path) -> tuple[Path, str]:
    """A repository with ``main``, ``feature/x`` (with a folder ``pkg``), the
    tag ``v1``, and a branch and a tag both called ``dup``; returns it and the
    commit of ``main``."""
    root = tmp_path / "origin"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "checkout", "-q", "-b", "main")
    (root / "root.txt").write_text("main\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "one")
    _git(root, "tag", "v1")
    _git(root, "tag", "dup")
    main_commit = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "-b", "feature/x")
    (root / "pkg").mkdir()
    (root / "pkg" / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "1"\n', encoding="utf-8"
    )
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "two")
    _git(root, "branch", "dup")  # a branch called like the tag, on another commit
    _git(root, "checkout", "-q", "main")
    return root, main_commit


def _url(root: Path, page: str = "") -> str:
    return f"file://{root}{page}"


@pytest.mark.parametrize(
    ("page", "files"),
    [
        ("", ("root.txt", "pkg")),
        ("/tree/main", ("root.txt", "pkg")),
        ("/tree/v1", ("root.txt", "pkg")),
        ("/-/tree/feature/x/pkg", ("pyproject.toml", "root.txt")),
        ("/src/branch/feature/x/pkg", ("pyproject.toml", "root.txt")),
        ("/blob/feature/x/pkg/pyproject.toml", ("pyproject.toml", "root.txt")),
        ("/blob/feature/x/pkg", ("pyproject.toml", "root.txt")),
        ("/tree/main?tab=readme#top", ("root.txt", "pkg")),
    ],
    ids=[
        "default-branch",
        "branch",
        "tag",
        "gitlab-branch-with-slash-and-folder",
        "gitea-branch-with-slash-and-folder",
        "file-page",
        "file-page-that-is-a-folder",
        "query-and-fragment",
    ],
)
def test_the_checkout_is_the_ref_and_folder_the_url_names(
    repo: tuple[Path, str], page: str, files: tuple[str, str]
) -> None:
    """The folder Pitloom reads is the one the URL names, at that ref: the
    first file is there, the second is not."""
    with fetch_git_project(_url(repo[0], page)) as checkout:
        folder = Path(checkout.folder)
        assert (folder / files[0]).exists()
        assert not (folder / files[1]).exists()
    assert not folder.exists()  # removed on exit


@pytest.mark.parametrize(
    ("page", "content"),
    [("/src/tag/dup", "main\n"), ("/src/branch/dup", "two\n"), ("/tree/dup", "two\n")],
    ids=[
        "tag-page-takes-the-tag",
        "branch-page-takes-the-branch",
        "plain-takes-branch",
    ],
)
def test_a_name_that_is_branch_and_tag_follows_the_page(
    repo: tuple[Path, str], page: str, content: str
) -> None:
    """The tag ``dup`` is the commit of ``main``; the branch ``dup`` has the
    folder ``pkg``."""
    with fetch_git_project(_url(repo[0], page)) as checkout:
        folder = Path(checkout.folder)
        assert (folder / "pkg").exists() == (content == "two\n")


def test_a_commit_in_the_url_is_checked_out(repo: tuple[Path, str]) -> None:
    """A full commit id works where no branch or tag has that name."""
    root, commit = repo
    with fetch_git_project(_url(root, f"/src/commit/{commit}")) as checkout:
        assert checkout.commit == commit
        assert (Path(checkout.folder) / "root.txt").is_file()


def test_the_checkout_reports_what_it_holds(repo: tuple[Path, str]) -> None:
    """The commit, the ref and the folder of what was fetched."""
    root, _ = repo
    with fetch_git_project(_url(root, "/tree/feature/x/pkg")) as checkout:
        assert checkout.ref == "feature/x" and checkout.subdir == "pkg"
        assert not checkout.whole_repository
        assert checkout.commit == _git(root, "rev-parse", "feature/x")
    with fetch_git_project(_url(root)) as checkout:
        assert checkout.whole_repository and checkout.ref is None


@pytest.mark.parametrize(
    ("page", "code"),
    [
        ("/tree/nope/pkg", "git.ref-not-found"),
        ("/tree/0123abc/pkg", "git.ref-not-found"),
        ("/tree/main/pkg", "git.path-not-found"),
        ("/tree/main/../../x", "git.url-invalid"),
    ],
    ids=["unknown-ref", "short-commit", "missing-folder", "dot-dot"],
)
def test_a_url_that_names_nothing_fetchable_has_a_code(
    repo: tuple[Path, str], page: str, code: str
) -> None:
    """Each refusal has a stable code and names what was wrong."""
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(_url(repo[0], page)):
            pass  # pragma: no cover
    assert excinfo.value.code == code


def test_a_link_cannot_lead_out_of_the_checkout(
    repo: tuple[Path, str], tmp_path: Path
) -> None:
    """A symlink folder pointing outside the checkout is refused."""
    root, _ = repo
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:  # pragma: no cover
        pytest.skip("symlinks need a privilege")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "link")
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(_url(root, "/tree/main/link")):
            pass  # pragma: no cover
    assert excinfo.value.code == "git.path-not-found"


def test_a_group_called_like_a_marker_falls_back_to_the_whole_url(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``.../src/proj`` is read as a page of ``.../`` first, which is no
    repository; the whole URL is then tried, with one ``INFO:``."""
    proj = tmp_path / "a" / "o" / "src" / "proj"
    proj.mkdir(parents=True)
    _git(proj, "init", "-q")
    _git(proj, "checkout", "-q", "-b", "main")
    (proj / "f.txt").write_text("x\n", encoding="utf-8")
    _git(proj, "add", ".")
    _git(proj, "commit", "-q", "-m", "one")
    with caplog.at_level(logging.INFO):
        with fetch_git_project(f"file://{proj}") as checkout:
            assert (Path(checkout.folder) / "f.txt").is_file()
    tried = [
        r.getMessage() for r in caplog.records if "is not a repository" in r.message
    ]
    parent = f"file://{proj.parent.parent}"
    assert tried == [f"Git source: {parent} is not a repository; trying file://{proj}"]


def test_a_resolved_url_is_one_info_naming_source_and_target(
    repo: tuple[Path, str], caplog: pytest.LogCaptureFixture
) -> None:
    """The ``INFO:`` holds the URL given, the repository, the branch and the
    folder; a plain repository URL says nothing of the kind."""
    root, _ = repo
    given = _url(root, "/tree/feature/x/pkg")
    with caplog.at_level(logging.INFO):
        with fetch_git_project(given):
            pass
    lines = [r.getMessage() for r in caplog.records if "names repository" in r.message]
    assert lines == [
        RESOLVED_INFO % (given, _url(root), ", branch feature/x, folder pkg")
    ]
    caplog.clear()
    with caplog.at_level(logging.INFO):
        with fetch_git_project(_url(root)):
            pass
    assert "names repository" not in caplog.text


def test_offline_fetches_nothing(repo: tuple[Path, str]) -> None:
    """``git.offline`` before any ``git`` call."""
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(_url(repo[0]), offline=True):
            pass  # pragma: no cover
    assert excinfo.value.code == "git.offline"


@pytest.mark.parametrize("url", ["ssh://host/o/r", "git@host:o/r.git", "ftp://h/r"])
def test_only_http_and_https_are_fetched(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any other scheme is ``git.url-invalid``, with the real allow-list."""
    monkeypatch.setattr(git_url, "ALLOWED_SCHEMES", frozenset({"http", "https"}))
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(url):
            pass  # pragma: no cover
    assert excinfo.value.code == "git.url-invalid"


def test_a_missing_git_is_a_clear_error(
    repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No ``git`` on the path: ``git.not-found``."""
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(_url(repo[0])):
            pass  # pragma: no cover
    assert excinfo.value.code == "git.not-found"


def test_a_failed_clone_carries_gits_message_without_credentials(
    tmp_path: Path,
) -> None:
    """``git.clone-failed``, with git's own text."""
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(f"file://{tmp_path}/nowhere/repo"):
            pass  # pragma: no cover
    assert excinfo.value.code == "git.clone-failed"
    assert "nowhere" in str(excinfo.value)


def test_the_time_and_output_of_git_are_limited(
    repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deadline already passed is ``git.timeout``; an output over the cap
    stops the call with ``git.output-too-large``."""
    monkeypatch.setattr(_git_run, "GIT_TIMEOUT_SECONDS", 0.0)
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(_url(repo[0])):
            pass  # pragma: no cover
    assert excinfo.value.code == "git.timeout"
    monkeypatch.setattr(_git_run, "GIT_TIMEOUT_SECONDS", 600.0)
    monkeypatch.setattr(_git_run, "MAX_OUTPUT_BYTES", 10)
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(_url(repo[0], "/tree/main")):
            pass  # pragma: no cover
    assert excinfo.value.code == "git.output-too-large"


def test_the_monorepo_hint_names_projects_and_escapes_names(tmp_path: Path) -> None:
    """Projects below a root with none are listed (sorted, skipped folders
    left out, at most five); a name with a newline cannot add a line."""
    for sub in ("services/b", "services/a", "tools/t", "p/q", "r", "a\nb", "dist/x"):
        (tmp_path / sub).mkdir(parents=True)
        (tmp_path / sub / "setup.py").write_text("", encoding="utf-8")
    hint = subproject_hint(str(tmp_path), whole_repository=True)
    assert "\n" not in hint and "a\\nb" in hint and "dist" not in hint
    assert hint.count(",") == 4 and "and 1 more" in hint
    assert "Give the URL of one of them" in hint
    assert "folder in the URL only" in subproject_hint(str(tmp_path), False)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    assert subproject_hint(str(tmp_path), True) == ""
