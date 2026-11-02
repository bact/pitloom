# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Decide whether a push to ``main`` repeats a run that already passed.

Used by ``.github/actions/skip-duplicate-push``. A merge commit whose tree is
byte-for-byte the tree of its second parent (the PR head) tests nothing new
when that head already has a successful ``pull_request`` run of the same
workflow.

Writes ``skip=true`` or ``skip=false`` to ``$GITHUB_OUTPUT`` and always exits
0. Fail open: any doubt (not a push to ``main``, not a two-parent merge,
trees differ, no green run, a git or API error) gives ``skip=false`` and the
tests run. Nothing from the API is echoed, only its status code and the
exception type, so a ``::`` line cannot reach the runner log.

Usage: ``python scripts/ci/skip_duplicate_push.py WORKFLOW_FILE``
Environment: ``GITHUB_EVENT_NAME``, ``GITHUB_REF``, ``GITHUB_SHA``,
``GITHUB_REPOSITORY``, ``GITHUB_TOKEN``, ``GITHUB_OUTPUT``; optional
``GITHUB_API_URL``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, NamedTuple

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORKFLOW_RE = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")
BRANCH_REF = "refs/heads/main"
API_TIMEOUT = 20

RunGit = Callable[[list[str]], str]
FetchJson = Callable[[str], Any]


class Decision(NamedTuple):
    """The verdict and the reason, for the log."""

    skip: bool
    reason: str


def run_git(args: list[str]) -> str:
    """Run ``git`` and return stdout stripped; raise on a non-zero exit."""
    done = subprocess.run(  # nosec B603 B607
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return done.stdout.strip()


def make_fetch_json(token: str) -> FetchJson:
    """Return a GET-JSON function authenticated with *token*."""

    def fetch(url: str) -> Any:
        if not url.startswith("https://") and not url.startswith("http://127."):
            raise ValueError("refusing a non-HTTPS URL")
        request = urllib.request.Request(  # noqa: S310  # nosec B310
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(  # noqa: S310  # nosec B310
            request, timeout=API_TIMEOUT
        ) as response:
            return json.loads(response.read())

    return fetch


def has_green_run(runs: Any, head_sha: str) -> bool:
    """Whether the API's run list holds a finished, successful PR run."""
    if not isinstance(runs, dict):
        return False
    items = runs.get("workflow_runs")
    if not isinstance(items, list):
        return False
    return any(
        isinstance(run, dict)
        and run.get("head_sha") == head_sha
        and run.get("event") == "pull_request"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        for run in items
    )


def check_git(git: RunGit, sha: str) -> tuple[Decision | None, str]:
    """Return (a "run" verdict, or None) and the second parent's SHA."""
    if git(["rev-parse", "HEAD"]) != sha:
        return Decision(False, "checked-out HEAD is not GITHUB_SHA"), ""
    parts = git(["rev-list", "--parents", "-n", "1", "HEAD"]).split()
    if len(parts) != 3 or not all(SHA_RE.match(p) for p in parts):
        return Decision(False, "not a two-parent merge commit"), ""
    if git(["rev-parse", "HEAD^{tree}"]) != git(["rev-parse", f"{parts[2]}^{{tree}}"]):
        return Decision(False, "merge tree differs from the PR head tree"), ""
    return None, parts[2]


def decide(
    env: Mapping[str, str], workflow: str, git: RunGit, fetch: FetchJson
) -> Decision:
    """Return the verdict for this push. Never raises."""
    try:
        return _decide(env, workflow, git, fetch)
    except urllib.error.HTTPError as exc:
        return Decision(False, f"API error HTTP {exc.code}")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return Decision(False, f"check failed: {type(exc).__name__}")


def _decide(
    env: Mapping[str, str], workflow: str, git: RunGit, fetch: FetchJson
) -> Decision:
    if env.get("GITHUB_EVENT_NAME") != "push":
        return Decision(False, "not a push event")
    if env.get("GITHUB_REF") != BRANCH_REF:
        return Decision(False, "not a push to main")
    sha = env.get("GITHUB_SHA", "")
    repo = env.get("GITHUB_REPOSITORY", "")
    if not SHA_RE.match(sha) or not REPO_RE.match(repo):
        return Decision(False, "unexpected GITHUB_SHA or GITHUB_REPOSITORY")
    if not WORKFLOW_RE.match(workflow):
        return Decision(False, "unexpected workflow file name")
    verdict, head = check_git(git, sha)
    if verdict is not None:
        return verdict
    api = env.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    query = urllib.parse.urlencode(
        {"head_sha": head, "status": "success", "event": "pull_request"}
    )
    url = f"{api}/repos/{repo}/actions/workflows/{workflow}/runs?{query}"
    if not has_green_run(fetch(url), head):
        return Decision(False, "no successful pull_request run for the PR head")
    return Decision(True, f"merge tree equals PR head {head[:12]} that passed")


def main(argv: list[str]) -> int:
    """Entry point; always returns 0."""
    workflow = argv[1] if len(argv) == 2 else ""
    env = os.environ
    decision = decide(
        env, workflow, run_git, make_fetch_json(env.get("GITHUB_TOKEN", ""))
    )
    verdict = "skip" if decision.skip else "run"
    sys.stderr.write(f"INFO: duplicate-push check: {verdict}: {decision.reason}\n")
    out = env.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(f"skip={'true' if decision.skip else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
