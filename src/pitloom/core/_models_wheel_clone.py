# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In a Git URL's temporary clone, the repository is untrusted: the files a
build backend lists outside it (a ``force-include`` of an absolute or ``..``
path, a link out) or in its ``.git`` directory are left out unread, and a
setting that would have the file discovery run the repository's own code
is ignored. A local project keeps every file its backend lists, and runs
what its backend runs.

See also: :mod:`pitloom.core._models_wheel` (the one loop every discovered
file passes through), :func:`pitloom.core.lfs_pointer.reading_remote_clone`
(the clone and its root), and the backends that leave settings out before
discovery: :mod:`pitloom.core._models_wheel_hatchling`,
:mod:`pitloom.core._models_wheel_setuptools_clone`,
:mod:`pitloom.core._models_wheel_pdm`.
"""

from __future__ import annotations

import logging
import ntpath
import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path, PurePath

from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.clone_mark import in_remote_clone, remote_clone_root
from pitloom.core.path_confine import inside_clone_but_not_git
from pitloom.messages import (
    emit,
)
from pitloom.messages.files import (
    FILE_UNREADABLE_OUTSIDE_REPOSITORY,
)
from pitloom.messages.targets import (
    CONFIG_UNSAFE_BUILD_CODE,
)

log = logging.getLogger(__name__)


def clone_root(project_dir: Path) -> PurePath:
    """The resolved root of the clone being read: its root directory, else
    *project_dir*."""
    return PurePath(os.path.realpath(remote_clone_root() or project_dir))


def left_out(path: str, root: PurePath) -> bool:
    """Whether *path*, links followed, is not a file of the repository at
    *root* (already resolved): outside it, or in the clone's ``.git``
    directory, which can hold the URL's user information
    (:func:`~pitloom.core.path_confine.inside_clone_but_not_git`). Never
    raises (a NUL, or a link loop on Windows, leaves it out)."""
    try:
        real = PurePath(os.path.realpath(path))
    except (OSError, ValueError):
        return True
    return not inside_clone_but_not_git(real, root)


def warn_entries_left_out(project_dir: Path, entries: Iterable[str]) -> None:
    """One ``WARNING:`` (``file-unreadable/outside-repository``) per
    setting entry of *project_dir* left out before discovery, named as the
    configuration writes it (never a host file's name), each once."""
    for entry in sorted(set(entries)):
        emit(
            log,
            FILE_UNREADABLE_OUTSIDE_REPOSITORY,
            logging.WARNING,
            file=entry,
            once=f"outside-entry:{project_dir}\x00{entry}",
        )


def warn_build_code_ignored(
    project_dir: Path, file: str, settings: Sequence[str]
) -> None:
    """One ``WARNING:`` (``config-unsafe/build-code``) naming the settings
    of *file* (relative to *project_dir*) that were ignored, once per
    project, file and settings; nothing for none."""
    if settings:
        shown = sorted(settings)
        emit(
            log,
            CONFIG_UNSAFE_BUILD_CODE,
            logging.WARNING,
            file=file,
            settings=shown,
            once=f"build-code:{project_dir}\x00{file}\x00{','.join(shown)}",
        )


class LeftOut:
    """What a clone's build configuration leaves out before a discovery
    reads it: the settings that name code, and the entries out of the clone
    or in its ``.git``, each named as written by :meth:`warn`."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.root = clone_root(project_dir)
        self.code: list[str] = []
        self.entries: list[str] = []

    def outside(self, path: str) -> bool:
        """Whether the directory or file *path* (relative to the project) is
        out of the clone or in its ``.git`` (:func:`left_out`), added to the
        entries left out when it is."""
        if left_out(os.path.join(self.project_dir, path), self.root):
            self.entries.append(path)
            return True
        return False

    def pattern_outside(self, pattern: str) -> bool:
        """Whether the file pattern or path *pattern* can reach out of the
        clone (absolute: rooted or with a drive; from the home directory;
        or with a ``..`` part) or into its ``.git``, added to the entries
        left out when it can."""
        written = pattern.replace("\\", "/")
        parts = written.split("/")
        if (
            written.startswith(("/", "~"))
            or ntpath.splitdrive(written)[0]
            or ".." in parts
            or any(part.casefold() == ".git" for part in parts)
        ):
            self.entries.append(pattern)
            return True
        return False

    def kept(self, listed: list[str], test: Callable[[str], bool]) -> list[str]:
        """The entries of *listed* that *test* (:meth:`outside`,
        :meth:`pattern_outside`) keeps."""
        return [entry for entry in listed if not test(entry)]

    def warn(self, file: str) -> None:
        """Say what *file* had left out."""
        warn_build_code_ignored(self.project_dir, file, self.code)
        warn_entries_left_out(self.project_dir, self.entries)


def drop_outside_clone(
    included_files: list[IncludedFile], project_dir: Path
) -> list[IncludedFile]:
    """*included_files* without those :func:`left_out` of the clone being
    read (its root, else *project_dir*), said in one ``WARNING:``
    (``file-unreadable/outside-repository``) giving how many, never a
    name; every file outside a clone, and a file a build extracted (a
    library caller's own ``--allow-build`` within the clone), is kept.
    Nothing is opened."""
    if not in_remote_clone():
        return included_files
    root = clone_root(project_dir)
    kept = [f for f in included_files if f.built or not left_out(f.path, root)]
    if len(kept) < len(included_files):
        emit(
            log,
            FILE_UNREADABLE_OUTSIDE_REPOSITORY,
            logging.WARNING,
            count=len(included_files) - len(kept),
        )
    return kept
