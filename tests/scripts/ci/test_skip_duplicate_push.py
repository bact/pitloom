# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/ci/skip_duplicate_push.py`` (the push-to-main skip)."""

from __future__ import annotations

import json
import subprocess
import threading
import urllib.error
from collections.abc import Callable
from email.message import Message
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests._loopback_server import LoopbackHTTPServer

REPO = "owner/repo"


@pytest.fixture(name="mod")
def mod_fixture(load_script: Callable[[str], ModuleType]) -> ModuleType:
    """The script module."""
    return load_script("ci/skip_duplicate_push")


def git(repo: Path, *args: str) -> str:
    """Run git in *repo* with a fixed identity and clock."""
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.org",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        "HOME": str(repo),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return done.stdout.strip()


def commit(repo: Path, name: str, text: str) -> str:
    """Write *name*, commit it, return the SHA."""
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    """A repo on ``main`` with one commit."""
    path = tmp_path / "r"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    commit(path, "a.txt", "a")
    return path


def merge(repo: Path, branch_file: str, main_file: str | None) -> tuple[str, str]:
    """Merge a one-file branch into main (``--no-ff``); return (merge, head).

    With *main_file*, main moves first, so the merge tree differs from the
    branch tree.
    """
    git(repo, "checkout", "-q", "-b", "feature")
    head = commit(repo, branch_file, "x")
    git(repo, "checkout", "-q", "main")
    if main_file:
        commit(repo, main_file, "m")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge", "feature")
    return git(repo, "rev-parse", "HEAD"), head


def make_env(sha: str, **over: str) -> dict[str, str]:
    """The environment of a push to main."""
    env = {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": sha,
        "GITHUB_REPOSITORY": REPO,
    }
    env.update(over)
    return env


def pull_run(head: str, number: Any = 1, base: str | None = "main", **over: Any) -> Any:
    """A finished, successful pull_request run of *head* for a PR on *base*.

    ``base=None`` gives the empty ``pull_requests`` list of a fork PR.
    """
    run: dict[str, Any] = {
        "head_sha": head,
        "event": "pull_request",
        "status": "completed",
        "conclusion": "success",
        "run_number": number,
        "created_at": f"2026-01-01T00:00:{int(number or 0):02d}Z",
        "pull_requests": [] if base is None else [{"base": {"ref": base}}],
    }
    run.update(over)
    return run


def green(head: str, **over: Any) -> dict[str, Any]:
    """An API answer with one successful pull_request run of *head*."""
    return {"total_count": 1, "workflow_runs": [pull_run(head, **over)]}


def decide(
    mod: ModuleType, repo: Path, env: dict[str, str], answer: Any
) -> tuple[bool, str, list[str]]:
    """Run ``decide`` in *repo* with a fixture API; return skip, reason, urls."""
    urls: list[str] = []

    def run_git(args: list[str]) -> str:
        return git(repo, *args)

    def fetch(url: str) -> Any:
        urls.append(url)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    verdict = mod.decide(env, "test.yml", run_git, fetch)
    return verdict.skip, verdict.reason, urls


def test_equal_tree_and_green_head_skips(mod: ModuleType, repo: Path) -> None:
    merged, head = merge(repo, "b.txt", None)
    skip, _, urls = decide(mod, repo, make_env(merged), green(head))
    assert skip
    assert len(urls) == 1
    assert f"/repos/{REPO}/actions/workflows/test.yml/runs?" in urls[0]
    assert f"head_sha={head}" in urls[0]
    assert "status=" not in urls[0]  # an old green run must not hide a newer red one


def test_tree_differs_runs_without_asking_the_api(mod: ModuleType, repo: Path) -> None:
    merged, head = merge(repo, "b.txt", "c.txt")
    skip, reason, urls = decide(mod, repo, make_env(merged), green(head))
    assert not skip
    assert "tree differs" in reason
    assert not urls


@pytest.mark.parametrize(
    "answer",
    [
        {"workflow_runs": []},
        {},
        [],
        None,
        {"workflow_runs": "x"},
        {"workflow_runs": [None, 3]},
        green("0" * 40),
        green("HEAD", conclusion="failure"),
        green("HEAD", conclusion=None),
        green("HEAD", status="in_progress"),
        green("HEAD", event="push"),
    ],
    ids=[
        "empty",
        "no-key",
        "list",
        "none",
        "bad-type",
        "bad-items",
        "other-sha",
        "failure",
        "no-conclusion",
        "in-progress",
        "push-event",
    ],
)
def test_no_usable_green_run_runs(mod: ModuleType, repo: Path, answer: Any) -> None:
    merged, head = merge(repo, "b.txt", None)
    if isinstance(answer, dict) and answer.get("workflow_runs", 0):
        runs = answer["workflow_runs"]
        if isinstance(runs[0], dict) and runs[0]["head_sha"] == "HEAD":
            runs[0]["head_sha"] = head
    skip, reason, urls = decide(mod, repo, make_env(merged), answer)
    assert not skip
    assert urls
    assert "no green newest" in reason


def spec(**fields: Any) -> dict[str, Any]:
    """The fields a test run differs in, for ``pull_run``."""
    return fields


def answer_of(*runs: dict[str, Any]) -> dict[str, Any]:
    """An API answer holding *runs* (newest first, as GitHub lists them)."""
    return {"total_count": len(runs), "workflow_runs": list(runs)}


@pytest.mark.parametrize(
    ("runs", "skip"),
    [
        # An older green run on develop, the newest run (main) red.
        ([spec(number=1, base="develop"), spec(number=2, conclusion="failure")], False),
        # Same, but the old green run was also for main.
        ([spec(number=1), spec(number=2, conclusion="failure")], False),
        # The newest run is still going.
        (
            [spec(number=1), spec(number=2, status="in_progress", conclusion=None)],
            False,
        ),
        # An older red run, the newest green on main.
        ([spec(number=1, conclusion="failure"), spec(number=2)], True),
        # Newest green run, but for develop.
        ([spec(number=1), spec(number=2, base="develop")], False),
        # A fork PR lists no pull requests.
        ([spec(number=1, base=None)], False),
        ([spec(number=1, base="develop"), spec(number=2, base=None)], False),
        # One run, several PRs, one of them not against main.
        (
            [
                spec(
                    number=1,
                    pull_requests=[
                        {"base": {"ref": "main"}},
                        {"base": {"ref": "develop"}},
                    ],
                )
            ],
            False,
        ),
        # Number order, not list order, decides.
        ([spec(number=2), spec(number=1, conclusion="failure")], True),
        ([spec(number=2, conclusion="failure"), spec(number=1)], False),
        # Equal numbers: the later creation time wins ...
        (
            [
                spec(number=3, created_at="2026-01-02T00:00:00Z"),
                spec(number=3, created_at="2026-01-01T00:00:00Z", conclusion="failure"),
            ],
            True,
        ),
        (
            [
                spec(number=3, created_at="2026-01-01T00:00:00Z"),
                spec(number=3, created_at="2026-01-02T00:00:00Z", conclusion="failure"),
            ],
            False,
        ),
        # ... and a full tie with a non-green run runs the tests.
        (
            [
                spec(number=3, created_at="z"),
                spec(number=3, created_at="z", conclusion="failure"),
            ],
            False,
        ),
        ([spec(number=3, created_at="z"), spec(number=3, created_at="z")], True),
        # No usable number: unknown order.
        ([spec(number=1), spec(number="2")], False),
        ([spec(number=1), spec(number=True)], False),
        ([spec(number=1), spec(number=None)], False),
        # pull_requests of the wrong shape.
        ([spec(number=1, pull_requests=None)], False),
        ([spec(number=1, pull_requests=["main"])], False),
        ([spec(number=1, pull_requests=[{"base": "main"}])], False),
    ],
    ids=[
        "old-green-develop-newest-red-main",
        "old-green-main-newest-red",
        "newest-in-progress",
        "old-red-newest-green",
        "newest-green-develop",
        "fork-pr-empty-list",
        "fork-pr-newest",
        "one-pr-not-main",
        "number-beats-list-order",
        "number-beats-list-order-red",
        "tie-later-created-wins",
        "tie-later-created-red",
        "full-tie-with-red",
        "full-tie-both-green",
        "number-str",
        "number-bool",
        "number-none",
        "pulls-none",
        "pulls-str",
        "base-str",
    ],
)
def test_newest_run_must_be_green_on_main(
    mod: ModuleType, repo: Path, runs: list[dict[str, Any]], skip: bool
) -> None:
    merged, head = merge(repo, "b.txt", None)
    answer = answer_of(*(pull_run(head, **run) for run in runs))
    got, _, urls = decide(mod, repo, make_env(merged), answer)
    assert got is skip
    assert len(urls) == 1


def test_other_head_and_event_runs_do_not_count(mod: ModuleType, repo: Path) -> None:
    merged, head = merge(repo, "b.txt", None)
    # A newer red run of another SHA or of a push event is not this head's.
    answer = answer_of(
        pull_run("0" * 40, number=9, conclusion="failure"),
        pull_run(head, number=8, conclusion="failure", event="push"),
        pull_run(head, number=1),
    )
    assert decide(mod, repo, make_env(merged), answer)[0]


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.HTTPError(
            "u",
            403,
            "x\n::error::boom",
            Message(),
            None,
        ),
        urllib.error.URLError("down"),
        TimeoutError("slow"),
        json.JSONDecodeError("bad", "", 0),
    ],
    ids=["http-403", "url-error", "timeout", "bad-json"],
)
def test_api_error_runs_and_echoes_no_server_text(
    mod: ModuleType, repo: Path, error: BaseException
) -> None:
    merged, _ = merge(repo, "b.txt", None)
    skip, reason, _ = decide(mod, repo, make_env(merged), error)
    assert not skip
    assert "::" not in reason
    assert "\n" not in reason


def test_non_merge_commit_runs(mod: ModuleType, repo: Path) -> None:
    sha = commit(repo, "b.txt", "x")
    skip, reason, urls = decide(mod, repo, make_env(sha), green(sha))
    assert not skip
    assert "two-parent" in reason
    assert not urls


def test_octopus_merge_runs(mod: ModuleType, repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "f1")
    commit(repo, "f1.txt", "1")
    git(repo, "checkout", "-q", "main")
    git(repo, "checkout", "-q", "-b", "f2")
    commit(repo, "f1.txt", "1")  # the same tree as f1 ...
    git(repo, "commit", "-q", "--amend", "-m", "other")  # ... another commit
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "oct", "f1", "f2")
    sha = git(repo, "rev-parse", "HEAD")
    head = git(repo, "rev-parse", "HEAD^2")
    # Without the parent-count check this would pass the tree test.
    assert git(repo, "rev-parse", "HEAD^{tree}") == git(repo, "rev-parse", "f1^{tree}")
    skip, reason, _ = decide(mod, repo, make_env(sha), green(head))
    assert not skip
    assert "two-parent" in reason


@pytest.mark.parametrize(
    "over",
    [
        {"GITHUB_REF": "refs/tags/v1.0.0"},
        {"GITHUB_REF": "refs/heads/develop"},
        {"GITHUB_REF": "refs/heads/main2"},
        {"GITHUB_REF": "refs/pull/7/merge"},
        {"GITHUB_EVENT_NAME": "pull_request"},
        {"GITHUB_EVENT_NAME": "workflow_dispatch"},
        {"GITHUB_EVENT_NAME": "schedule"},
        {"GITHUB_EVENT_NAME": "release"},
        {"GITHUB_EVENT_NAME": ""},
        {"GITHUB_REPOSITORY": "no-slash"},
        {"GITHUB_REPOSITORY": "a/b?x=1"},
    ],
    ids=lambda o: "-".join(o.values()).replace("/", "_") or "empty",
)
def test_other_events_and_refs_run(
    mod: ModuleType, repo: Path, over: dict[str, str]
) -> None:
    merged, head = merge(repo, "b.txt", None)
    skip, _, urls = decide(mod, repo, make_env(merged, **over), green(head))
    assert not skip
    assert not urls


def test_checked_out_head_must_be_the_pushed_sha(mod: ModuleType, repo: Path) -> None:
    merged, head = merge(repo, "b.txt", None)
    skip, reason, _ = decide(mod, repo, make_env(head), green(head))
    assert not skip
    assert "GITHUB_SHA" in reason
    assert merged != head


@pytest.mark.parametrize("workflow", ["", "../x.yml", "test.yml?x", "test"])
def test_odd_workflow_name_runs(mod: ModuleType, repo: Path, workflow: str) -> None:
    merged, head = merge(repo, "b.txt", None)
    verdict = mod.decide(
        make_env(merged), workflow, lambda a: git(repo, *a), lambda u: green(head)
    )
    assert not verdict.skip


def test_git_failure_runs(mod: ModuleType) -> None:
    def broken(args: list[str]) -> str:
        raise subprocess.CalledProcessError(128, ["git", *args])

    verdict = mod.decide(make_env("a" * 40), "test.yml", broken, lambda u: {})
    assert not verdict.skip
    assert "CalledProcessError" in verdict.reason


def test_main_writes_output_and_exits_zero(
    mod: ModuleType,
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    merged, head = merge(repo, "b.txt", None)
    out = tmp_path / "out.txt"
    for key, value in make_env(merged, GITHUB_OUTPUT=str(out)).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(mod, "run_git", lambda a: git(repo, *a))
    monkeypatch.setattr(mod, "make_fetch_json", lambda t: lambda u: green(head))
    assert mod.main(["x", "test.yml"]) == 0
    assert out.read_text(encoding="utf-8") == "skip=true\n"
    monkeypatch.setattr(mod, "make_fetch_json", lambda t: lambda u: {})
    assert mod.main(["x", "test.yml"]) == 0
    assert out.read_text(encoding="utf-8") == "skip=true\nskip=false\n"
    assert mod.main(["x"]) == 0
    assert out.read_text(encoding="utf-8").endswith("skip=false\n")


@pytest.mark.loopback
def test_fetch_json_sends_the_token_and_parses(
    mod: ModuleType,
) -> None:
    seen: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        """Answer one GET with a JSON body."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization", "")
            body = b'{"workflow_runs": []}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # pylint: disable-next=redefined-builtin
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Stay quiet."""

    with LoopbackHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/x?y=1"
        assert mod.make_fetch_json("tok")(url) == {"workflow_runs": []}
        thread.join(10)
    assert seen == {"path": "/x?y=1", "auth": "Bearer tok"}


def test_fetch_json_refuses_plain_http_to_other_hosts(mod: ModuleType) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        mod.make_fetch_json("tok")("http://example.org/x")
