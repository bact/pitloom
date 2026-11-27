# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fetch a Git repository, or a folder of one, by URL into a temporary
directory that Pitloom reads like a local project.

See also: :mod:`pitloom.extract.remote.pypi` (the PyPI URL route, which a
PyPI-family URL is sent to and never cloned: this module refuses it,
``pypi-url-unusable``).

The URL is a clone URL or the address of a repository page naming a branch,
tag or commit and a folder (:func:`~pitloom.extract.remote.git_url.
parse_git_page`). The server's redirect (GitLab's ``project`` to
``project.git``) is followed first, each hop passed to the caller's URL check
(:func:`~pitloom.extract.remote._git_redirect.resolve_git_url`). The clone is
shallow and asks the server to leave out blobs over 10 MiB that the checkout
does not need (a server without partial clone sends them; one that rejects
the filter is asked again without it): a large file in the checked-out tree
is still fetched, at checkout. It follows no redirect itself and runs with
git-lfs off; with ``max_bytes`` it stops past a disk cap (``git.too-large``),
which bounds a large file too. Git is never given a URL's user information
(:mod:`~pitloom.extract.remote._git_credentials`), so ``.git/config`` holds
none; once checked out, a symbolic link out of the checkout, into its
``.git`` or to a folder is removed.
One ``INFO:`` names the URL given and the repository, branch, tag, commit and
folder it reads as (:mod:`pitloom.extract.remote._git_say`).

Needs the ``git`` program. Every failure is a :class:`~pitloom.extract.remote.
errors.RemoteSourceError` with a code.

See also: :mod:`pitloom.extract.remote._git_say` (what the fetch says about
the URL and the checkout) and :mod:`pitloom.extract.remote._git_run` (the git
calls).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from pitloom.core.bool_arguments import checked_bools
from pitloom.core.clone_mark import reading_remote_clone
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.internal_error import InternalError
from pitloom.core.temp_dirs import temp_dir
from pitloom.core.url_masking import CHECKOUT_DIR_PREFIX
from pitloom.extract.remote._git_credentials import host_is_plain
from pitloom.extract.remote._git_folder import subproject_hint
from pitloom.extract.remote._git_redirect import resolve_git_url
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote._git_say import (
    drop_outside_links,
    folder_to_read,
    project_hint_error,
    say_not_a_repository,
    say_resolution,
)
from pitloom.extract.remote._http_errors import remote_error, shown_url
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git_url import (
    GitPage,
    GitTarget,
    parse_git_page,
    scheme_allowed,
    split_ref,
)
from pitloom.extract.remote.pypi_url import is_pypi_url
from pitloom.logging_config import configure_logging
from pitloom.messages import GIT_FRAME, code_of, emit, url_text
from pitloom.messages.config import require_text_argument
from pitloom.messages.git import (
    GIT_EMPTY_LINE,
    GIT_FILTER_UNUSABLE,
    GIT_REPOSITORY_EMPTY,
    GIT_URL_HOST_LINE,
    GIT_URL_INVALID,
    GIT_URL_NO_REPOSITORY_LINE,
    GIT_URL_SCHEME_LINE,
)
from pitloom.messages.network import (
    GIT_HOST_SPELLING_LINE,
    OFFLINE_LINE,
    OFFLINE_UNUSABLE,
    URL_HOST_SPELLING,
)
from pitloom.messages.pypi import (
    GIT_PYPI_URL_LINE,
    PYPI_URL_UNUSABLE,
)
from pitloom.messages.targets import PROJECT_NOT_FOUND

log = logging.getLogger(__name__)

__all__ = [
    "BLOB_LIMIT",
    "GitCheckout",
    "fetch_git_project",
]

#: The partial-clone filter leaves out blobs above this size that the
#: checkout does not need; a large file in the checked-out tree is fetched at
#: checkout, bounded by the ``max_bytes`` cap. A server without partial clone
#: ignores the filter; one that rejects it (HTTP 400) is asked again without
#: it (:func:`_checkout`).
BLOB_LIMIT = "10m"


@dataclass(frozen=True)
class GitCheckout:
    """A fetched repository.

    ``folder`` is the directory Pitloom reads: the checkout, or the folder
    the URL named; ``whole_repository`` says which. ``commit`` is the commit
    checked out. ``file`` is the file the URL named, relative to ``folder``;
    empty for a folder URL.
    """

    folder: str
    repo_url: str
    ref: str | None
    commit: str
    subdir: str
    whole_repository: bool
    file: str = ""
    trust_model_files: bool = False

    @contextmanager
    def explaining_failures(self) -> Iterator[None]:
        """Re-raise a ``project-not-found`` failure to read :attr:`folder` as
        ``git.no-project`` naming the sub-projects below it when the folder
        holds no Python project but folders below it do (a monorepo); any
        other failure, one with no such folders included, is untouched."""
        try:
            yield
        except (RemoteSourceError, InternalError):
            raise
        except Exception as exc:
            if code_of(exc) != PROJECT_NOT_FOUND.code:
                raise
            names, more = subproject_hint(self.folder)
            if not names:
                raise
            raise project_hint_error(
                self.folder, names, more, self.whole_repository
            ) from exc

    @property
    def root(self) -> str:
        """The checkout's root directory: :attr:`folder` without the
        :attr:`subdir` below it."""
        depth = len(self.subdir.split("/")) if self.subdir else 0
        return str(Path(self.folder).parents[depth - 1]) if depth else self.folder

    @contextmanager
    def reading(self) -> Iterator[None]:
        """The context in which a caller reads :attr:`folder`: failures are
        explained (:meth:`explaining_failures`), and a Git LFS pointer
        is reported as in a temporary clone, out of whose :attr:`root`
        nothing is read
        (:func:`~pitloom.core.clone_mark.reading_remote_clone`)."""
        with (
            reading_remote_clone(self.root, trust_model_files=self.trust_model_files),
            self.explaining_failures(),
        ):
            yield


@contextmanager
@checked_bools
def fetch_git_project(
    url: str,
    *,
    policy: RemoteFetchPolicy = RemoteFetchPolicy(),
    trust_model_files: bool = False,
) -> Iterator[GitCheckout]:
    """Fetch the repository *url* names into a temporary directory
    (``pitloom-git-`` and eight random characters), removed on exit (no
    termination guard: Ctrl-C removes it, a process ended by SIGTERM or
    SIGKILL leaves it); one that cannot be fully removed (a file still held
    open on Windows) is left behind with one ``WARNING:``, never an error.

    Within the block, the reads are a temporary clone's
    (:func:`~pitloom.core.clone_mark.reading_remote_clone`, as in
    :meth:`GitCheckout.reading`): nothing out of the checkout's root is read,
    the model readers a wheel scan does not run are not run, and the
    repository's build-time code is not run. The mark is reset on every exit
    and belongs to the calling thread's context alone.

    With *trust_model_files* the caller vouches for the repository's model
    files: the readers a wheel scan does not run are run (the build-time code
    is still not run). The default is to run none of them.

    *policy* (:func:`~pitloom.core.config_cascade.resolve_fetch_policy`)
    says what the fetch may do. Its ``check_url`` is called with the URL of
    every redirect target, without user information, before it is requested
    and raises for one that must not be fetched; Pitloom does not check the
    URL it is given (the caller does, as it knows its own policy; the PyPI
    route, unlike this one, passes its first URLs to its check too). With
    ``offline`` nothing is fetched. The fetch is stopped once the checkout
    (the ``.git`` directory included) takes more disk than ``max_bytes``
    (``git.too-large``).

    Raises:
        RemoteSourceError: the URL names no fetchable repository, ref or
            folder (``git.url-invalid``, checked before ``offline``; a
            PyPI URL is catalogued ``pypi-url-unusable``), ``git`` is
            missing, ``offline`` is set (``git.offline``,
            ``offline-unusable``), git cannot reach the server
            (``git.clone-failed``, ``download-network-failed``) or does not
            finish in time (``git.timeout``, ``download-timeout``), or the
            repository is larger than ``max_bytes`` (``over-cap``).
        pitloom.messages.CodedTypeError: *url* is no ``str``
            (``option-invalid``), on entering the block, before anything is
            made.
        pitloom.messages.CodedValueError: *url* is empty or white space only
            (``option-invalid``), likewise.
        Exception: whatever ``check_url`` raises, unchanged.
    """
    configure_logging()
    require_text_argument(url, "url")
    runner = GitRunner(max_bytes=policy.max_bytes)
    # Each git call has ended (its process group too) before the removal.
    with temp_dir(CHECKOUT_DIR_PREFIX, frame=GIT_FRAME) as work:
        checkout = _prepare(url, str(work), runner, policy)
        checkout = replace(checkout, trust_model_files=trust_model_files)
        with reading_remote_clone(checkout.root, trust_model_files=trust_model_files):
            yield checkout


def _prepare(
    url: str, work_dir: str, runner: GitRunner, policy: RemoteFetchPolicy
) -> GitCheckout:
    """Fetch what *url* names into *work_dir* and describe it."""
    shown = url_text(url)
    if is_pypi_url(url):
        # PyPI is no Git host: refused, never cloned.
        raise RemoteSourceError(
            "git.url-invalid",
            GIT_PYPI_URL_LINE.render({"url": shown}),
            pitloom_code=PYPI_URL_UNUSABLE.code,
        )
    # The URL is read first, as the PyPI and Hugging Face routes read theirs:
    # an invalid one is ``git.url-invalid`` offline too.
    page = _read_url(url, shown)
    if policy.offline:
        raise RemoteSourceError(
            "git.offline",
            OFFLINE_LINE.render({"url": shown}),
            pitloom_code=OFFLINE_UNUSABLE.code,
        )
    clone_url, page, target = _resolve(runner, page, policy.check_url)
    say_resolution(url, clone_url, target, page)
    _checkout(runner, clone_url, work_dir, target)
    drop_outside_links(work_dir, clone_url)
    folder, file = folder_to_read(work_dir, target, url)
    commit = _head(runner, work_dir, shown)
    subdir = os.path.relpath(os.path.realpath(folder), os.path.realpath(work_dir))
    return GitCheckout(
        folder=folder,
        repo_url=clone_url,
        ref=target.ref,
        commit=commit,
        subdir="" if subdir == "." else subdir.replace(os.sep, "/"),
        whole_repository=subdir == ".",
        file=file,
    )


def _read_url(url: str, shown: str) -> GitPage:
    """The page *url* names.

    Raises:
        RemoteSourceError: ``git.url-invalid``, a scheme other than http(s),
            no host or no repository path (``git-url-invalid``), a host that
            is not plain
            (:func:`_host_as_typed`, ``url-unsafe/host-spelling``) or a path
            that leaves the checkout.
    """
    if not scheme_allowed(url.strip()):
        raise remote_error(
            "git.url-invalid", GIT_URL_INVALID, GIT_URL_SCHEME_LINE, url=shown
        )
    if not _names_host(url.strip()):
        raise remote_error(
            "git.url-invalid", GIT_URL_INVALID, GIT_URL_HOST_LINE, url=shown
        )
    if not _host_as_typed(url.strip()):
        raise RemoteSourceError(
            "git.url-invalid",
            GIT_HOST_SPELLING_LINE.render({"url": shown}),
            pitloom_code=URL_HOST_SPELLING.code,
        )
    page = parse_git_page(url)
    # A host alone (https://github.com/) names no repository to clone.
    if not urlsplit(page.plain_url).path.strip("/"):
        raise remote_error(
            "git.url-invalid", GIT_URL_INVALID, GIT_URL_NO_REPOSITORY_LINE, url=shown
        )
    return page


def _names_host(url: str) -> bool:
    """Whether *url* names a host, or is a ``file:`` URL, which names none
    by design (allowed by tests alone): git would resolve a host a URL with
    none (``https://``, ``https://u@/o/r``) does not spell. *url* is one
    :func:`scheme_allowed` accepted, so it parses."""
    parts = urlsplit(url)
    return bool(parts.hostname) or parts.scheme.lower() == "file"


def _host_as_typed(url: str) -> bool:
    """Whether the host of *url* is plain (:func:`host_is_plain`); a
    ``file:`` URL, which names none (:func:`_names_host`), is. curl maps
    another spelling (``pypi%2Eorg``, a full-width dot) to a host the URL's
    text does not name, which no check of that text (a PyPI host is never
    cloned) would see; a host holding ``=``, ``!`` or white space, or
    starting with ``-``, names none; and a bracketed name (``[v1.x]``)
    would lose its brackets in the clone URL and name a DNS host.

    *url* is one :func:`scheme_allowed` accepted, so it parses: a URL
    ``urlsplit`` refuses never reaches here."""
    parts = urlsplit(url)
    if not parts.hostname:
        return parts.scheme.lower() == "file"
    return host_is_plain(parts)


def _resolve(
    runner: GitRunner, page: GitPage, check_url: Callable[[str], None] | None
) -> tuple[str, GitPage, GitTarget]:
    """The URL to clone, the page it was read from and what to check out.

    A page URL whose repository part is not a repository (a group called
    ``src`` or ``tree``) is tried again with the whole URL as the repository.
    """
    clone_url = resolve_git_url(page.repo_url, check_url)
    if not page.rest and not page.query_style:
        return clone_url, page, GitTarget()
    try:
        return clone_url, page, _target(runner, clone_url, page)
    except RemoteSourceError as exc:
        if page.plain_url == page.repo_url or not _not_a_repository(exc):
            raise
        say_not_a_repository(page)
    plain = GitPage(page.plain_url, cut=page.cut, plain_url=page.plain_url)
    return resolve_git_url(plain.repo_url, check_url), plain, GitTarget()


def _not_a_repository(exc: RemoteSourceError) -> bool:
    """Whether *exc* says the URL is no repository (a 404), not that it could
    not be reached (TLS, DNS, sign-in): only the first is worth another try."""
    text = str(exc).lower()
    return exc.code == "git.clone-failed" and (
        "not found" in text or "does not appear to be a git repository" in text
    )


def _target(runner: GitRunner, repo_url: str, page: GitPage) -> GitTarget:
    """The branch, tag or commit and the folder the page URL names, read
    against the repository's own refs."""
    listing = runner.run(
        ["ls-remote", "--heads", "--tags", "--refs", "--", repo_url], "ls-remote"
    )
    kinds: dict[str, set[str]] = {}
    for line in listing.splitlines():
        _sha, _tab, name = line.partition("\t")
        if name.startswith("refs/heads/"):
            kinds.setdefault(name.removeprefix("refs/heads/"), set()).add("branch")
        elif name.startswith("refs/tags/"):
            kinds.setdefault(name.removeprefix("refs/tags/"), set()).add("tag")
    return split_ref(page, {n: frozenset(k) for n, k in kinds.items()})


def _checkout(
    runner: GitRunner, clone_url: str, work_dir: str, target: GitTarget
) -> None:
    """Check out *target* of *clone_url* into *work_dir*, shallowly, with a
    filter that leaves out blobs over :data:`BLOB_LIMIT` the checkout does
    not need (a large file in the checked-out tree is fetched at checkout).
    A server that answers the filter with an error (Azure DevOps: HTTP 400)
    is asked again without it; the size cap still bounds the transfer.
    ``init`` and ``remote add`` run once, and the tag and commit retry says
    ``--no-filter``: the failed fetch saved the filter in the repository
    config."""
    pinned = bool(target.commit or target.tag)
    if pinned:
        runner.run(["init", "--quiet", "--", work_dir], "init")
        runner.run(
            ["-C", work_dir, "remote", "add", "origin", "--", clone_url], "remote"
        )
    try:
        _fetch(
            runner, clone_url, work_dir, target, [f"--filter=blob:limit={BLOB_LIMIT}"]
        )
    except RemoteSourceError as exc:
        if exc.code != "git.clone-failed" or "HTTP 400" not in str(exc):
            raise
        emit(
            log,
            GIT_FILTER_UNUSABLE,
            logging.INFO,
            frame=GIT_FRAME,
            url=shown_url(clone_url),
        )
        # A failed filtered fetch leaves the filter in the repository's
        # config, which a plain fetch would send again.
        _fetch(runner, clone_url, work_dir, target, ["--no-filter"] if pinned else [])
    if pinned:
        runner.run(
            [
                "-C",
                work_dir,
                "-c",
                "advice.detachedHead=false",
                "checkout",
                "FETCH_HEAD",
            ],
            "checkout",
            watch=work_dir,
        )


def _fetch(
    runner: GitRunner,
    clone_url: str,
    work_dir: str,
    target: GitTarget,
    blobs: list[str],
) -> None:
    """Fetch *target* of *clone_url* with the clone options *blobs*: into the
    repository ``init`` made for a tag or commit, else by a shallow clone."""
    if target.commit or target.tag:
        # A refspec begins with ``refs/``: it cannot be read as an option.
        wanted = f"refs/tags/{target.ref}" if target.tag else str(target.commit)
        runner.run(
            ["-C", work_dir, "fetch", "--depth", "1", *blobs, "origin", wanted],
            "fetch",
            watch=work_dir,
        )
        return
    branch = ["--branch", target.ref] if target.ref else []
    runner.run(
        ["clone", "--depth", "1", *blobs, *branch, "--", clone_url, work_dir],
        "clone",
        watch=work_dir,
    )


def _head(runner: GitRunner, work_dir: str, shown: str) -> str:
    """The commit checked out; an empty repository has none."""
    try:
        return runner.run(
            ["-C", work_dir, "rev-parse", "--verify", "HEAD"], "rev-parse", echo=False
        ).strip()
    except RemoteSourceError as exc:
        if exc.code != "git.clone-failed":
            raise
        raise remote_error(
            "git.clone-failed", GIT_REPOSITORY_EMPTY, GIT_EMPTY_LINE, url=shown
        ) from exc
