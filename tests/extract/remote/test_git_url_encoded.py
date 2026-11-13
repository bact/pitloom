# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A percent-encoded separator in a Git page URL: a ``/`` encoded in one
segment (``%2F``, ``%2f``, Azure DevOps' ``path=`` decoded twice:
``%252F``) or a ``\\`` (``%5C``) never walks out of the checkout, on every
page form, nor into its ``.git`` directory (in any letter case, or as
Windows reads ``.git.``, ``.git ``, ``GIT~1`` and ``.git::$DATA``); a
branch named with an encoded ``/`` (Bitbucket's ``feature%2Fx``) is still
read, as is a name that starts with ``.git`` (``.github``). A host that is
not plain ASCII, or is percent-encoded, is refused before any git process
starts (curl would map it to another host), and before ``offline``.

See also: :mod:`tests.extract.remote.test_git_url` (the page forms) and
:mod:`tests.extract.remote.test_git_target_named` and
:mod:`tests.extract.remote.test_git_fetch_models` (the same URLs against a
real checkout).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import git
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import fetch_git_project
from pitloom.extract.remote.git_url import parse_git_page
from pitloom.messages.network import (
    GIT_HOST_SPELLING_LINE,
    URL_HOST_SPELLING,
)
from tests._message_drift import raised_as

#: Encoded paths that leave, or start outside, the checkout.
_ESCAPES = {
    "dotdot-upper": ".git%2F..%2F..%2Fhost%2Fm.gguf",
    "dotdot-lower": ".git%2f..%2f..%2fhost%2fm.gguf",
    "dotdot-first": "..%2fhost%2fm.gguf",
    "absolute": "%2Fetc%2Fpasswd",
    "dot": "a%2F.%2Fm.gguf",
    "double-slash": "a%2F%2Fm.gguf",
    "backslash": "..%5Chost%5Cm.gguf",
    "nul": "m.gguf%00.txt",
    "dotgit": ".git/config",
    "dotgit-encoded": ".git%2Fconfig",
    "dotgit-upper": "sub/.GIT/config",
    "dotgit-win32": ".git.%2Fconfig",
    "dotgit-short": "GIT~1/config",
    "dotgit-short-2": "git~12/config",
    "dotgit-space": ".git%20/config",
    "dotgit-ads": ".git::$DATA",
    "dotgit-ads-index": ".git::$INDEX_ALLOCATION/config",
    "dotgit-stream": ".git:x/config",
}

#: Page forms whose path segments follow a marker, ``{p}`` the path.
_FORMS = {
    "blob": "https://h.example/o/r/blob/main/{p}",
    "raw": "https://h.example/o/r/raw/main/{p}",
    "tree": "https://h.example/o/r/tree/main/{p}",
    "gitlab-blob": "https://h.example/g/r/-/blob/main/{p}",
    "gitea-src-branch": "https://h.example/o/r/src/branch/main/{p}",
    "gitea-raw-branch": "https://h.example/o/r/raw/branch/main/{p}",
    "gitiles": "https://h.example/r/+/refs/heads/main/{p}",
    "cgit": "https://h.example/pub/r.git/tree/{p}?h=main",
    "azure": "https://dev.azure.com/o/p/_git/r?path=/{p}&version=GBmain",
}

#: Azure DevOps' ``path=`` is a path once the query is parsed: there a
#: ``%2F`` is a separator, and an empty segment is dropped, not refused.
_CASES = [
    (form_id, path_id)
    for form_id in _FORMS
    for path_id in _ESCAPES
    if not (form_id == "azure" and path_id in {"absolute", "double-slash"})
]


@pytest.mark.parametrize(
    ("form_id", "path_id"), _CASES, ids=[f"{f}-{p}" for f, p in _CASES]
)
def test_an_encoded_separator_that_leaves_the_checkout_is_refused(
    form_id: str, path_id: str
) -> None:
    """Decoded, each segment is a path of names: none is ``.``, ``..``,
    ``.git`` or empty, and none holds a ``\\`` or a NUL."""
    with pytest.raises(RemoteSourceError) as excinfo:
        parse_git_page(_FORMS[form_id].format(p=_ESCAPES[path_id]))
    assert excinfo.value.code == "git.url-invalid"


def test_an_azure_path_is_a_path_once_the_query_is_parsed() -> None:
    """An encoded ``/`` in ``path=`` separates folders like a plain one."""
    page = parse_git_page("https://dev.azure.com/o/p/_git/r?path=%2Fetc%2F%2Fx")
    assert page.rest == ("etc", "x")


@pytest.mark.parametrize(
    "query",
    [
        "path=%252F..%252F..%252Fetc&version=GBmain",
        "path=/a%252F..%252F..&version=GBmain",
        "path=/a%255Cb",
    ],
    ids=["leading", "inner", "backslash"],
)
def test_an_azure_path_encoded_twice_is_checked_once_decoded(query: str) -> None:
    """``path=`` is decoded by the query parse and again as a segment: what
    the second decoding yields is checked."""
    with pytest.raises(RemoteSourceError) as excinfo:
        parse_git_page("https://dev.azure.com/o/p/_git/r?" + query)
    assert excinfo.value.code == "git.url-invalid"


@pytest.mark.parametrize(
    ("url", "rest"),
    [
        ("https://h.example/o/r/tree/feature%2Fx/dir", ("feature/x", "dir")),
        (
            "https://h.example/o/r/blob/main/models%2Fsub%2Fm.keras",
            ("main", "models/sub/m.keras"),
        ),
        (
            "https://h.example/o/r/blob/main/models/sub/m.keras",
            ("main", "models", "sub", "m.keras"),
        ),
        ("https://h.example/o/r/blob/main/a..b%2F.hidden", ("main", "a..b/.hidden")),
    ],
    ids=["branch", "encoded-nested", "nested", "dots-in-names"],
)
def test_an_encoded_slash_between_plain_names_is_kept(
    url: str, rest: tuple[str, ...]
) -> None:
    """A ``/`` encoded between names (a branch ``feature/x``) stays in its
    segment: the ref split reads it from the server's refs."""
    assert parse_git_page(url).rest == rest


@pytest.mark.parametrize(
    "name",
    [".gitmodules", ".gitattributes", ".gitignore", ".github", "foo.git", "git~x"],
)
def test_a_name_that_only_starts_or_ends_with_git_is_kept(name: str) -> None:
    page = parse_git_page(f"https://h.example/o/r/blob/main/{name}/m.gguf")
    assert page.rest == ("main", name, "m.gguf")


@pytest.fixture(name="no_git")
def _no_git(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Fail on any git command or redirect probe; the calls are listed."""
    calls: list[str] = []

    def boom(*args: object, **_kwargs: object) -> None:
        calls.append(repr(args))
        raise AssertionError("git started")

    monkeypatch.setattr(git, "resolve_git_url", boom)
    monkeypatch.setattr(GitRunner, "run", boom)
    yield calls
    assert not calls


def _refusal(url: str, offline: bool) -> RemoteSourceError:
    policy = RemoteFetchPolicy(offline=offline)
    with pytest.raises(RemoteSourceError) as excinfo:
        with fetch_git_project(url, policy=policy):
            pytest.fail("not fetched")  # pragma: no cover
    return excinfo.value


@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
@pytest.mark.parametrize(
    "url",
    [
        "https://github\u3002com/o/r",
        "https://github\uff0ecom/o/r",
        "https://huggingface\uff61co/spaces/o/s",
        "https://gith%75b.com/o/r",
        "https://github.com%2E/o/r",
        "https://b\u00fccher.example/o/r",
    ],
    ids=["ideographic", "full-width", "half-width", "encoded", "encoded-dot", "idn"],
)
@pytest.mark.usefixtures("no_git")
def test_a_host_not_typed_in_ascii_is_refused_unfetched(
    url: str, offline: bool
) -> None:
    error = _refusal(url, offline)
    assert error.code == "git.url-invalid"
    assert raised_as(error, URL_HOST_SPELLING)
    assert str(error) == GIT_HOST_SPELLING_LINE.render({"url": url})


@pytest.mark.parametrize(
    "url",
    [
        "ssh://h/r.git",
        "git://h/r.git",
        "https://h/o/r/tree/main/..%2F..%2Fx",
        "https://[::1/o/r",
    ],
    ids=["ssh", "git", "escape", "unparseable"],
)
@pytest.mark.usefixtures("no_git")
def test_an_invalid_url_is_refused_before_offline(url: str) -> None:
    """As on the PyPI and Hugging Face routes: the URL is read first."""
    assert _refusal(url, offline=True).code == "git.url-invalid"


@pytest.mark.usefixtures("no_git")
def test_an_international_host_in_its_xn_form_passes() -> None:
    assert _refusal("https://xn--bcher-kva.example/o/r", True).code == "git.offline"
