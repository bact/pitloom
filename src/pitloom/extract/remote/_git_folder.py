# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The folder of a checkout Pitloom runs on, and the sub-projects it names
when it has no Python project but folders below it do (a monorepo)."""

from __future__ import annotations

import os
from pathlib import Path, PurePath

from pitloom.core.path_confine import (
    in_git_dir,
    regular_file_inside,
    spelled_as_on_disk,
)
from pitloom.core.project_markers import PROJECT_MARKERS
from pitloom.core.url_masking import masked_given_path
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import loggable
from pitloom.messages.targets import (
    GIT_FOLDER_NOT_FOUND_LINE,
    INPUT_NOT_FOUND,
)

__all__ = [
    "PROJECT_MARKERS",
    "checkout_folder",
    "checkout_has_file",
    "folders_text",
    "subproject_hint",
]

#: Directories never searched for sub-projects, and how deep to look.
_SKIPPED_DIRS = frozenset(
    {
        ".git",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    }
)
_SEARCH_DEPTH = 4
_HINT_LIMIT = 5


def checkout_folder(work_dir: str, subdir: str) -> str:
    """The folder *subdir* of the checkout *work_dir* (the checkout itself
    for ``""``).

    Raises:
        RemoteSourceError: ``git.path-not-found`` (its ``pitloom_code``
            ``input-not-found``), *subdir* is no folder of the checkout (a
            case-insensitive file system finding it in another case
            included), a link leads out of it, or it is the checkout's
            ``.git`` directory or below it.
    """
    if not subdir:
        return work_dir
    root = os.path.realpath(work_dir)
    folder = os.path.realpath(os.path.join(root, subdir))
    if (
        not folder.startswith(root + os.sep)
        or in_git_dir(PurePath(folder), PurePath(root))
        or not os.path.isdir(folder)
        or not spelled_as_on_disk(root, subdir)
    ):
        raise RemoteSourceError(
            "git.path-not-found",
            GIT_FOLDER_NOT_FOUND_LINE.render({"path": subdir}),
            pitloom_code=INPUT_NOT_FOUND.code,
        )
    return folder


def checkout_has_file(work_dir: str, path: str) -> bool:
    """Whether *path* is a regular file of the checkout *work_dir*, not
    reached through a link that leads out of it, not in its ``.git``
    directory, and spelled as on disk
    (:func:`~pitloom.core.path_confine.regular_file_inside`)."""
    root = os.path.realpath(work_dir)
    return regular_file_inside(work_dir, path) and not in_git_dir(
        PurePath(os.path.realpath(os.path.join(root, path))), PurePath(root)
    )


def subproject_hint(folder: str) -> tuple[list[str], int]:
    """The sub-projects of *folder*, when it has no Python project but folders
    below it do (a monorepo): their folder names, the first :data:`_HINT_LIMIT`
    in sorted order, and how many more there are. ``([], 0)`` when *folder* is
    a project or none is found."""
    root = Path(folder)
    if any((root / marker).is_file() for marker in PROJECT_MARKERS):
        return [], 0
    found: list[str] = []
    for current, dirs, files in os.walk(root):
        depth = len(Path(current).relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if d not in _SKIPPED_DIRS)
        if depth >= _SEARCH_DEPTH:
            dirs[:] = []
        if depth and any(marker in files for marker in PROJECT_MARKERS):
            found.append(Path(current).relative_to(root).as_posix())
    found.sort()
    return found[:_HINT_LIMIT], max(len(found) - _HINT_LIMIT, 0)


def folders_text(names: list[str], more: int) -> str:
    """The ``folders`` value of a hint line: *names* comma-separated, each
    escaped when it holds a control character, then ``and N more`` when
    *more* folders are left out."""
    # Masked before the escape, as a tab would hide a bare token's boundary.
    shown = ", ".join(loggable(masked_given_path(name, line=True)) for name in names)
    return f"{shown} and {more} more" if more else shown
