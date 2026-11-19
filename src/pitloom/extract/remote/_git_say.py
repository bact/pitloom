# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a Git URL fetch says and does about the checkout once it has it: how
the URL was read (the ``INFO:`` lines of ``target-ambiguous/git-page`` and
``query-no-effect``), the symbolic links removed from the checkout
(``git-link-unsafe``), the folder or file of the checkout to read, and the
``project-not-found`` and ``project-or-model-not-found`` errors that name the
sub-projects of a monorepo (kept as ``git.no-project``).

See also: :mod:`pitloom.extract.remote.git` (the fetch that calls them) and
:mod:`pitloom.extract.remote._git_folder` (the folder and sub-project reads).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path, PurePath
from typing import Any

from pitloom.core.path_confine import in_git_dir, is_inside
from pitloom.core.url_masking import sanitize_url
from pitloom.extract.remote._git_folder import (
    checkout_folder,
    checkout_has_file,
    folders_text,
)
from pitloom.extract.remote._http_errors import remote_error, shown_url
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git_url import GitPage, GitTarget
from pitloom.messages import GIT_FRAME, emit
from pitloom.messages.git import GIT_LINK_UNSAFE
from pitloom.messages.network import (
    QUERY_LINE,
    QUERY_NO_EFFECT,
    VERSION_IGNORED_LINE,
)
from pitloom.messages.targets import (
    GIT_PAGE_DIR_LINE,
    GIT_PAGE_FILE_LINE,
    GIT_PAGE_FOLDER_LINE,
    GIT_PAGE_LINE,
    GIT_PAGE_NOT_REPO_LINE,
    GIT_PAGE_REF_FOLDER_LINE,
    GIT_PAGE_REF_LINE,
    NO_SBOM_TARGET,
    NO_TARGET_FOLDER_HINT_LINE,
    NO_TARGET_HINT_LINE,
    PROJECT_FOLDER_HINT_LINE,
    PROJECT_HINT_LINE,
    PROJECT_NOT_FOUND,
    TARGET_AMBIGUOUS_GIT_PAGE,
)

log = logging.getLogger(__name__)

__all__ = [
    "drop_outside_links",
    "folder_to_read",
    "no_target_hint_error",
    "project_hint_error",
    "say_resolution",
    "say_not_a_repository",
]


def say_not_a_repository(page: GitPage) -> None:
    """One ``INFO:``: the repository part of *page* is no repository, and the
    whole URL is tried as one."""
    emit(
        log,
        TARGET_AMBIGUOUS_GIT_PAGE,
        logging.INFO,
        line=GIT_PAGE_NOT_REPO_LINE,
        frame=GIT_FRAME,
        url=shown_url(page.repo_url),
        target=shown_url(page.plain_url),
    )


def say_resolution(url: str, clone_url: str, target: GitTarget, page: GitPage) -> None:
    """One ``INFO:`` when the URL given names more than the repository: a
    branch, tag, commit or folder, or a URL cleaned of a trailing slash; and
    one for a query or fragment that was cut, one for a version that names
    nothing. A redirect has its own ``INFO:``."""
    given = sanitize_url(url.strip())
    # Each value is a field's, written by it: emit takes them as keywords.
    values: dict[str, Any] = {
        "url": shown_url(url.strip()),
        "target": shown_url(clone_url),
    }
    ref = target.ref or target.commit
    if ref:
        values["ref_kind"] = (
            "tag" if target.tag else "branch" if target.ref else "commit"
        )
        values["ref"] = ref
    if target.subdir:
        values["path"] = target.subdir
    if ref and target.subdir:
        line = GIT_PAGE_REF_FOLDER_LINE
    elif ref:
        line = GIT_PAGE_REF_LINE
    elif target.subdir:
        line = GIT_PAGE_FOLDER_LINE
    elif not page.cut and given != sanitize_url(page.repo_url):
        line = GIT_PAGE_LINE
    else:
        line = None
    if line is not None:
        emit(
            log,
            TARGET_AMBIGUOUS_GIT_PAGE,
            logging.INFO,
            line=line,
            frame=GIT_FRAME,
            **values,
        )
    if page.cut:
        emit(
            log,
            QUERY_NO_EFFECT,
            logging.INFO,
            line=QUERY_LINE,
            frame=GIT_FRAME,
            url=values["url"],
        )
    if page.version_ignored:
        emit(
            log,
            QUERY_NO_EFFECT,
            logging.INFO,
            line=VERSION_IGNORED_LINE,
            frame=GIT_FRAME,
            url=values["url"],
        )


def drop_outside_links(work_dir: str, clone_url: str) -> None:
    """Remove a symbolic link of the checkout that leads out of it, into its
    ``.git`` directory or to a folder: the repository is untrusted, a link
    to a host file would have Pitloom read, and hash, that file, one into
    ``.git`` a file Pitloom wrote (its ``config`` names the URL), and two
    links to folders (``a -> .``, ``b -> .``) make every walk of the files
    endless. A link to a file of the checkout is kept. One ``INFO:`` says
    how many, of the repository *clone_url*."""
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
        emit(
            log,
            GIT_LINK_UNSAFE,
            logging.INFO,
            frame=GIT_FRAME,
            url=shown_url(clone_url),
            number=dropped,
        )


def folder_to_read(work_dir: str, target: GitTarget, url: str) -> tuple[str, str]:
    """The folder of the checkout to read and the file of it the URL named
    (``""``: none). A file page that names a folder reads that folder, and a
    folder page that names a file (Bitbucket and SourceHut write both alike)
    names that file of the folder holding it; each says so in one ``INFO:``
    naming the URL given, *url*."""
    try:
        folder = checkout_folder(work_dir, target.subdir)
    except RemoteSourceError:
        parent, _slash, leaf = target.subdir.rpartition("/")
        if target.file or not checkout_has_file(work_dir, target.subdir):
            raise
        emit(
            log,
            TARGET_AMBIGUOUS_GIT_PAGE,
            logging.INFO,
            line=GIT_PAGE_FILE_LINE,
            frame=GIT_FRAME,
            url=shown_url(url.strip()),
            path=target.subdir,
        )
        return checkout_folder(work_dir, parent), leaf
    if target.file and Path(folder, target.file).is_dir():
        named = f"{target.subdir}/{target.file}".lstrip("/")
        emit(
            log,
            TARGET_AMBIGUOUS_GIT_PAGE,
            logging.INFO,
            line=GIT_PAGE_DIR_LINE,
            frame=GIT_FRAME,
            url=shown_url(url.strip()),
            path=named,
        )
        return checkout_folder(work_dir, named), ""
    return folder, target.file


def project_hint_error(
    folder: str, names: list[str], more: int, whole_repository: bool
) -> RemoteSourceError:
    """``git.no-project`` for *folder*, read as a project: ``project-not-found``
    with the sub-projects *names* (and *more* left out) below it, advising the
    URL of one of them for the whole repository, else that only the folder in
    the URL is read."""
    return remote_error(
        "git.no-project",
        PROJECT_NOT_FOUND,
        PROJECT_HINT_LINE if whole_repository else PROJECT_FOLDER_HINT_LINE,
        path=folder,
        folders=folders_text(names, more),
    )


def no_target_hint_error(
    subject: str, names: list[str], more: int, whole_repository: bool
) -> RemoteSourceError:
    """``git.no-project`` for the folder *subject* names, which is neither a
    project nor a model: ``project-or-model-not-found`` with the sub-projects
    *names* (and *more* left out) below it, advised as
    :func:`project_hint_error` does."""
    return remote_error(
        "git.no-project",
        NO_SBOM_TARGET,
        NO_TARGET_HINT_LINE if whole_repository else NO_TARGET_FOLDER_HINT_LINE,
        path=subject,
        folders=folders_text(names, more),
    )
