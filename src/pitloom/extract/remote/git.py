# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fetch a Git repository, or a folder of one, by URL into a temporary
directory that Pitloom reads like a local project.

The URL is a clone URL or the address of a repository page naming a branch,
tag or commit and a folder (:func:`~pitloom.extract.remote.git_url.
parse_git_page`). The server's redirect (GitLab's ``project`` to
``project.git``) is followed first, each hop passed to the caller's URL check
(:func:`~pitloom.extract.remote._git_redirect.resolve_git_url`). The clone is
shallow, asks the server to omit blobs over 10 MB (a server without partial
clone sends them), follows no redirect itself and runs with git-lfs off.
One ``INFO:`` names the URL given and the URL cloned when they differ.

Needs the ``git`` program. Every failure is a :class:`~pitloom.extract.remote.
errors.RemoteSourceError` with a code; a refusal is also a ``WARNING:``.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

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
from pitloom.logging_config import loggable, sanitize_url_credentials

log = logging.getLogger(__name__)

__all__ = [
    "BLOB_LIMIT",
    "CONFIG_IGNORED_INFO",
    "RESOLVED_INFO",
    "GitCheckout",
    "fetch_git_project",
]

#: Blobs above this size are not fetched: Pitloom reads packaging metadata.
#: A server without partial clone ignores the filter, never fails on it.
BLOB_LIMIT = "10m"

#: ``log.info()`` for a repository's own settings, which are not used.
CONFIG_IGNORED_INFO = (
    "Git source: the repository's own [tool.pitloom] settings are ignored "
    "(untrusted); --config or pitloom_config= applies"
)

#: ``log.info()`` format for a URL that names more than the clone URL.
#: Arguments: the URL given, the repository cloned, what else it names.
RESOLVED_INFO = "Git source: %s names repository %s%s"


@dataclass(frozen=True)
class GitCheckout:
    """A fetched repository.

    ``folder`` is the directory Pitloom reads: the checkout, or the folder
    the URL named; ``whole_repository`` says which. ``commit`` is the commit
    checked out.
    """

    folder: str
    repo_url: str
    ref: str | None
    commit: str
    subdir: str
    whole_repository: bool

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
            hint = subproject_hint(self.folder, self.whole_repository)
            if not hint:
                raise
            raise RemoteSourceError("git.no-project", f"{exc}{hint}") from exc


@contextmanager
def fetch_git_project(
    url: str,
    *,
    check_url: Callable[[str], None] | None = None,
    offline: bool | None = None,
    max_bytes: int | None = None,
) -> Iterator[GitCheckout]:
    """Fetch the repository *url* names into a temporary directory, removed
    on exit.

    *check_url* is called with the URL of every redirect target, without
    user information, before it is requested and raises for one that must not
    be fetched; Pitloom does not check the URL it is given (the caller does,
    as it knows its own policy).
    With *offline* true nothing is fetched. With *max_bytes* the fetch is
    stopped once the checkout (the ``.git`` directory included) takes more
    disk than that (``git.too-large``); ``None`` sets no limit.

    Raises:
        ValueError: *max_bytes* is not a positive integer.
        RemoteSourceError: the URL names no fetchable repository, ref or
            folder, ``git`` is missing, *offline* is set (``git.offline``),
            or the repository is larger than *max_bytes*.
        Exception: whatever *check_url* raises, unchanged.
    """
    if max_bytes is not None and max_bytes <= 0:
        raise ValueError(f"max_bytes must be a positive integer, got {max_bytes}")
    runner = GitRunner(max_bytes=max_bytes)
    with tempfile.TemporaryDirectory(prefix="pitloom-git-") as work_dir:
        try:
            checkout = _prepare(url, work_dir, runner, check_url, offline)
        except Exception as exc:
            # A refusal is said here, so a caller that only logs shows it.
            log.warning("Git source: %s", loggable(sanitize_url_credentials(str(exc))))
            raise
        yield checkout


def _prepare(
    url: str,
    work_dir: str,
    runner: GitRunner,
    check_url: Callable[[str], None] | None,
    offline: bool | None,
) -> GitCheckout:
    """Fetch what *url* names into *work_dir* and describe it."""
    shown = loggable(sanitize_url_credentials(url))
    if offline:
        raise RemoteSourceError(
            "git.offline", f"Cannot fetch {shown}: network access is forbidden."
        )
    page = _read_url(url, shown)
    clone_url, page, target = _resolve(runner, page, check_url)
    _log_resolution(url, clone_url, target, page)
    _checkout(runner, clone_url, work_dir, target)
    _drop_outside_links(work_dir)
    folder = _folder(work_dir, target)
    commit = _head(runner, work_dir, shown)
    subdir = os.path.relpath(os.path.realpath(folder), os.path.realpath(work_dir))
    return GitCheckout(
        folder=folder,
        repo_url=clone_url,
        ref=target.ref,
        commit=commit,
        subdir="" if subdir == "." else subdir.replace(os.sep, "/"),
        whole_repository=subdir == ".",
    )


def _read_url(url: str, shown: str) -> GitPage:
    """The page *url* names.

    Raises:
        RemoteSourceError: ``git.url-invalid``, a scheme other than http(s) or
            a path that leaves the checkout.
    """
    if not scheme_allowed(url.strip()):
        raise RemoteSourceError(
            "git.url-invalid",
            f"Cannot fetch {shown}: only http and https URLs are fetched "
            "(not ssh, git, file or scp-style addresses).",
        )
    return parse_git_page(url)


def _resolve(
    runner: GitRunner, page: GitPage, check_url: Callable[[str], None] | None
) -> tuple[str, GitPage, GitTarget]:
    """The URL to clone, the page it was read from and what to check out.

    A page URL whose repository part is not a repository (a group called
    ``src`` or ``tree``) is tried again with the whole URL as the repository.
    """
    clone_url = resolve_git_url(page.repo_url, check_url)
    if not page.rest:
        return clone_url, page, GitTarget()
    try:
        return clone_url, page, _target(runner, clone_url, page)
    except RemoteSourceError as exc:
        if page.plain_url == page.repo_url or not _not_a_repository(exc):
            raise
        log.info(
            "Git source: %s is not a repository; trying %s",
            loggable(sanitize_url_credentials(page.repo_url)),
            loggable(sanitize_url_credentials(page.plain_url)),
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
    given = sanitize_url_credentials(url.strip())
    if named or given.rstrip("/") != sanitize_url_credentials(page.repo_url):
        log.info(
            RESOLVED_INFO,
            loggable(given),
            loggable(sanitize_url_credentials(clone_url)),
            named,
        )


def _checkout(
    runner: GitRunner, clone_url: str, work_dir: str, target: GitTarget
) -> None:
    """Check out *target* of *clone_url* into *work_dir*, shallowly."""
    blobs = f"--filter=blob:limit={BLOB_LIMIT}"
    if target.commit or target.tag:
        # A refspec begins with ``refs/``: it cannot be read as an option.
        wanted = f"refs/tags/{target.ref}" if target.tag else str(target.commit)
        runner.run(["init", "--quiet", "--", work_dir], "init")
        runner.run(
            ["-C", work_dir, "remote", "add", "origin", "--", clone_url], "remote"
        )
        runner.run(
            ["-C", work_dir, "fetch", "--depth", "1", blobs, "origin", wanted],
            "fetch",
            watch=work_dir,
        )
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
        return
    branch = ["--branch", target.ref] if target.ref else []
    runner.run(
        ["clone", "--depth", "1", blobs, *branch, "--", clone_url, work_dir],
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
        raise RemoteSourceError(
            "git.clone-failed", f"{shown} is an empty repository (no commits)."
        ) from exc


def _drop_outside_links(work_dir: str) -> None:
    """Remove a symbolic link of the checkout that leads out of it: the
    repository is untrusted, and a link to a host file would have Pitloom
    read, and hash, that file. One ``INFO:`` says how many."""
    root = os.path.realpath(work_dir)
    dropped = 0
    for here, folders, files in os.walk(work_dir):
        if here == work_dir and ".git" in folders:
            folders.remove(".git")
        for name in files + folders:
            path = os.path.join(here, name)
            if not os.path.islink(path):
                continue
            target = os.path.realpath(path)
            if target != root and not target.startswith(root + os.sep):
                os.unlink(path)
                dropped += 1
    if dropped:
        log.info(
            "Git source: %d symbolic link(s) leading out of the repository "
            "were not followed",
            dropped,
        )


def _folder(work_dir: str, target: GitTarget) -> str:
    """The folder of the checkout to read. A file page that names a folder
    reads that folder, and a folder page that names a file (Bitbucket and
    SourceHut write both alike) reads the folder holding it; each says so."""
    try:
        folder = checkout_folder(work_dir, target.subdir)
    except RemoteSourceError:
        parent = target.subdir.rpartition("/")[0]
        if target.file or not checkout_has_file(work_dir, target.subdir):
            raise
        log.info(
            "Git source: %s is a file, not a folder; reading the folder holding it",
            loggable(target.subdir),
        )
        return checkout_folder(work_dir, parent)
    if target.file and Path(folder, target.file).is_dir():
        log.info(
            "Git source: %s is a folder, not a file; reading it",
            loggable(f"{target.subdir}/{target.file}".lstrip("/")),
        )
        return checkout_folder(work_dir, f"{target.subdir}/{target.file}".lstrip("/"))
    return folder
