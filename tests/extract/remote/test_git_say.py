# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a Git URL fetch decides and says: how the URL was read (one line, or
two notes), the symbolic links removed, a file page that names a folder and a
folder page that names a file, the retry of a page URL whose repository part
is no repository, the retry without the blob filter, and the git command
echo. Each line is the catalogue's, after ``Git source: ``, with the URL
given in front and its code at the end (trusted as a script reads it).

The server is a local smart-HTTP one (`loopback`).

See also: tests/extract/remote/test_git_say_errors.py (what stops a fetch),
tests/extract/remote/test_git_say_redirect.py (the redirect walk) and
tests/messages/test_git.py (the lines themselves).
"""

from __future__ import annotations

import logging
import os
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote._git_say import drop_outside_links, say_resolution
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import fetch_git_project
from pitloom.extract.remote.git_url import GitPage, GitTarget
from pitloom.messages import GIT_PREFIX, Line, Message, trusted_message
from pitloom.messages.git import GIT_FILTER_UNUSABLE, GIT_LINK_UNSAFE
from pitloom.messages.network import (
    QUERY_LINE,
    QUERY_NO_EFFECT,
    REDIRECT_LINE,
    URL_MOVED,
    VERSION_IGNORED_LINE,
)
from pitloom.messages.targets import (
    GIT_PAGE_DIR_LINE,
    GIT_PAGE_FILE_LINE,
    GIT_PAGE_FOLDER_LINE,
    GIT_PAGE_LINE,
    GIT_PAGE_NOT_REPO_LINE,
    GIT_PAGE_REF_FOLDER_LINE,
    GIT_PAGE_REF_LINE,
    TARGET_AMBIGUOUS_GIT_PAGE,
)
from tests._git_http_server import serve_git
from tests._git_say_repos import (
    SERVER_MARKS,
    Repos,
    build_repos,
    printed,
    trusted_codes,
)

pytestmark = [*SERVER_MARKS, pytest.mark.platform]

_PAGE = TARGET_AMBIGUOUS_GIT_PAGE
#: The codes of the lines that say how a URL was read or moved.
_READ = ("target-ambiguous/git-page", "query-no-effect", "url-moved")


@pytest.fixture(name="served", scope="module")
def _served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Repos]]:
    root = tmp_path_factory.mktemp("srv")
    repos = build_repos(root)
    with serve_git(root, gitlab_style=True) as base:
        yield base, repos


def _said(message: Message, line: Line, **values: object) -> str:
    """*line* of *message* as printed: after ``Git source: ``, coded."""
    return f"{line.level}: {GIT_PREFIX}{line.render(values)} [{message.code}]"


def _fetch(url: str, caplog: pytest.LogCaptureFixture, *codes: str) -> list[str]:
    """Fetch *url*; the coded lines it said (of *codes*, else :data:`_READ`)."""
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with fetch_git_project(url):
            pass
    return printed(caplog, *(codes or _READ))


# -- how the URL was read (row 14) ---------------------------------------------

_Said = Callable[[str, str, str], list[str]]  # (url, clone url, commit) -> lines


def _read_as(*shapes: tuple[Message, Line, dict[str, str]]) -> _Said:
    """The lines of *shapes*, each with the URL given and the clone URL."""

    def lines(url: str, repo: str, sha: str) -> list[str]:
        said = []
        for message, line, extra in shapes:
            values = {"url": url, "target": repo, **extra}
            named = {
                k: v.format(sha=sha) for k, v in values.items() if k in line.fields
            }
            said.append(_said(message, line, **named))
        return said

    return lines


_ONLY_QUERY: tuple[Message, Line, dict[str, str]] = (QUERY_NO_EFFECT, QUERY_LINE, {})
_BRANCH = {"ref_kind": "branch", "ref": "feat/x"}


@pytest.mark.parametrize(
    ("page", "expect"),
    [
        ("/g/p.git", _read_as()),
        ("/g/p.git/", _read_as((_PAGE, GIT_PAGE_LINE, {}))),
        ("/g/p.git/-/tree/feat/x", _read_as((_PAGE, GIT_PAGE_REF_LINE, _BRANCH))),
        (
            "/g/p.git/-/tree/v1",
            _read_as((_PAGE, GIT_PAGE_REF_LINE, {"ref_kind": "tag", "ref": "v1"})),
        ),
        (
            "/g/p.git/-/tree/{sha}",
            _read_as(
                (_PAGE, GIT_PAGE_REF_LINE, {"ref_kind": "commit", "ref": "{sha}"})
            ),
        ),
        (
            "/g/p.git/-/tree/main/svc/a",
            _read_as(
                (
                    _PAGE,
                    GIT_PAGE_REF_FOLDER_LINE,
                    {"ref_kind": "branch", "ref": "main", "path": "svc/a"},
                )
            ),
        ),
        ("/g/p.git?x=1#frag", _read_as(_ONLY_QUERY)),
    ],
    ids=["clone-url", "slash", "branch", "tag", "commit", "ref-folder", "cut-query"],
)
def test_each_way_a_url_is_read_is_one_line_or_none(
    served: tuple[str, Repos],
    caplog: pytest.LogCaptureFixture,
    page: str,
    expect: _Said,
) -> None:
    """A clone URL equal to the one given says nothing; a trailing slash
    alone is shape 1; a cut query says only that; each ref kind and a folder
    name themselves."""
    base, repos = served
    sha = repos.main_commit
    said = _fetch(base + page.format(sha=sha), caplog)
    assert said == expect(base + page.format(sha=sha), base + "/g/p.git", sha)
    assert len(trusted_codes(said)) == len(said)


def test_a_folder_in_the_query_and_a_version_that_names_nothing(
    served: tuple[str, Repos], caplog: pytest.LogCaptureFixture
) -> None:
    """Azure DevOps' ``path`` is a folder; its ``version`` of another kind is
    said as ignored, apart: the folder line, then the version note; a
    ``version`` of a branch is the ref and the folder in one line."""
    base, _ = served
    repo = base + "/g/_git/p.git"
    moved = _said(URL_MOVED, REDIRECT_LINE, url=base + "/g/_git/p", target=repo)
    folder = {"target": repo, "path": "svc/a"}
    for query, tail in (
        ("path=/svc/a", []),
        ("path=/svc/a&version=Xmain", [(QUERY_NO_EFFECT, VERSION_IGNORED_LINE)]),
    ):
        url = f"{base}/g/_git/p?{query}"
        wanted = [moved, _said(_PAGE, GIT_PAGE_FOLDER_LINE, url=url, **folder)]
        wanted += [_said(m, ln, url=url) for m, ln in tail]
        assert _fetch(url, caplog) == wanted
    url = f"{base}/g/_git/p?path=/svc/a&version=GBmain"
    said = _fetch(url, caplog)
    assert said[1] == _said(
        _PAGE,
        GIT_PAGE_REF_FOLDER_LINE,
        url=url,
        **folder,
        ref_kind="branch",
        ref="main",
    )


def test_a_cut_query_and_an_ignored_version_are_both_said(
    served: tuple[str, Repos], caplog: pytest.LogCaptureFixture
) -> None:
    """No URL gives both (a query-style page cuts nothing): the notes are
    independent, in order, each its own line."""
    base, _ = served
    url = base + "/g/p.git?v=1"
    page = GitPage(base + "/g/p.git", cut=True, version_ignored=True)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        say_resolution(url, base + "/g/p.git", GitTarget(), page)
    assert printed(caplog) == [
        _said(QUERY_NO_EFFECT, QUERY_LINE, url=url),
        _said(QUERY_NO_EFFECT, VERSION_IGNORED_LINE, url=url),
    ]


def test_a_cut_query_is_said_after_a_ref_line(caplog: pytest.LogCaptureFixture) -> None:
    """The note of a cut query does not depend on what else was said."""
    repo = "https://h.example/o/r"
    url = repo + "/tree/main?x=1"
    page = GitPage(repo, ("main",), cut=True)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        say_resolution(url, repo, GitTarget(ref="main"), page)
    ref = {"ref_kind": "branch", "ref": "main"}
    assert printed(caplog) == [
        _said(_PAGE, GIT_PAGE_REF_LINE, url=url, target=repo, **ref),
        _said(QUERY_NO_EFFECT, QUERY_LINE, url=url),
    ]


# -- links (row 17) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "number", "gone", "kept"),
    [
        ("g/links-out", 1, ["leak"], []),
        ("g/links-git", 1, ["into-git"], []),
        ("g/links-dir", 1, ["to-folder"], []),
        ("g/links-two", 2, ["leak", "to-folder"], []),
        ("g/links-kept", 0, [], ["ok"]),
        ("g/p", 0, [], []),
    ],
    ids=["out", "into-git", "to-folder", "two", "kept-only", "none"],
)
def test_links_that_lead_out_are_removed_and_counted(
    served: tuple[str, Repos],
    caplog: pytest.LogCaptureFixture,
    name: str,
    number: int,
    gone: list[str],
    kept: list[str],
) -> None:
    """Zero links, no line; one or two, one line with the number. A link to
    a file of the repository stays."""
    base, _ = served
    url = f"{base}/{name}.git"
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with fetch_git_project(url) as checkout:
            folder = Path(checkout.folder)
            assert [os.path.lexists(folder / n) for n in gone] == [False] * len(gone)
            assert all((folder / n).is_symlink() for n in kept)
    expected = [
        _said(GIT_LINK_UNSAFE, GIT_LINK_UNSAFE.lines[0], url=url, number=number)
    ]
    assert printed(caplog, "git-link-unsafe") == (expected if number else [])


# -- a file page that names a folder, a folder page that names a file ----------


@pytest.mark.parametrize(
    ("page", "want"),
    [
        (
            "/g/p.git/-/tree/main/README.md",
            (GIT_PAGE_FILE_LINE, "README.md", "", "README.md"),
        ),
        ("/g/p.git/-/blob/main/svc", (GIT_PAGE_DIR_LINE, "svc", "svc", "")),
        ("/g/p.git/-/blob/main/svc/a/README.md", (None, "", "svc/a", "README.md")),
        ("/g/p.git/-/tree/main/svc/a", (None, "", "svc/a", "")),
    ],
    ids=["tree-names-a-file", "blob-names-a-folder", "blob-file", "tree-folder"],
)
def test_a_page_of_the_other_kind_is_said_once(
    served: tuple[str, Repos],
    caplog: pytest.LogCaptureFixture,
    page: str,
    want: tuple[Line | None, str, str, str],
) -> None:
    """*want*: the line, the path it names, the folder read and the file."""
    line, path, subdir, file = want
    base, _ = served
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with fetch_git_project(base + page) as checkout:
            assert (checkout.subdir, checkout.file) == (subdir, file)
    said = printed(caplog, "target-ambiguous/git-page")
    assert len(said) == (2 if line else 1)
    if line is not None:
        assert said[-1] == _said(_PAGE, line, url=base + page, path=path)
        assert trusted_message(said[-1]) is _PAGE


def test_a_blob_page_whose_folder_is_a_file_is_refused_unsaid(
    served: tuple[str, Repos], caplog: pytest.LogCaptureFixture
) -> None:
    """``target.file`` is set (``x``), so the file ``README.md`` is not
    taken for the folder: ``git.path-not-found``, and neither line 18 nor 19."""
    base, _ = served
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            with fetch_git_project(base + "/g/p.git/-/blob/main/README.md/x"):
                pass
    assert raised.value.code == "git.path-not-found"
    assert all(" is a " not in line for line in printed(caplog))


# -- a page URL whose repository part is no repository -----------------------------


def test_a_group_called_src_is_retried_as_a_whole_repository(
    served: tuple[str, Repos], caplog: pytest.LogCaptureFixture
) -> None:
    """``a/b/src/p``: ``a/b`` is no repository (``not found``, code
    ``git.clone-failed``), so the whole URL is one: one line names both."""
    base, _ = served
    url = base + "/a/b/src/p"
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with fetch_git_project(url) as checkout:
            assert checkout.repo_url == url + ".git"
    said = printed(caplog, "target-ambiguous/git-page")
    assert len(said) == 1
    line = said[0]
    assert line == _said(_PAGE, GIT_PAGE_NOT_REPO_LINE, url=base + "/a/b", target=url)
    assert trusted_message(line) is _PAGE


def _count(caplog: pytest.LogCaptureFixture, command: str) -> int:
    """How many times the echo says it ran ``git <command>``."""
    return sum(
        r.getMessage().startswith(f"{GIT_PREFIX}$ ")
        and f" {command} " in r.getMessage()
        for r in caplog.records
    )


def test_no_retry_when_only_the_code_is_clone_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``A and B`` of ``_not_a_repository``, A alone: the failure is a
    ``git.clone-failed`` whose text is no 404 (a refused connection)."""
    with socket.socket() as closed:  # a port nothing listens on
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            with fetch_git_project(f"http://127.0.0.1:{port}/a/b/src/p"):
                pass
    assert raised.value.code == "git.clone-failed"
    assert "not found" not in str(raised.value).lower()
    assert not printed(caplog, "target-ambiguous/git-page")
    assert _count(caplog, "ls-remote") == 1


def test_no_retry_when_only_the_text_says_not_found(
    served: tuple[str, Repos],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B alone: the text says ``not found`` but the code is another's."""
    base, _ = served
    seen: list[str] = []

    def run(_self: GitRunner, _args: list[str], what: str, **_kw: Any) -> str:
        seen.append(what)
        raise RemoteSourceError("git.timeout", "fatal: repository 'x' not found")

    monkeypatch.setattr(GitRunner, "run", run)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            with fetch_git_project(base + "/a/b/src/p"):
                pass
    assert raised.value.code == "git.timeout"
    assert seen == ["ls-remote"]
    assert not printed(caplog, "target-ambiguous/git-page")


def test_no_retry_when_the_repository_part_is_the_whole_url(
    served: tuple[str, Repos], caplog: pytest.LogCaptureFixture
) -> None:
    """Both true, but ``page.plain_url == page.repo_url`` (a query-style
    page names the repository alone): no second try, no line."""
    base, _ = served
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            with fetch_git_project(base + "/g/_git/missing?path=/x"):
                pass
    assert raised.value.code == "git.clone-failed"
    assert "not found" in str(raised.value)
    assert not printed(caplog, "target-ambiguous/git-page")
    assert _count(caplog, "ls-remote") == 1


# -- the retry without the blob filter ---------------------------------------------


def _filter_refused(
    monkeypatch: pytest.MonkeyPatch, code: str, text: str
) -> list[list[str]]:
    """Make the first filtered ``clone`` or ``fetch`` fail with *code* and
    *text*; the calls the runner was asked for, in order."""
    real = GitRunner.run
    calls: list[list[str]] = []

    def run(self: GitRunner, args: list[str], what: str, **kw: Any) -> str:
        calls.append(args)
        if what in {"clone", "fetch"} and any(a.startswith("--filter=") for a in args):
            raise RemoteSourceError(code, text)
        return real(self, args, what, **kw)

    monkeypatch.setattr(GitRunner, "run", run)
    return calls


@pytest.mark.parametrize(
    "page", ["/g/p.git", "/g/p.git/-/tree/v1"], ids=["clone", "tag-fetch"]
)
def test_a_server_that_rejects_the_filter_is_asked_again_without_it(
    served: tuple[str, Repos],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    page: str,
) -> None:
    base, _ = served
    calls = _filter_refused(
        monkeypatch, "git.clone-failed", "fatal: unable to access: HTTP 400"
    )
    said = _fetch(base + page, caplog, "git-filter-unusable")
    line = GIT_FILTER_UNUSABLE.lines[0]
    assert said == [_said(GIT_FILTER_UNUSABLE, line, url=base + "/g/p.git")]
    assert trusted_message(said[0]) is GIT_FILTER_UNUSABLE
    filtered = [c for c in calls if any(a.startswith("--filter=") for a in c)]
    assert len(filtered) == 1
    retry = calls[calls.index(filtered[0]) + 1]
    assert not any(a.startswith("--filter=") for a in retry)
    assert ("--no-filter" in retry) == page.endswith("/v1")


@pytest.mark.parametrize(
    ("code", "text"),
    [
        ("git.clone-failed", "fatal: repository gone"),
        ("git.timeout", "fatal: HTTP 400"),
    ],
    ids=["code-only", "text-only"],
)
def test_the_filter_is_kept_unless_both_the_code_and_the_text_say_400(
    served: tuple[str, Repos],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    text: str,
) -> None:
    """``A or B`` -> ``A and B``: one side alone raises, with no second try."""
    base, _ = served
    calls = _filter_refused(monkeypatch, code, text)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            with fetch_git_project(base + "/g/p.git"):
                pass
    assert raised.value.code == code
    assert not printed(caplog, "git-filter-unusable")
    assert [c for c in calls if "clone" in c] == calls[-1:]


def test_a_link_in_a_nested_git_directory_is_examined(tmp_path: Path) -> None:
    """Only the checkout's own ``.git`` is skipped: a ``.git`` folder further
    down is walked, and a link of it that leads out is dropped."""
    outside = tmp_path / "host-file"
    outside.write_text("secret", encoding="utf-8")
    work = tmp_path / "work"
    (work / "sub" / ".git").mkdir(parents=True)
    leak = work / "sub" / ".git" / "leak"
    leak.symlink_to(outside)
    drop_outside_links(str(work), "https://h.example/r.git")
    assert not os.path.lexists(leak)
    assert outside.read_text(encoding="utf-8") == "secret"
