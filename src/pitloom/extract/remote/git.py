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
which bounds a large file too. Once checked out, the URL git wrote to
``.git/config`` loses its user information, and a symbolic link out of the
checkout, into its ``.git`` or to a folder is removed.
One ``INFO:`` names the URL given and the URL cloned when they differ.

Needs the ``git`` program. Every failure is a :class:`~pitloom.extract.remote.
errors.RemoteSourceError` with a code; a refusal is also a ``WARNING:``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path, PurePath
from typing import Final
from urllib.parse import urlsplit

from pitloom.core.clone_mark import reading_remote_clone
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.path_confine import in_git_dir, is_inside
from pitloom.core.temp_dirs import temp_dir
from pitloom.core.url_masking import (
    CHECKOUT_DIR_PREFIX,
    sanitize_url,
    sanitize_url_credentials,
    url_without_credentials,
)
from pitloom.extract.remote._git_folder import (
    checkout_folder,
    checkout_has_file,
    subproject_hint,
)
from pitloom.extract.remote._git_redirect import resolve_git_url
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git_url import (
    GitPage,
    GitTarget,
    parse_git_page,
    scheme_allowed,
    split_ref,
)
from pitloom.extract.remote.pypi_url import is_pypi_url
from pitloom.logging_config import loggable
from pitloom.messages import (
    GIT_HOST_SPELLING_LINE,
    GIT_PYPI_URL_LINE,
    OFFLINE_LINE,
    OFFLINE_UNUSABLE,
    PROJECT_NOT_FOUND,
    PYPI_URL_UNUSABLE,
    URL_HOST_SPELLING,
    code_of,
)

log = logging.getLogger(__name__)

__all__ = [
    "BLOB_LIMIT",
    "RESOLVED_INFO",
    "GitCheckout",
    "fetch_git_project",
]

#: The partial-clone filter leaves out blobs above this size that the
#: checkout does not need; a large file in the checked-out tree is fetched at
#: checkout, bounded by the ``max_bytes`` cap. A server without partial clone
#: ignores the filter; one that rejects it (HTTP 400) is asked again without
#: it (:func:`_checkout`).
BLOB_LIMIT = "10m"

#: ``log.info()`` format for a URL that names more than the clone URL.
#: Arguments: the URL given, the repository cloned, what else it names.
RESOLVED_INFO = "Git source: %s names repository %s%s"

#: What starts a message about the checkout's directory, as every other
#: message of the route starts.
_LOG_PREFIX: Final = "Git source: "


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
        """Re-raise a failure to read :attr:`folder` as ``git.no-project``
        with a hint when the folder holds no Python project but folders below
        it do (a monorepo); any other failure is untouched."""
        try:
            yield
        except RemoteSourceError:
            raise
        except Exception as exc:
            # A catalogued refusal (a model file's) says its own condition;
            # a missing project's is the one the hint explains.
            hint = (
                ""
                if code_of(exc) not in (None, PROJECT_NOT_FOUND.code)
                else subproject_hint(self.folder, self.whole_repository)
            )
            if not hint:
                raise
            raise RemoteSourceError("git.no-project", f"{exc}{hint}") from exc

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
        (:func:`~pitloom.core.lfs_pointer.reading_remote_clone`)."""
        with (
            reading_remote_clone(self.root, trust_model_files=self.trust_model_files),
            self.explaining_failures(),
        ):
            yield


@contextmanager
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
    (:func:`~pitloom.core.lfs_pointer.reading_remote_clone`, as in
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
        Exception: whatever ``check_url`` raises, unchanged.
    """
    runner = GitRunner(max_bytes=policy.max_bytes)
    # Each git call has ended (its process group too) before the removal.
    with temp_dir(CHECKOUT_DIR_PREFIX, log_prefix=_LOG_PREFIX) as work:
        try:
            checkout = _prepare(url, str(work), runner, policy)
        except Exception as exc:
            # A refusal is said here, so a caller that only logs shows it.
            log.warning("Git source: %s", loggable(sanitize_url_credentials(str(exc))))
            raise
        checkout = replace(checkout, trust_model_files=trust_model_files)
        with reading_remote_clone(checkout.root, trust_model_files=trust_model_files):
            yield checkout


def _prepare(
    url: str, work_dir: str, runner: GitRunner, policy: RemoteFetchPolicy
) -> GitCheckout:
    """Fetch what *url* names into *work_dir* and describe it."""
    shown = loggable(sanitize_url(url))
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
    _log_resolution(url, clone_url, target, page)
    _checkout(runner, clone_url, work_dir, target)
    _forget_credentials(runner, clone_url, work_dir)
    _drop_outside_links(work_dir)
    folder, file = _folder(work_dir, target)
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
            a host that is not plain ASCII (:func:`_host_as_typed`,
            ``url-unsafe/host-spelling``) or a path that leaves the checkout.
    """
    if not scheme_allowed(url.strip()):
        raise RemoteSourceError(
            "git.url-invalid",
            f"Cannot fetch {shown}: only http and https URLs are fetched "
            "(not ssh, git, file or scp-style addresses).",
        )
    if not _host_as_typed(url.strip()):
        raise RemoteSourceError(
            "git.url-invalid",
            GIT_HOST_SPELLING_LINE.render({"url": shown}),
            pitloom_code=URL_HOST_SPELLING.code,
        )
    return parse_git_page(url)


def _host_as_typed(url: str) -> bool:
    """Whether the host of *url* is plain ASCII, not percent-encoded: curl
    maps any other spelling (``pypi%2Eorg``, a full-width dot) to a host
    the URL's text does not name, which no check of that text (a PyPI host
    is never cloned) would see."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return False
    return host.isascii() and "%" not in host


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
        log.info(
            "Git source: %s is not a repository; trying %s",
            loggable(sanitize_url(page.repo_url)),
            loggable(sanitize_url(page.plain_url)),
        )
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


def _log_resolution(url: str, clone_url: str, target: GitTarget, page: GitPage) -> None:
    """One ``INFO:`` when the URL given names more than the repository: a
    branch, tag, commit or folder, or a query or fragment that was cut, or a
    URL cleaned of a trailing slash. A redirect has its own ``INFO:``."""
    named = ""
    if target.ref or target.commit:
        named += f", {'tag' if target.tag else 'branch' if target.ref else 'commit'} "
        named += loggable(target.ref or target.commit or "")
    if target.subdir:
        named += f", folder {loggable(target.subdir)}"
    if page.cut:
        named += " (query and fragment ignored)"
    if page.version_ignored:
        named += " (version names no branch, tag or commit: default branch read)"
    given = sanitize_url(url.strip())
    if named or given.rstrip("/") != sanitize_url(page.repo_url):
        log.info(
            RESOLVED_INFO,
            loggable(given),
            loggable(sanitize_url(clone_url)),
            named,
        )


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
        log.info("Git source: the server rejected the blob filter; fetching without it")
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


def _forget_credentials(runner: GitRunner, clone_url: str, work_dir: str) -> None:
    """Rewrite the URL git wrote to the clone's ``.git/config`` (``clone``
    and ``remote add`` keep it as given) without its user information
    (:func:`~pitloom.core.url_masking.url_without_credentials`): no read of
    the clone, a link into ``.git`` included, can find the credential.
    Nothing else of the clone holds the URL whole (git writes it to
    ``FETCH_HEAD`` and the reflog without the user information)."""
    stored = url_without_credentials(clone_url)
    if stored != clone_url:
        runner.run(
            ["-C", work_dir, "config", "remote.origin.url", stored],
            "config",
            echo=False,
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
        raise RemoteSourceError(
            "git.clone-failed", f"{shown} is an empty repository (no commits)."
        ) from exc


def _drop_outside_links(work_dir: str) -> None:
    """Remove a symbolic link of the checkout that leads out of it, into its
    ``.git`` directory or to a folder: the repository is untrusted, a link
    to a host file would have Pitloom read, and hash, that file, one into
    ``.git`` a file Pitloom wrote (its ``config`` names the URL), and two
    links to folders (``a -> .``, ``b -> .``) make every walk of the files
    endless. A link to a file of the checkout is kept. One ``INFO:`` says
    how many."""
    root = PurePath(os.path.realpath(work_dir))
    dropped = 0
    for here, folders, files in os.walk(work_dir):
        if here == work_dir and ".git" in folders:
            folders.remove(".git")
        for name in files + folders:
            path = os.path.join(here, name)
            if not os.path.islink(path):
                continue
            target = PurePath(os.path.realpath(path))
            if (
                not is_inside(target, root)
                or in_git_dir(target, root)
                or os.path.isdir(target)
            ):
                os.unlink(path)
                dropped += 1
    if dropped:
        log.info(
            "Git source: %d symbolic link(s) leading out of the repository, "
            "into its .git directory or to a folder were not followed",
            dropped,
        )


def _folder(work_dir: str, target: GitTarget) -> tuple[str, str]:
    """The folder of the checkout to read and the file of it the URL named
    (``""``: none). A file page that names a folder reads that folder, and a
    folder page that names a file (Bitbucket and SourceHut write both alike)
    names that file of the folder holding it; each says so."""
    try:
        folder = checkout_folder(work_dir, target.subdir)
    except RemoteSourceError:
        parent, _slash, leaf = target.subdir.rpartition("/")
        if target.file or not checkout_has_file(work_dir, target.subdir):
            raise
        log.info("Git source: %s is a file, not a folder", loggable(target.subdir))
        return checkout_folder(work_dir, parent), leaf
    if target.file and Path(folder, target.file).is_dir():
        log.info(
            "Git source: %s is a folder, not a file; reading it",
            loggable(f"{target.subdir}/{target.file}".lstrip("/")),
        )
        named = f"{target.subdir}/{target.file}".lstrip("/")
        return checkout_folder(work_dir, named), ""
    return folder, target.file
