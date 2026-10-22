# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The folder of a checkout Pitloom runs on, and the hint when it has no
Python project but folders below it do (a monorepo)."""

from __future__ import annotations

import os
from pathlib import Path

from pitloom.core.quote_source import quote_source
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import loggable

__all__ = ["PROJECT_MARKERS", "checkout_folder", "subproject_hint"]

#: Files that make a directory a Python project.
PROJECT_MARKERS = ("pyproject.toml", "setup.cfg", "setup.py")

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
        RemoteSourceError: ``git.path-not-found``, *subdir* is no folder of
            the checkout, or a link leads out of it.
    """
    if not subdir:
        return work_dir
    root = os.path.realpath(work_dir)
    folder = os.path.realpath(os.path.join(root, subdir))
    if not folder.startswith(root + os.sep) or not os.path.isdir(folder):
        raise RemoteSourceError(
            "git.path-not-found",
            f"No folder {quote_source(subdir)} in the repository at that branch.",
        )
    return folder


def subproject_hint(folder: str, whole_repository: bool) -> str:
    """When *folder* has no Python project but folders below it do, say where
    (the text to add to the failure, starting with ``". "``); ``""`` when it
    is a project or none is found. For the whole repository the user can give
    the URL of one of them."""
    root = Path(folder)
    if any((root / marker).is_file() for marker in PROJECT_MARKERS):
        return ""
    found: list[str] = []
    for current, dirs, files in os.walk(root):
        depth = len(Path(current).relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if d not in _SKIPPED_DIRS)
        if depth >= _SEARCH_DEPTH:
            dirs[:] = []
        if depth and any(marker in files for marker in PROJECT_MARKERS):
            found.append(Path(current).relative_to(root).as_posix())
    if not found:
        return ""
    found.sort()
    shown = ", ".join(loggable(name) for name in found[:_HINT_LIMIT])
    more = f" and {len(found) - _HINT_LIMIT} more" if len(found) > _HINT_LIMIT else ""
    advice = (
        "Give the URL of one of them (the link to its folder in the "
        "repository's web page)."
        if whole_repository
        else "Pitloom reads the folder in the URL only."
    )
    return (
        f". There is no Python project here; Python projects are in "
        f"subfolders ({shown}{more}). {advice}"
    )
