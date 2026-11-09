# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A percent-encoded separator in a Git page URL: a ``/`` encoded in one
segment (``%2F``, ``%2f``, Azure DevOps' ``path=`` decoded twice:
``%252F``) or a ``\\`` (``%5C``) never walks out of the checkout, on every
page form; a branch named with an encoded ``/`` (Bitbucket's ``feature%2Fx``)
is still read.

See also: :mod:`tests.extract.remote.test_git_url` (the page forms) and
:mod:`tests.extract.remote.test_git_fetch_escape` (the same URLs against a
real checkout).
"""

from __future__ import annotations

import pytest

from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git_url import parse_git_page

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
    """Decoded, each segment is a path of names: none is ``.``, ``..`` or
    empty, and none holds a ``\\`` or a NUL."""
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
