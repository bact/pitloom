# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a Git URL names: a repository, and maybe a branch and a folder.

People paste the address of the page they were looking at, not a clone URL:
``.../-/tree/main/services/x`` (GitLab, including the instances run by public
bodies), ``.../tree/main/src`` (GitHub), ``.../src/branch/main/cmd`` (Gitea,
Forgejo, Codeberg), ``.../src/main/dir`` (Bitbucket Cloud) and
``.../tree/main/item/dir`` (SourceHut). The page syntax is the same on every
host that runs the same software, so no host list is kept: a URL is read by
its path, and the repository is the part before the page marker.

A branch name may hold ``/``, so the split between branch and folder cannot be
read from the URL; :func:`split_ref` takes it from the server's own refs.

Messages quote a URL without its credentials.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit

from pitloom.core.quote_source import quote_source
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import sanitize_url_credentials

__all__ = [
    "ALLOWED_SCHEMES",
    "GitPage",
    "GitTarget",
    "HUB_HOST_PATTERN",
    "is_git_url",
    "is_unsupported_remote_url",
    "parse_git_page",
    "scheme_allowed",
    "split_ref",
]

#: The URL schemes a repository is fetched over, and a redirect may lead to:
#: a server that redirects to ``file:`` or ``ssh:`` is not followed.
ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Page markers, as path-segment sequences, with the kind of ref the page
#: names (``None``: the page does not say) and whether it is a file page.
_MARKERS: tuple[tuple[tuple[str, ...], str | None, bool], ...] = (
    (("-", "tree"), None, False),  # GitLab
    (("-", "blob"), None, True),
    (("src", "branch"), "branch", False),  # Gitea, Forgejo, Codeberg
    (("src", "tag"), "tag", False),
    (("src", "commit"), "commit", False),
    (("tree",), None, False),  # GitHub, SourceHut
    (("blob",), None, True),
    (("src",), None, False),  # Bitbucket Cloud
)

#: A commit id given as a ref: the full 40 (SHA-1) or 64 (SHA-256) hex digits,
#: which is what a server's page URL holds and what a server can be asked for.
_COMMIT = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")

#: SourceHut (owners are ``~name``) puts ``item`` between the ref and the path.
_SOURCEHUT_ITEM = "item"

#: Hosts whose URLs are models, not Git repositories (``huggingface.co``, its
#: ``www.`` form and the ``hf.co`` short name), any case.
HUB_HOST_PATTERN = r"(?:www\.)?(?:huggingface|hf)\.co"
_HF_HOST = re.compile(HUB_HOST_PATTERN, re.IGNORECASE)


def is_git_url(source: str) -> bool:
    """Whether *source* is an ``http`` or ``https`` URL of a Git repository or
    of one of its web pages: any such URL that is not a Hugging Face one.

    Only the scheme and host are read; the server decides whether it is a
    repository. A local path is never one, nor is a bare ``owner/name``.
    """
    text = source.strip()
    if not text.lower().startswith(("http://", "https://")):
        return False
    try:
        host = urlsplit(text).hostname or ""
    except ValueError:
        return False
    return bool(host) and _HF_HOST.fullmatch(host) is None


def scheme_allowed(url: str) -> bool:
    """Whether *url* is of a scheme a repository is fetched over
    (:data:`ALLOWED_SCHEMES`)."""
    try:
        return urlsplit(url).scheme.lower() in ALLOWED_SCHEMES
    except ValueError:
        return False


#: A URL of any scheme (two or more characters, so a Windows drive is none).
_ANY_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]+://")

#: An scp-style Git address, ``user@host:path``.
_SCP_ADDRESS = re.compile(r"[\w.-]+@[\w.-]+:(?![/\\])\S+")


def is_unsupported_remote_url(source: str) -> bool:
    """Whether *source* is a remote address Pitloom does not fetch: a URL of a
    scheme other than http(s) (``ssh://``, ``git://``, ``file://``), or an
    scp-style ``user@host:path``. Told apart so the user is told, not given
    a "directory not found". A Hugging Face URL is neither.
    """
    text = source.strip()
    if is_git_url(text) or _HF_HOST.search(text):
        return False
    return bool(_ANY_URL.match(text) or _SCP_ADDRESS.fullmatch(text))


@dataclass(frozen=True)
class GitPage:
    """A pasted URL, read by its path.

    ``rest`` holds the segments after the page marker (the branch or tag,
    then the folder or file), already percent-decoded; it is empty for a
    plain repository URL. ``plain_url`` is the whole URL as a repository, for
    when the marker proves to be part of the repository's own path.
    ``sourcehut`` marks a SourceHut ``tree`` page, whose ``rest`` puts an
    ``item`` segment between the ref and the path; a ``~owner`` ``tree`` page
    with no such segment is read like any other host's.
    """

    repo_url: str
    rest: tuple[str, ...] = ()
    is_file: bool = False
    #: Whether a query or fragment was cut from the URL.
    cut: bool = False
    #: ``"branch"``, ``"tag"`` or ``"commit"`` when the page says which.
    kind: str | None = None
    plain_url: str = ""
    sourcehut: bool = False

    @property
    def repo_name(self) -> str:
        """The repository's last path segment, without ``.git``."""
        parts = [p for p in urlsplit(self.repo_url).path.split("/") if p]
        return parts[-1].removesuffix(".git") if parts else ""


@dataclass(frozen=True)
class GitTarget:
    """What to check out: a branch, tag or commit, and a folder below it.

    ``file`` is the file a file page named, so a page that names a folder
    under a file marker is still read as that folder.
    """

    ref: str | None = None
    commit: str | None = None
    subdir: str = ""
    tag: bool = False
    file: str = ""


def parse_git_page(url: str) -> GitPage:
    """The repository *url* names, and the branch and folder of a page URL.

    A URL whose last path segment ends in ``.git`` is a repository whatever
    its path holds.

    Raises:
        RemoteSourceError: ``git.url-invalid``, a ``..`` or ``.`` segment
            after the marker.
    """
    parts = urlsplit(url.strip())
    cut = bool(parts.query or parts.fragment)
    raw = [s for s in parts.path.split("/") if s]
    plain = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    if raw and raw[-1].endswith(".git"):
        return GitPage(plain, cut=cut, plain_url=plain)
    # GitLab's ``-`` is unambiguous (a group may be called ``src`` or
    # ``tree``): its markers are looked for first, the others by position.
    gitlab = tuple(m for m in _MARKERS if m[0][0] == "-")
    for markers in (gitlab, _MARKERS):
        found = _find_marker(raw, markers)
        if found is None:
            continue
        index, (marker, kind, is_file) = found
        rest = tuple(unquote(s) for s in raw[index + len(marker) :])
        _check_segments(rest, url)
        sourcehut = (
            raw[0].startswith("~")
            and marker == ("tree",)
            and _SOURCEHUT_ITEM in rest[1:]
        )
        repo = urlunsplit(
            (parts.scheme, parts.netloc, "/" + "/".join(raw[:index]), "", "")
        )
        return GitPage(repo, rest, is_file, cut, kind, plain, sourcehut)
    return GitPage(plain, cut=cut, plain_url=plain)


def _find_marker(
    raw: list[str], markers: tuple[tuple[tuple[str, ...], str | None, bool], ...]
) -> tuple[int, tuple[tuple[str, ...], str | None, bool]] | None:
    """The first page marker of *markers* in the path segments *raw*, from
    index 2 (an owner and a repository come first), with its index."""
    for index in range(2, len(raw)):
        for entry in markers:
            size = len(entry[0])
            if tuple(raw[index : index + size]) == entry[0] and index + size < len(raw):
                return index, entry
    return None


def _check_segments(rest: tuple[str, ...], url: str) -> None:
    """Refuse a segment that would walk out of the checkout."""
    for segment in rest:
        if segment in {".", ".."} or "\0" in segment or "\\" in segment:
            raise RemoteSourceError(
                "git.url-invalid",
                f"Invalid path in URL: {quote_source(sanitize_url_credentials(url))}",
            )


def split_ref(page: GitPage, refs: Mapping[str, frozenset[str]]) -> GitTarget:
    """The branch or tag (or commit) and the folder a page URL names, from
    *refs*, the repository's branch and tag names, each with its kinds
    (``"branch"``, ``"tag"``): the longest leading run of segments that is a
    ref wins. A name that is both a branch and a tag is the kind the page
    names (a ``src/tag`` page: the tag), else the branch. A file page names
    the folder holding the file, and that file as ``file``. On a SourceHut
    page a ref is followed by ``item`` or by nothing, and that ``item`` is
    not part of the folder.

    Raises:
        RemoteSourceError: ``git.ref-not-found``, the leading segments are no
            ref and not a full commit id.
    """
    rest = list(page.rest)
    if not rest:
        return GitTarget()
    for size in range(len(rest), 0, -1):
        name = "/".join(rest[:size])
        kinds = refs.get(name)
        path = _after_ref(page, rest, size)
        if kinds and path is not None:
            folder, file = _folder(path, page.is_file)
            return GitTarget(
                ref=name,
                subdir=folder,
                tag="tag" in kinds and (page.kind == "tag" or "branch" not in kinds),
                file=file,
            )
    first = rest[0]
    path = _after_ref(page, rest, 1)
    if _COMMIT.fullmatch(first) and path is not None:
        folder, file = _folder(path, page.is_file)
        return GitTarget(commit=first, subdir=folder, file=file)
    if page.sourcehut:
        end = rest.index(_SOURCEHUT_ITEM) if _SOURCEHUT_ITEM in rest else len(rest)
        first = "/".join(rest[: max(end, 1)])
    raise RemoteSourceError(
        "git.ref-not-found",
        f"No branch or tag {quote_source(first)} in "
        f"{quote_source(sanitize_url_credentials(page.repo_url))} "
        "(a commit needs its full 40 or 64 hex digits).",
    )


def _after_ref(page: GitPage, rest: list[str], size: int) -> list[str] | None:
    """The path segments after a ref of *size* segments of *rest*; on a
    SourceHut page without the ``item`` that follows the ref, and ``None``
    when another segment follows it instead."""
    path = rest[size:]
    if not page.sourcehut or not path:
        return path
    return path[1:] if path[0] == _SOURCEHUT_ITEM else None


def _folder(path: list[str], is_file: bool) -> tuple[str, str]:
    """The folder of *path* and the file it ends in: for a file page the
    folder holding it and its name, else the whole path and no file."""
    if is_file and path:
        return "/".join(path[:-1]), path[-1]
    return "/".join(path), ""
