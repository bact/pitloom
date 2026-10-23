# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A pasted Git URL names a repository and maybe a branch and a folder, on
every platform whose web pages Pitloom reads: GitHub, GitLab (also the
instances of public bodies), Gitea, Forgejo (Codeberg, code.overheid.nl),
Bitbucket Cloud and SourceHut.

See also: :mod:`tests.extract.remote.test_git_fetch` for a real checkout.
"""

from __future__ import annotations

import pytest

from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git_url import (
    GitPage,
    GitTarget,
    is_git_url,
    parse_git_page,
    scheme_allowed,
    split_ref,
)

# (id, page URL, repository URL, segments after the marker, is a file page)
_PAGES = [
    (
        "github-tree",
        "https://github.com/psf/requests/tree/main/src/requests",
        "https://github.com/psf/requests",
        ("main", "src", "requests"),
        False,
    ),
    (
        "github-blob",
        "https://github.com/psf/requests/blob/main/pyproject.toml",
        "https://github.com/psf/requests",
        ("main", "pyproject.toml"),
        True,
    ),
    (
        "gitlab-com",
        "https://gitlab.com/gitlab-org/gitlab-foss/-/tree/master/doc",
        "https://gitlab.com/gitlab-org/gitlab-foss",
        ("master", "doc"),
        False,
    ),
    (
        "gitlab-path-prefix-etsi",
        "https://labs.etsi.org/rep/ocf/capif/-/tree/main/services/register",
        "https://labs.etsi.org/rep/ocf/capif",
        ("main", "services", "register"),
        False,
    ),
    (
        "gitlab-eu-commission",
        "https://code.europa.eu/ITB/shacl-validator/-/tree/master",
        "https://code.europa.eu/ITB/shacl-validator",
        ("master",),
        False,
    ),
    (
        "gitlab-de-opencode",
        "https://gitlab.opencode.de/lfe/fuk/r/-/blob/main/docs/README.md",
        "https://gitlab.opencode.de/lfe/fuk/r",
        ("main", "docs", "README.md"),
        True,
    ),
    (
        "gitlab-fr-education",
        "https://forge.apps.education.fr/lajuscla/odrt/-/tree/main/src",
        "https://forge.apps.education.fr/lajuscla/odrt",
        ("main", "src"),
        False,
    ),
    (
        "forgejo-codeberg",
        "https://codeberg.org/forgejo/forgejo/src/branch/forgejo/cmd",
        "https://codeberg.org/forgejo/forgejo",
        ("forgejo", "cmd"),
        False,
    ),
    (
        "forgejo-nl-government",
        "https://code.overheid.nl/ForumStandaardisatie/.profile/src/branch/main",
        "https://code.overheid.nl/ForumStandaardisatie/.profile",
        ("main",),
        False,
    ),
    (
        "gitea-tag",
        "https://gitea.com/gitea/tea/src/tag/v0.9.2/cmd",
        "https://gitea.com/gitea/tea",
        ("v0.9.2", "cmd"),
        False,
    ),
    (
        "gitea-commit",
        "https://gitea.com/gitea/tea/src/commit/c5f6741/cmd",
        "https://gitea.com/gitea/tea",
        ("c5f6741", "cmd"),
        False,
    ),
    (
        "bitbucket",
        "https://bitbucket.org/atlassian/aui/src/master/docs",
        "https://bitbucket.org/atlassian/aui",
        ("master", "docs"),
        False,
    ),
    (
        "bitbucket-branch-page",
        "https://bitbucket.org/atlassian/aui/branch/feature%2Fx",
        "https://bitbucket.org/atlassian/aui",
        ("feature/x",),
        False,
    ),
    (
        "bitbucket-commits-tag",
        "https://bitbucket.org/atlassian/aui/commits/tag/v1.0",
        "https://bitbucket.org/atlassian/aui",
        ("v1.0",),
        False,
    ),
    (
        "bitbucket-commits-branch",
        "https://bitbucket.org/atlassian/aui/commits/branch/main",
        "https://bitbucket.org/atlassian/aui",
        ("main",),
        False,
    ),
    (
        "bitbucket-commits-hash",
        "https://bitbucket.org/atlassian/aui/commits/" + "a" * 40,
        "https://bitbucket.org/atlassian/aui",
        ("a" * 40,),
        False,
    ),
    (
        "sourcehut-log",
        "https://git.sr.ht/~sircmpwn/scdoc/log/master",
        "https://git.sr.ht/~sircmpwn/scdoc",
        ("master",),
        False,
    ),
    (
        "sourcehut",
        "https://git.sr.ht/~sircmpwn/scdoc/tree/master/item/src",
        "https://git.sr.ht/~sircmpwn/scdoc",
        ("master", "item", "src"),
        False,
    ),
    (
        "encoded-slash-in-branch",
        "https://github.com/o/r/tree/feature%2Fx/dir",
        "https://github.com/o/r",
        ("feature/x", "dir"),
        False,
    ),
    (
        "folder-named-item-on-github",
        "https://github.com/o/r/tree/main/item/x",
        "https://github.com/o/r",
        ("main", "item", "x"),
        False,
    ),
]


@pytest.mark.parametrize(
    ("url", "repo", "rest", "is_file"),
    [pytest.param(u, r, s, f, id=i) for i, u, r, s, f in _PAGES],
)
def test_a_page_url_names_its_repository(
    url: str, repo: str, rest: tuple[str, ...], is_file: bool
) -> None:
    """The repository is what is before the page marker; the branch and
    folder are what is after it."""
    page = parse_git_page(url)
    assert (page.repo_url, page.rest, page.is_file) == (repo, rest, is_file)


@pytest.mark.parametrize(
    ("url", "repo", "cut"),
    [
        ("https://gitlab.com/g/p", "https://gitlab.com/g/p", False),
        ("https://gitlab.com/g/p/", "https://gitlab.com/g/p", False),
        ("https://gitlab.com/g/p.git", "https://gitlab.com/g/p.git", False),
        (
            "https://github.com/psf/requests#readme",
            "https://github.com/psf/requests",
            True,
        ),
        ("https://gitlab.com/g/p?ref=1", "https://gitlab.com/g/p", True),
        # A group or project called like a marker is not a page.
        ("https://gitlab.com/tree/x", "https://gitlab.com/tree/x", False),
        ("https://gitlab.com/src/p/x", "https://gitlab.com/src/p/x", False),
        # A marker with nothing after it is part of the path.
        ("https://github.com/o/r/tree", "https://github.com/o/r/tree", False),
    ],
)
def test_a_plain_repository_url_has_no_branch_or_folder(
    url: str, repo: str, cut: bool
) -> None:
    """Only a marker after owner and repository makes a page."""
    page = parse_git_page(url)
    assert (page.repo_url, page.rest, page.cut) == (repo, (), cut)


@pytest.mark.parametrize("path", ["../x", "a/../../b", "./a", "a%5Cb", "a%2F..%2Fb/.."])
def test_a_path_that_leaves_the_checkout_is_refused(path: str) -> None:
    """``..``, ``.`` and a backslash after the marker are invalid."""
    with pytest.raises(RemoteSourceError) as excinfo:
        parse_git_page("https://github.com/o/r/tree/main/" + path)
    assert excinfo.value.code == "git.url-invalid"


def test_an_encoded_slash_stays_inside_one_segment() -> None:
    """``%2F`` is part of a name (a branch ``feature/x``), not a separator."""
    page = parse_git_page("https://github.com/o/r/tree/a%2F..%2Fb")
    assert page.rest == ("a/../b",)


_SHA = "0123456789abcdef0123456789abcdef01234567"
_REFS = {
    "main": frozenset({"branch"}),
    "feature/x": frozenset({"branch"}),
    "feature/x/y": frozenset({"branch"}),
    "v1.0": frozenset({"tag"}),
    "dup": frozenset({"branch", "tag"}),
}


@pytest.mark.parametrize(
    ("rest", "is_file", "expected"),
    [
        (("main",), False, GitTarget(ref="main")),
        (("main", "src", "a"), False, GitTarget(ref="main", subdir="src/a")),
        (("feature", "x", "dir"), False, GitTarget(ref="feature/x", subdir="dir")),
        # The longest ref wins over a shorter one.
        (("feature", "x", "y", "d"), False, GitTarget(ref="feature/x/y", subdir="d")),
        (("v1.0", "docs"), False, GitTarget(ref="v1.0", subdir="docs", tag=True)),
        # A file page names the folder holding the file.
        (
            ("main", "docs", "a.md"),
            True,
            GitTarget(ref="main", subdir="docs", file="a.md"),
        ),
        (("main", "a.md"), True, GitTarget(ref="main", file="a.md")),
        ((_SHA, "src"), False, GitTarget(commit=_SHA, subdir="src")),
        ((), False, GitTarget()),
    ],
)
def test_the_branch_and_folder_are_read_from_the_repositorys_refs(
    rest: tuple[str, ...], is_file: bool, expected: GitTarget
) -> None:
    """A branch name may hold ``/``: the refs decide where the folder starts."""
    page = GitPage("https://h/o/r", rest, is_file)
    assert split_ref(page, _REFS) == expected


@pytest.mark.parametrize("first", ["nope", "abc", "0123abc", "g" * 40])
def test_an_unknown_ref_is_an_error_naming_it(first: str) -> None:
    """Neither a ref nor a full commit id: ``git.ref-not-found``."""
    with pytest.raises(RemoteSourceError) as excinfo:
        split_ref(GitPage("https://h/o/r", (first, "x")), _REFS)
    assert excinfo.value.code == "git.ref-not-found"
    assert first in str(excinfo.value)


@pytest.mark.parametrize(
    ("url", "sourcehut"),
    [
        ("https://git.sr.ht/~o/r/tree/main/item/src", True),
        ("https://git.sr.ht/~o/r/tree/main", False),
        ("https://git.sr.ht/~o/r/tree/item/item/x", True),
        ("https://git.sr.ht/~o/r/blob/main/a.md", False),
        ("https://git.sr.ht/o/r/tree/main/item/src", False),
        ("https://github.com/o/r/tree/main/item/x", False),
    ],
    ids=["sourcehut-tree", "no-item", "item-ref", "blob", "no-tilde", "github"],
)
def test_only_a_sourcehut_tree_page_is_marked_sourcehut(
    url: str, sourcehut: bool
) -> None:
    """An owner ``~name``, the ``tree`` marker and an ``item`` segment after
    the ref make a SourceHut page."""
    assert parse_git_page(url).sourcehut is sourcehut


_SR = "https://git.sr.ht/~o/r/tree/"
_SR_REFS = {**_REFS, "item": frozenset({"branch"}), "v1.0/item": frozenset({"tag"})}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("main/item/src", GitTarget(ref="main", subdir="src")),
        ("main", GitTarget(ref="main")),
        ("main/item", GitTarget(ref="main")),
        ("feature/x/item/dir", GitTarget(ref="feature/x", subdir="dir")),
        ("feature/x/y/item/d/e", GitTarget(ref="feature/x/y", subdir="d/e")),
        ("v1.0/item/docs", GitTarget(ref="v1.0", subdir="docs", tag=True)),
        (f"{_SHA}/item/src", GitTarget(commit=_SHA, subdir="src")),
        # Only the ``item`` right after the ref is dropped.
        ("main/item/a/item/b", GitTarget(ref="main", subdir="a/item/b")),
        ("main/item/item", GitTarget(ref="main", subdir="item")),
        # A ref named ``item``; a ``v1.0/item`` ref needs its own ``item``.
        ("item/item/dir", GitTarget(ref="item", subdir="dir")),
        ("v1.0/item/x", GitTarget(ref="v1.0", subdir="x", tag=True)),
        ("v1.0/item/item/x", GitTarget(ref="v1.0/item", subdir="x", tag=True)),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_sourcehut_item_after_a_ref_of_any_length_is_no_folder(
    path: str, expected: GitTarget
) -> None:
    """SourceHut's ``item`` separates the ref, of any number of segments,
    from the path, and is not part of the folder."""
    assert split_ref(parse_git_page(_SR + path), _SR_REFS) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://git.sr.ht/~o/r/blob/feature/x/item/a.md",
            GitTarget(ref="feature/x", subdir="item", file="a.md"),
        ),
        (
            "https://github.com/o/r/tree/feature/x/item/d",
            GitTarget(ref="feature/x", subdir="item/d"),
        ),
    ],
    ids=["sourcehut-blob", "github-tree"],
)
def test_item_is_a_folder_outside_a_sourcehut_tree_page(
    url: str, expected: GitTarget
) -> None:
    """A SourceHut ``blob`` page or another host's page has no ``item``
    separator: a folder ``item`` stays."""
    assert split_ref(parse_git_page(url), _REFS) == expected


@pytest.mark.parametrize(
    ("path", "named"),
    [("nope/x/item/d", "nope/x"), ("item", "item")],
)
def test_a_sourcehut_ref_not_followed_by_item_is_not_found(
    path: str, named: str
) -> None:
    """SourceHut spells the whole ref before ``item``: the error names it."""
    with pytest.raises(RemoteSourceError) as excinfo:
        split_ref(parse_git_page(_SR + path), _REFS)
    assert excinfo.value.code == "git.ref-not-found"
    assert named in str(excinfo.value)


def test_a_tilde_owner_tree_page_without_item_is_read_as_on_other_hosts() -> None:
    """A ``~owner`` page that has no ``item`` segment is not a SourceHut page."""
    page = parse_git_page(_SR + "main/dir")
    assert not page.sourcehut
    target = split_ref(page, _REFS)
    assert (target.ref, target.subdir) == ("main", "dir")


@pytest.mark.parametrize(
    ("kind", "tag"),
    [("tag", True), ("branch", False), (None, False)],
    ids=["tag-page", "branch-page", "page-says-nothing"],
)
def test_a_name_that_is_branch_and_tag_is_the_kind_the_page_names(
    kind: str | None, tag: bool
) -> None:
    """``dup`` is both: a ``src/tag`` page wants the tag, any other the branch."""
    page = GitPage("https://h/o/r", ("dup", "d"), kind=kind)
    assert split_ref(page, _REFS) == GitTarget(ref="dup", subdir="d", tag=tag)


@pytest.mark.parametrize(
    "url",
    [
        "https://host/a/o/src/r.git",
        "https://host/git/org/tree/proj.git",
        "https://host/a/b/blob/c.git/",
    ],
)
def test_a_url_ending_in_git_is_a_repository_whatever_its_path_holds(url: str) -> None:
    """A group or prefix called ``src``, ``tree`` or ``blob`` before a
    ``.git`` repository is no page."""
    page = parse_git_page(url)
    assert (page.repo_url, page.rest) == (url.rstrip("/"), ())


def test_the_whole_url_is_kept_for_a_page_whose_marker_is_part_of_the_path() -> None:
    """A group named ``src`` before a project: the page reading is wrong, and
    the whole URL, cleaned, is what to try next."""
    page = parse_git_page("https://host/a/o/src/proj?x=1")
    assert page.repo_url == "https://host/a/o"
    assert page.plain_url == "https://host/a/o/src/proj"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("https://github.com/psf/requests", True),
        ("http://127.0.0.1:3000/o/r", True),
        ("  https://gitlab.com/g/p  ", True),
        ("HTTPS://Codeberg.org/o/r", True),
        ("https://huggingface.co/o/m", False),
        ("https://HuggingFace.co/o/m/tree/main", False),
        ("git@github.com:o/r.git", False),
        ("ssh://git@host/o/r", False),
        ("file:///tmp/r", False),
        ("owner/name", False),
        ("./project", False),
        ("https://", False),
        ("https://[::1", False),
    ],
)
def test_which_sources_are_git_urls(source: str, expected: bool) -> None:
    """Only an http(s) URL that is not a Hugging Face one."""
    assert is_git_url(source) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://h/x", True),
        ("HTTP://h/x", True),
        ("file:///x", False),
        ("ssh://h/x", False),
    ],
)
def test_a_repository_is_fetched_over_http_or_https_only(
    url: str, expected: bool
) -> None:
    """``file:`` and ``ssh:`` are never followed or fetched."""
    assert scheme_allowed(url) is expected


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("branch/main", "branch"),
        ("commits/branch/main", "branch"),
        ("commits/tag/v1", "tag"),
        ("commits/" + "b" * 40, None),
    ],
    ids=["branch", "commits-branch", "commits-tag", "commits-hash"],
)
def test_a_bitbucket_branch_or_commits_page_names_its_ref(
    path: str, kind: str | None
) -> None:
    """A page that is not a repository is not cloned as one: Bitbucket serves
    the default branch for ``<repository>/branch/x``, whatever ``x`` is."""
    page = parse_git_page("https://bitbucket.org/o/r/" + path)
    assert (page.repo_url, page.kind) == ("https://bitbucket.org/o/r", kind)
    assert page.rest and page.rest[-1] == path.rsplit("/", 1)[-1]
