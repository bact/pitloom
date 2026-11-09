# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In a Git URL's temporary clone, the files a build backend lists outside
the downloaded repository (a ``force-include`` of an absolute or ``..``
path, a link out) are left out unread: the repository is untrusted, and
such a file is the host's. A local project keeps every file its backend
lists.

See also: :mod:`pitloom.core._models_wheel` (the one loop every discovered
file passes through) and :func:`pitloom.core.lfs_pointer.reading_remote_clone`
(the clone and its root).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path, PurePath

from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.lfs_pointer import in_remote_clone, remote_clone_root
from pitloom.core.path_confine import is_inside
from pitloom.messages import FILE_UNREADABLE_OUTSIDE_REPOSITORY, emit

log = logging.getLogger(__name__)


def _inside(path: str, root: PurePath) -> bool:
    """Whether *path*, links followed, lies in *root* (already resolved)."""
    try:
        return is_inside(PurePath(os.path.realpath(path)), root)
    except (OSError, ValueError):  # a NUL, or a link loop on Windows
        return False


def drop_outside_clone(
    included_files: list[IncludedFile], project_dir: Path
) -> list[IncludedFile]:
    """*included_files* without those outside the clone being read (its
    root, else *project_dir*), said in one ``WARNING:``
    (``file-unreadable/outside-repository``) naming the first by its wheel
    path, and how many; every file outside a clone, and a file a build
    extracted (none in a clone: no build is run), is kept. Nothing is
    opened."""
    if not in_remote_clone():
        return included_files
    root = PurePath(os.path.realpath(remote_clone_root() or project_dir))
    kept: list[IncludedFile] = []
    dropped: list[str] = []
    for included_file in included_files:
        if included_file.built or _inside(included_file.path, root):
            kept.append(included_file)
        else:
            dropped.append(included_file.distribution_path)
    if dropped:
        emit(
            log,
            FILE_UNREADABLE_OUTSIDE_REPOSITORY,
            logging.WARNING,
            file=min(dropped),
            count=len(dropped),
        )
    return kept
