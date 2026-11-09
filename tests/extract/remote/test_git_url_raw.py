# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A pasted ``raw`` file page of a Git host (GitHub, GitLab, Gitea, Forgejo,
Codeberg, Bitbucket) names its repository, branch and file like a ``blob``
page does, and a path that leaves the checkout is refused.

See also: :mod:`tests.extract.remote.test_git_url` (the other page forms) and
:mod:`tests.extract.remote.test_git_url_encoded` (encoded slashes).
"""

from __future__ import annotations

import pytest

from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git_url import parse_git_page

# (id, page URL, repository URL, segments after the marker, is a file page)
_RAW_PAGES = [
    (
        "github-raw",
        "https://github.com/O/R/raw/main/m.keras",
        "https://github.com/O/R",
        ("main", "m.keras"),
        True,
    ),
    (
        "github-raw-nested",
        "https://github.com/O/R/raw/main/sub/dir/m.keras",
        "https://github.com/O/R",
        ("main", "sub", "dir", "m.keras"),
        True,
    ),
    (
        "gitlab-raw",
        "https://gitlab.com/g/p/-/raw/main/m.keras?ref_type=heads",
        "https://gitlab.com/g/p",
        ("main", "m.keras"),
        True,
    ),
    (
        "gitea-raw-branch",
        "https://codeberg.org/o/r/raw/branch/main/sub/m.onnx",
        "https://codeberg.org/o/r",
        ("main", "sub", "m.onnx"),
        True,
    ),
    (
        "gitea-raw-tag",
        "https://codeberg.org/o/r/raw/tag/v1/m.onnx",
        "https://codeberg.org/o/r",
        ("v1", "m.onnx"),
        True,
    ),
    (
        "gitea-raw-commit",
        f"https://codeberg.org/o/r/raw/commit/{'a' * 40}/m.onnx",
        "https://codeberg.org/o/r",
        ("a" * 40, "m.onnx"),
        True,
    ),
    (
        "bitbucket-raw",
        "https://bitbucket.org/o/r/raw/main/m",
        "https://bitbucket.org/o/r",
        ("main", "m"),
        True,
    ),
    (
        "gitea-raw-stray-query",
        "https://codeberg.org/o/r/raw/branch/main/m.onnx?h=x",
        "https://codeberg.org/o/r",
        ("main", "m.onnx"),
        True,
    ),
]


@pytest.mark.parametrize(
    ("url", "repo", "rest", "is_file"),
    [pytest.param(u, r, s, f, id=i) for i, u, r, s, f in _RAW_PAGES],
)
def test_a_raw_page_url_names_its_repository(
    url: str, repo: str, rest: tuple[str, ...], is_file: bool
) -> None:
    """The repository is what is before the ``raw`` marker; the branch and
    file are what is after it."""
    page = parse_git_page(url)
    assert (page.repo_url, page.rest, page.is_file) == (repo, rest, is_file)


@pytest.mark.parametrize("path", ["a/../b", "a%5Cb"])
@pytest.mark.parametrize("marker", ["raw", "-/raw", "raw/branch"])
def test_a_raw_path_that_leaves_the_checkout_is_refused(marker: str, path: str) -> None:
    """A raw-file page is checked like a ``blob`` one."""
    with pytest.raises(RemoteSourceError) as excinfo:
        parse_git_page(f"https://h.example/o/r/{marker}/main/{path}")
    assert excinfo.value.code == "git.url-invalid"
