# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""Real Git hosting platforms: the URL forms a person pastes are fetched.

These reach live servers, so they are marked ``network`` (skipped when the
network fails, failing under ``PITLOOM_REQUIRE_NETWORK``). A host's transient
5xx answer is retried twice first (``tests/_network_retry.py``). A failure here
means a platform changed how it answers, or a repository moved: the table in
``docs/git-urls.md`` lists what was verified and when.

Only the fetch is run (repository, branch, folder); reading the project is
tested with local servers in ``test_git_http_e2e.py``.
"""

from __future__ import annotations

import logging
import re
from contextlib import ExitStack
from pathlib import Path

import pytest

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import fetch_git_project
from pitloom.extract.remote._git_redirect import PROBE_FAILED_INFO
from pitloom.extract.remote.errors import RemoteSourceError
from tests._network import network_unavailable, skip_on_network_error
from tests._network_retry import retry_on_transient_server_error

pytestmark = pytest.mark.network

# (id, URL, branch or tag named, folder named, a file expected in the folder)
_PLATFORMS = [
    # GitLab. A bare project URL is answered with a redirect to ``.git``.
    (
        "gitlab-com",
        "https://gitlab.com/freedesktop-sdk/mirrors/github/pypa/pyproject-hooks",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "gitlab-com-page",
        "https://gitlab.com/freedesktop-sdk/mirrors/github/pypa/"
        "pyproject-hooks/-/tree/main/src",
        "main",
        "src",
        "pyproject_hooks",
    ),
    # Forgejo and Gitea. The bare URL is served as it is.
    (
        "forgejo-codeberg",
        "https://codeberg.org/kfdm/pyproject-add-url",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "forgejo-codeberg-page",
        "https://codeberg.org/kfdm/pyproject-add-url/src/branch/main",
        "main",
        "",
        "pyproject.toml",
    ),
    (
        "gitea-com-page",
        "https://gitea.com/gitea/tea/src/branch/main/cmd",
        "main",
        "cmd",
        "actions.go",
    ),
    # Forgejo writes a file page like a folder page.
    (
        "forgejo-codeberg-file-page",
        "https://codeberg.org/kfdm/pyproject-add-url/src/branch/main/pyproject.toml",
        "main",
        "",
        "pyproject.toml",
    ),
    (
        "forgejo-codeberg-tag-page",
        "https://codeberg.org/kfdm/pyproject-add-url/src/tag/v0.1.0",
        "v0.1.0",
        "",
        "pyproject.toml",
    ),
    # Gerrit (the bare URL).
    (
        "gerrit-opendev",
        "https://review.opendev.org/openstack/pbr",
        None,
        "",
        "setup.py",
    ),
    # Gitiles, Gerrit's code browser: ``+`` and the ref in full.
    (
        "gitiles-googlesource-page",
        "https://pigweed.googlesource.com/pigweed/pigweed/+/refs/heads/main/pw_cli",
        "main",
        "pw_cli",
        "py",
    ),
    # A Hugging Face Space is a Git repository (the host is not a model).
    (
        "hugging-face-space",
        "https://huggingface.co/spaces/Chuanming/"
        "facebook-fasttext-language-identification",
        None,
        "",
        "app.py",
    ),
    (
        "hugging-face-space-page",
        "https://huggingface.co/spaces/Chuanming/"
        "facebook-fasttext-language-identification/tree/main",
        "main",
        "",
        "app.py",
    ),
    # cgit puts the ref in the query.
    (
        "cgit-kernel-org",
        "https://git.kernel.org/pub/scm/utils/b4/b4.git",
        None,
        "",
        "COPYING",
    ),
    (
        "cgit-kernel-org-page",
        "https://git.kernel.org/pub/scm/utils/b4/b4.git/tree/src/b4?h=master",
        "master",
        "src/b4",
        "__init__.py",
    ),
    # Azure DevOps rejects the blob filter, and puts the ref in the query.
    (
        "azure-devops",
        "https://dev.azure.com/mseng/PipelineTools/_git/PipelineTools",
        None,
        "",
        "readme.md",
    ),
    (
        "azure-devops-page",
        "https://dev.azure.com/mseng/PipelineTools/_git/PipelineTools"
        "?path=/templates&version=GBmaster",
        "master",
        "templates",
        "cluster-control-job.yml",
    ),
    # Bitbucket Cloud. A file page is written like a folder page.
    (
        "bitbucket",
        "https://bitbucket.org/zzzeek/sqlalchemy",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "bitbucket-src-page",
        "https://bitbucket.org/zzzeek/sqlalchemy/src/main/lib/sqlalchemy",
        "main",
        "lib/sqlalchemy",
        "__init__.py",
    ),
    # SourceHut. ``item`` stands for a folder and a file alike.
    ("sourcehut", "https://git.sr.ht/~sircmpwn/scm.sr.ht", None, "", "setup.py"),
    # GitHub.
    ("github", "https://github.com/pypa/pyproject-hooks", None, "", "pyproject.toml"),
    (
        "github-page",
        "https://github.com/pypa/pyproject-hooks/tree/main/src",
        "main",
        "src",
        "pyproject_hooks",
    ),
]


#: A bound for a live fetch (the largest, SQLAlchemy on Bitbucket, is about
#: 150 MB) so a server that ignores the blob filter cannot fill a CI disk.
_LIVE_CAP = 400 * 1024 * 1024

#: What git reports for a redirect it was told not to follow.
_BARE_REDIRECT = re.compile(r"returned error: 30[1278]\b")


@pytest.mark.parametrize(
    ("url", "ref", "folder", "expected"),
    [pytest.param(u, r, f, e, id=i) for i, u, r, f, e in _PLATFORMS],
)
def test_a_platforms_url_is_fetched(
    url: str,
    ref: str | None,
    folder: str,
    expected: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The branch and folder the URL names are checked out, with a redirect
    followed where the platform sends one."""
    caplog.set_level(logging.INFO, logger="pitloom")
    try:
        with skip_on_network_error(), ExitStack() as stack:
            # Only entering is retried, after a transient 5xx from the host;
            # a failed attempt has removed its own temporary directory.
            checkout = retry_on_transient_server_error(
                lambda: stack.enter_context(
                    fetch_git_project(
                        url, policy=RemoteFetchPolicy(max_bytes=_LIVE_CAP)
                    )
                )
            )
            assert checkout.ref == ref and checkout.subdir == folder
            assert (Path(checkout.folder) / expected).exists()
            assert len(checkout.commit) in {40, 64}
    except RemoteSourceError as exc:
        # A host too slow to answer the redirect probe leaves Pitloom asking
        # git directly, and git follows no redirect: it reports a bare 301 or
        # 302. That is the network, not the platform handling under test.
        probe_failed = any(r.msg == PROBE_FAILED_INFO for r in caplog.records)
        if probe_failed and _BARE_REDIRECT.search(str(exc)):
            network_unavailable("the redirect probe failed (slow or unreachable host)")
        raise
